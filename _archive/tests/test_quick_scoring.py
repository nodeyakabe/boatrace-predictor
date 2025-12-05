# -*- coding: utf-8 -*-
"""簡易スコアリングテスト"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'c:\\Users\\seizo\\Desktop\\BoatRace')

import sqlite3
from datetime import datetime
from src.analysis.race_predictor import RacePredictor
from config.settings import DATABASE_PATH

def quick_test():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')

    # 10レース取得（複数会場）
    cursor.execute("""
        SELECT DISTINCT r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date = ?
        ORDER BY r.venue_code, r.race_number
        LIMIT 10
    """, (today,))

    races = cursor.fetchall()
    conn.close()

    if not races:
        print("本日のレースなし")
        return

    predictor = RacePredictor()
    results = []

    for race_date, venue_code, race_number in races:
        print(f"\n【{venue_code} {race_number}R】")
        try:
            predictions = predictor.predict_race_by_key(race_date, venue_code, race_number)
            if predictions:
                for i, pred in enumerate(predictions[:3], 1):
                    pit = pred['pit_number']
                    name = pred.get('racer_name', '?')[:6]
                    cs = pred.get('course_score', 0)
                    rs = pred.get('racer_score', 0)
                    ms = pred.get('motor_score', 0)
                    total = pred['total_score']
                    print(f"  {i}位: {pit}号艇 {name} C:{cs:.1f} R:{rs:.1f} M:{ms:.1f} = {total:.1f}")

                results.append({
                    'venue': venue_code,
                    'race': race_number,
                    'first': predictions[0]['pit_number']
                })
        except Exception as e:
            print(f"  エラー: {e}")

    # 統計
    if results:
        course1_count = sum(1 for r in results if r['first'] == 1)
        print(f"\n統計: {len(results)}レース中、1号艇1位予測 = {course1_count}回 ({course1_count/len(results)*100:.1f}%)")

if __name__ == "__main__":
    quick_test()
