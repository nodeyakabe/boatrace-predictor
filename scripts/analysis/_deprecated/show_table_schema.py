"""
racer_venue_featuresテーブルのスキーマ確認
"""

import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# テーブル一覧
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%venue%' OR name LIKE '%racer%' ORDER BY name")
tables = cursor.fetchall()
print("関連テーブル一覧:")
for table in tables:
    print(f"  - {table[0]}")
print()

# racer_venue_featuresのスキーマ
print("racer_venue_features テーブルスキーマ:")
cursor.execute("PRAGMA table_info(racer_venue_features)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]:<30} {col[2]:<15} (NULL: {col[3] == 0})")
print()

# サンプルデータ
print("サンプルデータ（3件）:")
cursor.execute("SELECT * FROM racer_venue_features LIMIT 3")
rows = cursor.fetchall()
if rows:
    cursor.execute("PRAGMA table_info(racer_venue_features)")
    headers = [col[1] for col in cursor.fetchall()]
    print(" | ".join(headers))
    print("-" * 100)
    for row in rows:
        print(" | ".join(str(x) if x is not None else "NULL" for x in row))

conn.close()
