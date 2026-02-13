#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# テーブル構造確認
cursor.execute('PRAGMA table_info(bet_history)')
cols = cursor.fetchall()
print('bet_history テーブル構造:')
print('カラム名 | 型 | NULL許可')
print('-' * 50)
for col in cols:
    print(f'{col[1]:20s} | {col[2]:10s} | {"○" if col[3] == 0 else "×"}')

# データ確認
cursor.execute('SELECT COUNT(*) FROM bet_history')
count = cursor.fetchone()[0]
print(f'\n総レコード数: {count}件')

if count > 0:
    cursor.execute('SELECT * FROM bet_history LIMIT 10')
    rows = cursor.fetchall()
    print('\nbet_history データサンプル:')
    print('-' * 100)
    col_names = [c[1] for c in cols]
    print(' | '.join(col_names))
    print('-' * 100)
    for row in rows:
        print(' | '.join([str(x) if x is not None else 'NULL' for x in row]))

conn.close()
