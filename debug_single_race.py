"""
1レースのみで詳細なエラー確認
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor
import traceback

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 最新レース1件取得
cursor.execute("""
    SELECT r.id, r.race_date, r.venue_code, r.race_number
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
if not race:
    print("テスト対象のレースが見つかりません")
    exit(1)

race_id, race_date, venue, race_no = race

print("=" * 80)
print(f"デバッグテスト: 1レースのみ")
print("=" * 80)
print(f"レースID: {race_id}")
print(f"日付: {race_date}")
print(f"会場: {venue}")
print(f"レース番号: {race_no}")
print()

# 実際の結果
cursor.execute("""
    SELECT pit_number FROM results
    WHERE race_id = ? AND rank = 1 AND is_invalid = 0
""", (race_id,))
actual = cursor.fetchone()
actual_winner = actual[0] if actual else None

print(f"実際の1着: {actual_winner}号")
print()

print("予測実行中...")
print("-" * 80)

try:
    predictor = RacePredictor(db_path='data/boatrace.db')
    predictions = predictor.predict_race(race_id)

    print()
    print("-" * 80)
    print("予測成功！")
    print()

    if predictions and len(predictions) > 0:
        print(f"予測結果: {len(predictions)}艇")
        print()

        for i, pred in enumerate(predictions[:3], 1):
            print(f"{i}位予測: {pred['pit_number']}号")
            print(f"  total_score: {pred.get('total_score', 0):.2f}")
            print(f"  pre_score: {pred.get('pre_score', 0):.2f}")
            print(f"  before_score: {pred.get('before_score', 0):.2f}")
            print()

        # PRE単体での予測
        pre_only = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
        integrated_pred = predictions[0]['pit_number']
        pre_pred = pre_only[0]['pit_number']

        print(f"統合予測: {integrated_pred}号")
        print(f"PRE単体予測: {pre_pred}号")
        print(f"実際の1着: {actual_winner}号")
        print()

        if integrated_pred == actual_winner:
            print("✓ 統合予測が的中")
        else:
            print("× 統合予測が外れ")

        if pre_pred == actual_winner:
            print("✓ PRE単体予測が的中")
        else:
            print("× PRE単体予測が外れ")

    else:
        print("エラー: 予測結果が空です")

except Exception as e:
    print()
    print("-" * 80)
    print("予測失敗！")
    print()
    print(f"エラータイプ: {type(e).__name__}")
    print(f"エラーメッセージ: {e}")
    print()
    print("詳細なスタックトレース:")
    print("-" * 80)
    traceback.print_exc()

conn.close()

print()
print("=" * 80)
