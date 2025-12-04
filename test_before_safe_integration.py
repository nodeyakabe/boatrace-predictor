"""
BEFORE_SAFE統合のテスト（30レース）
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor

def main():
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 最新30レース取得
    cursor.execute("""
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 30
    """)

    test_races = cursor.fetchall()

    def get_actual_winner(race_id):
        cursor.execute("""
            SELECT pit_number 
            FROM results 
            WHERE race_id = ? AND rank = 1 AND is_invalid = 0
        """, (race_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    predictor = RacePredictor(db_path='data/boatrace.db')

    safe_correct = 0
    total = 0
    prediction_changed = 0

    print("=" * 80)
    print("BEFORE_SAFE統合テスト: 30レース")
    print("=" * 80)
    print()

    for i, (race_id, date, venue, race_no) in enumerate(test_races, 1):
        predictions = predictor.predict_race(race_id)
        if not predictions or len(predictions) < 2:
            continue

        # 統合予測の1位
        safe_1st = predictions[0]['pit_number']

        # PRE単体の1位（pre_scoreでソート）
        pre_sorted = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
        pre_1st = pre_sorted[0]['pit_number']

        # 実際の1着
        actual = get_actual_winner(race_id)
        if actual is None:
            continue

        total += 1
        safe_hit = (safe_1st == actual)

        if safe_hit:
            safe_correct += 1

        if safe_1st != pre_1st:
            prediction_changed += 1
            status = "[的中]" if safe_hit else "[外れ]"
            print(f"[{i}/{len(test_races)}] {date} {venue} {race_no}R: SAFE={safe_1st}号 PRE={pre_1st}号 実際={actual}号 {status}")

        if i % 10 == 0:
            print(f"進捗: {i}/{len(test_races)}")

    print()
    print("=" * 80)
    print("結果サマリー")
    print("=" * 80)
    print(f"有効レース数: {total}")
    print()
    print(f"【的中率】")
    print(f"  BEFORE_SAFE統合: {safe_correct}/{total} ({safe_correct/total*100:.1f}%)")
    print()
    print(f"【予測変化】")
    print(f"  予測が変わったレース: {prediction_changed}/{total} ({prediction_changed/total*100:.1f}%)")
    print()
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    main()
