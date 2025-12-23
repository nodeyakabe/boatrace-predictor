# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / 'data' / 'boatrace.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 年別のレース数
cur.execute("""
    SELECT SUBSTR(race_date, 1, 4) as year, COUNT(*) as count
    FROM races
    GROUP BY year
    ORDER BY year
""")

print("年別レース数:")
for row in cur.fetchall():
    print(f"  {row[0]}年: {row[1]}レース")

# 年別の信頼度B予測数
cur.execute("""
    SELECT SUBSTR(r.race_date, 1, 4) as year, COUNT(*) as count
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    WHERE rp.confidence = 'B'
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
    GROUP BY year
    ORDER BY year
""")

print("\n年別信頼度B予測数:")
for row in cur.fetchall():
    print(f"  {row[0]}年: {row[1]}件")

conn.close()
