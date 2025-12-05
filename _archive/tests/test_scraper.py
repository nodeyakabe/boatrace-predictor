"""
スクレイパーのテストスクリプト
STタイムが欠損しているレースでスクレイパーが正しく動作するか確認
"""

from src.scraper.result_scraper import ResultScraper
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
import time

def test_scraper():
    """スクレイパーをテスト"""

    # analyze_data_quality.pyで見つかったサンプルレース
    test_cases = [
        # STタイムが完全に欠損しているレース (0/6)
        {"venue": "01", "date": "20151217", "race": 6, "label": "Complete Missing (0/6)"},
        {"venue": "01", "date": "20160117", "race": 1, "label": "Complete Missing (0/6)"},

        # STタイムが部分的に欠損しているレース (5/6)
        {"venue": "01", "date": "20151109", "race": 1, "label": "Partial Missing (5/6)"},
        {"venue": "01", "date": "20151109", "race": 2, "label": "Partial Missing (5/6)"},
    ]

    result_scraper = ResultScraper()

    print("="*100)
    print("Scraper Test - ST Time Collection")
    print("="*100)

    for i, test in enumerate(test_cases, 1):
        print(f"\n[Test {i}] {test['label']}")
        print(f"  Venue: {test['venue']}, Date: {test['date']}, Race: {test['race']}")
        print("-"*100)

        try:
            # 完全な結果を取得
            result = result_scraper.get_race_result_complete(
                test['venue'],
                test['date'],
                test['race']
            )

            if result:
                st_times = result.get('st_times', {})
                actual_courses = result.get('actual_courses', {})

                print(f"  Results: {len(result.get('results', []))} boats")
                print(f"  ST Times: {len(st_times)}/6 boats collected")
                if st_times:
                    print(f"    Details: {st_times}")
                else:
                    print(f"    Details: NO ST TIMES COLLECTED")

                print(f"  Actual Courses: {len(actual_courses)}/6 boats collected")
                if actual_courses:
                    print(f"    Details: {actual_courses}")

                print(f"  Is Invalid: {result.get('is_invalid', False)}")
                print(f"  Trifecta Odds: {result.get('trifecta_odds', 'N/A')}")

                # 6艇すべてのSTタイムが取得できたか
                if len(st_times) == 6:
                    print(f"  Status: [OK] SUCCESS - All 6 ST times collected")
                elif len(st_times) > 0:
                    print(f"  Status: [WARN] PARTIAL - Only {len(st_times)}/6 ST times collected")
                    missing_pits = [p for p in range(1, 7) if p not in st_times]
                    print(f"  Missing pits: {missing_pits}")
                else:
                    print(f"  Status: [NG] FAILED - No ST times collected")
            else:
                print(f"  Status: [NG] ERROR - No result data returned")

        except Exception as e:
            print(f"  Status: [NG] EXCEPTION - {e}")
            import traceback
            traceback.print_exc()

        # レート制限対策
        if i < len(test_cases):
            time.sleep(1)

    result_scraper.close()

    print("\n" + "="*100)
    print("Test Complete")
    print("="*100)


if __name__ == '__main__':
    test_scraper()
