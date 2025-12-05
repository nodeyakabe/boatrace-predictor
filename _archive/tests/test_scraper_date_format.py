"""
スクレイパーの日付フォーマットテスト
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.scraper.schedule_scraper import ScheduleScraper
from src.scraper.bulk_scraper import BulkScraper

def test_schedule_date_format():
    """スケジュールの日付フォーマット確認"""
    print("="*70)
    print("スケジュールの日付フォーマット確認")
    print("="*70)

    try:
        schedule_scraper = ScheduleScraper()
        today_schedule = schedule_scraper.get_today_schedule()

        if today_schedule:
            print(f"\n本日の開催: {len(today_schedule)}会場")

            for venue_code, race_date in today_schedule.items():
                print(f"\n会場コード: {venue_code}")
                print(f"  日付: {race_date}")
                print(f"  型: {type(race_date)}")
                print(f"  長さ: {len(race_date)}")
                print(f"  数字のみ: {race_date.isdigit()}")

                # フォーマット検証
                if len(race_date) == 8 and race_date.isdigit():
                    year = race_date[:4]
                    month = race_date[4:6]
                    day = race_date[6:8]
                    print(f"  解析: {year}年{month}月{day}日")
                    print(f"  [OK] フォーマットは正常です")
                else:
                    print(f"  [NG] フォーマットが不正です")

            return True
        else:
            print("\n本日の開催がありません")
            return True

    except Exception as e:
        print(f"[NG] エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_single_race_fetch():
    """1レースのみ取得テスト"""
    print("\n" + "="*70)
    print("1レース取得テスト")
    print("="*70)

    try:
        schedule_scraper = ScheduleScraper()
        today_schedule = schedule_scraper.get_today_schedule()

        if not today_schedule:
            print("本日の開催がないため、スキップします")
            return True

        # 最初の会場の1Rのみ取得
        venue_code = list(today_schedule.keys())[0]
        race_date = today_schedule[venue_code]

        print(f"\nテスト対象:")
        print(f"  会場コード: {venue_code}")
        print(f"  日付: {race_date}")
        print(f"  レース: 1R")

        from src.scraper.race_scraper_v2 import RaceScraperV2

        scraper = RaceScraperV2()

        print("\nデータ取得開始...")
        race_data = scraper.get_race_card(venue_code, race_date, 1)

        if race_data:
            print("[OK] データ取得成功")
            print(f"  選手数: {len(race_data.get('entries', []))}名")
            return True
        else:
            print("[NG] データが取得できませんでした")
            return False

    except Exception as e:
        print(f"[NG] エラー: {e}")
        print(f"エラー型: {type(e).__name__}")
        print(f"エラー番号: {getattr(e, 'errno', 'なし')}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# スクレイパー日付フォーマットテスト")
    print("#"*70)

    results = []

    # テスト1: 日付フォーマット確認
    results.append(("日付フォーマット確認", test_schedule_date_format()))

    # テスト2: 1レース取得
    results.append(("1レース取得", test_single_race_fetch()))

    # 結果サマリー
    print("\n" + "="*70)
    print("テスト結果サマリー")
    print("="*70)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")

    total_tests = len(results)
    passed_tests = sum(1 for _, result in results if result)

    print(f"\n合計: {passed_tests}/{total_tests} テスト成功")

    print("\n" + "#"*70)
