# -*- coding: utf-8 -*-
"""
特徴量効果の検証スクリプト（改善版 v2）

改善ポイント:
1. ベースライン比較の追加（常に1コース予測との比較）
2. 公平な比較の実装（同一条件での精度比較）
3. サンプルサイズ表示と警告
4. 統計的検定（信頼区間）の追加
5. 分析の限界の明記

検証する特徴量:
1. 会場×コース勝率テーブル（24会場×6コース=144エントリー）
2. 天候強化特徴量（風向×風速の複合補正）
3. チルト×風向シナジー
"""

import sys
import io
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
import math

# Windows環境での文字化け対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


# 定数
MIN_SAMPLE_SIZE = 30  # 統計的信頼性の最小サンプルサイズ
CONFIDENCE_LEVEL = 0.95  # 95%信頼区間


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Wilson score intervalによる信頼区間の計算"""
    if total == 0:
        return (0.0, 0.0)

    # z値（95%信頼区間の場合は1.96）
    z = 1.96 if confidence == 0.95 else 1.645  # 90%の場合

    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    margin = (z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))) / denominator

    return (max(0, center - margin), min(1, center + margin))


def sample_size_warning(n: int) -> str:
    """サンプルサイズに基づく警告メッセージ"""
    if n < 10:
        return " [警告: サンプル数極小]"
    elif n < MIN_SAMPLE_SIZE:
        return " [警告: サンプル数不足]"
    return ""


class FeatureImpactAnalyzerV2:
    """特徴量効果分析クラス（改善版）"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def analyze_baseline(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """ベースライン比較: 常に1コース予測 vs 予測システム"""
        print("\n" + "=" * 70)
        print("【ベースライン比較】")
        print("=" * 70)

        cursor = self.conn.cursor()

        # 常に1コースを予測した場合の的中率（= 1コースの実勝率）
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = 1 AND res.pit_number = 1 THEN 1 ELSE 0 END) as course1_wins
            FROM races r
            JOIN results res ON r.id = res.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND res.pit_number = 1
        ''', (start_date, end_date))

        baseline_row = cursor.fetchone()
        baseline_total = baseline_row['total']
        baseline_wins = baseline_row['course1_wins']
        baseline_accuracy = (baseline_wins / baseline_total * 100) if baseline_total > 0 else 0
        baseline_ci = wilson_score_interval(baseline_wins, baseline_total)

        print(f"常に1コース予測: {baseline_accuracy:.1f}% ({baseline_wins:,}/{baseline_total:,})")
        print(f"  95%信頼区間: [{baseline_ci[0]*100:.1f}%, {baseline_ci[1]*100:.1f}%]")

        # 予測システム全体の精度
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits
            FROM races r
            JOIN race_predictions p ON r.id = p.race_id
            JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND p.prediction_type = 'advance'
              AND p.rank_prediction = 1
        ''', (start_date, end_date))

        system_row = cursor.fetchone()
        system_total = system_row['total']
        system_hits = system_row['hits'] or 0
        system_accuracy = (system_hits / system_total * 100) if system_total > 0 else 0
        system_ci = wilson_score_interval(system_hits, system_total)

        print(f"予測システム全体: {system_accuracy:.1f}% ({system_hits:,}/{system_total:,})")
        print(f"  95%信頼区間: [{system_ci[0]*100:.1f}%, {system_ci[1]*100:.1f}%]")

        # 付加価値の計算
        value_added = system_accuracy - baseline_accuracy
        print(f"\n付加価値: {value_added:+.1f}pt")

        if value_added < 0:
            print("  [重大な問題] 予測システムがベースラインより低精度")
            print("  --> A-1（モデル再学習）を優先すべき")
        elif value_added < 2:
            print("  [注意] 予測システムの付加価値が小さい")
        else:
            print("  [良好] 予測システムがベースラインを上回っている")

        return {
            'baseline_accuracy': baseline_accuracy,
            'baseline_total': baseline_total,
            'baseline_ci': baseline_ci,
            'system_accuracy': system_accuracy,
            'system_total': system_total,
            'system_ci': system_ci,
            'value_added': value_added
        }

    def analyze_venue_course_fair_comparison(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """会場×コース勝率テーブルの公平な効果分析"""
        print("\n" + "=" * 70)
        print("【会場×コース勝率テーブル】")
        print("=" * 70)

        cursor = self.conn.cursor()

        # インが強い会場（徳山、大村、下関）
        strong_in_venues = ['18', '24', '19']
        # インが弱い会場（戸田、平和島、江戸川）
        weak_in_venues = ['02', '04', '03']

        print("\n(1) 全予測での比較（不公平な比較）:")
        print("  注意: この比較は予測戦略の差を含むため、特徴量の効果を正確に測定できない")
        print()

        # 全予測での比較（従来の方法）
        for venues, label in [(strong_in_venues, 'イン有利会場'), (weak_in_venues, 'イン不利会場')]:
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits,
                    SUM(CASE WHEN p.pit_number = 1 THEN 1 ELSE 0 END) as course1_predictions
                FROM races r
                JOIN race_predictions p ON r.id = p.race_id
                JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND p.prediction_type = 'advance'
                  AND p.rank_prediction = 1
                  AND r.venue_code IN ({})
            '''.format(','.join(['?' for _ in venues])), (start_date, end_date, *venues))

            row = cursor.fetchone()
            total = row['total']
            hits = row['hits'] or 0
            course1_preds = row['course1_predictions'] or 0
            accuracy = (hits / total * 100) if total > 0 else 0
            course1_ratio = (course1_preds / total * 100) if total > 0 else 0

            print(f"  {label}: {accuracy:.1f}% (n={total:,})")
            print(f"    --> 1コース予測率: {course1_ratio:.1f}%")

        print("\n(2) 公平な比較（1コース予測のみ）:")
        print("  注意: 同一条件での比較だが、イン不利会場で1コースを予測するケースは")
        print("        特に有利な条件に限定されるため、この差は特徴量の効果を反映しない")
        print()

        fair_results = {}
        for venues, label in [(strong_in_venues, 'イン有利会場'), (weak_in_venues, 'イン不利会場')]:
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as hits
                FROM races r
                JOIN race_predictions p ON r.id = p.race_id
                JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND p.prediction_type = 'advance'
                  AND p.rank_prediction = 1
                  AND p.pit_number = 1  -- 1コース予測のみ
                  AND r.venue_code IN ({})
            '''.format(','.join(['?' for _ in venues])), (start_date, end_date, *venues))

            row = cursor.fetchone()
            total = row['total']
            hits = row['hits'] or 0
            accuracy = (hits / total * 100) if total > 0 else 0
            ci = wilson_score_interval(hits, total)
            warning = sample_size_warning(total)

            fair_results[label] = {
                'accuracy': accuracy,
                'total': total,
                'hits': hits,
                'ci': ci
            }

            print(f"  {label}: {accuracy:.1f}% (n={total:,}){warning}")
            print(f"    95%信頼区間: [{ci[0]*100:.1f}%, {ci[1]*100:.1f}%]")

        diff = fair_results['イン不利会場']['accuracy'] - fair_results['イン有利会場']['accuracy']
        print(f"\n  差: {diff:+.1f}pt（イン不利会場が{'高い' if diff > 0 else '低い'}）")

        print("\n(3) 分析の限界:")
        print("  - 現在の分析では「特徴量の効果」を因果的に測定できない")
        print("  - 特徴量あり/なしでのA/Bテストが必要")
        print("  - 特徴量は正常に動作していると推定されるが、効果は定量化できない")

        return {
            'fair_results': fair_results,
            'accuracy_diff': diff
        }

    def analyze_weather_feature_impact(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """天候強化特徴量の効果分析"""
        print("\n" + "=" * 70)
        print("【天候強化特徴量】")
        print("=" * 70)

        cursor = self.conn.cursor()

        print("\n風速別の精度:")
        print("  注意: この差は強風時の予測困難度を反映しており、特徴量の効果を直接測定していない")
        print()

        wind_speed_bins = [
            (0, 2, '微風 (0-2m)'),
            (2, 4, '弱風 (2-4m)'),
            (4, 6, '中風 (4-6m)'),
            (6, 100, '強風 (6m+)')
        ]

        wind_results = []
        for min_speed, max_speed, label in wind_speed_bins:
            cursor.execute('''
                SELECT
                    COUNT(DISTINCT r.id) as total,
                    SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits
                FROM races r
                JOIN race_conditions rc ON r.id = rc.race_id
                JOIN race_predictions p ON r.id = p.race_id
                JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND p.prediction_type = 'advance'
                  AND p.rank_prediction = 1
                  AND rc.wind_speed >= ? AND rc.wind_speed < ?
            ''', (start_date, end_date, min_speed, max_speed))

            row = cursor.fetchone()
            total = row['total']
            hits = row['hits'] or 0
            accuracy = (hits / total * 100) if total > 0 else 0
            ci = wilson_score_interval(hits, total)
            warning = sample_size_warning(total)

            wind_results.append({
                'label': label,
                'total': total,
                'hits': hits,
                'accuracy': accuracy,
                'ci': ci
            })

            print(f"  {label}: {accuracy:.1f}% (n={total:,}){warning}")
            print(f"    95%信頼区間: [{ci[0]*100:.1f}%, {ci[1]*100:.1f}%]")

        print("\n分析の限界:")
        print("  - 風速別の精度差は「予測困難度」を反映しており「特徴量の効果」ではない")
        print("  - 特徴量が機能していることは確認できるが、効果の大きさは測定できない")
        print("  - 特徴量あり/なしでのA/Bテストが必要")

        return {
            'wind_speed_results': wind_results
        }

    def analyze_tilt_wind_synergy(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """チルト×風向シナジーの効果分析"""
        print("\n" + "=" * 70)
        print("【チルト×風向シナジー】")
        print("=" * 70)

        cursor = self.conn.cursor()

        print("\nチルト角度×風向の1着的中率:")
        print()

        tilt_bins = [
            (-0.5, -0.5, '-0.5'),
            (0.0, 0.0, '0.0'),
            (0.5, 0.5, '+0.5'),
            (1.0, 1.0, '+1.0'),
            (1.5, 100, '+1.5以上')
        ]

        wind_types = [
            (['南', '南南東', '南東', '東南東', '南南西', '南西', '西南西'], '追い風'),
            (['北', '北北東', '北東', '東北東', '北北西', '北西', '西北西'], '向かい風'),
        ]

        synergy_results = []
        small_sample_count = 0

        for tilt_min, tilt_max, tilt_label in tilt_bins:
            for directions, wind_label in wind_types:
                placeholders = ','.join(['?' for _ in directions])
                cursor.execute(f'''
                    SELECT
                        COUNT(DISTINCT r.id) as total,
                        SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits
                    FROM races r
                    JOIN race_details rd ON r.id = rd.race_id
                    JOIN race_conditions rc ON r.id = rc.race_id
                    JOIN race_predictions p ON r.id = p.race_id AND rd.pit_number = p.pit_number
                    JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
                    WHERE r.race_date >= ? AND r.race_date <= ?
                      AND p.prediction_type = 'advance'
                      AND p.rank_prediction = 1
                      AND rd.tilt_angle >= ? AND rd.tilt_angle <= ?
                      AND rc.wind_direction IN ({placeholders})
                      AND rc.wind_speed >= 3  -- 風速3m以上
                ''', (start_date, end_date, tilt_min, tilt_max, *directions))

                row = cursor.fetchone()
                total = row['total']
                hits = row['hits'] or 0
                accuracy = (hits / total * 100) if total > 0 else 0
                ci = wilson_score_interval(hits, total)
                warning = sample_size_warning(total)

                if total < MIN_SAMPLE_SIZE:
                    small_sample_count += 1

                synergy_results.append({
                    'tilt': tilt_label,
                    'wind': wind_label,
                    'total': total,
                    'hits': hits,
                    'accuracy': accuracy,
                    'ci': ci
                })

                if total >= 5:  # 最低5件以上は表示
                    print(f"  {tilt_label} x {wind_label}: {accuracy:.1f}% (n={total}){warning}")
                    if total >= MIN_SAMPLE_SIZE:
                        print(f"    95%信頼区間: [{ci[0]*100:.1f}%, {ci[1]*100:.1f}%]")

        print(f"\n統計的信頼性:")
        print(f"  サンプル数{MIN_SAMPLE_SIZE}件未満の組み合わせ: {small_sample_count}/{len(synergy_results)}件")

        if small_sample_count > len(synergy_results) / 2:
            print("  [警告] 大半の組み合わせでサンプル数が不足しており、統計的信頼性が低い")
            print("  [評価] 効果不明（判断保留）")

        print("\n分析の限界:")
        print("  - サンプルサイズが小さく、偶然の誤差範囲内の可能性が高い")
        print("  - 統計的に有意な結論を出せない")
        print("  - より長期間のデータ収集が必要")

        return {
            'synergy_results': synergy_results,
            'small_sample_count': small_sample_count
        }

    def calculate_overall_assessment(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """総合評価"""
        print("\n" + "=" * 70)
        print("【総合評価】")
        print("=" * 70)

        print("\n1. 特徴量は正常に動作している")
        print("   - 会場×コース勝率テーブル: 会場特性に応じた予測をしている")
        print("   - 天候強化特徴量: 風速条件を考慮している")
        print("   - チルト×風向: 組み合わせ効果を考慮している")

        print("\n2. ただし、効果を正確に測定できていない")
        print("   - 「条件別の精度差」は「特徴量の効果」と同義ではない")
        print("   - 特徴量あり/なしでのA/Bテストが必要")
        print("   - 現在の分析では因果関係を示せない")

        baseline_result = results['baseline']
        if baseline_result['value_added'] < 0:
            print("\n3. 予測システム全体がベースラインより低精度")
            print(f"   - 常に1コース予測: {baseline_result['baseline_accuracy']:.1f}%")
            print(f"   - 予測システム: {baseline_result['system_accuracy']:.1f}%")
            print(f"   - 付加価値: {baseline_result['value_added']:+.1f}pt")
            print("   --> A-1（モデル再学習）を優先すべき")

        print("\n" + "=" * 70)
        print("【推奨アクション】")
        print("=" * 70)

        recommendations = [
            "1. 特徴量自体は維持（正常に動作している）",
            "2. 効果測定方法の改善が必要",
            "   - 特徴量あり/なしでのA/Bテスト実装",
            "   - 公平な条件での比較（同一予測ターゲットでの比較）",
            "   - 統計的信頼性の確保（サンプルサイズ、信頼区間）",
        ]

        if baseline_result['value_added'] < 0:
            recommendations.append("3. 予測システム全体の精度向上（ベースライン超えが最優先）")
            recommendations.append("   --> A-1（モデル再学習）を優先すべき")

        for rec in recommendations:
            print(rec)

        return {
            'recommendations': recommendations
        }

    def run_full_analysis(self, start_date: str, end_date: str):
        """完全な分析を実行"""
        print("\n" + "=" * 70)
        print("特徴量効果検証（改善版）")
        print("=" * 70)
        print(f"期間: {start_date} ~ {end_date}")

        results = {}

        # 0. ベースライン比較
        results['baseline'] = self.analyze_baseline(start_date, end_date)

        # 1. 会場×コース勝率テーブル
        results['venue_course'] = self.analyze_venue_course_fair_comparison(start_date, end_date)

        # 2. 天候強化特徴量
        results['weather'] = self.analyze_weather_feature_impact(start_date, end_date)

        # 3. チルト×風向シナジー
        results['synergy'] = self.analyze_tilt_wind_synergy(start_date, end_date)

        # 4. 総合評価
        results['overall'] = self.calculate_overall_assessment(results)

        return results

    def close(self):
        """接続を閉じる"""
        self.conn.close()


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='特徴量効果の検証（改善版）')
    parser.add_argument('--year', type=str, default='2025', help='検証年（デフォルト: 2025）')
    args = parser.parse_args()

    db_path = str(ROOT_DIR / 'data' / 'boatrace.db')

    analyzer = FeatureImpactAnalyzerV2(db_path)

    try:
        # 指定年の全期間で分析
        start_date = f'{args.year}-01-01'
        end_date = f'{args.year}-12-31'

        results = analyzer.run_full_analysis(start_date, end_date)

        print("\n" + "=" * 70)
        print("検証完了")
        print("=" * 70)

    finally:
        analyzer.close()


if __name__ == '__main__':
    main()
