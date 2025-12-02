"""
全レースの展示タイム・チルト・部品交換を補完
"""
import sys
sys.path.append('src')

import sqlite3
from scraper.beforeinfo_scraper import BeforeInfoScraper
from tqdm import tqdm
import time

print("="*80)
print("展示タイム・チルト・部品交換 補完（全件・自動実行）")
print("="*80)

# DBから展示タイムがNULLのrace_detailsを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# レースごとに1件でもNULLがあれば補完対象
cursor.execute("""
    SELECT DISTINCT r.venue_code, r.race_date, r.race_number, r.id
    FROM races r
    WHERE EXISTS (
        SELECT 1 FROM race_details rd
        WHERE rd.race_id = r.id
        AND rd.exhibition_time IS NULL
    )
    ORDER BY r.race_date DESC
""")

rows = cursor.fetchall()

print(f"\n展示タイムが未収集のレース数: {len(rows)}件")

if len(rows) == 0:
    print("補完対象レースがありません")
    conn.close()
    sys.exit(0)

print(f"{len(rows)}件のレースを自動補完します...\n")

scraper = BeforeInfoScraper(delay=0.3)
success_count = 0
error_count = 0
skip_count = 0

for venue_code, race_date, race_number, race_id in tqdm(rows, desc="展示タイム補完"):
    # 日付をYYYYMMDD形式に変換
    date_str = race_date.replace('-', '')

    try:
        # 事前情報を取得
        beforeinfo = scraper.get_race_beforeinfo(venue_code, date_str, race_number)

        if beforeinfo:
            exhibition_times = beforeinfo.get('exhibition_times', {})
            tilt_angles = beforeinfo.get('tilt_angles', {})
            parts_replacements = beforeinfo.get('parts_replacements', {})

            if exhibition_times:
                # 各艇のデータを更新
                updated = 0
                for pit in range(1, 7):
                    ex_time = exhibition_times.get(pit)
                    tilt = tilt_angles.get(pit)
                    parts = parts_replacements.get(pit)

                    if ex_time or tilt or parts:
                        cursor.execute("""
                            UPDATE race_details
                            SET exhibition_time = COALESCE(?, exhibition_time),
                                tilt_angle = COALESCE(?, tilt_angle),
                                parts_replacement = COALESCE(?, parts_replacement)
                            WHERE race_id = ? AND pit_number = ?
                        """, (ex_time, tilt, parts, race_id, pit))
                        updated += 1

                if updated > 0:
                    conn.commit()
                    success_count += 1
            else:
                # 展示タイムが取得できなかった
                skip_count += 1
        else:
            # レースデータが存在しない
            skip_count += 1

        # レート制限対策
        time.sleep(0.3)

    except Exception as e:
        error_count += 1
        # エラーは無視して続行

scraper.close()
conn.close()

print("\n" + "="*80)
print("補完完了")
print("="*80)
print(f"成功: {success_count}レース")
print(f"スキップ: {skip_count}レース（展示タイムなし）")
print(f"失敗: {error_count}レース")
if (success_count + error_count + skip_count) > 0:
    print(f"成功率: {success_count/(success_count+error_count+skip_count)*100:.1f}%")
