"""レース詳細補完の進捗確認"""
import sqlite3
import time

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

# 総レース数
cursor.execute("SELECT COUNT(*) FROM races")
total_races = cursor.fetchone()[0]

# race_detailsテーブルの状況
cursor.execute("""
    SELECT
        COUNT(*) as total_records,
        COUNT(CASE WHEN st_time IS NOT NULL THEN 1 END) as with_st_time,
        COUNT(CASE WHEN actual_course IS NOT NULL THEN 1 END) as with_actual_course
    FROM race_details
""")

row = cursor.fetchone()
total_records, with_st_time, with_actual_course = row

conn.close()

print("=" * 80)
print("レース詳細補完の進捗状況")
print("=" * 80)
print(f"総レース数: {total_races:,}")
print(f"race_detailsレコード数: {total_records:,}")
print(f"ST時間データあり: {with_st_time:,} ({with_st_time/total_races*100:.1f}%)")
print(f"実際のコースデータあり: {with_actual_course:,} ({with_actual_course/total_races*100:.1f}%)")
print()

# 欠損数
missing = total_races - with_st_time
print(f"残り欠損数: {missing:,}件")

# 前回の状況（71.1%完了時点で227,681件欠損）
previous_missing = 227681
processed_since_last = previous_missing - missing

if processed_since_last > 0:
    print(f"前回チェックから処理済み: {processed_since_last:,}件")

print("=" * 80)
