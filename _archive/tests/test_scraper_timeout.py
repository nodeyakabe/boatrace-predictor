"""
スクレイパーのタイムアウト動作をテストする
"""
import os
import sys
import time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(__file__)
sys.path.insert(0, PROJECT_ROOT)

def test_single_venue_fetch():
    """単一会場のデータ取得をテスト"""
    print("=" * 60)
    print("単一会場データ取得テスト")
    print("=" * 60)

    from src.scraper.bulk_scraper import BulkScraper

    scraper = BulkScraper()
    today = datetime.now().strftime('%Y-%m-%d')

    # 会場01（桐生）を取得してみる
    venue_code = "01"

    print(f"会場: {venue_code}")
    print(f"日付: {today}")
    print(f"開始時刻: {datetime.now().strftime('%H:%M:%S')}")

    start = time.time()

    try:
        result = scraper.fetch_multiple_venues(
            venue_codes=[venue_code],
            race_date=today,
            race_count=12
        )

        elapsed = time.time() - start
        print(f"\n終了時刻: {datetime.now().strftime('%H:%M:%S')}")
        print(f"所要時間: {elapsed:.1f}秒")
        print(f"取得レース数: {len(result.get(venue_code, []))}")

    except Exception as e:
        elapsed = time.time() - start
        print(f"\nエラー発生:")
        print(f"  エラー内容: {e}")
        print(f"  経過時間: {elapsed:.1f}秒")
        import traceback
        traceback.print_exc()

    finally:
        scraper.close()


def test_schedule_scraper():
    """スケジュールスクレイパーをテスト"""
    print("\n" + "=" * 60)
    print("スケジュールスクレイパーテスト")
    print("=" * 60)

    from src.scraper.schedule_scraper import ScheduleScraper

    scraper = ScheduleScraper()

    print(f"開始時刻: {datetime.now().strftime('%H:%M:%S')}")
    start = time.time()

    try:
        schedule = scraper.get_today_schedule()

        elapsed = time.time() - start
        print(f"終了時刻: {datetime.now().strftime('%H:%M:%S')}")
        print(f"所要時間: {elapsed:.1f}秒")

        if schedule:
            print(f"\n今日開催の会場数: {len(schedule)}")
            print("会場リスト:")
            for venue_code in sorted(schedule.keys()):
                print(f"  - {venue_code}")
        else:
            print("\n開催会場が見つかりませんでした")

    except Exception as e:
        elapsed = time.time() - start
        print(f"\nエラー発生:")
        print(f"  エラー内容: {e}")
        print(f"  経過時間: {elapsed:.1f}秒")
        import traceback
        traceback.print_exc()

    finally:
        scraper.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='スクレイパータイムアウトテスト')
    parser.add_argument('--test', choices=['schedule', 'venue', 'both'], default='both',
                        help='実行するテスト')

    args = parser.parse_args()

    if args.test in ['schedule', 'both']:
        test_schedule_scraper()

    if args.test in ['venue', 'both']:
        test_single_venue_fetch()

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
