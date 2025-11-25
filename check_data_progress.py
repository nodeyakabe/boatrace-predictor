"""
データ取得の進捗状況を確認
"""

import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/boatrace_readonly.db')
cursor = conn.cursor()

print("=" * 70)
print("データ取得進捗確認")
print("=" * 70)

# 基本情報
cursor.execute('SELECT COUNT(*) FROM races')
race_count = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM results')
result_count = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM entries')
entry_count = cursor.fetchone()[0]

print(f"\n【データ件数】")
print(f"  レース数: {race_count}")
print(f"  エントリー数: {entry_count}")
print(f"  結果データ数: {result_count}")

# 日付別の集計
cursor.execute("""
    SELECT race_date, COUNT(*) as cnt
    FROM races
    GROUP BY race_date
    ORDER BY race_date DESC
    LIMIT 10
""")

print(f"\n【最近の取得日付】")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}レース")

# 結果データの状況
if result_count > 0:
    cursor.execute("""
        SELECT r.race_date, COUNT(DISTINCT res.race_id) as race_with_results
        FROM races r
        LEFT JOIN results res ON r.id = res.race_id
        WHERE res.race_id IS NOT NULL
        GROUP BY r.race_date
        ORDER BY r.race_date DESC
        LIMIT 10
    """)

    print(f"\n【結果データが保存されている日付】")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}レース")
else:
    print(f"\n【結果データ】まだ保存されていません")

# 競艇場別
cursor.execute("""
    SELECT v.name, COUNT(r.id) as race_count
    FROM venues v
    LEFT JOIN races r ON v.code = r.venue_code
    GROUP BY v.code
    ORDER BY race_count DESC
""")

print(f"\n【競艇場別レース数】")
for row in cursor.fetchall():
    venue_name = row[0] if row[0] else "不明"
    print(f"  {venue_name}: {row[1]}レース")

conn.close()

print("=" * 70)
