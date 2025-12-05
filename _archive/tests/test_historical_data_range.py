#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
過去データの取得可能範囲テスト
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

# スクレイパー初期化
scraper = ImprovedResultScraperV4()

# テスト対象
test_cases = [
    ('01', '20151101', 1, '2015-11-01'),  # 最古のデータ
    ('01', '20201103', 1, '2020-11-03'),  # 既に確認済み
    ('19', '20241102', 1, '2024-11-02'),  # 以前失敗したデータ
    ('01', '20251104', 1, '2025-11-04'),  # 最新データ
]

print('=== 過去データ取得可能範囲テスト ===')
print()

results = []

for venue, date, race, label in test_cases:
    print(f'テスト: {label} 会場{venue} {race}R ... ', end='')

    try:
        race_data = scraper.get_race_result_complete(venue, date, race)

        if race_data and 'st_times' in race_data and race_data['st_times']:
            st_count = len(race_data['st_times'])
            print(f'[OK] ST {st_count}/6')
            results.append((label, True, st_count))
        else:
            print('[NG] データなし')
            results.append((label, False, 0))
    except Exception as e:
        print(f'[ERROR] {str(e)[:50]}')
        results.append((label, False, 0))

print()
print('=== テスト結果サマリー ===')
for label, success, st_count in results:
    status = f'[OK] ST {st_count}/6' if success else '[NG]'
    print(f'  {label}: {status}')

success_count = sum(1 for _, success, _ in results if success)
print()
print(f'成功: {success_count}/{len(test_cases)}')
