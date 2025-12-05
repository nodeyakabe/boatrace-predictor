#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ST <5レースのサンプルテスト
本当に中止やFなのか確認
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

# スクレイパー初期化
scraper = ImprovedResultScraperV4()

# テストケース: check_st_less_than_5.pyで取得したレースから3つ
test_cases = [
    ('19', '20251031', 5, 'Race ID: 14276'),   # ST 4/6
    ('22', '20251031', 10, 'Race ID: 14688'),  # ST 4/6
    ('05', '20251030', 1, 'Race ID: 10284'),   # ST 0/6
]

print('=== ST <5レースのサンプルテスト ===')
print()

for venue, date, race, label in test_cases:
    print(f'{label} - 会場{venue} {date} {race}R')

    race_data = scraper.get_race_result_complete(venue, date, race)

    if race_data:
        if 'st_times' in race_data and race_data['st_times']:
            st_count = len(race_data['st_times'])
            print(f'  結果: ST {st_count}/6取得可能 - データは存在する！')

            # ST時間を表示
            for pit, st_time in sorted(race_data['st_times'].items()):
                status = race_data.get('st_status', {}).get(pit, 'normal')
                print(f'    {pit}号艇: {st_time} ({status})')
        else:
            print('  結果: ST時間なし - レース中止またはデータ不在')
    else:
        print('  結果: データ取得失敗 - レース中止またはページ不在')

    print()
