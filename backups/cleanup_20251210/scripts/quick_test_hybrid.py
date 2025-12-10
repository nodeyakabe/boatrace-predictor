"""ハイブリッドスコアリングの簡易テスト（10レースのみ）"""

import sys
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor

db_path = PROJECT_ROOT / "data" / "boatrace.db"
predictor = RacePredictor(str(db_path))

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 信頼度Bのレースを10件だけ取得
cursor.execute('''
    SELECT DISTINCT r.id
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id
    WHERE rp.confidence = 'B'
      AND rp.prediction_type = 'advance'
      AND r.race_date >= '2024-01-01'
      AND r.race_date < '2025-01-01'
    LIMIT 10
''')
race_ids = [row[0] for row in cursor.fetchall()]

print(f"テストレース数: {len(race_ids)}")

hit = 0
total = 0

for race_id in race_ids:
    try:
        predictions = predictor.predict_race(race_id)

        if not predictions or len(predictions) < 3:
            continue

        # 予想
        predicted = [p['pit_number'] for p in predictions[:3]]

        # 実際
        cursor.execute('''
            SELECT pit_number
            FROM results
            WHERE race_id = ? AND is_invalid = 0 AND CAST(rank AS INTEGER) <= 3
            ORDER BY CAST(rank AS INTEGER)
        ''', (race_id,))
        actual = [row[0] for row in cursor.fetchall()]

        if len(actual) < 3:
            continue

        total += 1
        is_hit = (predicted == actual)

        print(f"\nレースID {race_id}:")
        print(f"  予想: {'-'.join(map(str, predicted))}")
        print(f"  実際: {'-'.join(map(str, actual))}")
        print(f"  結果: {'的中' if is_hit else '外れ'}")

        # ハイブリッドスコア情報
        if 'hybrid_score' in predictions[0]:
            print(f"  ハイブリッド情報:")
            for i, pred in enumerate(predictions[:3], 1):
                print(f"    {i}位: {pred['pit_number']}号 - {pred.get('hybrid_reason', 'N/A')}")

        if is_hit:
            hit += 1

    except Exception as e:
        print(f"エラー (race_id={race_id}): {e}")
        import traceback
        traceback.print_exc()

conn.close()

print(f"\n={'='*60}")
print(f"的中: {hit}/{total} = {hit/total*100 if total > 0 else 0:.2f}%")
print(f"={'='*60}")
