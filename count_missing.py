"""
欠損データ数を確認
"""

import sqlite3

db_path = "data/boatrace.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

query = """
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
      AND (rd.race_id IS NULL
           OR rd.exhibition_time IS NULL
           OR rd.st_time IS NULL
           OR rd.actual_course IS NULL)
"""

cursor.execute(query)
count = cursor.fetchone()[0]

print(f"Missing data count (2015-2021): {count} races")

# 推定時間
est_time_per_race = 15  # seconds
est_total_seconds = count * est_time_per_race
est_hours = est_total_seconds / 3600

print(f"Estimated time (sequential): {est_hours:.1f} hours")

# 並列処理での推定
workers = 5
est_parallel_hours = est_hours / workers
print(f"Estimated time (5 workers): {est_parallel_hours:.1f} hours")

conn.close()
