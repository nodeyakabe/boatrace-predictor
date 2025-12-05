#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import sqlite3

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT
        r.venue_code,
        v.name,
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT CASE
            WHEN rd.chikusen_time IS NOT NULL
              OR rd.isshu_time IS NOT NULL
              OR rd.mawariashi_time IS NOT NULL
            THEN r.id
        END) as saved_races
    FROM races r
    LEFT JOIN venues v ON r.venue_code = v.code
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date = "2025-11-27"
    GROUP BY r.venue_code, v.name
    ORDER BY r.venue_code
''')

results = cursor.fetchall()

print('=' * 60)
print('11/27 オリジナル展示収集状況')
print('=' * 60)
print()

total_all = 0
saved_all = 0

for code, name, total, saved in results:
    total_all += total
    saved_all += saved
    status = '✓' if saved == total else '✗'
    percentage = saved/total*100 if total > 0 else 0
    print(f'{status} {code} {name}: {saved}/{total}レース ({percentage:.0f}%)')

print()
print('-' * 60)
print(f'合計: {saved_all}/{total_all}レース ({saved_all/total_all*100:.1f}%)')
print('=' * 60)

conn.close()
