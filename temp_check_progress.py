"""
wave_height補完の進捗確認
"""
import sqlite3

db_path = 'data/boatrace.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 80)
print('wave_height補完進捗確認')
print('=' * 80)
print()

# 年度別のwave_height状況
cursor.execute('''
    SELECT
        substr(r.race_date, 1, 4) as year,
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT CASE WHEN rc.wave_height IS NOT NULL THEN rc.race_id END) as with_wave,
        COUNT(DISTINCT CASE WHEN rc.wave_height IS NULL THEN r.id END) as missing_wave
    FROM races r
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2024-12-31'
    GROUP BY substr(r.race_date, 1, 4)
    ORDER BY year
''')

print('年度別wave_height状況:')
print('-' * 80)
print(f'{"年度":<6} {"総レース数":>12} {"wave_height有":>14} {"欠損":>12} {"充足率":>8}')
print('-' * 80)

total_races = 0
total_with_wave = 0
total_missing = 0

for row in cursor.fetchall():
    year, races, with_wave, missing = row
    rate = (with_wave / races * 100) if races > 0 else 0
    print(f'{year:<6} {races:>12,} {with_wave:>14,} {missing:>12,} {rate:>7.1f}%')

    total_races += races
    total_with_wave += with_wave
    total_missing += missing

print('-' * 80)
total_rate = (total_with_wave / total_races * 100) if total_races > 0 else 0
print(f'{"合計":<6} {total_races:>12,} {total_with_wave:>14,} {total_missing:>12,} {total_rate:>7.1f}%')

print()
print('=' * 80)

conn.close()
