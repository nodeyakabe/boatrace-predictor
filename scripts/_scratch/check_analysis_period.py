#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print("="*60)
print("分析対象期間の確認")
print("="*60)
print()

# 全体期間
cursor.execute('''
    SELECT
        MIN(r.race_date) as start_date,
        MAX(r.race_date) as end_date,
        COUNT(DISTINCT rp.race_id) as race_count,
        COUNT(DISTINCT substr(r.race_date, 1, 4)) as year_count
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE rp.prediction_type = 'before'
    AND rp.rank_prediction = 1
''')

result = cursor.fetchone()
print(f"対象期間:  {result[0]} ～ {result[1]}")
print(f"レース数:  {result[2]:,}件")
print(f"年数:      {result[3]}年分")
print()

# 年度別内訳
cursor.execute('''
    SELECT
        substr(r.race_date, 1, 4) as year,
        COUNT(DISTINCT rp.race_id) as races
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE rp.prediction_type = 'before'
    AND rp.rank_prediction = 1
    GROUP BY year
    ORDER BY year
''')

print("年度別レース数:")
print("-"*40)
total = 0
for row in cursor.fetchall():
    print(f"  {row[0]}年: {row[1]:>6,}件")
    total += row[1]

print("-"*40)
print(f"  合計:   {total:>6,}件")
print()

# 月別の最新データ確認
cursor.execute('''
    SELECT
        substr(r.race_date, 1, 7) as month,
        COUNT(DISTINCT rp.race_id) as races
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE rp.prediction_type = 'before'
    AND rp.rank_prediction = 1
    AND r.race_date >= (
        SELECT substr(MAX(race_date), 1, 4) || '-01-01'
        FROM races r2
        JOIN race_predictions rp2 ON r2.id = rp2.race_id
        WHERE rp2.prediction_type = 'before'
    )
    GROUP BY month
    ORDER BY month
''')

print("最新年度の月別レース数:")
print("-"*40)
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:>4,}件")

conn.close()

print()
print("="*60)
