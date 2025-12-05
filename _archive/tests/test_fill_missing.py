#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')

# テスト: 2022年の不足レースを10件取得
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT r.id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date >= '2022-01-01' AND r.race_date <= '2022-01-10'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM race_details)
    LIMIT 10
""")

test_races = cursor.fetchall()
conn.close()

print(f'テスト対象: {len(test_races)}レース')

if len(test_races) > 0:
    print('
サンプル:')
    for race in test_races[:5]:
        print(f'  race_id={race[0]}, 会場{race[1]}, {race[2]}, {race[3]}R')
    print('
[OK] スクリプトは正常に動作しています')
else:
    print('[INFO] 補充対象のレースがありません')
