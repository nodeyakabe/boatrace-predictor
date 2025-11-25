"""
ワークフロー統合テスト
新UIの主要機能が正常に動作するか確認
"""
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def test_imports():
    """すべてのインポートが正常か確認"""
    print("=" * 60)
    print("テスト1: インポートチェック")
    print("=" * 60)

    try:
        # 設定ファイル
        from config.settings import DATABASE_PATH, VENUES
        print("✅ config.settings - OK")

        # スクレイパー
        from src.scraper.bulk_scraper import BulkScraper
        from src.scraper.schedule_scraper import ScheduleScraper
        print("✅ スクレイパー - OK")

        # 分析モジュール
        from src.analysis.realtime_predictor import RealtimePredictor
        from src.analysis.race_predictor import RacePredictor
        from src.analysis.data_coverage_checker import DataCoverageChecker
        print("✅ 分析モジュール - OK")

        # UIコンポーネント
        from ui.components.common.filters import render_sidebar_filters
        from ui.components.common.widgets import show_database_stats
        from ui.components.common.db_utils import get_db_connection, safe_query_to_df
        print("✅ 共通コンポーネント - OK")

        from ui.components.realtime_dashboard import render_realtime_dashboard
        from ui.components.workflow_manager import render_workflow_manager
        from ui.components.auto_data_collector import render_auto_data_collector
        print("✅ 新規コンポーネント - OK")

        print("\n✅ すべてのインポート成功\n")
        return True

    except Exception as e:
        print(f"\n❌ インポートエラー: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_bulk_scraper():
    """BulkScraperのschedule_scraperプロパティをテスト"""
    print("=" * 60)
    print("テスト2: BulkScraperチェック")
    print("=" * 60)

    try:
        from src.scraper.bulk_scraper import BulkScraper

        scraper = BulkScraper()

        # schedule_scraperプロパティが存在するか
        if hasattr(scraper, 'schedule_scraper'):
            print("✅ schedule_scraperプロパティ存在")
        else:
            print("❌ schedule_scraperプロパティが存在しない")
            return False

        # ScheduleScraperのインスタンスか
        from src.scraper.schedule_scraper import ScheduleScraper
        if isinstance(scraper.schedule_scraper, ScheduleScraper):
            print("✅ ScheduleScraperのインスタンス")
        else:
            print("❌ ScheduleScraperのインスタンスではない")
            return False

        print("\n✅ BulkScraper正常\n")
        return True

    except Exception as e:
        print(f"\n❌ BulkScraperエラー: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_database_connection():
    """データベース接続をテスト"""
    print("=" * 60)
    print("テスト3: データベース接続チェック")
    print("=" * 60)

    try:
        from ui.components.common.db_utils import get_db_connection, safe_query_to_df

        # コンテキストマネージャーのテスト
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM races")
            count = cursor.fetchone()[0]
            print(f"✅ DB接続成功（総レース数: {count:,}件）")

        # safe_query_to_dfのテスト
        df = safe_query_to_df("SELECT * FROM races LIMIT 5")
        print(f"✅ DataFrame取得成功（{len(df)}行）")

        print("\n✅ データベース接続正常\n")
        return True

    except Exception as e:
        print(f"\n❌ データベースエラー: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_cache_system():
    """キャッシュシステムをテスト"""
    print("=" * 60)
    print("テスト4: キャッシュシステムチェック")
    print("=" * 60)

    try:
        from ui.components.common.widgets import get_database_stats
        import time

        # 1回目（キャッシュなし）
        start = time.time()
        count1 = get_database_stats()
        time1 = (time.time() - start) * 1000
        print(f"✅ 1回目: {time1:.2f}ms（キャッシュなし）")

        # 2回目（キャッシュあり）
        start = time.time()
        count2 = get_database_stats()
        time2 = (time.time() - start) * 1000
        print(f"✅ 2回目: {time2:.2f}ms（キャッシュあり）")

        if time2 < time1:
            improvement = ((time1 - time2) / time1) * 100
            print(f"✅ キャッシュ効果: {improvement:.1f}%高速化")

        print("\n✅ キャッシュシステム正常\n")
        return True

    except Exception as e:
        print(f"\n❌ キャッシュエラー: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_predictor_basic():
    """予想機能の基本動作をテスト"""
    print("=" * 60)
    print("テスト5: 予想機能チェック")
    print("=" * 60)

    try:
        from src.analysis.race_predictor import RacePredictor

        predictor = RacePredictor()
        print("✅ RacePredictorインスタンス生成")

        # 基本的なメソッドが存在するか
        if hasattr(predictor, 'predict_race_by_key'):
            print("✅ predict_race_by_keyメソッド存在")
        else:
            print("❌ predict_race_by_keyメソッドが存在しない")
            return False

        print("\n✅ 予想機能正常\n")
        return True

    except Exception as e:
        print(f"\n❌ 予想機能エラー: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_data_quality_checker():
    """データ品質チェッカーをテスト"""
    print("=" * 60)
    print("テスト6: データ品質チェッカー")
    print("=" * 60)

    try:
        from src.analysis.data_coverage_checker import DataCoverageChecker
        from config.settings import DATABASE_PATH

        checker = DataCoverageChecker(DATABASE_PATH)
        print("✅ DataCoverageCheckerインスタンス生成")

        report = checker.get_coverage_report()

        if 'overall_score' in report:
            score = report['overall_score'] * 100
            print(f"✅ 全体充足率: {score:.1f}%")
        else:
            print("❌ レポート生成エラー")
            return False

        print("\n✅ データ品質チェッカー正常\n")
        return True

    except Exception as e:
        print(f"\n❌ データ品質チェッカーエラー: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    """すべてのテストを実行"""
    print("\n" + "=" * 60)
    print(" 競艇予想システム ワークフロー統合テスト")
    print("=" * 60 + "\n")

    tests = [
        ("インポートチェック", test_imports),
        ("BulkScraperチェック", test_bulk_scraper),
        ("データベース接続チェック", test_database_connection),
        ("キャッシュシステムチェック", test_cache_system),
        ("予想機能チェック", test_predictor_basic),
        ("データ品質チェッカー", test_data_quality_checker),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}で予期しないエラー: {e}")
            results.append((test_name, False))

    # 結果サマリー
    print("\n" + "=" * 60)
    print(" テスト結果サマリー")
    print("=" * 60 + "\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\n合計: {passed}/{total} テスト成功")
    print(f"成功率: {(passed/total)*100:.1f}%\n")

    if passed == total:
        print("🎉 すべてのテストに合格しました！")
        print("✅ システムは正常に動作しています\n")
        return 0
    else:
        print("⚠️ 一部のテストが失敗しました")
        print("❌ 失敗したテストを確認してください\n")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
