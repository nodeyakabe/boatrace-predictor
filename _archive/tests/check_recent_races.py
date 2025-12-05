"""
最近保存されたレースデータを確認
"""

import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print("=" * 70)
print("最近のレースデータを確認")
print("=" * 70)

# 最新10件のレースを取得
query = """
SELECT id, venue_code, race_date, race_number, race_time
FROM races
ORDER BY id DESC
LIMIT 20
"""

cursor.execute(query)
results = cursor.fetchall()

print("\n最近保存されたレース (新しい順):")
for race_id, venue, date, num, time in results:
    print(f"  ID={race_id}: {venue}_{date}_R{num} ({time})")

# 2025-11-13のデータがあるか確認
print("\n" + "=" * 70)
print("2025-11-13のレースデータ確認")
print("=" * 70)

query = """
SELECT venue_code, race_number, race_time
FROM races
WHERE race_date = '20251113'
ORDER BY venue_code, race_number
"""

cursor.execute(query)
results = cursor.fetchall()

if results:
    print(f"\n見つかりました: {len(results)}レース")
    for venue, num, time in results:
        print(f"  {venue}_{num}R ({time})")
else:
    print("\n2025-11-13のデータは見つかりませんでした")

conn.close()
