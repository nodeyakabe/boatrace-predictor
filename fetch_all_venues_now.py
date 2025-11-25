"""全会場データを今すぐ取得"""
import sys
sys.path.append('src')

from scraper.official_venue_scraper import OfficialVenueScraper
from database.venue_data import VenueDataManager
from config.settings import DATABASE_PATH

print("="*70)
print("全24会場のデータを取得します")
print("="*70)

# スクレイパー初期化
scraper = OfficialVenueScraper(timeout=30)
manager = VenueDataManager(DATABASE_PATH)

print(f"\nデータベース: {DATABASE_PATH}")
print(f"現在の会場数: {manager.count_venues()}件\n")

# 全会場データ取得
print("データ取得開始...\n")
all_data = scraper.fetch_all_venues(delay=2.0)

if all_data:
    print(f"\n取得成功: {len(all_data)}/24 会場")

    # データベースに保存
    print("\nデータベースに保存中...")
    success_count = manager.save_all_venues(all_data)

    print(f"保存成功: {success_count}/{len(all_data)} 会場")

    # TOP5表示
    print("\n【1コース勝率 TOP5】")
    sorted_venues = sorted(
        all_data.values(),
        key=lambda x: x.get('course_1_win_rate', 0),
        reverse=True
    )

    for i, venue in enumerate(sorted_venues[:5], 1):
        print(f"  {i}. {venue['venue_name']:8s} - {venue['course_1_win_rate']:.1f}%")
        print(f"     水質:{venue.get('water_type', 'なし')} モーター:{venue.get('motor_type', 'なし')}")

    print(f"\n最終会場数: {manager.count_venues()}件")
    print("\n[OK] 完了")
else:
    print("\n[ERROR] データ取得失敗")

scraper.close()
