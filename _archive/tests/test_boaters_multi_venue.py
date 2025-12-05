#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Boatersサイト 複数会場テスト

11/27開催の全会場でデータ取得を試行
"""
import sys
import os
import sqlite3

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper
from config.settings import DATABASE_PATH


def get_venues_on_date(date_str):
    """指定日の開催会場を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT venue_code
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code
    """, [date_str])

    venues = [row[0] for row in cursor.fetchall()]
    conn.close()
    return venues


def test_multi_venue():
    """複数会場でテスト"""
    print("="*70)
    print("Boatersサイト 複数会場テスト")
    print("="*70)
    print()

    target_date = "2025-11-27"
    race_number = 1

    # 開催会場を取得
    venues = get_venues_on_date(target_date)
    print(f"対象日: {target_date}")
    print(f"開催会場数: {len(venues)}")
    print(f"テストレース: {race_number}R")
    print()

    scraper = None
    results = {
        'success': [],
        'no_data': [],
        'error': []
    }

    try:
        print("Boatersスクレイパーを初期化中...")
        scraper = OriginalTenjiBrowserScraper(headless=True, timeout=15)
        print("✓ 初期化完了\n")

        for idx, venue_code in enumerate(venues, 1):
            venue_name = scraper.VENUE_CODE_TO_NAME.get(venue_code, '不明')
            print(f"[{idx}/{len(venues)}] 会場{venue_code} ({venue_name})...", end=' ')

            try:
                result = scraper.get_original_tenji(venue_code, target_date, race_number)

                if result and len(result) > 0:
                    results['success'].append(venue_code)
                    print(f"✓ 成功 ({len(result)}艇)")
                else:
                    results['no_data'].append(venue_code)
                    print("○ データなし")

            except Exception as e:
                results['error'].append(venue_code)
                print(f"✗ エラー: {str(e)[:50]}")

        print()
        print("="*70)
        print("テスト結果サマリー")
        print("="*70)
        print(f"対象会場: {len(venues)}")
        print(f"成功: {len(results['success'])}会場")
        print(f"データなし: {len(results['no_data'])}会場")
        print(f"エラー: {len(results['error'])}会場")
        print()

        success_rate = len(results['success']) / len(venues) * 100 if venues else 0
        print(f"成功率: {success_rate:.1f}%")

        if results['success']:
            print()
            print("成功した会場:")
            for v in results['success']:
                venue_name = scraper.VENUE_CODE_TO_NAME.get(v, '不明')
                print(f"  会場{v} ({venue_name})")

        if results['no_data']:
            print()
            print("データなしの会場:")
            for v in results['no_data']:
                venue_name = scraper.VENUE_CODE_TO_NAME.get(v, '不明')
                print(f"  会場{v} ({venue_name})")

    except Exception as e:
        print(f"✗ エラー発生: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if scraper:
            print("\nスクレイパーを終了中...")
            scraper.close()
            print("✓ 終了完了")

    print()
    print("="*70)


if __name__ == "__main__":
    test_multi_venue()
