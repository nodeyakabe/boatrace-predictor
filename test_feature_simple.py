"""
新機能の動作確認（シンプル版）
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor

# 最新5レースで確認
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
cursor.execute("""
    SELECT r.id, r.race_date, r.venue_code, r.race_number
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id
    WHERE rd.exhibition_course IS NOT NULL
    AND res.rank IS NOT NULL
    AND res.is_invalid = 0
    ORDER BY r.race_date DESC, r.id DESC
    LIMIT 5
""")
test_races = cursor.fetchall()

print("=" * 80)
print("新機能動作確認テスト")
print("=" * 80)
print()

predictor = RacePredictor(db_path='data/boatrace.db')

success = 0
errors = 0

for race_id, race_date, venue, race_no in test_races:
    print(f"[{race_date} {venue} {race_no}R]")
    
    try:
        # 実際の結果
        cursor.execute("""
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank = 1 AND is_invalid = 0
        """, (race_id,))
        actual_winner = cursor.fetchone()[0]
        
        # 予測
        predictions = predictor.predict_race(race_id)
        
        if predictions:
            integrated_pred = predictions[0]['pit_number']
            integrated_score = predictions[0]['total_score']
            
            # PRE単体スコア
            pre_only = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
            pre_pred = pre_only[0]['pit_number']
            pre_score = pre_only[0].get('pre_score', 0)
            
            int_hit = '◎' if integrated_pred == actual_winner else '×'
            pre_hit = '◎' if pre_pred == actual_winner else '×'
            
            print(f"  実際: {actual_winner}号")
            print(f"  統合予測: {integrated_pred}号 (スコア: {integrated_score:.1f}) {int_hit}")
            print(f"  PRE予測: {pre_pred}号 (スコア: {pre_score:.1f}) {pre_hit}")
            
            if integrated_pred != pre_pred:
                print(f"  ★ 予測が異なる")
            
            success += 1
        else:
            print("  エラー: 予測結果なし")
            errors += 1
            
    except Exception as e:
        print(f"  エラー: {e}")
        errors += 1
    
    print()

conn.close()

print("=" * 80)
print(f"成功: {success}レース / エラー: {errors}レース")
print("=" * 80)
