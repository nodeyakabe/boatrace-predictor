"""
既存の天候データに風向を補完
"""
import sys
sys.path.append('src')

import sqlite3
from scraper.result_scraper import ResultScraper
from tqdm import tqdm
import time

print("="*80)
print("風向データ補完")
print("="*80)

# DBから風向がNULLのweatherレコードを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT w.venue_code, w.weather_date
    FROM weather w
    WHERE w.wind_direction IS NULL
    ORDER BY w.weather_date DESC
    LIMIT 100
""")

rows = cursor.fetchall()

print(f"\n風向データが未収集の日数: {len(rows)}件")
print("最初の100件を補完します...\n")

if len(rows) == 0:
    print("補完対象データがありません")
    conn.close()
    sys.exit(0)

scraper = ResultScraper()
success_count = 0
error_count = 0

for venue_code, weather_date in tqdm(rows, desc="風向データ補完"):
    # 日付をYYYYMMDD形式に変換
    date_str = weather_date.replace('-', '')

    try:
        # 1Rのデータから天候情報を取得
        result = scraper.get_race_result_complete(venue_code, date_str, 1)

        if result and 'weather' in result and result['weather']:
            weather = result['weather']
            wind_direction = weather.get('wind_direction')

            if wind_direction:
                # DBを更新
                cursor.execute("""
                    UPDATE weather
                    SET wind_direction = ?
                    WHERE venue_code = ? AND weather_date = ?
                """, (wind_direction, venue_code, weather_date))

                conn.commit()
                success_count += 1
                # print(f"[OK] 場{venue_code} {weather_date}: {wind_direction}")
            else:
                error_count += 1
                # print(f"[NG] 場{venue_code} {weather_date}: 風向データなし")
        else:
            error_count += 1
            # print(f"[NG] 場{venue_code} {weather_date}: 天候データ取得失敗")

        # レート制限対策
        time.sleep(0.5)

    except Exception as e:
        error_count += 1
        # print(f"[エラー] 場{venue_code} {weather_date}: {e}")

scraper.close()
conn.close()

print("\n" + "="*80)
print("補完完了")
print("="*80)
print(f"成功: {success_count}件")
print(f"失敗: {error_count}件")
print(f"成功率: {success_count/(success_count+error_count)*100:.1f}%")
