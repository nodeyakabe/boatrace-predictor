import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 2024年12月のデータ確認
cursor.execute('''
    SELECT COUNT(*) FROM races
    WHERE race_date >= '2024-12-01' AND race_date <= '2024-12-31'
''')
total = cursor.fetchone()[0]

cursor.execute('''
    SELECT COUNT(*) FROM (
        SELECT r.id FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2024-12-01' AND r.race_date <= '2024-12-31'
        GROUP BY r.id
        HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) = 6
    )
''')
complete = cursor.fetchone()[0]

cursor.execute('''
    SELECT COUNT(*) FROM (
        SELECT r.id FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2024-12-01' AND r.race_date <= '2024-12-31'
        GROUP BY r.id
        HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) = 5
    )
''')
before_incomplete = cursor.fetchone()[0]

print('=== 2024年12月のST時間データ ===')
print(f'総レース: {total}')
print(f'ST 6/6（完全）: {complete} ({complete/total*100:.1f}%)')
print(f'ST 5/6（最適化前）: {before_incomplete}')
print()

# テストで処理した30レースの状態を確認
cursor.execute('''
    SELECT r.race_date, r.venue_code, r.race_number,
           COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2024-12-01' AND r.race_date <= '2024-12-03'
    GROUP BY r.id
    ORDER BY r.race_date, r.venue_code, r.race_number
    LIMIT 30
''')

test_races = cursor.fetchall()
print(f'テスト対象範囲（12/1-12/3）の最初の30レース:')
complete_count = 0
for race in test_races:
    status = 'OK' if race[3] == 6 else f'{race[3]}/6'
    venue = int(race[1]) if race[1] else 0
    race_num = int(race[2]) if race[2] else 0
    print(f'  {race[0]} 会場{venue:02d} {race_num:2d}R: ST {status}')
    if race[3] == 6:
        complete_count += 1

print(f'\n完全データ: {complete_count}/30 ({complete_count/30*100:.0f}%)')

conn.close()
