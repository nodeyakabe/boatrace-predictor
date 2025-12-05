import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

cursor.execute('''
    SELECT r.id, r.venue_code, r.race_date, r.race_number,
           COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= ?
    GROUP BY r.id
    HAVING st_count = 5
    LIMIT 5
''', (yesterday,))

print(f'{yesterday}以降のST 5/6レース:')
for row in cursor.fetchall():
    print(f'  会場{row[1]} {row[2]} {row[3]}R - ST:{row[4]}/6')

conn.close()
