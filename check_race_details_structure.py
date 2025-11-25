"""
race_detailsテーブルの構造を確認
"""

import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print("=" * 70)
print("race_detailsテーブルの構造")
print("=" * 70)

cursor.execute("PRAGMA table_info(race_details)")
columns = cursor.fetchall()

print("\nカラム一覧:")
for col in columns:
    col_id, name, col_type, not_null, default, pk = col
    print(f"  {name:30} {col_type:15} {'NOT NULL' if not_null else ''} {'PRIMARY KEY' if pk else ''}")

conn.close()
print("\n" + "=" * 70)
