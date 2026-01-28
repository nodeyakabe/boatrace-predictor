#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""1月のbefore予測データ確認スクリプト"""
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
print('1月の予測データ分析')
print('=' * 80)
print()

# テーブル一覧確認
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row['name'] for row in cursor.fetchall()]
print('[0] データベース内のテーブル:')
print('-' * 80)
for table in tables:
    print(f'  - {table}')
print()

# 予測テーブルの存在確認
pred_tables = [t for t in tables if 'predict' in t.lower() or 'forecast' in t.lower()]
if pred_tables:
    print(f'[INFO] 予測関連テーブル: {", ".join(pred_tables)}')

    # 最初の予測テーブルのスキーマ確認
    pred_table = pred_tables[0]
    cursor.execute(f"PRAGMA table_info({pred_table})")
    print(f'\n[1] {pred_table}テーブルのカラム:')
    print('-' * 80)
    for row in cursor.fetchall():
        print(f"  {row['name']}: {row['type']}")

    # prediction_typeカラムの存在確認
    columns = [row['name'] for row in cursor.execute(f"PRAGMA table_info({pred_table})")]

    if 'prediction_type' in columns:
        # 予測タイプ別のレース数
        cursor.execute(f'''
            SELECT
                p.prediction_type,
                COUNT(DISTINCT p.race_id) as race_count,
                COUNT(*) as prediction_count
            FROM {pred_table} p
            JOIN races r ON p.race_id = r.id
            WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
            GROUP BY p.prediction_type
            ORDER BY p.prediction_type
        ''')
        print(f'\n[2] 予測タイプ別レース数:')
        print('-' * 80)
        for row in cursor.fetchall():
            pred_type = row['prediction_type'] or 'NULL'
            print(f"  {pred_type}: {row['race_count']:,}レース ({row['prediction_count']:,}件の予測)")

        # before予測の6艇揃っているレース数
        cursor.execute(f'''
            SELECT COUNT(*) FROM (
                SELECT r.id
                FROM races r
                JOIN {pred_table} p ON r.id = p.race_id
                WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
                    AND p.prediction_type = 'before'
                GROUP BY r.id
                HAVING COUNT(DISTINCT p.pit_number) = 6
            )
        ''')
        before_complete = cursor.fetchone()[0]

        # advance予測の6艇揃っているレース数
        cursor.execute(f'''
            SELECT COUNT(*) FROM (
                SELECT r.id
                FROM races r
                JOIN {pred_table} p ON r.id = p.race_id
                WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
                    AND (p.prediction_type IS NULL OR p.prediction_type = 'advance')
                GROUP BY r.id
                HAVING COUNT(DISTINCT p.pit_number) = 6
            )
        ''')
        advance_complete = cursor.fetchone()[0]

        print(f'\n[3] 6艇揃っているレース数（購入候補）:')
        print('-' * 80)
        print(f'  before予測: {before_complete:,}レース')
        print(f'  advance予測: {advance_complete:,}レース')

        # before予測のサンプルデータ（最初の5レース）
        cursor.execute(f'''
            SELECT
                r.race_date, r.venue_code, r.race_number, r.id,
                COUNT(DISTINCT p.pit_number) as pit_count
            FROM races r
            JOIN {pred_table} p ON r.id = p.race_id
            WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
                AND p.prediction_type = 'before'
            GROUP BY r.id
            ORDER BY r.race_date, r.venue_code, r.race_number
            LIMIT 5
        ''')
        rows = cursor.fetchall()
        if rows:
            print(f'\n[4] before予測サンプル（最初の5レース）:')
            print('-' * 80)
            for row in rows:
                print(f"  {row['race_date']} 会場{row['venue_code']:02d} {row['race_number']:2d}R (race_id={row['id']}): {row['pit_count']}艇分の予測")
        else:
            print(f'\n[4] before予測: データなし')
    else:
        print(f'\n[WARNING] {pred_table}テーブルにprediction_typeカラムがありません')
        # サンプルデータを表示
        cursor.execute(f"SELECT * FROM {pred_table} LIMIT 3")
        print(f'\n[INFO] {pred_table}のサンプルデータ:')
        for row in cursor.fetchall():
            print(f'  {dict(row)}')
else:
    print('[ERROR] 予測関連のテーブルが見つかりません')

conn.close()
print()
print('=' * 80)
