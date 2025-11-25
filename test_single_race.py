"""
単一レースのデータ取得テスト
"""

from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.result_scraper import ResultScraper
from src.scraper.beforeinfo_scraper import BeforeInfoScraper

def test_single_race():
    """2022-01-15のレースをテスト"""

    venue_code = "01"  # 桐生
    date_str = "20220115"
    race_number = 1

    print("=" * 80)
    print(f"テスト対象: 会場={venue_code}, 日付={date_str}, レース={race_number}")
    print("=" * 80)

    # 出走表の取得
    print("\n1. 出走表を取得中...")
    try:
        race_scraper = RaceScraperV2()
        race_data = race_scraper.fetch_race_data(venue_code, date_str, race_number)

        if race_data and 'entries' in race_data and len(race_data['entries']) > 0:
            print(f"  ✓ 出走表取得成功: {len(race_data['entries'])}艇")
            print(f"    レース名: {race_data.get('race_name', 'N/A')}")
        else:
            print(f"  × 出走表取得失敗: データが空")
            return
    except Exception as e:
        print(f"  × 出走表取得エラー: {e}")
        return

    # 結果の取得
    print("\n2. レース結果を取得中...")
    try:
        result_scraper = ResultScraper()
        complete_result = result_scraper.fetch_result(venue_code, date_str, race_number)

        if complete_result and 'results' in complete_result:
            print(f"  ✓ 結果取得成功: {len(complete_result['results'])}件")
            # 1着の情報を表示
            if len(complete_result['results']) > 0:
                first = complete_result['results'][0]
                print(f"    1着: 艇番={first.get('pit_number', 'N/A')}, タイム={first.get('race_time', 'N/A')}")
        else:
            print(f"  × 結果取得失敗: データが空")
            return
    except Exception as e:
        print(f"  × 結果取得エラー: {e}")
        return

    # 直前情報の取得
    print("\n3. 直前情報を取得中...")
    try:
        beforeinfo_scraper = BeforeInfoScraper()
        beforeinfo = beforeinfo_scraper.scrape(venue_code, date_str, race_number)

        if beforeinfo and len(beforeinfo) > 0:
            print(f"  ✓ 直前情報取得成功: {len(beforeinfo)}件")
            # 1号艇の展示タイムを表示
            if len(beforeinfo) > 0:
                first_boat = beforeinfo[0]
                print(f"    1号艇: 展示タイム={first_boat.get('exhibition_time', 'N/A')}, 進入={first_boat.get('actual_course', 'N/A')}")
        else:
            print(f"  × 直前情報取得失敗: データが空")
    except Exception as e:
        print(f"  × 直前情報取得エラー: {e}")

    print("\n" + "=" * 80)
    print("結論:")
    print("=" * 80)
    print("✓ 出走表と結果は取得可能")
    if beforeinfo and len(beforeinfo) > 0:
        print("✓ 直前情報も取得可能")
        print("\n→ 2022年のデータは取得可能なはずです。")
        print("→ スクリプトのロジックに問題がある可能性があります。")
    else:
        print("× 直前情報は取得不可")
        print("\n→ 2022年は出走表と結果のみ取得可能です。")

if __name__ == "__main__":
    test_single_race()
