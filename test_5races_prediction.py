"""
5レースで予測をテストして分布を確認
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor
from collections import Counter

def test_5races():
    print("=" * 60)
    print("5レース予測テスト")
    print("=" * 60)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 5レース取得
    target_date = '2025-11-19'
    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
        LIMIT 5
    """, (target_date,))

    races = cursor.fetchall()
    print(f"\nテスト対象: {len(races)}レース")

    conn.close()

    # 予測実行
    predictor = RacePredictor()
    predictions_1st = []  # 1着予測の号艇

    for race_id, venue_code, race_number in races:
        try:
            predictions = predictor.predict_race(race_id)
            if predictions:
                # 1着予測の号艇を記録
                first_pred = [p for p in predictions if p['rank_prediction'] == 1][0]
                predictions_1st.append(first_pred['pit_number'])

                print(f"\n会場{int(venue_code):02d} {int(race_number):2d}R:")
                for pred in predictions[:3]:  # 上位3艇だけ表示
                    print(f"  {pred['rank_prediction']}位: {pred['pit_number']}号艇 ({pred['total_score']:.1f}点, {pred['confidence']})")
        except Exception as e:
            print(f"エラー (race_id={race_id}): {e}")

    # 分布を集計
    print("\n" + "=" * 60)
    print("1着予測の分布")
    print("=" * 60)
    counter = Counter(predictions_1st)
    for pit in sorted(counter.keys()):
        count = counter[pit]
        pct = count / len(predictions_1st) * 100
        print(f"{pit}号艇: {count}回 ({pct:.1f}%)")

    print(f"\n合計: {len(predictions_1st)}レース")


if __name__ == "__main__":
    test_5races()
