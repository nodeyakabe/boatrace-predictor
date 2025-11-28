#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
江戸川公式HPからのオリジナル展示取得テスト

Boatersで取得できなかった江戸川を、公式HPから取得できるか試す
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.venue_tenji_scraper import VenueTenjiScraper


def test_edogawa_venue_hp():
    """江戸川公式HPテスト"""
    print("="*70)
    print("江戸川公式HP オリジナル展示取得テスト")
    print("="*70)
    print()

    venue_code = "03"  # 江戸川
    race_date = "2025-11-27"
    race_number = 1

    print(f"テスト対象:")
    print(f"  会場: {venue_code} (江戸川)")
    print(f"  日付: {race_date}")
    print(f"  レース: {race_number}R")
    print()
    print("注意: Boatersサイトでは取得できなかったレース")
    print()

    scraper = None
    try:
        print("江戸川公式HPスクレイパーを初期化中...")
        scraper = VenueTenjiScraper(headless=True, timeout=15)
        print("✓ 初期化完了\n")

        # URL確認
        venue_info = scraper.VENUE_URLS.get(venue_code, {})
        if venue_info:
            date_str = race_date.replace('-', '')  # 20251127
            url = venue_info['url_pattern'].format(date=date_str, race=race_number)
            print(f"アクセスURL:")
            print(f"  {url}")
            print()
        else:
            print("✗ 会場情報が見つかりません")
            return

        print("データ取得中...")
        result = scraper.get_original_tenji(venue_code, race_date, race_number)

        print()
        print("-" * 70)
        print("取得結果:")
        print("-" * 70)

        if result:
            print(f"✓ データ取得成功!")
            print(f"  データソース: 江戸川公式HP")
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
            print()
            print("🎉 統合収集器の価値を実証！")
            print("   Boatersで取れなくても、公式HPから取得できました")
        else:
            print("✗ データ取得失敗")
            print()
            print("考えられる原因:")
            print("  1. 公式HPでもデータが公開されていない")
            print("  2. レースが終了済みでデータが削除された")
            print("  3. HTML構造が想定と異なる（パーサー調整が必要）")
            print("  4. URLパターンが間違っている")

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
    test_edogawa_venue_hp()
