#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""1月のbefore予測データ確認スクリプト（race_predictions版）"""
import sys
import sqlite3
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print('=' * 80)
print('1月の予測データ分析（race_predictionsテーブル）')
print('=' * 80)
print()

# race_predictionsテーブルのスキーマ確認
cursor.execute("PRAGMA table_info(race_predictions)")
print('[1] race_predictionsテーブルのカラム:')
print('-' * 80)
columns = []
for row in cursor.fetchall():
    columns.append(row['name'])
    print(f"  {row['name']}: {row['type']}")
print()

# 1月のデータ件数確認
cursor.execute('''
    SELECT COUNT(*) as total
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
''')
total_predictions = cursor.fetchone()['total']
print(f'[2] 1月の予測データ総数: {total_predictions:,}件')
print()

# prediction_typeカラムの存在確認
if 'prediction_type' in columns:
    # 予測タイプ別のレース数
    cursor.execute('''
        SELECT
            rp.prediction_type,
            COUNT(DISTINCT rp.race_id) as race_count,
            COUNT(*) as prediction_count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        GROUP BY rp.prediction_type
        ORDER BY rp.prediction_type
    ''')
    print('[3] 予測タイプ別レース数:')
    print('-' * 80)
    for row in cursor.fetchall():
        pred_type = row['prediction_type'] or 'NULL'
        print(f"  {pred_type}: {row['race_count']:,}レース ({row['prediction_count']:,}件の予測)")
    print()

    # before予測の6艇揃っているレース数
    cursor.execute('''
        SELECT COUNT(*) FROM (
            SELECT r.id
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
                AND rp.prediction_type = 'before'
            GROUP BY r.id
            HAVING COUNT(DISTINCT rp.pit_number) = 6
        )
    ''')
    before_complete = cursor.fetchone()[0]

    # advance予測の6艇揃っているレース数
    cursor.execute('''
        SELECT COUNT(*) FROM (
            SELECT r.id
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
                AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
            GROUP BY r.id
            HAVING COUNT(DISTINCT rp.pit_number) = 6
        )
    ''')
    advance_complete = cursor.fetchone()[0]

    print('[4] 6艇揃っているレース数（購入候補）:')
    print('-' * 80)
    print(f'  before予測: {before_complete:,}レース')
    print(f'  advance予測: {advance_complete:,}レース')
    print()

    # before予測のサンプルデータ（最初の5レース）
    cursor.execute('''
        SELECT
            r.race_date, r.venue_code, r.race_number, r.id,
            COUNT(DISTINCT rp.pit_number) as pit_count
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
            AND rp.prediction_type = 'before'
        GROUP BY r.id
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 5
    ''')
    rows = cursor.fetchall()
    if rows:
        print('[5] before予測サンプル（最初の5レース）:')
        print('-' * 80)
        for row in rows:
            print(f"  {row['race_date']} 会場{row['venue_code']:02d} {row['race_number']:2d}R (race_id={row['id']}): {row['pit_count']}艇分の予測")
        print()
    else:
        print('[5] before予測: データなし')
        print()

    # advance予測のサンプルデータ（最初の5レース）
    cursor.execute('''
        SELECT
            r.race_date, r.venue_code, r.race_number, r.id,
            COUNT(DISTINCT rp.pit_number) as pit_count
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
            AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
        GROUP BY r.id
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 5
    ''')
    rows = cursor.fetchall()
    if rows:
        print('[6] advance予測サンプル（最初の5レース）:')
        print('-' * 80)
        for row in rows:
            print(f"  {row['race_date']} 会場{row['venue_code']:02d} {row['race_number']:2d}R (race_id={row['id']}): {row['pit_count']}艇分の予測")
        print()

    # 6艇未満の予測があるレースをチェック
    cursor.execute('''
        SELECT
            r.race_date, r.venue_code, r.race_number, r.id,
            rp.prediction_type,
            COUNT(DISTINCT rp.pit_number) as pit_count
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
            AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
        GROUP BY r.id, rp.prediction_type
        HAVING COUNT(DISTINCT rp.pit_number) < 6
        LIMIT 10
    ''')
    rows = cursor.fetchall()
    if rows:
        print('[7] 不完全な予測（6艇未満）のサンプル:')
        print('-' * 80)
        for row in rows:
            pred_type = row['prediction_type'] or 'NULL'
            print(f"  {row['race_date']} 会場{row['venue_code']:02d} {row['race_number']:2d}R (race_id={row['id']}): {row['pit_count']}艇分の予測 (type={pred_type})")
        print()

else:
    print('[WARNING] race_predictionsテーブルにprediction_typeカラムがありません')
    # サンプルデータを表示
    cursor.execute('''
        SELECT * FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        LIMIT 3
    ''')
    print('[INFO] race_predictionsのサンプルデータ:')
    for row in cursor.fetchall():
        print(f'  {dict(row)}')

conn.close()
print('=' * 80)
