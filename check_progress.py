"""
データ取得の進行状況確認スクリプト
"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/boatrace_readonly.db')
cursor = conn.cursor()

print("="*70)
print("【データ取得進行状況】")
print("="*70)
print(f"確認時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# レース数
cursor.execute('SELECT COUNT(*) FROM races')
total_races = cursor.fetchone()[0]
print(f"総レース数: {total_races:,}件")

# 展示タイム
cursor.execute('SELECT COUNT(*) FROM race_details WHERE exhibition_time IS NOT NULL')
total_exhibition = cursor.fetchone()[0]
print(f"展示タイム: {total_exhibition:,}件")

# 進入コース
cursor.execute('SELECT COUNT(*) FROM race_details WHERE actual_course IS NOT NULL')
total_courses = cursor.fetchone()[0]
print(f"進入コース: {total_courses:,}件")

# 日数
cursor.execute('SELECT COUNT(DISTINCT race_date) FROM races')
day_count = cursor.fetchone()[0]
print(f"処理済み日数: {day_count}日")

# 競艇場数
cursor.execute('SELECT COUNT(DISTINCT venue_code) FROM races')
venue_count = cursor.fetchone()[0]
print(f"処理済み競艇場: {venue_count}場")

# 最新の処理日時
cursor.execute('SELECT MAX(race_date) FROM races')
latest_date = cursor.fetchone()[0]
print(f"最新処理日: {latest_date}")

# 競艇場別の状況
print()
print("-"*70)
print("【競艇場別レース数】")
cursor.execute('''
    SELECT venue_code, COUNT(*) as race_count
    FROM races
    GROUP BY venue_code
    ORDER BY venue_code
''')
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:,}レース")

conn.close()

print("="*70)
