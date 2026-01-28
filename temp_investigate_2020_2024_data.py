"""
2020-2024年レース詳細データ状況調査
"""
import sqlite3

db_path = 'data/boatrace.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 80)
print('2020-2024年レース詳細データ状況調査')
print('=' * 80)
print()

# 年度別の状況
cursor.execute('''
    SELECT
        substr(r.race_date, 1, 4) as year,
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT res.race_id) as with_result,
        COUNT(DISTINCT rd.race_id) as with_details,
        COUNT(DISTINCT CASE WHEN rd.chikusen_time IS NOT NULL THEN rd.race_id END) as with_chikusen,
        COUNT(DISTINCT CASE WHEN rd.st_time IS NOT NULL THEN rd.race_id END) as with_st,
        COUNT(DISTINCT CASE WHEN rc.wave_height IS NOT NULL THEN rc.race_id END) as with_wave
    FROM races r
    LEFT JOIN results res ON r.id = res.race_id
    LEFT JOIN race_details rd ON r.id = rd.race_id
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2025-01-01'
    GROUP BY substr(r.race_date, 1, 4)
    ORDER BY year
''')

print('年度別データ状況:')
print('-' * 80)
print(f'{"年度":<6} {"レース数":>10} {"結果":>8} {"詳細":>8} {"展示T":>8} {"ST":>8} {"波高":>8}')
print('-' * 80)

total_races = 0
total_with_result = 0
total_with_details = 0
total_with_chikusen = 0
total_with_st = 0
total_with_wave = 0

for row in cursor.fetchall():
    year, races, with_result, with_details, with_chikusen, with_st, with_wave = row
    print(f'{year:<6} {races:>10,} {with_result:>8,} {with_details:>8,} {with_chikusen:>8,} {with_st:>8,} {with_wave:>8,}')

    total_races += races
    total_with_result += with_result
    total_with_details += with_details
    total_with_chikusen += with_chikusen
    total_with_st += with_st
    total_with_wave += with_wave

print('-' * 80)
print(f'{"合計":<6} {total_races:>10,} {total_with_result:>8,} {total_with_details:>8,} {total_with_chikusen:>8,} {total_with_st:>8,} {total_with_wave:>8,}')
print()

# 補完が必要なレース数
print('補完が必要なデータ:')
print('-' * 80)

cursor.execute('''
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2025-01-01'
      AND rd.chikusen_time IS NULL
''')
missing_chikusen = cursor.fetchone()[0]
print(f'chikusen_time欠損: {missing_chikusen:,}件')

cursor.execute('''
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2025-01-01'
      AND rd.st_time IS NULL
''')
missing_st = cursor.fetchone()[0]
print(f'st_time欠損: {missing_st:,}件')

cursor.execute('''
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2025-01-01'
      AND rc.wave_height IS NULL
''')
missing_wave = cursor.fetchone()[0]
print(f'wave_height欠損: {missing_wave:,}件')

print()
print('=' * 80)

conn.close()
