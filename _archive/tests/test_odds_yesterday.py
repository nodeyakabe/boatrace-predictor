#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
昨日のオッズデータで動作テスト
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.playwright_odds_scraper import PlaywrightOddsScraper

def test_yesterday_odds():
    """昨日のオッズで動作テスト"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

    print("="*60)
    print(f"昨日（{yesterday}）のオッズ取得テスト")
    print("="*60)

    scraper = PlaywrightOddsScraper(headless=True, timeout=30000)

    # 戸田競艇場 1R
    odds = scraper.get_trifecta_odds('02', yesterday, 1)

    if odds:
        print(f"\n[OK] オッズ取得成功: {len(odds)}通り")

        # いくつか表示
        print("\n最初の10通り:")
        for i, (combo, odd) in enumerate(list(odds.items())[:10], 1):
            print(f"  {i:2d}. {combo}: {odd:,.1f}倍")

        # 統計
        odds_values = list(odds.values())
        print(f"\n統計:")
        print(f"  最小オッズ: {min(odds_values):,.1f}倍")
        print(f"  最大オッズ: {max(odds_values):,.1f}倍")
        print(f"  平均オッズ: {sum(odds_values)/len(odds_values):,.1f}倍")

        # 120通り揃っているか確認
        expected_combinations = []
        for first in range(1, 7):
            for second in range(1, 7):
                if second == first:
                    continue
                for third in range(1, 7):
                    if third == first or third == second:
                        continue
                    expected_combinations.append(f"{first}-{second}-{third}")

        missing = set(expected_combinations) - set(odds.keys())
        if missing:
            print(f"\n[WARNING] 不足している組み合わせ: {len(missing)}通り")
            if len(missing) <= 10:
                for combo in sorted(missing):
                    print(f"  - {combo}")
        else:
            print(f"\n[OK] 全120通り揃っています")

        return True
    else:
        print("\n[ERROR] オッズ取得失敗")
        return False


if __name__ == "__main__":
    success = test_yesterday_odds()
    sys.exit(0 if success else 1)
