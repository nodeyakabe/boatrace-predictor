# -*- coding: utf-8 -*-
"""race_detailsテーブルのスキーマ確認"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(race_details)")
columns = cursor.fetchall()

print("race_details テーブルのカラム:")
print("-" * 80)
for col in columns:
    cid, name, type_, notnull, default, pk = col
    print(f"{cid}: {name:30s} {type_:15s} {'NOT NULL' if notnull else ''}")

conn.close()
