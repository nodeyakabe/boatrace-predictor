#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import sqlite3

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()

# 11/27の開催会場
cur.execute("""
    SELECT DISTINCT venue_code
    FROM races
    WHERE race_date = '2025-11-27'
    ORDER BY venue_code
""")
venues = [r[0] for r in cur.fetchall()]

print("2025-11-27の開催会場:")
for v in venues:
    print(f"  会場{v}")

print()

# 各会場のレース数
cur.execute("""
    SELECT venue_code, COUNT(*) as race_count
    FROM races
    WHERE race_date = '2025-11-27'
    GROUP BY venue_code
    ORDER BY venue_code
""")

print("各会場のレース数:")
for row in cur.fetchall():
    print(f"  会場{row[0]}: {row[1]}レース")

conn.close()
