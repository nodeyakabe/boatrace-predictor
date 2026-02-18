"""1レースの予想生成テスト（エラー詳細確認用）"""
import sys
import io
import sqlite3
import traceback
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.prediction.predictor_helpers import create_standard_predictor
from config.settings import DATABASE_PATH

# 未生成の2020年レースIDを取得
conn = sqlite3.connect(DATABASE_PATH)
cur = conn.cursor()
cur.execute("""
    SELECT r.id, r.race_date
    FROM races r
    WHERE r.race_date LIKE '2020%'
    AND r.id NOT IN (
        SELECT DISTINCT rp.race_id
        FROM race_predictions rp
        WHERE rp.prediction_type = 'before'
    )
    ORDER BY r.race_date
    LIMIT 3
""")
test_races = cur.fetchall()
conn.close()

print(f"テスト対象レース: {test_races}")

print("\nPredictor初期化...")
start = datetime.now()
predictor = create_standard_predictor()
print(f"初期化完了 ({(datetime.now()-start).total_seconds():.1f}秒)")

print("\n予想生成テスト:")
for race_id, race_date in test_races:
    print(f"\nレース {race_id} ({race_date})")
    try:
        result = predictor.predict_race(race_id, use_beforeinfo=True)
        if result:
            print(f"  成功: {len(result)}件の予想")
        else:
            print(f"  失敗: 空のリスト")
    except Exception as e:
        print(f"  例外: {type(e).__name__}: {e}")
        traceback.print_exc()
