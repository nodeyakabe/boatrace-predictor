"""
racesテーブルのスキーマ確認
"""
import sqlite3
import pandas as pd

DB_PATH = r'c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db'

conn = sqlite3.connect(DB_PATH)

print("=" * 80)
print("【racesテーブル スキーマ】")
print("=" * 80)
schema = pd.read_sql_query("PRAGMA table_info(races)", conn)
print(schema.to_string(index=False))
print()

# サンプルデータ
print("=" * 80)
print("【該当2レースのracesテーブルデータ】")
print("=" * 80)
for race_id in [169834, 169274]:
    data = pd.read_sql_query(f"SELECT * FROM races WHERE id = '{race_id}'", conn)
    print(f"\nrace_id={race_id}:")
    print(data.T)  # 転置して見やすく
    print()

conn.close()
