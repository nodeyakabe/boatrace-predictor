#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
テストデータのセットアップ
2025-11-04のレースにST 5/6のダミーデータを設定
"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 2025-11-04のrace_idを取得
cursor.execute('''
    SELECT id FROM races
    WHERE race_date = '2025-11-04' AND venue_code = '01'
    ORDER BY race_number
    LIMIT 3
''')

race_ids = [row[0] for row in cursor.fetchall()]

print(f'対象race_id: {race_ids}')

# 各レースにrace_detailsレコードを作成（ST 5/6）
for race_id in race_ids:
    # 既存のrace_detailsを削除
    cursor.execute('DELETE FROM race_details WHERE race_id = ?', (race_id,))

    # 新しいレコードを作成（1-5号艇のみST時間を設定、6号艇はNULL）
    for waku in range(1, 7):
        if waku <= 5:
            # 1-5号艇: ダミーのST時間を設定
            st_time = 0.15 + (waku * 0.01)  # 0.16, 0.17, 0.18, 0.19, 0.20
        else:
            # 6号艇: ST時間なし（5/6の状態を作る）
            st_time = None

        cursor.execute('''
            INSERT INTO race_details (race_id, pit_number, st_time)
            VALUES (?, ?, ?)
        ''', (race_id, waku, st_time))

conn.commit()

# 確認
cursor.execute('''
    SELECT r.venue_code, r.race_date, r.race_number,
           COUNT(CASE WHEN rd.st_time IS NOT NULL THEN 1 END) as st_count
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date = '2025-11-04' AND r.venue_code = '01'
    GROUP BY r.id
    ORDER BY r.race_number
''')

print('\nセットアップ完了:')
for row in cursor.fetchall():
    print(f'  会場{row[0]} {row[1]} {row[2]}R: ST {row[3]}/6')

conn.close()
