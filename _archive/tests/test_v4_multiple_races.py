#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V4スクレイパーの複数レーステスト
"""
import sys
sys.path.insert(0, '.')

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

# テストケース: 2025-11-04の複数レース
test_cases = [
    ('01', '20251104', 1),  # 桐生 1R
    ('01', '20251104', 2),  # 桐生 2R
    ('01', '20251104', 3),  # 桐生 3R
]

scraper = ImprovedResultScraperV4()

print('=== V4スクレイパー 複数レーステスト ===\n')

total_success = 0
total_failed = 0

for venue_code, race_date, race_number in test_cases:
    print(f'会場{venue_code} {race_date} {race_number}R:')

    result = scraper.get_race_result_complete(venue_code, race_date, race_number)

    if result:
        st_times = result.get('st_times', {})
        st_status = result.get('st_status', {})

        # ST時間が6個取得できているか確認
        if len(st_times) == 6:
            print(f'  [OK] ST時間 6/6 取得成功')
            total_success += 1

            # ST時間を表示
            for pit in range(1, 7):
                st_time = st_times.get(pit)
                status = st_status.get(pit, 'unknown')
                status_mark = '' if status == 'normal' else f' ({status})'
                print(f'    {pit}号艇: {st_time}{status_mark}')
        else:
            print(f'  [NG] ST時間 {len(st_times)}/6')
            total_failed += 1
    else:
        print(f'  [NG] データ取得失敗')
        total_failed += 1

    print()

print(f'=== テスト結果サマリー ===')
print(f'成功: {total_success}/{len(test_cases)}')
print(f'失敗: {total_failed}/{len(test_cases)}')

if total_success == len(test_cases):
    print('\n[OK] 全テスト成功！')
else:
    print(f'\n[NG] {total_failed}件のテストが失敗')
