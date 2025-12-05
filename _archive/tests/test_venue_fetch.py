"""会場データ取得のテスト"""
import sys
sys.path.append('src')

from scraper.official_venue_scraper import OfficialVenueScraper
from database.venue_data import VenueDataManager
from config.settings import DATABASE_PATH

print("="*70)
print("会場データ取得テスト")
print("="*70)

try:
    print("\nスクレイパー初期化中...")
    scraper = OfficialVenueScraper(timeout=30)
    print("[OK] 初期化成功")

    print("\n桐生（会場コード01）のデータを取得中...")
    venue_data = scraper.fetch_venue_data('01')

    if venue_data:
        print("[OK] データ取得成功:")
        print(f"  会場名: {venue_data.get('venue_name')}")
        print(f"  水質: {venue_data.get('water_type')}")
        print(f"  1コース勝率: {venue_data.get('course_1_win_rate')}%")
        print(f"  レコード: {venue_data.get('record_time')}")

        # データベースに保存
        print("\nデータベースに保存中...")
        manager = VenueDataManager(DATABASE_PATH)
        success = manager.save_venue_data(venue_data)

        if success:
            print("[OK] 保存成功")
            print(f"現在の会場数: {manager.count_venues()}件")
        else:
            print("[ERROR] 保存失敗")
    else:
        print("[ERROR] データ取得失敗")

    scraper.close()
    print("\n[OK] テスト完了")

except Exception as e:
    print(f"\n[ERROR] エラー発生: {e}")
    import traceback
    traceback.print_exc()
