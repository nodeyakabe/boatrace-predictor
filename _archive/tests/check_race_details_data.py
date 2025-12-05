"""
race_detailsのデータ確認
"""

import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

race_id = 132764  # デバッグで使用したレースID

print("=" * 80)
print(f"race_details データ確認 (race_id: {race_id})")
print("=" * 80)
print()

cursor.execute("""
    SELECT
        pit_number,
        exhibition_time,
        st_time,
        exhibition_course,
        tilt_angle,
        adjusted_weight,
        parts_replacement,
        prev_race_st,
        prev_race_rank
    FROM race_details
    WHERE race_id = ?
    ORDER BY pit_number
""", (race_id,))

rows = cursor.fetchall()

if not rows:
    print("データなし！")
else:
    print(f"データ件数: {len(rows)}艇")
    print()
    print("艇  | 展示タイム | ST    | 展示コース | チルト | 重量 | 部品 | 前ST  | 前着 |")
    print("-" * 80)
    for row in rows:
        pit, ex_time, st, ex_course, tilt, weight, parts, prev_st, prev_rank = row
        print(f"{pit:2d}  | {ex_time or 'None':10} | {st or 'None':5} | {ex_course or 'None':10} | {tilt or 'None':6} | {weight or 'None':4} | {parts or '-':4} | {prev_st or 'None':5} | {prev_rank or 'None':4} |")

print()
print("=" * 80)

# 追加で: is_published の確認 (もしraces テーブルにあれば)
cursor.execute("PRAGMA table_info(races)")
race_columns = [col[1] for col in cursor.fetchall()]
print(f"races テーブルのカラム数: {len(race_columns)}")
if 'is_published' in race_columns:
    cursor.execute("SELECT is_published FROM races WHERE id = ?", (race_id,))
    is_pub = cursor.fetchone()
    print(f"is_published: {is_pub[0] if is_pub else 'カラムなし'}")
else:
    print("is_published カラムは races テーブルに存在しません")

conn.close()
