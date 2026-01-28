"""
2025年レースデータ状況調査
"""
import sqlite3
import sys

db_path = 'data/boatrace.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 80)
print('2025年レースデータ状況調査')
print('=' * 80)
print()

# 2025年のレース総数と結果あり数
cursor.execute('''
    SELECT
        COUNT(*) as total_races,
        COUNT(DISTINCT res.race_id) as completed_races,
        MIN(r.race_date) as first_race,
        MAX(r.race_date) as last_race
    FROM races r
    LEFT JOIN results res ON r.id = res.race_id
    WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
''')
total, completed, first_date, last_date = cursor.fetchone()

print(f'2025年レース総数: {total:,}件')
print(f'結果が入っているレース: {completed:,}件')
print(f'期間: {first_date} ～ {last_date}')
print()

# race_detailsにchikusen_timeがあるレース
cursor.execute('''
    SELECT
        COUNT(DISTINCT rd.race_id) as races_with_chikusen,
        MIN(r.race_date) as earliest_chikusen,
        MAX(r.race_date) as latest_chikusen
    FROM race_details rd
    JOIN races r ON rd.race_id = r.id
    WHERE rd.chikusen_time IS NOT NULL
      AND r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
''')
with_chikusen, earliest, latest = cursor.fetchone()

print(f'chikusen_timeがあるレース: {with_chikusen or 0:,}件')
if earliest and latest:
    print(f'chikusen_time期間: {earliest} ～ {latest}')
print()

# race_detailsに何かデータがあるレース
cursor.execute('''
    SELECT
        COUNT(DISTINCT rd.race_id) as races_with_details
    FROM race_details rd
    JOIN races r ON rd.race_id = r.id
    WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
''')
with_details = cursor.fetchone()[0]

print(f'race_detailsレコードがあるレース: {with_details:,}件')
print()

# 月別の状況
cursor.execute('''
    SELECT
        substr(r.race_date, 1, 7) as month,
        COUNT(*) as total,
        COUNT(DISTINCT res.race_id) as with_result,
        COUNT(DISTINCT CASE WHEN rd.chikusen_time IS NOT NULL THEN rd.race_id END) as with_chikusen
    FROM races r
    LEFT JOIN results res ON r.id = res.race_id
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
    GROUP BY substr(r.race_date, 1, 7)
    ORDER BY month
''')

print('月別データ状況:')
print('-' * 80)
print(f'{"月":<10} {"レース数":>10} {"結果あり":>10} {"chikusen_time":>15}')
print('-' * 80)
for row in cursor.fetchall():
    month, total, with_result, with_chikusen = row
    print(f'{month:<10} {total:>10,} {with_result:>10,} {with_chikusen:>15,}')

print('=' * 80)

conn.close()
