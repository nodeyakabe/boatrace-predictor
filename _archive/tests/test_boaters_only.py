#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Boatersサイト単体テスト

統合収集器を使わず、Boatersスクレイパーのみで動作確認
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper


def test_boaters_scraper():
    """Boatersスクレイパー単体テスト"""
    print("="*70)
    print("Boatersサイト オリジナル展示スクレイパー 単体テスト")
    print("="*70)
    print()

    # テスト対象
    venue_code = "22"  # 福岡
    race_date = "2025-11-27"
    race_number = 1

    print(f"テスト対象:")
    print(f"  会場: {venue_code} (福岡)")
    print(f"  日付: {race_date}")
    print(f"  レース: {race_number}R")
    print()

    scraper = None
    try:
        print("Boatersスクレイパーを初期化中...")
        scraper = OriginalTenjiBrowserScraper(headless=True, timeout=15)
        print("✓ 初期化完了\n")

        # URL確認
        venue_name = scraper.VENUE_CODE_TO_NAME.get(venue_code, '不明')
        url = f"https://boaters-boatrace.com/race/{venue_name}/{race_date}/{race_number}R/last-minute?last-minute-content=original-tenji"
        print(f"アクセスURL:")
        print(f"  {url}")
        print()

        print("データ取得中...")
        result = scraper.get_original_tenji(venue_code, race_date, race_number)

        print()
        print("-" * 70)
        print("取得結果:")
        print("-" * 70)

        if result:
            print(f"✓ データ取得成功!")
            print()

            # 各艇のデータを表示
            boat_count = 0
            for boat_num in range(1, 7):
                if boat_num in result:
                    boat_data = result[boat_num]
                    boat_count += 1
                    print(f"  {boat_num}号艇:")
                    print(f"    直線タイム: {boat_data.get('chikusen_time', 'なし')}")
                    print(f"    1周タイム: {boat_data.get('isshu_time', 'なし')}")
                    print(f"    回り足タイム: {boat_data.get('mawariashi_time', 'なし')}")

            print()
            print(f"  取得艇数: {boat_count}/6")
        else:
            print("✗ データ取得失敗")
            print()
            print("考えられる原因:")
            print("  1. レースが終了済みでデータが削除された")
            print("  2. BoatersサイトのHTML構造が変更された")
            print("  3. データがまだ公開されていない")
            print("  4. 会場コードとBoaters会場名のマッピングが間違っている")

        # マッピング確認
        print()
        print("-" * 70)
        print("会場コードマッピング確認:")
        print("-" * 70)
        print(f"  会場コード: {venue_code}")
        print(f"  Boaters会場名: {venue_name}")
        print(f"  正しいマッピング: {'✓' if venue_name != '不明' else '✗'}")

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
    print("テスト完了")
    print("="*70)


if __name__ == "__main__":
    test_boaters_scraper()
