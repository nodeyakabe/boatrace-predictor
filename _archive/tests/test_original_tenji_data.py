#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オリジナル展示データ取得テスト
"""

import sys
sys.path.append('src')

from scraper.original_tenji_browser import OriginalTenjiBrowserScraper

print("="*80)
print("オリジナル展示データ取得テスト")
print("="*80)

# 2025-11-17の戸田1Rをテスト
venue_code = "02"
race_date = "2025-11-17"
race_number = 1

scraper = OriginalTenjiBrowserScraper(headless=True, timeout=30)

print(f"\n対象: {venue_code}場 {race_number}R ({race_date})")
print("データ取得中...\n")

try:
    tenji_data = scraper.get_original_tenji(venue_code, race_date, race_number)

    if tenji_data:
        print("[OK] データ取得成功\n")
        print("取得データの内容:")
        for boat_num, data in sorted(tenji_data.items()):
            print(f"\n{boat_num}号艇:")
            print(f"  Type: {type(data)}")
            print(f"  Data: {data}")
            if isinstance(data, dict):
                print(f"  Keys: {data.keys()}")
                for key, value in data.items():
                    print(f"    {key}: {value} (type: {type(value)})")
    else:
        print("[ERROR] データ取得失敗 (Noneが返された)")

except Exception as e:
    print(f"[ERROR] エラーが発生: {e}")
    import traceback
    traceback.print_exc()

scraper.close()

print("\n" + "="*80)
