#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BeforeInfo直接テスト
"""

import sys
sys.path.insert(0, 'src')

from scraper.beforeinfo_scraper import BeforeInfoScraper

print("=" * 70)
print("BeforeInfoScraper直接テスト")
print("=" * 70)

# 2025-11-17の戸田1Rをテスト
venue_code = "02"
date_str = "20251117"
race_number = 1

scraper = BeforeInfoScraper()

print(f"\n対象: {venue_code}場 {race_number}R ({date_str})")
print(f"URL: https://www.boatrace.jp/owpc/pc/race/beforeinfo?jcd={venue_code}&hd={date_str}&rno={race_number}\n")

result = scraper.get_race_beforeinfo(venue_code, date_str, race_number)

if result:
    print("[OK] データ取得成功\n")

    print("展示タイム:")
    for pit, time_val in sorted(result['exhibition_times'].items()):
        print(f"  {pit}号艇: {time_val}秒")

    print("\nチルト角度:")
    for pit, tilt in sorted(result['tilt_angles'].items()):
        print(f"  {pit}号艇: {tilt}度")

    print("\n部品交換:")
    for pit, parts in sorted(result['parts_replacements'].items()):
        print(f"  {pit}号艇: {parts}")
else:
    print("[ERROR] データ取得失敗")

scraper.close()

print("\n" + "=" * 70)
