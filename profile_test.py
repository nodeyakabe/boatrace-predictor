"""
プロファイリングテスト - どの処理が遅いか特定
"""
import sqlite3
import time
from src.analysis.race_predictor import RacePredictor

# 最新1レース取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
cursor.execute("""
    SELECT DISTINCT r.id FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id
    WHERE rd.exhibition_course IS NOT NULL
    AND res.rank IS NOT NULL
    AND res.is_invalid = 0
    ORDER BY r.race_date DESC, r.id DESC
    LIMIT 1
""")
race_id = cursor.fetchone()[0]
conn.close()

print(f"プロファイリング対象: レースID {race_id}")
print("=" * 60)

# 初期化
start = time.time()
predictor = RacePredictor(db_path='data/boatrace.db')
print(f"初期化: {time.time() - start:.2f}秒")

# 予測実行（内部でタイム計測）
import cProfile
import pstats
from io import StringIO

profiler = cProfile.Profile()
profiler.enable()

predictions = predictor.predict_race(race_id)

profiler.disable()

# 結果表示
s = StringIO()
stats = pstats.Stats(profiler, stream=s)
stats.sort_stats('cumulative')
stats.print_stats(30)  # 上位30関数

print("\n【最も時間がかかっている処理（上位30）】")
print(s.getvalue())
