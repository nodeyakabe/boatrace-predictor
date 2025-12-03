"""race_detailsテーブルの詳細確認"""
import sqlite3

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

# テーブル構造確認
cursor.execute("PRAGMA table_info(race_details)")
columns = cursor.fetchall()

print("=" * 80)
print("race_detailsテーブル構造")
print("=" * 80)
for col in columns:
    print(f"{col[1]} ({col[2]})")
print()

# サンプルデータ
cursor.execute("SELECT * FROM race_details LIMIT 3")
rows = cursor.fetchall()
print("サンプルデータ:")
for row in rows:
    print(row)
print()

# 総レース数
cursor.execute("SELECT COUNT(*) FROM races")
total_races = cursor.fetchone()[0]

# race_detailsのrace_id別レコード数
cursor.execute("SELECT COUNT(DISTINCT race_id) FROM race_details")
distinct_races = cursor.fetchone()[0]

# ST時間がNULLでないレース数
cursor.execute("""
    SELECT COUNT(DISTINCT race_id)
    FROM race_details
    WHERE st_time IS NOT NULL
""")
races_with_st = cursor.fetchone()[0]

# actual_courseがNULLでないレース数
cursor.execute("""
    SELECT COUNT(DISTINCT race_id)
    FROM race_details
    WHERE actual_course IS NOT NULL
""")
races_with_course = cursor.fetchone()[0]

conn.close()

print("=" * 80)
print("データ状況サマリー")
print("=" * 80)
print(f"総レース数: {total_races:,}")
print(f"race_detailsに存在する異なるrace_id: {distinct_races:,}")
print(f"ST時間データがあるレース数: {races_with_st:,} ({races_with_st/total_races*100:.1f}%)")
print(f"実際のコースデータがあるレース数: {races_with_course:,} ({races_with_course/total_races*100:.1f}%)")
print()

# 欠損レース数
missing_st = total_races - races_with_st
missing_course = total_races - races_with_course

print(f"ST時間欠損レース: {missing_st:,}件")
print(f"実際のコース欠損レース: {missing_course:,}件")
print("=" * 80)
