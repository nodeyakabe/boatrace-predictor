import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# ST 5/6のレースを確認
cursor.execute('''
    SELECT r.venue_code, r.race_date, r.race_number,
           COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-12-31'
    GROUP BY r.id
    HAVING st_count = 5
    ORDER BY r.race_date DESC
    LIMIT 10
''')

print('最近のST 5/6レース（2024年）:')
for row in cursor.fetchall():
    print(f'  会場{row[0]} {row[1]} {row[2]}R - ST:{row[3]}/6')

# ST時間のカバー率
cursor.execute('''
    SELECT
        COUNT(CASE WHEN st_count = 6 THEN 1 END) as st_6,
        COUNT(CASE WHEN st_count = 5 THEN 1 END) as st_5,
        COUNT(CASE WHEN st_count < 5 THEN 1 END) as st_less,
        COUNT(*) as total
    FROM (
        SELECT r.id,
               COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-12-31'
        GROUP BY r.id
    )
''')

st_6, st_5, st_less, total = cursor.fetchone()
print(f'\n2024年のST時間カバー状況:')
print(f'  ST 6/6: {st_6} ({st_6/total*100:.1f}%)')
print(f'  ST 5/6: {st_5} ({st_5/total*100:.1f}%)')
print(f'  ST <5: {st_less} ({st_less/total*100:.1f}%)')
print(f'  総レース数: {total}')

conn.close()
