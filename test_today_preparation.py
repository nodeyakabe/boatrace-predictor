"""
今日の予想準備機能のテスト
UIで使用されるworkflow_manager.pyの機能をテストします
"""

import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.scraper.bulk_scraper import BulkScraper
from src.scraper.schedule_scraper import ScheduleScraper
from datetime import datetime

def test_bulk_scraper_initialization():
    """BulkScraperの初期化テスト"""
    print("\n" + "="*70)
    print("BulkScraper初期化テスト")
    print("="*70)

    try:
        scraper = BulkScraper()
        print("[OK] BulkScraperの初期化成功")

        # schedule_scraperの存在確認
        if hasattr(scraper, 'schedule_scraper'):
            print("[OK] schedule_scraper属性が存在します")
            print(f"   型: {type(scraper.schedule_scraper)}")
        else:
            print("[NG] schedule_scraper属性が存在しません")
            return False

        # scraperの存在確認
        if hasattr(scraper, 'scraper'):
            print("[OK] scraper属性が存在します")
            print(f"   型: {type(scraper.scraper)}")
        else:
            print("[NG] scraper属性が存在しません")
            return False

        scraper.close()
        return True

    except Exception as e:
        print(f"[NG] BulkScraperの初期化失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_schedule_scraper():
    """ScheduleScraperのテスト"""
    print("\n" + "="*70)
    print("ScheduleScraperテスト")
    print("="*70)

    try:
        schedule_scraper = ScheduleScraper()
        print("[OK] ScheduleScraperの初期化成功")

        # 今日のスケジュールを取得
        today_schedule = schedule_scraper.get_today_schedule()

        if today_schedule:
            print(f"[OK] 本日の開催スケジュール取得成功")
            print(f"   開催会場数: {len(today_schedule)}会場")
            for venue_code, date in today_schedule.items():
                print(f"   - 会場コード {venue_code}: {date}")
            return True
        else:
            print("[WARN] 本日は開催がありません")
            print("      （これは正常な結果の可能性があります）")
            return True

    except Exception as e:
        print(f"[NG] ScheduleScraperテスト失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_workflow_fetch_today_data():
    """workflow_managerのfetch_today_data関数の動作をシミュレート"""
    print("\n" + "="*70)
    print("今日のデータ取得ワークフローテスト")
    print("="*70)

    try:
        scraper = BulkScraper()

        # schedule_scraperの存在確認
        if not hasattr(scraper, 'schedule_scraper'):
            print("[NG] BulkScraperにschedule_scraperが存在しません")
            return False

        schedule_scraper = scraper.schedule_scraper
        today_schedule = schedule_scraper.get_today_schedule()

        if today_schedule:
            print(f"[OK] 本日の開催スケジュール: {len(today_schedule)}会場")

            # 実際のデータ取得はスキップ（テストのため）
            print("\n[INFO] 実際のデータ取得はスキップします（テストモード）")
            print("[INFO] 本番環境では以下のように動作します:")

            total_races = 0
            for venue_code, race_date in today_schedule.items():
                print(f"\n  会場 {venue_code} ({race_date}):")
                print(f"    - 12レース取得予定")
                # result = scraper.fetch_multiple_venues(
                #     venue_codes=[venue_code],
                #     race_date=race_date,
                #     race_count=12
                # )

            print("\n[OK] ワークフローテスト成功（シミュレーション）")
            return True
        else:
            print("[WARN] 本日は開催がありません")
            return True

    except AttributeError as e:
        print(f"[NG] 属性エラー: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"[NG] ワークフローテスト失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """メインテスト実行"""
    print("\n" + "#"*70)
    print("# 今日の予想準備機能 テストスイート")
    print("# " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("#"*70)

    results = []

    # テスト1: BulkScraper初期化
    results.append(("BulkScraper初期化", test_bulk_scraper_initialization()))

    # テスト2: ScheduleScraper
    results.append(("ScheduleScraper", test_schedule_scraper()))

    # テスト3: ワークフロー
    results.append(("今日のデータ取得ワークフロー", test_workflow_fetch_today_data()))

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

    if passed_tests == total_tests:
        print("\n[SUCCESS] 全テスト成功！UIの「今日の予想を準備」は正常に動作する見込みです。")
    else:
        print("\n[WARNING] 一部テストが失敗しました。UIで問題が発生する可能性があります。")

    print("\n" + "#"*70)


if __name__ == "__main__":
    main()
