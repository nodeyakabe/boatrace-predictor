"""
スクレイパーが取得したデータの構造を確認
"""

from src.scraper.bulk_scraper import BulkScraper
import json

def debug_scraper_data():
    """スクレイパーのデータ構造を確認"""
    print("=" * 70)
    print("スクレイパーデータ構造の確認")
    print("=" * 70)

    scraper = BulkScraper()

    try:
        # 1レースだけ取得してデータ構造を確認
        race_data = scraper.scraper.get_race_card("10", "20251113", 1)

        if race_data:
            print("\n[レースデータの構造]")
            print(f"venue_code: {race_data.get('venue_code')}")
            print(f"race_date: {race_data.get('race_date')}")
            print(f"race_number: {race_data.get('race_number')}")
            print(f"race_time: {race_data.get('race_time')}")
            print(f"race_grade: {race_data.get('race_grade')}")
            print(f"race_distance: {race_data.get('race_distance')}")
            print(f"entries数: {len(race_data.get('entries', []))}")

            if race_data.get('entries'):
                print("\n[1号艇のデータ構造]")
                first_entry = race_data['entries'][0]
                print(json.dumps(first_entry, indent=2, ensure_ascii=False))

                print("\n[必須フィールドの確認]")
                required_fields = ['pit_number', 'racer_number', 'racer_name']
                for field in required_fields:
                    value = first_entry.get(field)
                    print(f"  {field}: {value} (型: {type(value).__name__})")
            else:
                print("\n[ERROR] entriesが空です")
        else:
            print("\n[ERROR] レースデータが取得できませんでした")

    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.close()


if __name__ == "__main__":
    debug_scraper_data()
