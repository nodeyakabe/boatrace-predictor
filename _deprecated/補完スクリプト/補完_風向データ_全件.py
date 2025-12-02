"""
既存の天候データに風向を補完（全件）
"""
import sys
sys.path.append('src')

import sqlite3
from scraper.result_scraper import ResultScraper
from tqdm import tqdm
import time

print("="*80)
print("風向データ補完（全件）")
print("="*80)

# DBから風向がNULLのweatherレコードを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT w.venue_code, w.weather_date
    FROM weather w
    WHERE w.wind_direction IS NULL
    ORDER BY w.weather_date DESC
""")

rows = cursor.fetchall()

print(f"\n風向データが未収集の日数: {len(rows)}件")
print("全件補完を開始します...\n")

if len(rows) == 0:
    print("補完対象データがありません")
    conn.close()
    sys.exit(0)

# 確認
response = input(f"{len(rows)}件のデータを補完します。続行しますか？ (y/N): ")
if response.lower() != 'y':
    print("キャンセルしました")
    conn.close()
    sys.exit(0)

scraper = ResultScraper()
success_count = 0
error_count = 0
skip_count = 0

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
            else:
                error_count += 1
        else:
            # レースデータが存在しない（未来のレースなど）
            skip_count += 1

        # レート制限対策
        time.sleep(0.5)

    except Exception as e:
        error_count += 1
        # エラーは無視して続行

scraper.close()
conn.close()

print("\n" + "="*80)
print("補完完了")
print("="*80)
print(f"成功: {success_count}件")
print(f"スキップ: {skip_count}件（レースデータなし）")
print(f"失敗: {error_count}件")
print(f"成功率: {success_count/(success_count+error_count+skip_count)*100:.1f}%")
