"""
法則補正の影響を複数レースで分析
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor
from collections import defaultdict

def analyze_impact():
    print("=" * 80)
    print("法則補正の影響分析（30レース）")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    target_date = '2025-11-19'
    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
        LIMIT 30
    """, (target_date,))

    races = cursor.fetchall()
    conn.close()

    # 号艇ごとの補正統計
    adjustments_by_pit = defaultdict(list)
    rank_changes = defaultdict(int)  # 順位変動の統計

    predictor = RacePredictor()

    for race_id, venue_code, race_number in races:
        try:
            predictions = predictor.predict_race(race_id)
            if not predictions:
                continue

            for pred in predictions:
                pit = pred['pit_number']
                adjustment = pred.get('rule_adjustment', 0)
                adjustments_by_pit[pit].append(adjustment)

        except Exception as e:
            print(f"エラー (race_id={race_id}): {e}")

    # 統計を表示
    print(f"\n処理レース数: {len(races)}")
    print("\n号艇別の法則補正統計:")
    print("  号艇 | 平均補正 | 最大補正 | 最小補正 | サンプル数")
    print("  " + "-" * 60)

    for pit in sorted(adjustments_by_pit.keys()):
        adjustments = adjustments_by_pit[pit]
        avg = sum(adjustments) / len(adjustments)
        max_adj = max(adjustments)
        min_adj = min(adjustments)
        count = len(adjustments)

        print(f"  {pit}号艇 | {avg:+6.2f} | {max_adj:+6.2f} | {min_adj:+6.2f} | {count:4d}")

    # 補正が大きいレースを表示
    print("\n" + "=" * 80)
    print("2号艇の補正が大きいレース（上位5件）")
    print("=" * 80)

    race_adjustments = []
    for race_id, venue_code, race_number in races:
        try:
            predictions = predictor.predict_race(race_id)
            if not predictions:
                continue

            for pred in predictions:
                if pred['pit_number'] == 2:
                    adjustment = pred.get('rule_adjustment', 0)
                    race_adjustments.append((race_id, venue_code, race_number, adjustment, pred))
                    break
        except:
            pass

    # 補正が大きい順にソート
    race_adjustments.sort(key=lambda x: x[3], reverse=True)

    for race_id, venue_code, race_number, adjustment, pred in race_adjustments[:5]:
        print(f"\n会場{int(venue_code):02d} {int(race_number):2d}R (race_id={race_id}):")
        print(f"  2号艇補正: {adjustment:+.1f}")
        print(f"  選手: {pred['racer_name']}")
        print(f"  最終スコア: {pred['total_score']:.1f} (補正前: {pred['total_score'] - adjustment:.1f})")


if __name__ == "__main__":
    analyze_impact()
