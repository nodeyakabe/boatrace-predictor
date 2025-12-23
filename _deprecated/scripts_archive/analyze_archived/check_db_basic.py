# -*- coding: utf-8 -*-
"""データベース基本情報確認"""

import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
db_path = ROOT_DIR / "data" / "boatrace.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 70)
print("テーブル一覧")
print("=" * 70)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
for table in tables:
    print(f"- {table['name']}")

print()
print("=" * 70)
print("races テーブルのデータ件数")
print("=" * 70)
cursor.execute("SELECT COUNT(*) as count FROM races")
print(f"総レース数: {cursor.fetchone()['count']}")

cursor.execute("SELECT MIN(race_date) as min, MAX(race_date) as max FROM races")
result = cursor.fetchone()
print(f"期間: {result['min']} 〜 {result['max']}")

print()
print("=" * 70)
print("race_predictions テーブルのデータ件数")
print("=" * 70)
cursor.execute("SELECT COUNT(*) as count FROM race_predictions")
print(f"総予測数: {cursor.fetchone()['count']}")

cursor.execute('''
    SELECT prediction_type, COUNT(*) as count
    FROM race_predictions
    GROUP BY prediction_type
''')
for row in cursor.fetchall():
    print(f"- {row['prediction_type']}: {row['count']}")

cursor.execute('''
    SELECT COUNT(DISTINCT race_id) as count
    FROM race_predictions
''')
print(f"予測があるレース数: {cursor.fetchone()['count']}")

conn.close()
