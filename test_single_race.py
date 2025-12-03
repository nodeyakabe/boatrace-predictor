"""
1レースのみのテスト（問題調査用）
"""
import sqlite3
import time
from src.analysis.race_predictor import RacePredictor

print("=" * 80)
print("1レーステスト（問題調査）")
print("=" * 80)

# 最新1レース取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
cursor.execute("""
    SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id
    WHERE rd.exhibition_course IS NOT NULL
    AND res.rank IS NOT NULL
    AND res.is_invalid = 0
    ORDER BY r.race_date DESC, r.id DESC
    LIMIT 1
""")
race = cursor.fetchone()
conn.close()

if not race:
    print("テスト対象レースが見つかりません")
    exit(1)

race_id, race_date, venue, race_no = race
print(f"テスト対象: {race_date} {venue} {race_no}R (ID: {race_id})")
print()

# 予測実行
print("予測開始...")
start_time = time.time()

try:
    predictor = RacePredictor(db_path='data/boatrace.db')
    print("Predictor初期化完了")
    
    predictions = predictor.predict_race(race_id)
    
    elapsed = time.time() - start_time
    
    print(f"予測完了: {elapsed:.2f}秒")
    print(f"予測結果数: {len(predictions)}")
    
    if predictions:
        print("\n【予測結果】")
        for i, pred in enumerate(predictions[:3], 1):
            print(f"{i}位: {pred['pit_number']}号 {pred['racer_name']} (スコア: {pred['total_score']:.1f})")
    
except Exception as e:
    elapsed = time.time() - start_time
    print(f"エラー発生 ({elapsed:.2f}秒経過): {e}")
    import traceback
    traceback.print_exc()

print("=" * 80)
