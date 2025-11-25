"""
改善版スクレイパーの簡単なテスト
1レースだけ取得して動作確認
"""

import sys
sys.path.insert(0, '.')

from src.scraper.result_scraper_improved import ImprovedResultScraper
import time

def test_single_race():
    """1レースだけテスト"""

    print("="*80)
    print("Testing Improved Scraper - Single Race")
    print("="*80)

    # テストケース: 2015年のデータ
    venue = "01"
    date = "20151109"
    race = 1

    print(f"\nTest: Venue {venue}, Date {date}, Race {race}")
    print("-"*80)

    scraper = ImprovedResultScraper()

    try:
        print("Fetching data...")
        result = scraper.get_race_result_complete(venue, date, race)

        if result:
            print("\n[OK] Data retrieved successfully!")

            st_times = result.get('st_times', {})
            st_status = result.get('st_status', {})
            actual_courses = result.get('actual_courses', {})
            results = result.get('results', [])

            print(f"\nResults: {len(results)} boats")
            print(f"ST Times: {len(st_times)}/6 boats")
            print(f"Actual Courses: {len(actual_courses)}/6 boats")

            if st_times:
                print(f"\nST Time Details:")
                for pit in range(1, 7):
                    if pit in st_times:
                        st = st_times[pit]
                        status = st_status.get(pit, 'unknown')

                        if status == 'flying':
                            print(f"  Pit {pit}: {st:.2f} [FLYING]")
                        elif status == 'late':
                            print(f"  Pit {pit}: {st:.2f} [LATE]")
                        else:
                            print(f"  Pit {pit}: {st:.2f}")
                    else:
                        print(f"  Pit {pit}: MISSING")

            # 判定
            if len(st_times) >= 5:
                print("\n[SUCCESS] Scraper is working!")
                return True
            else:
                print(f"\n[WARN] Only {len(st_times)}/6 ST times collected")
                return False
        else:
            print("\n[ERROR] No data returned")
            return False

    except Exception as e:
        print(f"\n[ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        scraper.close()

if __name__ == '__main__':
    success = test_single_race()
    print("\n" + "="*80)
    if success:
        print("Test PASSED - Scraper is working correctly")
    else:
        print("Test FAILED - Scraper needs fixes")
    print("="*80)

    sys.exit(0 if success else 1)
