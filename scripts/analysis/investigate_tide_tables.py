#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
潮位テーブル調査スクリプト

3つの潮位関連テーブル（tide, rdmdb_tide, race_tide_data）の構造とデータを調査
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from config.settings import DATABASE_PATH


def investigate_table(cursor, table_name):
    """テーブルの構造とデータ量を調査"""
    print(f"\n{'='*70}")
    print(f"テーブル: {table_name}")
    print('='*70)

    # テーブルが存在するかチェック
    cursor.execute(f"""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='{table_name}'
    """)

    if not cursor.fetchone():
        print(f"❌ テーブル '{table_name}' は存在しません")
        return None

    # テーブル構造を取得
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()

    print("\n【カラム構造】")
    for col in columns:
        cid, name, col_type, notnull, default, pk = col
        print(f"  {name:20s} {col_type:15s} {'PRIMARY KEY' if pk else ''} {'NOT NULL' if notnull else ''}")

    # データ量を取得
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"\n【データ件数】 {count:,}件")

    # サンプルデータを取得（最初の3件）
    if count > 0:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
        rows = cursor.fetchall()
        print("\n【サンプルデータ（最初の3件）】")

        col_names = [col[1] for col in columns]
        for i, row in enumerate(rows, 1):
            print(f"\n  --- サンプル {i} ---")
            for col_name, value in zip(col_names, row):
                print(f"    {col_name:20s}: {value}")

    return {
        'exists': True,
        'columns': columns,
        'count': count
    }


def check_data_overlap(cursor):
    """テーブル間のデータ重複をチェック"""
    print(f"\n{'='*70}")
    print("データ重複チェック")
    print('='*70)

    # tide と rdmdb_tide の重複チェック
    try:
        cursor.execute("""
            SELECT COUNT(*)
            FROM tide t
            INNER JOIN rdmdb_tide r
              ON t.venue_code = r.venue_code
              AND t.tide_date = r.tide_date
        """)
        overlap = cursor.fetchone()[0]
        print(f"\ntide ⇔ rdmdb_tide の重複: {overlap:,}件")
    except Exception as e:
        print(f"\ntide ⇔ rdmdb_tide の比較エラー: {e}")

    # tide と race_tide_data の重複チェック
    try:
        cursor.execute("""
            SELECT COUNT(*)
            FROM tide t
            INNER JOIN race_tide_data r
              ON t.venue_code = r.venue_code
              AND t.tide_date = r.race_date
        """)
        overlap = cursor.fetchone()[0]
        print(f"tide ⇔ race_tide_data の重複: {overlap:,}件")
    except Exception as e:
        print(f"tide ⇔ race_tide_data の比較エラー: {e}")


def check_usage_in_code():
    """コード内での使用箇所を検索"""
    print(f"\n{'='*70}")
    print("コード内での使用箇所")
    print('='*70)

    import glob

    # Pythonファイルを検索
    patterns = ['src/**/*.py', 'scripts/**/*.py', 'ui/**/*.py']
    tide_files = []
    rdmdb_files = []
    race_tide_files = []

    for pattern in patterns:
        for filepath in glob.glob(pattern, recursive=True):
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if 'FROM tide' in content or 'tide' in content.lower():
                        if filepath not in tide_files:
                            tide_files.append(filepath)
                    if 'rdmdb_tide' in content:
                        if filepath not in rdmdb_files:
                            rdmdb_files.append(filepath)
                    if 'race_tide_data' in content:
                        if filepath not in race_tide_files:
                            race_tide_files.append(filepath)
            except:
                pass

    print(f"\n【tide テーブル参照ファイル】 {len(tide_files)}件")
    for f in tide_files[:5]:
        print(f"  - {f}")
    if len(tide_files) > 5:
        print(f"  ... 他 {len(tide_files) - 5}件")

    print(f"\n【rdmdb_tide テーブル参照ファイル】 {len(rdmdb_files)}件")
    for f in rdmdb_files:
        print(f"  - {f}")

    print(f"\n【race_tide_data テーブル参照ファイル】 {len(race_tide_files)}件")
    for f in race_tide_files:
        print(f"  - {f}")


def main():
    print("="*70)
    print("潮位テーブル調査")
    print("="*70)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 各テーブルを調査
    tide_info = investigate_table(cursor, 'tide')
    rdmdb_info = investigate_table(cursor, 'rdmdb_tide')
    race_tide_info = investigate_table(cursor, 'race_tide_data')

    # データ重複をチェック
    check_data_overlap(cursor)

    conn.close()

    # コード内での使用箇所をチェック
    check_usage_in_code()

    print("\n" + "="*70)
    print("調査完了")
    print("="*70)


if __name__ == "__main__":
    main()
