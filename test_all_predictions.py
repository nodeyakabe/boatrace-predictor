"""
全レースで予測をテストして分布を確認
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

def test_all():
    print("=" * 60)
    print("全レース予測テスト")
    print("=" * 60)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 全レース取得（100レースに制限）
    target_date = '2025-11-19'
    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
        LIMIT 100
    """, (target_date,))

    races = cursor.fetchall()
    print(f"\nテスト対象: {len(races)}レース")

    conn.close()

    # 予測実行
    predictor = RacePredictor()
    predictions_1st = []  # 1着予測の号艇
    success = 0
    errors = 0

    for race_id, venue_code, race_number in races:
        try:
            predictions = predictor.predict_race(race_id)
            if predictions:
                # 1着予測の号艇を記録
                first_pred = [p for p in predictions if p['rank_prediction'] == 1][0]
                predictions_1st.append(first_pred['pit_number'])
                success += 1
            else:
                errors += 1
        except Exception as e:
            print(f"エラー (race_id={race_id}): {e}")
            errors += 1

    # 分布を集計
    print(f"\n処理結果: 成功={success}, エラー={errors}")
    print("\n" + "=" * 60)
    print("1着予測の分布")
    print("=" * 60)
    counter = Counter(predictions_1st)
    total = len(predictions_1st)
    for pit in sorted(counter.keys()):
        count = counter[pit]
        pct = count / total * 100
        print(f"{pit}号艇: {count:3d}回 ({pct:5.1f}%)")

    print(f"\n合計: {total}レース")

    # 参考: 実際の勝率
    print("\n" + "=" * 60)
    print("参考: 実際の全国平均勝率")
    print("=" * 60)
    print("1号艇: 約 55%")
    print("2号艇: 約 14%")
    print("3号艇: 約 12%")
    print("4号艇: 約 10%")
    print("5号艇: 約  6%")
    print("6号艇: 約  3%")


if __name__ == "__main__":
    test_all()
