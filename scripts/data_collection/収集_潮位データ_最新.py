"""
最近のレースの潮位データを収集（ブラウザ自動化版）
"""
import sys
sys.path.append('src')

import sqlite3
from datetime import datetime, timedelta
from scraper.tide_browser_scraper import TideBrowserScraper
from tqdm import tqdm
import time

print("="*80)
print("潮位データ収集（海水場・最近1週間）")
print("="*80)

# 海水場の会場コード
SEAWATER_VENUES = ['15', '16', '17', '18', '20', '22', '24']

# 2024年10月の日付を取得（気象庁データが利用可能な期間）
base_date = datetime(2024, 10, 30)
dates = [(base_date - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]

print(f"\n収集対象:")
print(f"  会場: {len(SEAWATER_VENUES)}会場（海水場のみ）")
print(f"  期間: {dates[-1]} ～ {dates[0]}")

# DBから対象レースを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT r.venue_code, r.race_date
    FROM races r
    WHERE r.venue_code IN ({})
    AND r.race_date IN ({})
    ORDER BY r.race_date DESC, r.venue_code
""".format(','.join(['?']*len(SEAWATER_VENUES)), ','.join(['?']*len(dates))),
tuple(SEAWATER_VENUES + dates))

race_dates = cursor.fetchall()

print(f"\n対象レース日数: {len(race_dates)}日分\n")

if len(race_dates) == 0:
    print("対象レースがありません")
    conn.close()
    sys.exit(0)

# 潮位データを収集（ブラウザ自動化版）
scraper = TideBrowserScraper(headless=True, delay=2.0)
success_count = 0
no_data_count = 0
error_count = 0

for venue_code, race_date in tqdm(race_dates, desc="潮位データ収集"):
    try:
        # すでに潮位データがあるかチェック
        cursor.execute("""
            SELECT COUNT(*) FROM tide
            WHERE venue_code = ? AND tide_date = ?
        """, (venue_code, race_date))

        existing_count = cursor.fetchone()[0]

        if existing_count > 0:
            # すでにデータがある場合はスキップ
            continue

        # 潮位データを取得
        tide_data = scraper.get_tide_data(venue_code, race_date)

        if tide_data:
            # データをDBに保存
            for data in tide_data:
                cursor.execute("""
                    INSERT INTO tide (venue_code, tide_date, tide_time, tide_type, tide_level, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (venue_code, race_date, data['time'], data['type'], data['level']))

            conn.commit()
            success_count += 1
        else:
            no_data_count += 1

        # レート制限対策
        time.sleep(2.0)

    except Exception as e:
        error_count += 1
        print(f"\nエラー ({venue_code}, {race_date}): {e}")

scraper.close()

# 収集結果をレポート
print("\n" + "="*80)
print("収集完了")
print("="*80)
print(f"成功: {success_count}日分")
print(f"データなし: {no_data_count}日分")
print(f"失敗: {error_count}日分")
if (success_count + no_data_count + error_count) > 0:
    print(f"成功率: {success_count/(success_count+no_data_count+error_count)*100:.1f}%")

# 保存されたデータを確認
print("\n" + "="*80)
print("保存データ確認")
print("="*80)

cursor.execute("""
    SELECT
        venue_code,
        COUNT(DISTINCT tide_date) as days,
        COUNT(*) as records
    FROM tide
    GROUP BY venue_code
    ORDER BY venue_code
""")

rows = cursor.fetchall()

if rows:
    print("\n会場別潮位データ:")
    for venue_code, days, records in rows:
        print(f"  場{venue_code}: {days}日分 ({records}件)")
else:
    print("\n潮位データがありません")

# 最新データのサンプル表示
cursor.execute("""
    SELECT venue_code, tide_date, tide_time, tide_type, tide_level
    FROM tide
    ORDER BY tide_date DESC, tide_time DESC
    LIMIT 10
""")

sample_rows = cursor.fetchall()

if sample_rows:
    print("\n最新データサンプル:")
    for venue_code, tide_date, tide_time, tide_type, tide_level in sample_rows:
        print(f"  場{venue_code} {tide_date} {tide_time} {tide_type}: {tide_level}cm")

conn.close()
print("\n" + "="*80)
