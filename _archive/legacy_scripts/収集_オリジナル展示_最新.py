"""
昨日と今日のオリジナル展示データを収集
"""
import sys
sys.path.append('src')

import sqlite3
from datetime import datetime, timedelta
from scraper.original_tenji_scraper import OriginalTenjiScraper
from tqdm import tqdm
import time

print("="*80)
print("オリジナル展示データ収集（昨日・今日）")
print("="*80)

# 昨日と今日の日付を取得
today = datetime(2025, 11, 1)  # 環境の今日の日付
yesterday = today - timedelta(days=1)

dates = [yesterday, today]
date_strs = [d.strftime('%Y-%m-%d') for d in dates]

print(f"\n収集対象日:")
for d in date_strs:
    print(f"  - {d}")

# DBから対象日のレースを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE r.race_date IN (?, ?)
    ORDER BY r.race_date, r.venue_code, r.race_number
""", tuple(date_strs))

races = cursor.fetchall()

print(f"\n対象レース数: {len(races)}レース\n")

if len(races) == 0:
    print("対象レースがありません")
    conn.close()
    sys.exit(0)

# オリジナル展示データを収集
scraper = OriginalTenjiScraper(delay=1.0)
success_count = 0
no_data_count = 0
error_count = 0

for race_id, venue_code, race_date, race_number in tqdm(races, desc="オリジナル展示収集"):
    try:
        # オリジナル展示データを取得
        tenji_data = scraper.get_original_tenji(venue_code, race_date, race_number)

        if tenji_data:
            # 各艇のデータを更新
            updated = 0
            for boat_num, data in tenji_data.items():
                chikusen = data.get('chikusen_time')
                isshu = data.get('isshu_time')
                mawariashi = data.get('mawariashi_time')

                if chikusen is not None or isshu is not None or mawariashi is not None:
                    cursor.execute("""
                        UPDATE race_details
                        SET chikusen_time = COALESCE(?, chikusen_time),
                            isshu_time = COALESCE(?, isshu_time),
                            mawariashi_time = COALESCE(?, mawariashi_time)
                        WHERE race_id = ? AND pit_number = ?
                    """, (chikusen, isshu, mawariashi, race_id, boat_num))
                    updated += 1

            if updated > 0:
                conn.commit()
                success_count += 1
        else:
            no_data_count += 1

        # レート制限対策
        time.sleep(1.0)

    except Exception as e:
        error_count += 1
        print(f"\nエラー ({venue_code}, {race_date}, R{race_number}): {e}")

scraper.close()

# 収集結果をレポート
print("\n" + "="*80)
print("収集完了")
print("="*80)
print(f"成功: {success_count}レース")
print(f"データなし: {no_data_count}レース")
print(f"失敗: {error_count}レース")
if (success_count + no_data_count + error_count) > 0:
    print(f"成功率: {success_count/(success_count+no_data_count+error_count)*100:.1f}%")

# 保存されたデータを確認
print("\n" + "="*80)
print("保存データ確認")
print("="*80)

for date_str in date_strs:
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN rd.chikusen_time IS NOT NULL THEN 1 END) as with_chikusen,
            COUNT(CASE WHEN rd.isshu_time IS NOT NULL THEN 1 END) as with_isshu,
            COUNT(CASE WHEN rd.mawariashi_time IS NOT NULL THEN 1 END) as with_mawariashi
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date = ?
    """, (date_str,))

    row = cursor.fetchone()
    total, with_chikusen, with_isshu, with_mawariashi = row

    if total > 0:
        print(f"\n{date_str}:")
        print(f"  総艇数: {total}艇")
        print(f"  直線タイム: {with_chikusen}艇 ({with_chikusen/total*100:.1f}%)")
        print(f"  1周タイム: {with_isshu}艇 ({with_isshu/total*100:.1f}%)")
        print(f"  回り足タイム: {with_mawariashi}艇 ({with_mawariashi/total*100:.1f}%)")

conn.close()
print("\n" + "="*80)
