"""レース結果データの確認（修正版）"""
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

# 最新のレース日付
cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
date_range = cursor.fetchone()
print(f"レース期間: {date_range[0]} ~ {date_range[1]}")

# 会場別レース数
print("\n会場別レース数（TOP5）:")
cursor.execute("""
    SELECT v.name, COUNT(*) as count
    FROM races r
    JOIN venues v ON r.venue_code = v.code
    GROUP BY v.name
    ORDER BY count DESC
    LIMIT 5
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}レース")

# レース詳細データ
print("\nレース詳細データ:")
cursor.execute("SELECT COUNT(*) FROM race_details")
total_details = cursor.fetchone()[0]
print(f"  総race_details: {total_details}行")

cursor.execute("SELECT COUNT(*) FROM race_details WHERE finish_position = 1")
first_place_count = cursor.fetchone()[0]
print(f"  1着データ: {first_place_count}件")

# 決まり手データ
cursor.execute("SELECT COUNT(*) FROM race_details WHERE kimarite IS NOT NULL AND kimarite != ''")
kimarite_count = cursor.fetchone()[0]
print(f"  決まり手データ: {kimarite_count}件")

# 桐生の実績データ例
print("\n桐生（会場コード01）の最近の1着データ:")
cursor.execute("""
    SELECT r.race_date, r.race_number, rd.pit_number, rd.kimarite
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE r.venue_code = '01' AND rd.finish_position = 1
    ORDER BY r.race_date DESC
    LIMIT 5
""")
results = cursor.fetchall()
if results:
    for row in results:
        print(f"  {row[0]} R{row[1]} {row[2]}号艇 決まり手:{row[3]}")
else:
    print("  実績データなし")

# VenueAnalyzerが使うデータを確認
print("\nVenueAnalyzerで使用するデータ:")
cursor.execute("""
    SELECT
        COUNT(DISTINCT r.id) as race_count,
        COUNT(CASE WHEN rd.finish_position = 1 THEN 1 END) as first_place_count
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE r.venue_code = '01'
    AND r.race_date >= date('now', '-90 days')
""")
row = cursor.fetchone()
print(f"  桐生（過去90日）: {row[0]}レース, 1着データ{row[1]}件")

conn.close()
