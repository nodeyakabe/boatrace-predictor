# -*- coding: utf-8 -*-
"""データベース構造確認スクリプト"""

import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
db_path = ROOT_DIR / "data" / "boatrace.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 70)
print("race_predictions テーブル構造")
print("=" * 70)

# テーブル構造
cursor.execute("PRAGMA table_info(race_predictions)")
columns = cursor.fetchall()
for col in columns:
    print(f"{col['name']}: {col['type']}")

print()
print("=" * 70)
print("信頼度別レース数（2024年1-11月）")
print("=" * 70)

# 信頼度別レース数
cursor.execute('''
    SELECT
        p.confidence,
        COUNT(DISTINCT p.race_id) as race_count
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-11-30'
      AND p.prediction_type = 'advance'
    GROUP BY p.confidence
    ORDER BY p.confidence
''')

results = cursor.fetchall()
for row in results:
    print(f"信頼度{row['confidence']}: {row['race_count']}レース")

print()
print("=" * 70)
print("信頼度D × 会場別レース数（2024年1-11月）")
print("=" * 70)

cursor.execute('''
    SELECT
        r.venue_code,
        COUNT(DISTINCT p.race_id) as race_count
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-11-30'
      AND p.prediction_type = 'advance'
      AND p.confidence = 'D'
    GROUP BY r.venue_code
    ORDER BY race_count DESC
    LIMIT 10
''')

results = cursor.fetchall()
for row in results:
    print(f"会場{row['venue_code']}: {row['race_count']}レース")

print()
print("=" * 70)
print("イン強会場（24,19,18）のレース数")
print("=" * 70)

cursor.execute('''
    SELECT
        r.venue_code,
        COUNT(DISTINCT p.race_id) as race_count,
        SUM(CASE WHEN p.confidence = 'D' THEN 1 ELSE 0 END) as d_count
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-11-30'
      AND p.prediction_type = 'advance'
      AND r.venue_code IN (24, 19, 18)
    GROUP BY r.venue_code
''')

results = cursor.fetchall()
venue_names = {24: '大村', 19: '下関', 18: '徳山'}
for row in results:
    venue_name = venue_names.get(row['venue_code'], str(row['venue_code']))
    print(f"{venue_name}({row['venue_code']}): 全{row['race_count']}レース, 信頼度D: {row['d_count']}レース")

print()
print("=" * 70)
print("race_predictionsのサンプルデータ（信頼度D, イン強会場）")
print("=" * 70)

cursor.execute('''
    SELECT
        r.race_date,
        r.venue_code,
        r.race_number,
        p.confidence,
        p.rank_prediction,
        p.pit_number
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-11-30'
      AND p.prediction_type = 'advance'
      AND p.confidence = 'D'
      AND r.venue_code IN (24, 19, 18)
    ORDER BY r.race_date, r.venue_code, r.race_number, p.rank_prediction
    LIMIT 20
''')

results = cursor.fetchall()
for row in results:
    print(f"{row['race_date']} 会場{row['venue_code']} R{row['race_number']} "
          f"信頼度{row['confidence']} {row['rank_prediction']}位予測={row['pit_number']}号艇")

conn.close()
