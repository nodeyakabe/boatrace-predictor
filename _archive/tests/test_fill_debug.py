#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fill_missing_data.py のデバッグテスト
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fill_missing_data import get_missing_data_races, fill_missing_data
from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

print("=== デバッグテスト開始 ===")

# 不足レースを取得
print("\n1. 不足レースを取得中...")
races = get_missing_data_races("2022-01-01", "2022-01-05", "details")
print(f"  取得完了: {len(races)}件")

if len(races) > 0:
    print(f"\n  サンプル (最初の3件):")
    for i, race in enumerate(races[:3]):
        print(f"    {i+1}. レースID{race[0]}: 会場{race[1]} {race[2]} {race[3]}R (タイプ: {race[4]})")

# スクレイパー作成
print("\n2. スクレイパーを作成...")
scraper = ImprovedResultScraperV4()
print("  作成完了")

# 1件テスト
if len(races) > 0:
    print(f"\n3. 1件のデータ取得テスト...")
    race = races[0]
    print(f"  対象: 会場{race[1]} {race[2]} {race[3]}R")

    result = fill_missing_data(race, scraper, "details")

    print(f"  結果:")
    print(f"    成功: {result['success']}")
    if not result['success']:
        print(f"    エラー: {result['error']}")

print("\n=== テスト完了 ===")
