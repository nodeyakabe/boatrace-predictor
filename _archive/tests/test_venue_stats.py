"""会場統計データのテスト"""
import sys
sys.path.append('src')
import sqlite3
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# 桐生のコース別1着率を計算（過去90日）
print("桐生（過去90日）のコース別1着率:")
cursor.execute("""
    SELECT
        rd.actual_course as course,
        COUNT(CASE WHEN r2.rank = '1' THEN 1 END) as wins,
        COUNT(*) as total,
        ROUND(COUNT(CASE WHEN r2.rank = '1' THEN 1 END) * 100.0 / COUNT(*), 1) as win_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    LEFT JOIN results r2 ON r.id = r2.race_id AND rd.pit_number = r2.pit_number
    WHERE r.venue_code = '01'
    AND r.race_date >= date('now', '-90 days')
    AND rd.actual_course IS NOT NULL
    GROUP BY rd.actual_course
    ORDER BY rd.actual_course
""")

results = cursor.fetchall()
if results:
    for row in results:
        print(f"  {row[0]}コース: {row[3]}% ({row[1]}勝/{row[2]}レース)")
else:
    print("  データなし")

# 桐生の決まり手パターン（1コース、過去90日）
print("\n桐生（過去90日）の1コース決まり手:")
cursor.execute("""
    SELECT
        r2.kimarite,
        COUNT(*) as count
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results r2 ON r.id = r2.race_id AND rd.pit_number = r2.pit_number
    WHERE r.venue_code = '01'
    AND r.race_date >= date('now', '-90 days')
    AND rd.actual_course = 1
    AND r2.rank = '1'
    AND r2.kimarite IS NOT NULL
    GROUP BY r2.kimarite
    ORDER BY count DESC
""")

results = cursor.fetchall()
if results:
    total = sum(row[1] for row in results)
    for row in results:
        pct = row[1] * 100.0 / total
        print(f"  {row[0]}: {row[1]}回 ({pct:.1f}%)")
else:
    print("  データなし")

conn.close()
