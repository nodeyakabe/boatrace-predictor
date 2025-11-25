import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT r.id, r.venue_code, r.race_date, r.race_number,
           COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date = '2025-11-04' AND r.venue_code = '01' AND r.race_number <= 3
    GROUP BY r.id
    ORDER BY r.race_number
''')

print('2025-11-04 桐生 1-3R ST時間状況:')
for row in cursor.fetchall():
    status = 'OK' if row[4] == 6 else 'NG'
    print(f'  {row[3]}R: ST {row[4]}/6 [{status}]')

conn.close()
