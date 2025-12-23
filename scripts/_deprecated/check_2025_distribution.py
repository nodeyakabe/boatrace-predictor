# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / 'data' / 'boatrace.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 2025年BEFORE予測の月別分布
cur.execute("""
    SELECT SUBSTR(r.race_date, 6, 2) as month, COUNT(*) as count
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    WHERE rp.prediction_type = 'before'
        AND rp.confidence = 'B'
        AND rp.rank_prediction = 1
        AND r.race_date >= '2025-01-01'
    GROUP BY month
    ORDER BY month
""")

print("2025年BEFORE予測（信頼度B）の月別分布:")
total = 0
for row in cur.fetchall():
    print(f"  {row[0]}月: {row[1]:4d}件")
    total += row[1]
print(f"  合計: {total}件")

# 会場別分布（フィルター除外会場を含む）
cur.execute("""
    SELECT r.venue_code, COUNT(*) as count
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    WHERE rp.prediction_type = 'before'
        AND rp.confidence = 'B'
        AND rp.rank_prediction = 1
        AND r.race_date >= '2025-01-01'
    GROUP BY r.venue_code
    ORDER BY r.venue_code
""")

print("\n2025年BEFORE予測（信頼度B）の会場別分布:")
excluded_venues = [2, 3, 4, 14]  # 戸田、江戸川、平和島、鳴門
for row in cur.fetchall():
    marker = " [除外対象]" if row[0] in excluded_venues else ""
    print(f"  会場{row[0]:2d}: {row[1]:4d}件{marker}")

conn.close()
