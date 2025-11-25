#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2016年データの取得可能性テスト
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

# スクレイパー初期化
scraper = ImprovedResultScraperV4()

# 2016-01-07 桐生 1R のデータ取得テスト
print('=== 2016年データ取得テスト ===')
print('会場: 01 (桐生)')
print('日付: 20160107')
print('レース: 1R')
print()

race_data = scraper.get_race_result_complete('01', '20160107', 1)

if race_data:
    print('[OK] データ取得成功！')
    print()

    if 'st_times' in race_data and race_data['st_times']:
        print('ST時間:')
        for pit, st_time in sorted(race_data['st_times'].items()):
            status = race_data.get('st_status', {}).get(pit, 'normal')
            print(f'  {pit}号艇: {st_time} ({status})')

        print()
        print(f'取得したST時間数: {len(race_data["st_times"])}/6')
    else:
        print('[NG] ST時間データなし')
else:
    print('[NG] データ取得失敗')
