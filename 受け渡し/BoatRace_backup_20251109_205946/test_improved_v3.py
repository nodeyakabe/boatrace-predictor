"""
改善版V3スクレイパーのテスト
STタイムに決まり手が混入している問題の修正確認
"""

import sys
sys.path.insert(0, '.')

from src.scraper.result_scraper_improved_v3 import ImprovedResultScraperV3

def test_improved_v3():
    """改善版V3をテスト"""

    print("="*80)
    print("Testing ImprovedResultScraperV3")
    print("="*80)

    # 問題が発生したレース
    venue = "01"
    date = "20251031"
    race = 1

    print(f"\nTest Case: Venue {venue}, Date {date}, Race {race}")
    print("  Expected: 6/6 ST times (Pit 3 was missing in V2)")
    print("-"*80)

    scraper = ImprovedResultScraperV3()

    try:
        print("Fetching data...")
        result = scraper.get_race_result_complete(venue, date, race)

        if result:
            print("\n[OK] Data retrieved!")

            st_times = result.get('st_times', {})
            st_status = result.get('st_status', {})
            actual_courses = result.get('actual_courses', {})

            print(f"\nST Times: {len(st_times)}/6 boats")
            print(f"Actual Courses: {len(actual_courses)}/6 boats")

            if st_times:
                print(f"\nST Time Details:")
                for pit in range(1, 7):
                    if pit in st_times:
                        st = st_times[pit]
                        status = st_status.get(pit, 'unknown')

                        status_label = ""
                        if status == 'flying':
                            status_label = " [FLYING]"
                        elif status == 'late':
                            status_label = " [LATE]"

                        print(f"  Pit {pit}: {st:.2f}{status_label}")
                    else:
                        print(f"  Pit {pit}: MISSING")

            # テスト判定
            if len(st_times) == 6:
                print("\n[SUCCESS] All 6 ST times retrieved!")
                print("  V3 fixed the issue!")
                return True
            else:
                missing = [p for p in range(1, 7) if p not in st_times]
                print(f"\n[FAIL] Only {len(st_times)}/6 ST times")
                print(f"  Missing pits: {missing}")
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
    success = test_improved_v3()
    print("\n" + "="*80)
    if success:
        print("Test PASSED - V3 scraper is working correctly!")
    else:
        print("Test FAILED - V3 still has issues")
    print("="*80)

    sys.exit(0 if success else 1)
