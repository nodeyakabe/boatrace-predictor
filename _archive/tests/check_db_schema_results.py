#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
resultsテーブルのスキーマ確認
"""

import sqlite3

db_path = 'data/boatrace.db'

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()

    # テーブル一覧
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()

    print("テーブル一覧:")
    for table in tables:
        print(f"  - {table[0]}")

    # resultsテーブルのスキーマ
    print("\nresultsテーブルのスキーマ:")
    cursor.execute("PRAGMA table_info(results)")
    columns = cursor.fetchall()

    for col in columns:
        print(f"  {col[1]} ({col[2]})")

    # サンプルデータ
    print("\nresultsテーブルのサンプルデータ:")
    cursor.execute("SELECT * FROM results LIMIT 3")
    rows = cursor.fetchall()

    # カラム名
    col_names = [desc[0] for desc in cursor.description]
    print("  カラム名:", col_names)

    for row in rows:
        print("  ", row)
