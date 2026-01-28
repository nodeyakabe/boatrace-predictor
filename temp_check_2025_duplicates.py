"""
2025年レースデータの重複チェック
"""
import sqlite3

db_path = 'data/boatrace.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 80)
print('2025年レースデータ重複チェック')
print('=' * 80)
print()

# 重複レースの検出
cursor.execute('''
    SELECT
        venue_code,
        race_date,
        race_number,
        COUNT(*) as count
    FROM races
    WHERE race_date >= '2025-01-01' AND race_date <= '2025-12-31'
    GROUP BY venue_code, race_date, race_number
    HAVING COUNT(*) > 1
    ORDER BY count DESC
    LIMIT 20
''')

duplicates = cursor.fetchall()

if duplicates:
    print(f'重複レース発見: {len(duplicates)}件（上位20件表示）')
    print('-' * 80)
    print(f'{"会場":<6} {"日付":<12} {"R":<4} {"重複数":>6}')
    print('-' * 80)
    for venue, date, race_num, count in duplicates:
        print(f'{venue:<6} {date:<12} {race_num:<4} {count:>6}')
    print()
else:
    print('重複レースは見つかりませんでした。')
    print()

# 2025年の正味レース数（DISTINCT）
cursor.execute('''
    SELECT COUNT(DISTINCT venue_code || race_date || race_number)
    FROM races
    WHERE race_date >= '2025-01-01' AND race_date <= '2025-12-31'
''')
unique_races = cursor.fetchone()[0]

print(f'2025年ユニークレース数: {unique_races:,}件')
print()

# 通常の年度と比較
cursor.execute('''
    SELECT
        substr(race_date, 1, 4) as year,
        COUNT(DISTINCT venue_code || race_date || race_number) as unique_count
    FROM races
    WHERE race_date >= '2020-01-01' AND race_date <= '2024-12-31'
    GROUP BY substr(race_date, 1, 4)
    ORDER BY year
''')

print('過去年度との比較（ユニークレース数）:')
print('-' * 80)
print(f'{"年度":<6} {"レース数":>10}')
print('-' * 80)
for year, count in cursor.fetchall():
    print(f'{year:<6} {count:>10,}')
print(f'{"2025":<6} {unique_races:>10,}')

print()
print('=' * 80)

conn.close()
