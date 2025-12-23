# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / 'data' / 'boatrace.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 予測タイプ別・信頼度別件数
cur.execute("""
    SELECT prediction_type, confidence, COUNT(*) as count
    FROM race_predictions
    GROUP BY prediction_type, confidence
    ORDER BY prediction_type, confidence
""")

print("予測タイプ別・信頼度別件数:")
for row in cur.fetchall():
    print(f"  {row[0]:10s} / {row[1]}: {row[2]:8d}件")

# before予測の信頼度B（年別）
cur.execute("""
    SELECT SUBSTR(r.race_date, 1, 4) as year, COUNT(*) as count
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    WHERE rp.prediction_type = 'before'
        AND rp.confidence = 'B'
        AND rp.rank_prediction = 1
    GROUP BY year
    ORDER BY year
""")

print("\nBEFORE予測（信頼度B）の年別件数:")
for row in cur.fetchall():
    print(f"  {row[0]}年: {row[1]:8d}件")

# 2025年のbefore予測データ範囲
cur.execute("""
    SELECT MIN(r.race_date), MAX(r.race_date), COUNT(*) as count
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id
    WHERE rp.prediction_type = 'before'
        AND rp.confidence = 'B'
        AND rp.rank_prediction = 1
        AND r.race_date >= '2025-01-01'
""")

result = cur.fetchone()
if result[2] > 0:
    print(f"\n2025年BEFORE予測（信頼度B）:")
    print(f"  期間: {result[0]} - {result[1]}")
    print(f"  件数: {result[2]}件")
else:
    print("\n2025年BEFORE予測（信頼度B）: データなし")

conn.close()
