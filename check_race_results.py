"""レース結果データの確認"""
import sys
sys.path.append('src')
import sqlite3
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# レース総数
cursor.execute("SELECT COUNT(*) FROM races")
total_races = cursor.fetchone()[0]
print(f"総レース数: {total_races}")

# 結果データがあるレース数
cursor.execute("SELECT COUNT(*) FROM races WHERE result_time IS NOT NULL")
races_with_results = cursor.fetchone()[0]
print(f"結果データありレース: {races_with_results}")

# 最新のレース日付
cursor.execute("SELECT MAX(race_date) FROM races")
latest_date = cursor.fetchone()[0]
print(f"最新レース日: {latest_date}")

# 会場別レース数
print("\n会場別レース数（TOP10）:")
cursor.execute("""
    SELECT v.name, COUNT(*) as count
    FROM races r
    JOIN venues v ON r.venue_code = v.code
    GROUP BY v.name
    ORDER BY count DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}レース")

# コース別勝率計算に必要なデータ
print("\nレース詳細データ:")
cursor.execute("SELECT COUNT(*) FROM race_details")
total_details = cursor.fetchone()[0]
print(f"  総レース詳細: {total_details}行")

cursor.execute("SELECT COUNT(*) FROM race_details WHERE finish_position = 1")
first_place_count = cursor.fetchone()[0]
print(f"  1着データ: {first_place_count}件")

# 決まり手データ
cursor.execute("SELECT COUNT(*) FROM race_details WHERE kimarite IS NOT NULL")
kimarite_count = cursor.fetchone()[0]
print(f"  決まり手データ: {kimarite_count}件")

# 桐生の実績データ例
print("\n桐生（会場コード01）の実績データ:")
cursor.execute("""
    SELECT r.race_date, r.race_number, rd.pit_number, rd.finish_position, rd.kimarite
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE r.venue_code = '01' AND rd.finish_position = 1
    ORDER BY r.race_date DESC
    LIMIT 5
""")
results = cursor.fetchall()
if results:
    for row in results:
        print(f"  {row[0]} R{row[1]} {row[2]}号艇 1着 決まり手:{row[4]}")
else:
    print("  実績データなし")

conn.close()
