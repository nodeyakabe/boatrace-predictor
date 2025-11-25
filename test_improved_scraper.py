"""
改善版スクレイパーのテストスクリプト
F/L対応のImprovedResultScraperをテスト
"""

from src.scraper.result_scraper_improved import ImprovedResultScraper
import time

def test_improved_scraper():
    """改善版スクレイパーをテスト"""

    # テストケース: STタイムが部分的に欠損しているレース
    test_cases = [
        {"venue": "01", "date": "20151109", "race": 1, "label": "Partial Missing (5/6)"},
        {"venue": "01", "date": "20160117", "race": 1, "label": "Complete Missing (0/6)"},
        {"venue": "01", "date": "20151217", "race": 6, "label": "Complete Missing (0/6)"},
    ]

    scraper = ImprovedResultScraper()

    print("="*100)
    print("Improved Scraper Test - F/L Support")
    print("="*100)

    for i, test in enumerate(test_cases, 1):
        print(f"\n[Test {i}] {test['label']}")
        print(f"  Venue: {test['venue']}, Date: {test['date']}, Race: {test['race']}")
        print("-"*100)

        try:
            result = scraper.get_race_result_complete(
                test['venue'],
                test['date'],
                test['race']
            )

            if result:
                st_times = result.get('st_times', {})
                st_status = result.get('st_status', {})
                actual_courses = result.get('actual_courses', {})

                print(f"  Results: {len(result.get('results', []))} boats")
                print(f"  ST Times: {len(st_times)}/6 boats collected")

                if st_times:
                    print(f"    ST Times: {st_times}")
                    print(f"    ST Status: {st_status}")

                    # フライング・出遅れの検出
                    flying = [p for p, s in st_status.items() if s == 'flying']
                    late = [p for p, s in st_status.items() if s == 'late']
                    normal = [p for p, s in st_status.items() if s == 'normal']

                    if flying:
                        print(f"    Flying: Pit {flying}")
                    if late:
                        print(f"    Late: Pit {late}")
                    print(f"    Normal: {len(normal)} boats")
                else:
                    print(f"    NO ST TIMES")

                print(f"  Actual Courses: {len(actual_courses)}/6 boats")
                print(f"  Is Invalid: {result.get('is_invalid', False)}")

                # 結果判定
                if len(st_times) == 6:
                    print(f"  Status: [OK] All 6 ST times collected (including F/L)")
                elif len(st_times) >= 5:
                    print(f"  Status: [WARN] {len(st_times)}/6 ST times collected")
                    missing = [p for p in range(1, 7) if p not in st_times]
                    print(f"  Missing pits: {missing}")
                else:
                    print(f"  Status: [NG] Only {len(st_times)}/6 collected")

            else:
                print(f"  Status: [NG] No result data returned")

        except Exception as e:
            print(f"  Status: [NG] EXCEPTION - {e}")
            import traceback
            traceback.print_exc()

        if i < len(test_cases):
            time.sleep(1)

    scraper.close()

    print("\n" + "="*100)
    print("Test Complete")
    print("="*100)


if __name__ == '__main__':
    test_improved_scraper()
