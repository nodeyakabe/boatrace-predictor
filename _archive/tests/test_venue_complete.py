"""修正後の会場データ取得テスト"""
import sys
sys.path.append('src')

from scraper.official_venue_scraper import OfficialVenueScraper

print("="*70)
print("会場データ取得テスト（修正版）")
print("="*70)

scraper = OfficialVenueScraper(timeout=30)

# 桐生のデータを取得
print("\n桐生（会場コード01）のデータを取得中...")
venue_data = scraper.fetch_venue_data('01')

if venue_data:
    print("\n[OK] データ取得成功:\n")
    print(f"  会場名: {venue_data.get('venue_name')}")
    print(f"  水質: {venue_data.get('water_type')}")
    print(f"  干満差: {venue_data.get('tidal_range')}")
    print(f"  モーター: {venue_data.get('motor_type')}")
    print(f"  1コース勝率: {venue_data.get('course_1_win_rate')}%")
    print(f"  2コース勝率: {venue_data.get('course_2_win_rate')}%")
    print(f"  レコード: {venue_data.get('record_time')}")
    print(f"  記録保持者: {venue_data.get('record_holder')}")
    print(f"  記録日: {venue_data.get('record_date')}")

    # None値をカウント
    none_count = sum(1 for v in venue_data.values() if v is None)
    total_count = len(venue_data)
    print(f"\n  データ充足率: {(total_count - none_count) / total_count * 100:.1f}%")
    print(f"  (None値: {none_count}/{total_count})")
else:
    print("\n[ERROR] データ取得失敗")

scraper.close()
print("\n[OK] テスト完了")
