import sqlite3
from collections import defaultdict

# データベース接続
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print("=" * 60)
print("データベース状態確認")
print("=" * 60)

# レコード数確認
cursor.execute('SELECT COUNT(*) FROM races')
print(f"\nレース数: {cursor.fetchone()[0]:,}")

cursor.execute('SELECT COUNT(*) FROM entries')
print(f"出走表数: {cursor.fetchone()[0]:,}")

cursor.execute('SELECT COUNT(*) FROM results')
print(f"結果数: {cursor.fetchone()[0]:,}")

cursor.execute('SELECT COUNT(*) FROM race_details')
print(f"レース詳細数: {cursor.fetchone()[0]:,}")

cursor.execute('SELECT COUNT(*) FROM weather')
print(f"天気データ数: {cursor.fetchone()[0]:,}")

# 月別データ
print("\n" + "=" * 60)
print("月別レース数")
print("=" * 60)
cursor.execute('''
    SELECT substr(race_date, 1, 7) as month, COUNT(*)
    FROM races
    GROUP BY month
    ORDER BY month DESC
''')
monthly_data = cursor.fetchall()
for month, count in monthly_data[:12]:
    print(f"{month}: {count:,}レース")

# 最新データ
print("\n" + "=" * 60)
print("最近のデータ (最新20日)")
print("=" * 60)
cursor.execute('''
    SELECT race_date, COUNT(*)
    FROM races
    GROUP BY race_date
    ORDER BY race_date DESC
    LIMIT 20
''')
recent_data = cursor.fetchall()
for date, count in recent_data:
    print(f"{date}: {count}レース")

# 競艇場別データ
print("\n" + "=" * 60)
print("競艇場別レース数")
print("=" * 60)
cursor.execute('''
    SELECT v.name, COUNT(r.id)
    FROM races r
    JOIN venues v ON r.venue_code = v.code
    GROUP BY v.name
    ORDER BY COUNT(r.id) DESC
''')
venue_data = cursor.fetchall()
for venue, count in venue_data:
    print(f"{venue}: {count:,}レース")

conn.close()
print("\n" + "=" * 60)
print("確認完了")
print("=" * 60)
