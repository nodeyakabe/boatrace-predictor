"""
最も基本的なスクレイパーテスト
ResultScraperの基本動作を確認
"""

import sys
sys.path.insert(0, '.')

from src.scraper.result_scraper import ResultScraper

def test_basic():
    """基本的なテスト"""

    print("="*80)
    print("Testing Basic ResultScraper")
    print("="*80)

    venue = "01"
    date = "20151109"
    race = 1

    print(f"\nTest: Venue {venue}, Date {date}, Race {race}")
    print("-"*80)

    scraper = ResultScraper()

    try:
        print("Fetching data with get_race_result_complete...")
        result = scraper.get_race_result_complete(venue, date, race)

        if result:
            print("\n[OK] Data retrieved!")
            print(f"  Results: {len(result.get('results', []))}")
            print(f"  ST Times: {len(result.get('st_times', {}))}")
            print(f"  Actual Courses: {len(result.get('actual_courses', {}))}")
            print(f"  Is Invalid: {result.get('is_invalid')}")

            st_times = result.get('st_times', {})
            if st_times:
                print(f"\n  ST Times detail: {st_times}")

            return True
        else:
            print("\n[ERROR] No data returned")

            # URLを確認
            from config.settings import BOATRACE_OFFICIAL_URL
            url = f"{BOATRACE_OFFICIAL_URL}/raceresult"
            params = {"rno": race, "jcd": venue, "hd": date}
            print(f"\nURL: {url}")
            print(f"Params: {params}")

            return False

    except Exception as e:
        print(f"\n[ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        scraper.close()

if __name__ == '__main__':
    success = test_basic()
    print("\n" + "="*80)
    print("Test PASSED" if success else "Test FAILED")
    print("="*80)
