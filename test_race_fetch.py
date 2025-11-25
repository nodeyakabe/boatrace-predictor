"""本日のレース取得テスト"""
import sys
from datetime import datetime

# 今日の日付を取得
today = datetime.now().strftime('%Y%m%d')
print(f"今日の日付: {today}")

# fetch_upcoming_racesをインポート
sys.path.append('.')
from fetch_upcoming_races import fetch_race_schedule

print(f"\n{today}のレース開催情報を取得中...")
venues = fetch_race_schedule(today)

if venues:
    print(f"\n[OK] {len(venues)}会場で開催:")
    for venue in venues:
        print(f"  - 会場コード: {venue}")
else:
    print("\n[INFO] 本日は開催なし、またはデータ取得失敗")

# 明日も試す
from datetime import timedelta
tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y%m%d')
print(f"\n{tomorrow}(明日)のレース開催情報を取得中...")
venues_tomorrow = fetch_race_schedule(tomorrow)

if venues_tomorrow:
    print(f"\n[OK] {len(venues_tomorrow)}会場で開催:")
    for venue in venues_tomorrow:
        print(f"  - 会場コード: {venue}")
else:
    print("\n[INFO] 明日は開催なし、またはデータ取得失敗")
