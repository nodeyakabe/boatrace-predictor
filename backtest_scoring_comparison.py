"""
スコアリング配点比較バックテスト

現在の配点（旧）と改善提案の配点（新）を比較して、
予想精度の違いを検証する
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional
import json

from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor


# 旧配点（現在）
OLD_WEIGHTS = {
    'course_weight': 35,
    'racer_weight': 35,
    'motor_weight': 20,
    'kimarite_weight': 5,
    'grade_weight': 5
}

# 新配点（改善提案）
NEW_WEIGHTS = {
    'course_weight': 30,
    'racer_weight': 25,
    'motor_weight': 25,
    'kimarite_weight': 10,
    'grade_weight': 10
}


class ScoringComparisonBacktester:
    """配点比較バックテスター"""

    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path

    def get_test_races(self, start_date: str, end_date: str,
                       venue_code: str = None, limit: int = None) -> List[Dict]:
        """テスト対象レースを取得"""
        conn = sqlite3.connect(self.db_path)

        query = """
            SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            INNER JOIN results res ON r.id = res.race_id
            WHERE r.race_date BETWEEN ? AND ?
        """
        params = [start_date, end_date]

        if venue_code:
            query += " AND r.venue_code = ?"
            params.append(venue_code)

        query += " ORDER BY r.race_date, r.venue_code, r.race_number"

        if limit:
            query += f" LIMIT {limit}"

        cursor = conn.cursor()
        cursor.execute(query, params)
        races = [
            {'id': r[0], 'venue_code': r[1], 'race_date': r[2], 'race_number': r[3]}
            for r in cursor.fetchall()
        ]
        conn.close()

        return races

    def get_actual_results(self, race_id: int) -> Dict[int, int]:
        """実際の結果を取得（pit_number -> rank）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND rank IS NOT NULL
            ORDER BY rank
        """, (race_id,))

        results = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        return results

    def evaluate_predictions(self, predictions: List[Dict],
                            actual_results: Dict[int, int]) -> Dict:
        """予想を評価"""
        if not predictions or not actual_results:
            return None

        # 予想順位（スコア高い順）
        predicted_order = [p['pit_number'] for p in predictions]

        # 実際の1着、2着、3着
        actual_top3 = sorted(actual_results.keys(), key=lambda x: actual_results[x])[:3]
        actual_1st = actual_top3[0] if len(actual_top3) > 0 else None
        actual_2nd = actual_top3[1] if len(actual_top3) > 1 else None
        actual_3rd = actual_top3[2] if len(actual_top3) > 2 else None

        # 予想の1位、2位、3位
        pred_1st = predicted_order[0] if len(predicted_order) > 0 else None
        pred_2nd = predicted_order[1] if len(predicted_order) > 1 else None
        pred_3rd = predicted_order[2] if len(predicted_order) > 2 else None

        return {
            'win_hit': pred_1st == actual_1st,  # 1着的中
            'place_hit': pred_1st in actual_top3,  # 予想1位が3着以内
            'exacta_hit': pred_1st == actual_1st and pred_2nd == actual_2nd,  # 2連単的中
            'trifecta_hit': (pred_1st == actual_1st and
                           pred_2nd == actual_2nd and
                           pred_3rd == actual_3rd),  # 3連単的中
            'top3_match': len(set(predicted_order[:3]) & set(actual_top3)),  # 3連複一致数
            'top3_exact': set(predicted_order[:3]) == set(actual_top3),  # 3連複的中
            'predicted': predicted_order[:3],
            'actual': actual_top3
        }

    def run_comparison(self, start_date: str, end_date: str,
                       venue_code: str = None, limit: int = None,
                       show_details: bool = False) -> Dict:
        """新旧配点を比較してバックテスト実行"""

        print("=" * 80)
        print("スコアリング配点比較バックテスト")
        print("=" * 80)
        print(f"期間: {start_date} ～ {end_date}")
        if venue_code:
            print(f"会場: {venue_code}")
        if limit:
            print(f"レース数制限: {limit}")
        print()

        print("【旧配点】")
        for k, v in OLD_WEIGHTS.items():
            print(f"  {k}: {v}")
        print()

        print("【新配点】")
        for k, v in NEW_WEIGHTS.items():
            print(f"  {k}: {v}")
        print()

        # テスト対象レース取得
        races = self.get_test_races(start_date, end_date, venue_code, limit)

        if not races:
            print("対象レースが見つかりません")
            return None

        print(f"対象レース数: {len(races):,}レース")
        print()

        # 予測器を初期化（旧・新）
        predictor_old = RacePredictor(self.db_path, custom_weights=OLD_WEIGHTS)
        predictor_new = RacePredictor(self.db_path, custom_weights=NEW_WEIGHTS)

        # 結果を記録
        results_old = {
            'win_hits': 0, 'place_hits': 0, 'exacta_hits': 0,
            'trifecta_hits': 0, 'top3_exact': 0, 'total': 0
        }
        results_new = {
            'win_hits': 0, 'place_hits': 0, 'exacta_hits': 0,
            'trifecta_hits': 0, 'top3_exact': 0, 'total': 0
        }

        # 会場別統計
        venue_stats_old = defaultdict(lambda: {'win_hits': 0, 'total': 0})
        venue_stats_new = defaultdict(lambda: {'win_hits': 0, 'total': 0})

        # 詳細比較記録
        detail_records = []

        for i, race in enumerate(races, 1):
            race_id = race['id']

            # 実際の結果を取得
            actual_results = self.get_actual_results(race_id)
            if not actual_results:
                continue

            try:
                # 旧配点で予測
                pred_old = predictor_old.predict_race(race_id)
                if pred_old:
                    eval_old = self.evaluate_predictions(pred_old, actual_results)
                    if eval_old:
                        results_old['total'] += 1
                        if eval_old['win_hit']:
                            results_old['win_hits'] += 1
                            venue_stats_old[race['venue_code']]['win_hits'] += 1
                        if eval_old['place_hit']:
                            results_old['place_hits'] += 1
                        if eval_old['exacta_hit']:
                            results_old['exacta_hits'] += 1
                        if eval_old['trifecta_hit']:
                            results_old['trifecta_hits'] += 1
                        if eval_old['top3_exact']:
                            results_old['top3_exact'] += 1
                        venue_stats_old[race['venue_code']]['total'] += 1

                # 新配点で予測
                pred_new = predictor_new.predict_race(race_id)
                if pred_new:
                    eval_new = self.evaluate_predictions(pred_new, actual_results)
                    if eval_new:
                        results_new['total'] += 1
                        if eval_new['win_hit']:
                            results_new['win_hits'] += 1
                            venue_stats_new[race['venue_code']]['win_hits'] += 1
                        if eval_new['place_hit']:
                            results_new['place_hits'] += 1
                        if eval_new['exacta_hit']:
                            results_new['exacta_hits'] += 1
                        if eval_new['trifecta_hit']:
                            results_new['trifecta_hits'] += 1
                        if eval_new['top3_exact']:
                            results_new['top3_exact'] += 1
                        venue_stats_new[race['venue_code']]['total'] += 1

                # 詳細記録
                if show_details and eval_old and eval_new:
                    detail_records.append({
                        'race': race,
                        'old': eval_old,
                        'new': eval_new
                    })

            except Exception as e:
                # エラーはスキップ
                continue

            # 進捗表示
            if i % 50 == 0:
                print(f"処理中... {i}/{len(races)} レース")

        print()
        print("=" * 80)
        print("バックテスト結果比較")
        print("=" * 80)

        def calc_rate(hits, total):
            return hits / total * 100 if total > 0 else 0

        print()
        print(f"{'指標':<20} {'旧配点':>12} {'新配点':>12} {'差分':>12}")
        print("-" * 60)

        total = results_old['total']
        if total > 0:
            # 単勝的中率
            old_win = calc_rate(results_old['win_hits'], total)
            new_win = calc_rate(results_new['win_hits'], total)
            print(f"{'単勝的中率':<20} {old_win:>10.2f}% {new_win:>10.2f}% {new_win-old_win:>+10.2f}%")

            # 複勝的中率
            old_place = calc_rate(results_old['place_hits'], total)
            new_place = calc_rate(results_new['place_hits'], total)
            print(f"{'複勝的中率':<20} {old_place:>10.2f}% {new_place:>10.2f}% {new_place-old_place:>+10.2f}%")

            # 2連単的中率
            old_exacta = calc_rate(results_old['exacta_hits'], total)
            new_exacta = calc_rate(results_new['exacta_hits'], total)
            print(f"{'2連単的中率':<20} {old_exacta:>10.2f}% {new_exacta:>10.2f}% {new_exacta-old_exacta:>+10.2f}%")

            # 3連単的中率
            old_tri = calc_rate(results_old['trifecta_hits'], total)
            new_tri = calc_rate(results_new['trifecta_hits'], total)
            print(f"{'3連単的中率':<20} {old_tri:>10.2f}% {new_tri:>10.2f}% {new_tri-old_tri:>+10.2f}%")

            # 3連複的中率
            old_top3 = calc_rate(results_old['top3_exact'], total)
            new_top3 = calc_rate(results_new['top3_exact'], total)
            print(f"{'3連複的中率':<20} {old_top3:>10.2f}% {new_top3:>10.2f}% {new_top3-old_top3:>+10.2f}%")

        print()
        print(f"テスト実施レース数: {total:,}レース")

        # 会場別比較
        if len(venue_stats_old) > 1:
            print()
            print("【会場別単勝的中率比較】")
            print(f"{'会場':<8} {'旧配点':>12} {'新配点':>12} {'差分':>12}")
            print("-" * 50)

            all_venues = set(venue_stats_old.keys()) | set(venue_stats_new.keys())
            for venue in sorted(all_venues):
                old_v = venue_stats_old[venue]
                new_v = venue_stats_new[venue]

                old_rate = calc_rate(old_v['win_hits'], old_v['total'])
                new_rate = calc_rate(new_v['win_hits'], new_v['total'])

                print(f"{venue:<8} {old_rate:>10.1f}% {new_rate:>10.1f}% {new_rate-old_rate:>+10.1f}%")

        # 詳細表示
        if show_details and detail_records:
            print()
            print("【結果が異なったレース（最初の10件）】")
            diff_count = 0
            for rec in detail_records:
                if rec['old']['win_hit'] != rec['new']['win_hit']:
                    r = rec['race']
                    old_mark = "○" if rec['old']['win_hit'] else "×"
                    new_mark = "○" if rec['new']['win_hit'] else "×"
                    print(f"  {r['race_date']} {r['venue_code']} {r['race_number']}R: "
                          f"旧={old_mark} 新={new_mark} "
                          f"(予想: 旧{rec['old']['predicted'][:1]} 新{rec['new']['predicted'][:1]} "
                          f"実際: {rec['old']['actual'][:1]})")
                    diff_count += 1
                    if diff_count >= 10:
                        break

        return {
            'total_races': total,
            'old_results': results_old,
            'new_results': results_new,
            'venue_stats_old': dict(venue_stats_old),
            'venue_stats_new': dict(venue_stats_new)
        }


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='スコアリング配点比較バックテスト')
    parser.add_argument('--start', default='2024-10-01', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2024-11-30', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venue', help='会場コード（オプション）')
    parser.add_argument('--limit', type=int, help='レース数制限（オプション）')
    parser.add_argument('--details', action='store_true', help='詳細表示')

    args = parser.parse_args()

    backtester = ScoringComparisonBacktester()
    result = backtester.run_comparison(
        args.start,
        args.end,
        args.venue,
        args.limit,
        args.details
    )

    if result:
        # 結果をJSONに保存
        output_file = f"scoring_comparison_{args.start}_{args.end}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print()
        print(f"結果を保存しました: {output_file}")


if __name__ == "__main__":
    main()
