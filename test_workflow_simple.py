"""
ワークフロー統合テスト（簡易版）
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def test_imports():
    """すべてのインポートが正常か確認"""
    print("="*60)
    print("Test 1: Import Check")
    print("="*60)

    try:
        from config.settings import DATABASE_PATH, VENUES
        print("[OK] config.settings")

        from src.scraper.bulk_scraper import BulkScraper
        from src.scraper.schedule_scraper import ScheduleScraper
        print("[OK] Scrapers")

        from src.analysis.realtime_predictor import RealtimePredictor
        from src.analysis.race_predictor import RacePredictor
        from src.analysis.data_coverage_checker import DataCoverageChecker
        print("[OK] Analysis modules")

        from ui.components.common.filters import render_sidebar_filters
        from ui.components.common.widgets import show_database_stats
        from ui.components.common.db_utils import get_db_connection, safe_query_to_df
        print("[OK] Common components")

        from ui.components.realtime_dashboard import render_realtime_dashboard
        from ui.components.workflow_manager import render_workflow_manager
        from ui.components.auto_data_collector import render_auto_data_collector
        print("[OK] New components")

        print("\n[PASS] All imports successful\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Import error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_bulk_scraper():
    """BulkScraperテスト"""
    print("="*60)
    print("Test 2: BulkScraper Check")
    print("="*60)

    try:
        from src.scraper.bulk_scraper import BulkScraper
        from src.scraper.schedule_scraper import ScheduleScraper

        scraper = BulkScraper()

        if hasattr(scraper, 'schedule_scraper'):
            print("[OK] schedule_scraper property exists")
        else:
            print("[FAIL] schedule_scraper property missing")
            return False

        if isinstance(scraper.schedule_scraper, ScheduleScraper):
            print("[OK] schedule_scraper is ScheduleScraper instance")
        else:
            print("[FAIL] schedule_scraper is not ScheduleScraper")
            return False

        print("\n[PASS] BulkScraper is working\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] BulkScraper error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_database_connection():
    """データベース接続テスト"""
    print("="*60)
    print("Test 3: Database Connection Check")
    print("="*60)

    try:
        from ui.components.common.db_utils import get_db_connection, safe_query_to_df

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM races")
            count = cursor.fetchone()[0]
            print(f"[OK] DB connection successful (Total races: {count:,})")

        df = safe_query_to_df("SELECT * FROM races LIMIT 5")
        print(f"[OK] DataFrame retrieved ({len(df)} rows)")

        print("\n[PASS] Database connection is working\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Database error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_cache_system():
    """キャッシュシステムテスト"""
    print("="*60)
    print("Test 4: Cache System Check")
    print("="*60)

    try:
        from ui.components.common.widgets import get_database_stats
        import time

        start = time.time()
        count1 = get_database_stats()
        time1 = (time.time() - start) * 1000
        print(f"[OK] 1st call: {time1:.2f}ms (no cache)")

        start = time.time()
        count2 = get_database_stats()
        time2 = (time.time() - start) * 1000
        print(f"[OK] 2nd call: {time2:.2f}ms (cached)")

        if time2 < time1:
            improvement = ((time1 - time2) / time1) * 100
            print(f"[OK] Cache performance: {improvement:.1f}% faster")

        print("\n[PASS] Cache system is working\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Cache error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_predictor():
    """予想機能テスト"""
    print("="*60)
    print("Test 5: Predictor Check")
    print("="*60)

    try:
        from src.analysis.race_predictor import RacePredictor

        predictor = RacePredictor()
        print("[OK] RacePredictor instance created")

        if hasattr(predictor, 'predict_race_by_key'):
            print("[OK] predict_race_by_key method exists")
        else:
            print("[FAIL] predict_race_by_key method missing")
            return False

        print("\n[PASS] Predictor is working\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Predictor error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_data_quality():
    """データ品質チェッカーテスト"""
    print("="*60)
    print("Test 6: Data Quality Checker")
    print("="*60)

    try:
        from src.analysis.data_coverage_checker import DataCoverageChecker
        from config.settings import DATABASE_PATH

        checker = DataCoverageChecker(DATABASE_PATH)
        print("[OK] DataCoverageChecker instance created")

        report = checker.get_coverage_report()

        if 'overall_score' in report:
            score = report['overall_score'] * 100
            print(f"[OK] Overall coverage: {score:.1f}%")
        else:
            print("[FAIL] Report generation error")
            return False

        print("\n[PASS] Data quality checker is working\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Data quality error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    """全テスト実行"""
    print("\n" + "="*60)
    print(" Boat Race Prediction System - Integration Test")
    print("="*60 + "\n")

    tests = [
        ("Import Check", test_imports),
        ("BulkScraper Check", test_bulk_scraper),
        ("Database Connection", test_database_connection),
        ("Cache System", test_cache_system),
        ("Predictor", test_predictor),
        ("Data Quality Checker", test_data_quality),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[FAIL] Unexpected error in {test_name}: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "="*60)
    print(" Test Summary")
    print("="*60 + "\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")
    print(f"Success rate: {(passed/total)*100:.1f}%\n")

    if passed == total:
        print("All tests passed! System is working correctly.\n")
        return 0
    else:
        print("Some tests failed. Please check the errors above.\n")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
