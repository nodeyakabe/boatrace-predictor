"""
複数の配点パターンを比較するバックテスト

現在の配点、改善提案、中間的な配点を比較
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from collections import defaultdict
from typing import Dict, List
import json

from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor


# テストする配点パターン（中間案ベースで微調整）
WEIGHT_PATTERNS = {
    '現在': {
        'course_weight': 35,
        'racer_weight': 35,
        'motor_weight': 20,
        'kimarite_weight': 5,
        'grade_weight': 5
    },
    '中間案A': {  # コース維持＋モーター強化
        'course_weight': 35,
        'racer_weight': 30,
        'motor_weight': 23,
        'kimarite_weight': 7,
        'grade_weight': 5
    },
    '中間案B': {  # モーターさらに強化
        'course_weight': 35,
        'racer_weight': 28,
        'motor_weight': 25,
        'kimarite_weight': 7,
        'grade_weight': 5
    },
    '中間案C': {  # 決まり手強化
        'course_weight': 35,
        'racer_weight': 30,
        'motor_weight': 22,
        'kimarite_weight': 8,
        'grade_weight': 5
    }
}


class MultiScoringBacktester:
    """複数配点パターン比較バックテスター"""

    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path

    def get_test_races(self, start_date: str, end_date: str, limit: int = None) -> List[Dict]:
        """テスト対象レースを取得"""
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            INNER JOIN results res ON r.id = res.race_id
            WHERE r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date, r.venue_code, r.race_number
        """
        if limit:
            query += f" LIMIT {limit}"

        cursor = conn.cursor()
        cursor.execute(query, (start_date, end_date))
        races = [
            {'id': r[0], 'venue_code': r[1], 'race_date': r[2], 'race_number': r[3]}
            for r in cursor.fetchall()
        ]
        conn.close()
        return races

    def get_actual_results(self, race_id: int) -> Dict[int, int]:
        """実際の結果を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND rank IS NOT NULL
        """, (race_id,))
        results = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return results

    def evaluate_predictions(self, predictions: List[Dict], actual_results: Dict[int, int]) -> Dict:
        """予想を評価"""
        if not predictions or not actual_results:
            return None

        predicted_order = [p['pit_number'] for p in predictions]
        actual_top3 = sorted(actual_results.keys(), key=lambda x: actual_results[x])[:3]

        pred_1st = predicted_order[0] if len(predicted_order) > 0 else None
        pred_2nd = predicted_order[1] if len(predicted_order) > 1 else None
        pred_3rd = predicted_order[2] if len(predicted_order) > 2 else None

        actual_1st = actual_top3[0] if len(actual_top3) > 0 else None
        actual_2nd = actual_top3[1] if len(actual_top3) > 1 else None
        actual_3rd = actual_top3[2] if len(actual_top3) > 2 else None

        return {
            'win_hit': pred_1st == actual_1st,
            'place_hit': pred_1st in actual_top3,
            'exacta_hit': pred_1st == actual_1st and pred_2nd == actual_2nd,
            'trifecta_hit': (pred_1st == actual_1st and
                           pred_2nd == actual_2nd and
                           pred_3rd == actual_3rd),
            'top3_exact': set(predicted_order[:3]) == set(actual_top3),
        }

    def run_comparison(self, start_date: str, end_date: str, limit: int = None) -> Dict:
        """複数配点パターンを比較"""

        print("=" * 80)
        print("複数配点パターン比較バックテスト")
        print("=" * 80)
        print(f"期間: {start_date} ～ {end_date}")
        if limit:
            print(f"レース数制限: {limit}")
        print()

        # テスト対象レース取得
        races = self.get_test_races(start_date, end_date, limit)
        if not races:
            print("対象レースが見つかりません")
            return None

        print(f"対象レース数: {len(races):,}レース")
        print()

        # 各配点パターンの予測器を初期化
        predictors = {}
        for name, weights in WEIGHT_PATTERNS.items():
            predictors[name] = RacePredictor(self.db_path, custom_weights=weights)

        # 結果を記録
        all_results = {name: {
            'win_hits': 0, 'place_hits': 0, 'exacta_hits': 0,
            'trifecta_hits': 0, 'top3_exact': 0, 'total': 0
        } for name in WEIGHT_PATTERNS}

        for i, race in enumerate(races, 1):
            race_id = race['id']
            actual_results = self.get_actual_results(race_id)
            if not actual_results:
                continue

            for name, predictor in predictors.items():
                try:
                    predictions = predictor.predict_race(race_id)
                    if predictions:
                        evaluation = self.evaluate_predictions(predictions, actual_results)
                        if evaluation:
                            all_results[name]['total'] += 1
                            if evaluation['win_hit']:
                                all_results[name]['win_hits'] += 1
                            if evaluation['place_hit']:
                                all_results[name]['place_hits'] += 1
                            if evaluation['exacta_hit']:
                                all_results[name]['exacta_hits'] += 1
                            if evaluation['trifecta_hit']:
                                all_results[name]['trifecta_hits'] += 1
                            if evaluation['top3_exact']:
                                all_results[name]['top3_exact'] += 1
                except Exception:
                    continue

            if i % 100 == 0:
                print(f"処理中... {i}/{len(races)} レース")

        print()
        print("=" * 80)
        print("結果比較")
        print("=" * 80)

        def calc_rate(hits, total):
            return hits / total * 100 if total > 0 else 0

        # ヘッダー
        header = f"{'配点パターン':<12}"
        for metric in ['単勝', '複勝', '2連単', '3連単', '3連複']:
            header += f" {metric:>8}"
        print(header)
        print("-" * 70)

        # 各パターンの結果
        for name, results in all_results.items():
            total = results['total']
            if total == 0:
                continue

            line = f"{name:<12}"
            line += f" {calc_rate(results['win_hits'], total):>7.2f}%"
            line += f" {calc_rate(results['place_hits'], total):>7.2f}%"
            line += f" {calc_rate(results['exacta_hits'], total):>7.2f}%"
            line += f" {calc_rate(results['trifecta_hits'], total):>7.2f}%"
            line += f" {calc_rate(results['top3_exact'], total):>7.2f}%"
            print(line)

        print()
        print(f"テスト実施レース数: {total:,}レース")

        # 配点詳細を表示
        print()
        print("【各配点パターンの詳細】")
        for name, weights in WEIGHT_PATTERNS.items():
            print(f"\n{name}:")
            print(f"  コース={weights['course_weight']}, 選手={weights['racer_weight']}, "
                  f"モーター={weights['motor_weight']}, 決まり手={weights['kimarite_weight']}, "
                  f"グレード={weights['grade_weight']}")

        return all_results


def main():
    import argparse

    parser = argparse.ArgumentParser(description='複数配点パターン比較バックテスト')
    parser.add_argument('--start', default='2024-09-01', help='開始日')
    parser.add_argument('--end', default='2024-11-20', help='終了日')
    parser.add_argument('--limit', type=int, default=500, help='レース数制限')

    args = parser.parse_args()

    backtester = MultiScoringBacktester()
    backtester.run_comparison(args.start, args.end, args.limit)


if __name__ == "__main__":
    main()
