#!/usr/bin/env python3
"""
データベーススキーマ確認スクリプト
"""

import sqlite3

DB_PATH = "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032/data/boatrace.db"

def check_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # テーブル一覧
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()

    print("テーブル一覧:")
    for table in tables:
        print(f"  - {table[0]}")

    print("\n" + "="*80)

    # 各テーブルのスキーマ
    for table in tables:
        table_name = table[0]
        print(f"\n[{table_name}]")
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()

        for col in columns:
            print(f"  {col[1]} ({col[2]})")

        # サンプルデータ
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  → レコード数: {count:,}")

    conn.close()

if __name__ == "__main__":
    check_schema()
