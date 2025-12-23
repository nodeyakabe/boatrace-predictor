# -*- coding: utf-8 -*-
"""
バックテスト信頼性検証スクリプト

Phase A-Cの判定結果の統計的有意性を検証し、
payoutsテーブルとの整合性を確認する。

検証項目:
1. バックテスト実装の精度検証
2. 統計的有意性検定の追加
3. 実測データとの整合性確認
4. 標本サイズの確認
"""

import sys
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple
from scipy import stats
from collections import defaultdict

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


class BacktestReliabilityVerifier:
    """バックテスト信頼性検証クラス"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def verify_payout_integrity(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """payoutsテーブルとの整合性確認"""
        print("\n" + "=" * 70)
        print("1. payoutsテーブルとの整合性確認")
        print("=" * 70)

        cursor = self.conn.cursor()

        # 3連単払戻データの完全性確認
        cursor.execute('''
            SELECT
                COUNT(DISTINCT r.id) as total_races,
                COUNT(DISTINCT CASE
                    WHEN p.bet_type = 'trifecta' THEN r.id
                END) as races_with_trifecta_payout
            FROM races r
            JOIN results res ON r.id = res.race_id
            LEFT JOIN payouts p ON r.id = p.race_id AND p.bet_type = 'trifecta'
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND res.is_invalid = 0
              AND res.rank <= 3
        ''', (start_date, end_date))

        integrity = cursor.fetchone()
        total = integrity['total_races']
        with_payout = integrity['races_with_trifecta_payout']
        coverage = (with_payout / total * 100) if total > 0 else 0

        print(f"総レース数: {total:,}件")
        print(f"3連単払戻データあり: {with_payout:,}件")
        print(f"カバー率: {coverage:.1f}%")

        if coverage < 95:
            print(f"[警告] カバー率が95%未満です ({coverage:.1f}%)")
        else:
            print(f"[OK] カバー率は十分です ({coverage:.1f}%)")

        # 異常値チェック
        cursor.execute('''
            SELECT
                MIN(amount) as min_payout,
                MAX(amount) as max_payout,
                AVG(amount) as avg_payout,
                COUNT(*) as count
            FROM payouts
            WHERE bet_type = 'trifecta'
              AND race_id IN (
                  SELECT id FROM races
                  WHERE race_date >= ? AND race_date <= ?
              )
        ''', (start_date, end_date))

        stats_row = cursor.fetchone()
        print(f"\n払戻金額統計:")
        print(f"  最小値: {stats_row['min_payout']:,}円")
        print(f"  最大値: {stats_row['max_payout']:,}円")
        print(f"  平均値: {stats_row['avg_payout']:,.0f}円")
        print(f"  件数: {stats_row['count']:,}件")

        if stats_row['min_payout'] < 100:
            print(f"[警告] 100円未満の払戻があります")
        if stats_row['max_payout'] > 1000000:
            print(f"[警告] 100万円超の払戻があります（万舟券）")

        return {
            'total_races': total,
            'with_payout': with_payout,
            'coverage': coverage,
            'min_payout': stats_row['min_payout'],
            'max_payout': stats_row['max_payout'],
            'avg_payout': stats_row['avg_payout'],
        }

    def verify_sample_size(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """標本サイズの確認"""
        print("\n" + "=" * 70)
        print("2. 標本サイズの確認")
        print("=" * 70)

        cursor = self.conn.cursor()

        # 信頼度別のレース数を確認
        cursor.execute('''
            SELECT
                p.confidence,
                COUNT(DISTINCT r.id) as race_count
            FROM races r
            JOIN race_predictions p ON r.id = p.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND p.prediction_type = 'advance'
            GROUP BY p.confidence
            ORDER BY p.confidence
        ''', (start_date, end_date))

        confidence_counts = {}
        total_races = 0

        print("\n信頼度別レース数:")
        for row in cursor.fetchall():
            conf = row['confidence']
            count = row['race_count']
            confidence_counts[conf] = count
            total_races += count

            # 統計的有意性のための最小サンプル数チェック
            min_required = 30  # 中心極限定理の一般的な閾値
            status = "[OK]" if count >= min_required else "[警告]"
            print(f"  {conf}: {count:,}件 {status}")

            if count < min_required:
                print(f"    [警告] サンプル数が{min_required}件未満です（統計的信頼性が低い）")

        print(f"\n総レース数: {total_races:,}件")

        # 月別のレース数分布
        cursor.execute('''
            SELECT
                SUBSTR(r.race_date, 1, 7) as month,
                COUNT(DISTINCT r.id) as race_count
            FROM races r
            WHERE r.race_date >= ? AND r.race_date <= ?
            GROUP BY month
            ORDER BY month
        ''', (start_date, end_date))

        print("\n月別レース数:")
        monthly_counts = []
        for row in cursor.fetchall():
            month = row['month']
            count = row['race_count']
            monthly_counts.append(count)
            print(f"  {month}: {count:,}件")

        if monthly_counts:
            monthly_std = np.std(monthly_counts)
            monthly_mean = np.mean(monthly_counts)
            cv = (monthly_std / monthly_mean * 100) if monthly_mean > 0 else 0
            print(f"\n月別変動係数 (CV): {cv:.1f}%")
            if cv > 30:
                print(f"[警告] 月別のバラつきが大きいです (CV={cv:.1f}%)")

        return {
            'confidence_counts': confidence_counts,
            'total_races': total_races,
            'monthly_counts': monthly_counts,
        }

    def calculate_statistical_significance(
        self,
        baseline_roi: float,
        test_roi: float,
        baseline_samples: int,
        test_samples: int,
        baseline_std: float = 100,  # ROIの標準偏差（仮定値）
        test_std: float = 100
    ) -> Dict[str, Any]:
        """統計的有意性の計算"""
        print("\n" + "=" * 70)
        print("3. 統計的有意性検定")
        print("=" * 70)

        # 2標本t検定（ROI差の検定）
        # ROI差
        roi_diff = test_roi - baseline_roi

        # 標準誤差の計算
        se_baseline = baseline_std / np.sqrt(baseline_samples)
        se_test = test_std / np.sqrt(test_samples)
        se_diff = np.sqrt(se_baseline**2 + se_test**2)

        # t統計量
        t_stat = roi_diff / se_diff if se_diff > 0 else 0

        # 自由度（Welchの近似）
        df = ((se_baseline**2 + se_test**2)**2 /
              (se_baseline**4/(baseline_samples-1) + se_test**4/(test_samples-1)))

        # p値（両側検定）
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df))

        # 信頼区間（95%）
        t_critical = stats.t.ppf(0.975, df)
        ci_lower = roi_diff - t_critical * se_diff
        ci_upper = roi_diff + t_critical * se_diff

        print(f"\nBaseline ROI: {baseline_roi:.1f}%")
        print(f"Test ROI: {test_roi:.1f}%")
        print(f"ROI差: {roi_diff:.1f}%")
        print(f"\n統計検定結果:")
        print(f"  t統計量: {t_stat:.3f}")
        print(f"  自由度: {df:.1f}")
        print(f"  p値: {p_value:.4f}")
        print(f"  95%信頼区間: [{ci_lower:.1f}%, {ci_upper:.1f}%]")

        # 有意性判定
        alpha = 0.05
        is_significant = p_value < alpha

        if is_significant:
            if roi_diff > 0:
                print(f"\n[OK] 統計的に有意な改善が認められます (p < {alpha})")
            else:
                print(f"\n[NG] 統計的に有意な悪化が認められます (p < {alpha})")
        else:
            print(f"\n[警告] 統計的に有意な差は認められません (p >= {alpha})")
            print(f"   -> 偶然の範囲内の可能性があります")

        # 効果量（Cohen's d）
        pooled_std = np.sqrt((baseline_std**2 + test_std**2) / 2)
        cohens_d = roi_diff / pooled_std if pooled_std > 0 else 0

        print(f"\n効果量 (Cohen's d): {cohens_d:.3f}")
        if abs(cohens_d) < 0.2:
            effect_size = "小"
        elif abs(cohens_d) < 0.5:
            effect_size = "中"
        else:
            effect_size = "大"
        print(f"  効果サイズ: {effect_size}")

        return {
            'roi_diff': roi_diff,
            't_stat': t_stat,
            'p_value': p_value,
            'is_significant': is_significant,
            'ci_lower': ci_lower,
            'ci_upper': ci_upper,
            'cohens_d': cohens_d,
            'effect_size': effect_size,
        }

    def verify_prediction_accuracy(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """予測精度の検証"""
        print("\n" + "=" * 70)
        print("4. 予測精度の検証")
        print("=" * 70)

        cursor = self.conn.cursor()

        # 1着的中率の確認
        cursor.execute('''
            SELECT
                p.confidence,
                COUNT(*) as total,
                SUM(CASE
                    WHEN res.pit_number = p.pit_number AND res.rank = 1
                    THEN 1 ELSE 0
                END) as hits
            FROM race_predictions p
            JOIN races r ON p.race_id = r.id
            JOIN results res ON p.race_id = res.race_id AND res.rank = 1
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND p.prediction_type = 'advance'
              AND p.rank_prediction = 1
            GROUP BY p.confidence
            ORDER BY p.confidence
        ''', (start_date, end_date))

        print("\n1着的中率（信頼度別）:")
        accuracy_by_conf = {}

        for row in cursor.fetchall():
            conf = row['confidence']
            total = row['total']
            hits = row['hits']
            accuracy = (hits / total * 100) if total > 0 else 0
            accuracy_by_conf[conf] = accuracy

            print(f"  {conf}: {hits}/{total} ({accuracy:.1f}%)")

        # 3連単的中率の確認
        cursor.execute('''
            SELECT
                p.confidence,
                COUNT(DISTINCT p.race_id) as total,
                SUM(CASE
                    WHEN (
                        SELECT GROUP_CONCAT(pit_number, '-')
                        FROM (
                            SELECT pit_number
                            FROM results
                            WHERE race_id = p.race_id AND is_invalid = 0
                            ORDER BY rank
                            LIMIT 3
                        )
                    ) = (
                        SELECT GROUP_CONCAT(pit_number, '-')
                        FROM (
                            SELECT pit_number
                            FROM race_predictions
                            WHERE race_id = p.race_id
                              AND prediction_type = 'advance'
                            ORDER BY rank_prediction
                            LIMIT 3
                        )
                    )
                    THEN 1 ELSE 0
                END) as trifecta_hits
            FROM race_predictions p
            JOIN races r ON p.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND p.prediction_type = 'advance'
            GROUP BY p.confidence
            ORDER BY p.confidence
        ''', (start_date, end_date))

        print("\n3連単的中率（信頼度別）:")
        trifecta_accuracy_by_conf = {}

        for row in cursor.fetchall():
            conf = row['confidence']
            total = row['total']
            hits = row['trifecta_hits']
            accuracy = (hits / total * 100) if total > 0 else 0
            trifecta_accuracy_by_conf[conf] = accuracy

            print(f"  {conf}: {hits}/{total} ({accuracy:.1f}%)")

        return {
            'accuracy_by_conf': accuracy_by_conf,
            'trifecta_accuracy_by_conf': trifecta_accuracy_by_conf,
        }

    def run_full_verification(self, start_date: str, end_date: str):
        """完全な検証を実行"""
        print("\n" + "=" * 70)
        print("バックテスト信頼性検証")
        print("=" * 70)
        print(f"期間: {start_date} ～ {end_date}")

        # 1. 整合性確認
        integrity = self.verify_payout_integrity(start_date, end_date)

        # 2. 標本サイズ確認
        sample_size = self.verify_sample_size(start_date, end_date)

        # 3. 予測精度確認
        accuracy = self.verify_prediction_accuracy(start_date, end_date)

        # 4. 統計的有意性検定（仮のデータで例示）
        print("\n" + "=" * 70)
        print("統計的有意性検定の例（Phase A-C比較）")
        print("=" * 70)

        # baseline vs edge_test の比較例
        baseline_roi = 24.0
        edge_roi = 21.4
        baseline_samples = sample_size['total_races']
        test_samples = int(baseline_samples * 0.5)  # 仮定: 半分のレースが対象

        print("\n例: baseline vs edge_test")
        significance = self.calculate_statistical_significance(
            baseline_roi=baseline_roi,
            test_roi=edge_roi,
            baseline_samples=baseline_samples,
            test_samples=test_samples
        )

        # baseline vs venue_test の比較例
        venue_roi = 19.9
        print("\n例: baseline vs venue_test")
        significance_venue = self.calculate_statistical_significance(
            baseline_roi=baseline_roi,
            test_roi=venue_roi,
            baseline_samples=baseline_samples,
            test_samples=test_samples
        )

        # 総合判定
        print("\n" + "=" * 70)
        print("総合判定")
        print("=" * 70)

        issues = []

        if integrity['coverage'] < 95:
            issues.append(f"[NG] 払戻データのカバー率が低い ({integrity['coverage']:.1f}%)")

        for conf, count in sample_size['confidence_counts'].items():
            if count < 30:
                issues.append(f"[NG] 信頼度{conf}のサンプル数が不足 ({count}件)")

        if not significance['is_significant']:
            issues.append("[警告] edge_testの差は統計的に有意でない")

        if not significance_venue['is_significant']:
            issues.append("[警告] venue_testの差は統計的に有意でない")

        if issues:
            print("\n【検出された問題】")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n[OK] バックテストの信頼性は十分です")

        # 推奨事項
        print("\n【推奨事項】")
        print("1. 統計的有意性が認められない場合:")
        print("   -> サンプルサイズを増やす（期間延長、会場追加）")
        print("   -> より大きな効果のある施策に注力する")
        print()
        print("2. ROI差が小さい場合:")
        print("   -> 信頼区間の幅を確認し、実用上の意味を検討する")
        print("   -> 複数月のデータで再検証する")
        print()
        print("3. 予測精度が低い場合:")
        print("   -> モデル再学習を優先する")
        print("   -> 特徴量の見直しを検討する")

        return {
            'integrity': integrity,
            'sample_size': sample_size,
            'accuracy': accuracy,
            'significance_edge': significance,
            'significance_venue': significance_venue,
            'issues': issues,
        }

    def close(self):
        """接続を閉じる"""
        self.conn.close()


def main():
    """メイン処理"""
    db_path = str(ROOT_DIR / 'data' / 'boatrace.db')

    verifier = BacktestReliabilityVerifier(db_path)

    try:
        # 2025年全期間で検証
        results = verifier.run_full_verification('2025-01-01', '2025-12-15')

        # 11月のみでも検証（Phase A-Cの判定に使われた期間）
        print("\n\n" + "=" * 70)
        print("11月データでの再検証")
        print("=" * 70)
        results_nov = verifier.run_full_verification('2025-11-01', '2025-11-30')

    finally:
        verifier.close()

    print("\n検証完了")


if __name__ == '__main__':
    main()
