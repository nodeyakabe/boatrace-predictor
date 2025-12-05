import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 最近1ヶ月のST 5/6レースを確認
one_month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
print(f'過去30日間のST 5/6レース: ({one_month_ago}以降)')

cursor.execute('''
    SELECT r.venue_code, r.race_date, r.race_number,
           COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= ?
    GROUP BY r.id
    HAVING st_count = 5
    ORDER BY r.race_date DESC
    LIMIT 20
''', (one_month_ago,))

results = cursor.fetchall()
print(f'  該当レース数: {len(results)}')
if results:
    print('\n  最初の10件:')
    for row in results[:10]:
        print(f'    会場{row[0]} {row[1]} {row[2]}R - ST:{row[3]}/6')

conn.close()
