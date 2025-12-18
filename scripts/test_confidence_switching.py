#!/usr/bin/env python3
"""
信頼度ベース戦略切り替えのバックテスト

アプローチ1: 1着予測の確信度に応じた2着・3着予測方法の切り替え

テスト内容:
1. baselineとの比較（ROI、的中率）
2. 信頼度別の分布と精度
3. 閾値パターンの最適化

評価指標:
- ROI（回収率）
- 2着的中率、3着的中率
- 三連単的中率
- 購入数
- 信頼度別の精度
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
import pandas as pd
import numpy as np
from collections import defaultdict
import logging
import json

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.race_predictor import RacePredictor
from src.ml.confidence_based_rank_predictor import (
    ConfidenceBasedRankPredictor,
    ConfidenceBasedIntegrator,
    calculate_market_probs_from_odds
)
from config.feature_flags import is_feature_enabled, set_feature_flag


# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConfidenceSwitchingBacktester:
    """信頼度ベース戦略切り替えのバックテスト"""

    def __init__(
        self,
        db_path: str = 'data/boatrace.db',
        start_date: str = '2025-11-28',
        end_date: str = '2025-12-10'
    ):
        self.db_path = db_path
        self.start_date = start_date
        self.end_date = end_date

        # 結果格納用
        self.results = {
            'baseline': defaultdict(list),
            'confidence_based': defaultdict(list)
        }

        # 信頼度別統計
        self.confidence_stats = {
            'high': {'total': 0, 'correct_1st': 0, 'correct_2nd': 0, 'correct_3rd': 0},
            'medium': {'total': 0, 'correct_1st': 0, 'correct_2nd': 0, 'correct_3rd': 0},
            'low': {'total': 0, 'correct_1st': 0, 'correct_2nd': 0, 'correct_3rd': 0}
        }

    def get_test_races(self) -> pd.DataFrame:
        """テスト対象レースを取得"""
        conn = sqlite3.connect(self.db_path)

        query = """
        SELECT
            r.id AS race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            r.race_grade
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
            AND EXISTS (
                SELECT 1 FROM entries e WHERE e.race_id = r.id
                GROUP BY e.race_id HAVING COUNT(*) = 6
            )
            AND EXISTS (
                SELECT 1 FROM results res
                WHERE res.race_id = r.id
                    AND res.is_invalid = 0
                    AND res.rank IS NOT NULL
            )
        ORDER BY r.race_date, r.id
        """

        df = pd.read_sql_query(query, conn, params=(self.start_date, self.end_date))
        conn.close()

        logger.info(f"テスト対象レース数: {len(df)}")
        return df

    def get_actual_results(self, race_id: int) -> dict:
        """実際のレース結果を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank IS NOT NULL
            ORDER BY rank
        """, (race_id,))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        if len(results) < 3:
            return None

        return {
            'first': int(results[0][0]),
            'second': int(results[1][0]),
            'third': int(results[2][0])
        }

    def get_trifecta_payout(self, race_id: int, combination: str) -> float:
        """3連単の払戻金を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        """, (race_id, combination))

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row and row[0]:
            return float(row[0]) * 100  # 100円単位
        return 0.0

    def run_backtest(
        self,
        threshold_pattern: str = 'A'
    ) -> dict:
        """
        バックテストを実行

        Args:
            threshold_pattern: 閾値パターン
                - 'A': (high=0.7, medium=0.5)
                - 'B': (high=0.75, medium=0.6)
                - 'C': (high=0.8, medium=0.65)
        """
        # 閾値設定
        thresholds = {
            'A': (0.7, 0.5),
            'B': (0.75, 0.6),
            'C': (0.8, 0.65)
        }

        high_threshold, medium_threshold = thresholds.get(threshold_pattern, (0.7, 0.5))

        logger.info(f"=== バックテスト開始 ===")
        logger.info(f"期間: {self.start_date} ~ {self.end_date}")
        logger.info(f"閾値パターン: {threshold_pattern} (high={high_threshold}, medium={medium_threshold})")

        # テストレースを取得
        test_races = self.get_test_races()

        if len(test_races) == 0:
            logger.error("テスト対象レースが見つかりません")
            return {}

        # 結果をリセット
        self.results = {
            'baseline': defaultdict(list),
            'confidence_based': defaultdict(list)
        }

        self.confidence_stats = {
            'high': {'total': 0, 'correct_1st': 0, 'correct_2nd': 0, 'correct_3rd': 0},
            'medium': {'total': 0, 'correct_1st': 0, 'correct_2nd': 0, 'correct_3rd': 0},
            'low': {'total': 0, 'correct_1st': 0, 'correct_2nd': 0, 'correct_3rd': 0}
        }

        # ========================================
        # 1. Baseline（信頼度ベースなし）
        # ========================================
        logger.info("\n--- Baseline評価 ---")
        set_feature_flag('confidence_based_switching', False)
        predictor_baseline = RacePredictor(db_path=self.db_path)

        baseline_stats = {
            'total': 0,
            'bet': 0,
            'hit': 0,
            'payout': 0.0,
            'cost': 0.0,
            'hit_1st': 0,
            'hit_2nd': 0,
            'hit_3rd': 0
        }

        for idx, race in test_races.iterrows():
            race_id = race['race_id']

            # 実結果を取得
            actual = self.get_actual_results(race_id)
            if actual is None:
                continue

            baseline_stats['total'] += 1

            try:
                predictions = predictor_baseline.predict_race(race_id)

                if len(predictions) < 3:
                    continue

                # 信頼度チェック（B以上のみ購入）
                top_confidence = predictions[0].get('confidence', 'E')
                if top_confidence not in ['A', 'B']:
                    continue

                baseline_stats['bet'] += 1

                # 予測結果
                pred_1st = predictions[0]['pit_number']
                pred_2nd = predictions[1]['pit_number']
                pred_3rd = predictions[2]['pit_number']

                # 的中判定
                if pred_1st == actual['first']:
                    baseline_stats['hit_1st'] += 1

                if pred_2nd == actual['second']:
                    baseline_stats['hit_2nd'] += 1

                if pred_3rd == actual['third']:
                    baseline_stats['hit_3rd'] += 1

                combination = f"{pred_1st}-{pred_2nd}-{pred_3rd}"
                actual_combination = f"{actual['first']}-{actual['second']}-{actual['third']}"

                baseline_stats['cost'] += 100.0

                if combination == actual_combination:
                    baseline_stats['hit'] += 1
                    payout = self.get_trifecta_payout(race_id, actual_combination)
                    baseline_stats['payout'] += payout

            except Exception as e:
                logger.debug(f"Baseline Race {race_id}: {e}")

        # ========================================
        # 2. 信頼度ベース戦略切り替え
        # ========================================
        logger.info("\n--- 信頼度ベース戦略評価 ---")
        set_feature_flag('confidence_based_switching', True)

        # 予測器を新しい閾値で再初期化
        predictor_cb = RacePredictor(db_path=self.db_path)
        predictor_cb.confidence_based_predictor = ConfidenceBasedRankPredictor(
            high_threshold=high_threshold,
            medium_threshold=medium_threshold
        )
        predictor_cb.confidence_based_integrator = ConfidenceBasedIntegrator(
            predictor=predictor_cb.confidence_based_predictor,
            enable_logging=False
        )

        cb_stats = {
            'total': 0,
            'bet': 0,
            'hit': 0,
            'payout': 0.0,
            'cost': 0.0,
            'hit_1st': 0,
            'hit_2nd': 0,
            'hit_3rd': 0
        }

        for idx, race in test_races.iterrows():
            race_id = race['race_id']

            # 実結果を取得
            actual = self.get_actual_results(race_id)
            if actual is None:
                continue

            cb_stats['total'] += 1

            try:
                predictions = predictor_cb.predict_race(race_id)

                if len(predictions) < 3:
                    continue

                # 信頼度チェック
                top_confidence = predictions[0].get('confidence', 'E')
                if top_confidence not in ['A', 'B']:
                    continue

                cb_stats['bet'] += 1

                # 予測結果
                pred_1st = predictions[0]['pit_number']
                pred_2nd = predictions[1]['pit_number']
                pred_3rd = predictions[2]['pit_number']

                # 信頼度ベースの情報を取得
                confidence_info = predictions[0].get('confidence_score', {})
                confidence_level = confidence_info.get('confidence_level', 'medium')

                # 信頼度別統計を更新
                self.confidence_stats[confidence_level]['total'] += 1

                if pred_1st == actual['first']:
                    cb_stats['hit_1st'] += 1
                    self.confidence_stats[confidence_level]['correct_1st'] += 1

                if pred_2nd == actual['second']:
                    cb_stats['hit_2nd'] += 1
                    self.confidence_stats[confidence_level]['correct_2nd'] += 1

                if pred_3rd == actual['third']:
                    cb_stats['hit_3rd'] += 1
                    self.confidence_stats[confidence_level]['correct_3rd'] += 1

                combination = f"{pred_1st}-{pred_2nd}-{pred_3rd}"
                actual_combination = f"{actual['first']}-{actual['second']}-{actual['third']}"

                cb_stats['cost'] += 100.0

                if combination == actual_combination:
                    cb_stats['hit'] += 1
                    payout = self.get_trifecta_payout(race_id, actual_combination)
                    cb_stats['payout'] += payout

            except Exception as e:
                logger.debug(f"CB Race {race_id}: {e}")

        # ========================================
        # 結果集計
        # ========================================
        results = {
            'threshold_pattern': threshold_pattern,
            'high_threshold': high_threshold,
            'medium_threshold': medium_threshold,
            'period': f"{self.start_date} ~ {self.end_date}",
            'total_races': len(test_races),
            'baseline': self._calculate_metrics(baseline_stats),
            'confidence_based': self._calculate_metrics(cb_stats),
            'confidence_distribution': self._format_confidence_stats()
        }

        # 改善度を計算
        results['improvement'] = {
            'roi_diff': results['confidence_based']['roi'] - results['baseline']['roi'],
            '2nd_accuracy_diff': results['confidence_based']['accuracy_2nd'] - results['baseline']['accuracy_2nd'],
            '3rd_accuracy_diff': results['confidence_based']['accuracy_3rd'] - results['baseline']['accuracy_3rd'],
            'trifecta_accuracy_diff': results['confidence_based']['accuracy_trifecta'] - results['baseline']['accuracy_trifecta']
        }

        self._print_results(results)

        return results

    def _calculate_metrics(self, stats: dict) -> dict:
        """評価指標を計算"""
        bet = max(stats['bet'], 1)  # 0除算防止

        return {
            'total_races': stats['total'],
            'bets': stats['bet'],
            'hits': stats['hit'],
            'cost': stats['cost'],
            'payout': stats['payout'],
            'roi': (stats['payout'] / stats['cost'] * 100) if stats['cost'] > 0 else 0,
            'accuracy_1st': (stats['hit_1st'] / bet * 100) if bet > 0 else 0,
            'accuracy_2nd': (stats['hit_2nd'] / bet * 100) if bet > 0 else 0,
            'accuracy_3rd': (stats['hit_3rd'] / bet * 100) if bet > 0 else 0,
            'accuracy_trifecta': (stats['hit'] / bet * 100) if bet > 0 else 0
        }

    def _format_confidence_stats(self) -> dict:
        """信頼度別統計を整形"""
        formatted = {}

        for level, stats in self.confidence_stats.items():
            total = max(stats['total'], 1)
            formatted[level] = {
                'count': stats['total'],
                'accuracy_1st': (stats['correct_1st'] / total * 100) if total > 0 else 0,
                'accuracy_2nd': (stats['correct_2nd'] / total * 100) if total > 0 else 0,
                'accuracy_3rd': (stats['correct_3rd'] / total * 100) if total > 0 else 0
            }

        return formatted

    def _print_results(self, results: dict):
        """結果を表示"""
        print("\n" + "=" * 70)
        print("信頼度ベース戦略切り替え バックテスト結果")
        print("=" * 70)
        print(f"期間: {results['period']}")
        print(f"総レース数: {results['total_races']}")
        print(f"閾値パターン: {results['threshold_pattern']} (high={results['high_threshold']}, medium={results['medium_threshold']})")

        print("\n--- Baseline ---")
        bl = results['baseline']
        print(f"  購入数: {bl['bets']}")
        print(f"  的中数: {bl['hits']}")
        print(f"  投資額: {bl['cost']:,.0f}円")
        print(f"  払戻額: {bl['payout']:,.0f}円")
        print(f"  ROI: {bl['roi']:.1f}%")
        print(f"  1着的中率: {bl['accuracy_1st']:.1f}%")
        print(f"  2着的中率: {bl['accuracy_2nd']:.1f}%")
        print(f"  3着的中率: {bl['accuracy_3rd']:.1f}%")
        print(f"  三連単的中率: {bl['accuracy_trifecta']:.2f}%")

        print("\n--- 信頼度ベース戦略 ---")
        cb = results['confidence_based']
        print(f"  購入数: {cb['bets']}")
        print(f"  的中数: {cb['hits']}")
        print(f"  投資額: {cb['cost']:,.0f}円")
        print(f"  払戻額: {cb['payout']:,.0f}円")
        print(f"  ROI: {cb['roi']:.1f}%")
        print(f"  1着的中率: {cb['accuracy_1st']:.1f}%")
        print(f"  2着的中率: {cb['accuracy_2nd']:.1f}%")
        print(f"  3着的中率: {cb['accuracy_3rd']:.1f}%")
        print(f"  三連単的中率: {cb['accuracy_trifecta']:.2f}%")

        print("\n--- 改善効果 ---")
        imp = results['improvement']
        roi_sign = '+' if imp['roi_diff'] >= 0 else ''
        acc2_sign = '+' if imp['2nd_accuracy_diff'] >= 0 else ''
        acc3_sign = '+' if imp['3rd_accuracy_diff'] >= 0 else ''
        tri_sign = '+' if imp['trifecta_accuracy_diff'] >= 0 else ''
        print(f"  ROI変化: {roi_sign}{imp['roi_diff']:.1f}pt")
        print(f"  2着的中率変化: {acc2_sign}{imp['2nd_accuracy_diff']:.1f}pt")
        print(f"  3着的中率変化: {acc3_sign}{imp['3rd_accuracy_diff']:.1f}pt")
        print(f"  三連単的中率変化: {tri_sign}{imp['trifecta_accuracy_diff']:.2f}pt")

        print("\n--- 信頼度別分布 ---")
        for level, stats in results['confidence_distribution'].items():
            print(f"  {level.upper()}: 件数={stats['count']}, "
                  f"1着={stats['accuracy_1st']:.1f}%, "
                  f"2着={stats['accuracy_2nd']:.1f}%, "
                  f"3着={stats['accuracy_3rd']:.1f}%")

        print("=" * 70)

    def run_threshold_optimization(self) -> dict:
        """
        閾値の最適化テスト

        複数の閾値パターンでテストし、最適なパターンを特定
        """
        logger.info("=== 閾値最適化テスト ===")

        all_results = {}

        for pattern in ['A', 'B', 'C']:
            logger.info(f"\n--- パターン {pattern} ---")
            results = self.run_backtest(threshold_pattern=pattern)
            all_results[pattern] = results

        # 最適パターンを特定
        best_pattern = max(
            all_results.keys(),
            key=lambda p: all_results[p]['confidence_based']['roi']
        )

        print("\n" + "=" * 70)
        print("閾値最適化結果サマリー")
        print("=" * 70)

        for pattern, res in all_results.items():
            cb = res['confidence_based']
            imp = res['improvement']
            marker = "***" if pattern == best_pattern else "   "
            print(f"{marker} パターン{pattern}: ROI={cb['roi']:.1f}% (変化: {imp['roi_diff']:+.1f}pt), "
                  f"三連単={cb['accuracy_trifecta']:.2f}%")

        print(f"\n最適パターン: {best_pattern}")
        print("=" * 70)

        return all_results


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description='信頼度ベース戦略切り替えのバックテスト')
    parser.add_argument('--start-date', default='2025-11-28', help='開始日')
    parser.add_argument('--end-date', default='2025-12-10', help='終了日')
    parser.add_argument('--pattern', default='A', choices=['A', 'B', 'C', 'ALL'],
                        help='閾値パターン (A/B/C/ALL)')
    parser.add_argument('--db-path', default='data/boatrace.db', help='データベースパス')

    args = parser.parse_args()

    backtester = ConfidenceSwitchingBacktester(
        db_path=args.db_path,
        start_date=args.start_date,
        end_date=args.end_date
    )

    if args.pattern == 'ALL':
        results = backtester.run_threshold_optimization()
    else:
        results = backtester.run_backtest(threshold_pattern=args.pattern)

    # 結果をJSONで保存
    output_dir = project_root / 'results'
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = output_dir / f'confidence_switching_backtest_{timestamp}.json'

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"結果を保存しました: {output_path}")


if __name__ == '__main__':
    main()
