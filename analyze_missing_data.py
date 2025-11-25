#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不足データの詳細分析スクリプト
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print('=== 不足データの詳細分析 ===\n')

# 1. race_detailsが完全でないレースの分析
print('【1. race_details不足の分析】')
cursor.execute('''
    SELECT r.race_date, COUNT(*) as cnt
    FROM races r
    LEFT JOIN (
        SELECT race_id, COUNT(*) as detail_cnt
        FROM race_details
        GROUP BY race_id
    ) rd ON r.id = rd.race_id
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND (rd.detail_cnt IS NULL OR rd.detail_cnt < 6)
    GROUP BY strftime('%Y', r.race_date)
    ORDER BY r.race_date
''')
print('  年別の不足数:')
for row in cursor.fetchall():
    year = row[0][:4]
    print(f'    {year}年: {row[1]:,}レース')

# race_detailsが全くないレース
cursor.execute('''
    SELECT COUNT(*) FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM race_details)
''')
no_details = cursor.fetchone()[0]
print(f'  race_detailsが全くない: {no_details:,}レース')

# race_detailsはあるが6件未満
cursor.execute('''
    SELECT COUNT(DISTINCT r.id) FROM races r
    LEFT JOIN (
        SELECT race_id, COUNT(*) as cnt
        FROM race_details
        GROUP BY race_id
    ) rd ON r.id = rd.race_id
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND rd.cnt > 0 AND rd.cnt < 6
''')
incomplete_details = cursor.fetchone()[0]
print(f'  race_detailsが1-5件: {incomplete_details:,}レース')
print()

# 2. results不足の分析
print('【2. results不足の分析】')
cursor.execute('''
    SELECT strftime('%Y', r.race_date) as year, COUNT(*) as cnt
    FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM results)
    GROUP BY year
    ORDER BY year
''')
print('  年別の不足数:')
for row in cursor.fetchall():
    print(f'    {row[0]}年: {row[1]:,}レース')

# 最新の不足レース（未開催の可能性）
cursor.execute('''
    SELECT r.race_date, COUNT(*) as cnt
    FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM results)
    GROUP BY r.race_date
    ORDER BY r.race_date DESC
    LIMIT 10
''')
print('  最新の不足日（未開催の可能性）:')
for row in cursor.fetchall():
    print(f'    {row[0]}: {row[1]}レース')
print()

# 3. payouts不足の分析
print('【3. payouts不足の分析】')
cursor.execute('''
    SELECT strftime('%Y', r.race_date) as year, COUNT(*) as cnt
    FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM payouts)
    GROUP BY year
    ORDER BY year
''')
print('  年別の不足数:')
for row in cursor.fetchall():
    print(f'    {row[0]}年: {row[1]:,}レース')

# payoutsはないがresultsはあるレース（これは補充すべき）
cursor.execute('''
    SELECT COUNT(*) FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id IN (SELECT DISTINCT race_id FROM results)
    AND r.id NOT IN (SELECT DISTINCT race_id FROM payouts)
''')
payouts_only_missing = cursor.fetchone()[0]
print(f'  resultsはあるがpayoutsがない: {payouts_only_missing:,}レース（補充対象）')
print()

# 4. 補充対象のサマリー
print('【補充対象のサマリー】')

# race_detailsが全くないレース（最優先）
cursor.execute('''
    SELECT COUNT(*) FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM race_details)
    AND r.race_date < date('now')
''')
details_priority = cursor.fetchone()[0]
print(f'1. race_details完全欠損（過去の開催済みレース）: {details_priority:,}レース')

# resultsがないレース（過去分のみ）
cursor.execute('''
    SELECT COUNT(*) FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM results)
    AND r.race_date < date('now')
''')
results_priority = cursor.fetchone()[0]
print(f'2. results欠損（過去の開催済みレース）: {results_priority:,}レース')

# payoutsがないレース（resultsがある過去分）
print(f'3. payouts欠損（resultsあり）: {payouts_only_missing:,}レース')

print()
print('【推奨する補充順序】')
print('  1. race_details完全欠損 -> 選手情報・展示情報を取得')
print('  2. results欠損 -> レース結果を取得')
print('  3. payouts欠損 -> 払戻金を取得')

conn.close()
