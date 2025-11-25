#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V4スクレイパーのテスト
"""
import sys
sys.path.insert(0, '.')

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

# 添付画像のレース: 2025-11-04 1R （会場01 = 桐生）
venue_code = '01'
race_date = '20251104'
race_number = 1

scraper = ImprovedResultScraperV4()

print(f'=== V4スクレイパーテスト ===')
print(f'会場: {venue_code} 日付: {race_date} レース: {race_number}R\n')

result = scraper.get_race_result_complete(venue_code, race_date, race_number)

if result:
    print('レース結果取得: 成功\n')

    # 期待値（画像から）
    expected = {
        1: 0.21,
        2: 0.26,
        3: 0.13,
        4: 0.11,  # "まくり差し" の前
        5: 0.18,
        6: 0.19
    }

    st_times = result.get('st_times', {})
    st_status = result.get('st_status', {})

    print('ST時間:')
    for pit in range(1, 7):
        actual_time = st_times.get(pit)
        status = st_status.get(pit, 'unknown')
        expected_time = expected.get(pit)

        match = '[OK]' if actual_time == expected_time else '[NG]'
        print(f'  {pit}号艇: {actual_time} ({status}) - 期待値: {expected_time} {match}')

    # 全て一致しているか確認
    all_match = all(st_times.get(pit) == expected.get(pit) for pit in range(1, 7))

    print(f'\n総合結果: {"[OK] 全て正確に取得" if all_match else "[NG] 一部不一致"}')

else:
    print('レース結果取得: 失敗')
