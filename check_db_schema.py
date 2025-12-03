"""
データベーススキーマ確認スクリプト
"""

import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print("=" * 80)
print("データベーススキーマ確認")
print("=" * 80)
print()

# race_detailsテーブルのカラム一覧
print("【race_detailsテーブル】")
cursor.execute("PRAGMA table_info(race_details)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]:30s} {col[2]:15s} {'NOT NULL' if col[3] else ''}")
print()

# racesテーブルのカラム一覧
print("【racesテーブル】")
cursor.execute("PRAGMA table_info(races)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]:30s} {col[2]:15s} {'NOT NULL' if col[3] else ''}")
print()

# データの期間を確認
print("【データ期間】")
cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
min_date, max_date = cursor.fetchone()
print(f"  最古: {min_date}")
print(f"  最新: {max_date}")
print()

# 結果データのある期間
print("【結果データのある期間】")
cursor.execute("""
    SELECT MIN(r.race_date), MAX(r.race_date), COUNT(DISTINCT r.id)
    FROM races r
    JOIN results res ON r.id = res.race_id
    WHERE res.rank IS NOT NULL AND res.is_invalid = 0
""")
min_date, max_date, race_count = cursor.fetchone()
print(f"  最古: {min_date}")
print(f"  最新: {max_date}")
print(f"  総レース数: {race_count}")
print()

# 直前情報のある期間
print("【race_detailsデータのある期間】")
cursor.execute("""
    SELECT MIN(r.race_date), MAX(r.race_date), COUNT(DISTINCT r.id)
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE rd.exhibition_course IS NOT NULL
""")
min_date, max_date, race_count = cursor.fetchone()
print(f"  最古: {min_date}")
print(f"  最新: {max_date}")
print(f"  総レース数: {race_count}")
print()

# 両方揃っているレース
print("【race_details + results 両方あるレース】")
cursor.execute("""
    SELECT MIN(r.race_date), MAX(r.race_date), COUNT(DISTINCT r.id)
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id
    WHERE rd.exhibition_course IS NOT NULL
    AND res.rank IS NOT NULL AND res.is_invalid = 0
""")
min_date, max_date, race_count = cursor.fetchone()
print(f"  最古: {min_date}")
print(f"  最新: {max_date}")
print(f"  総レース数: {race_count}")
print()

conn.close()

print("=" * 80)
