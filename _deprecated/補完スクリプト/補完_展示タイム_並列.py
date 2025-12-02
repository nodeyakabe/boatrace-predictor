"""
全レースの展示タイム・チルト・部品交換を補完（並列処理版）
"""
import sys
sys.path.append('src')

import sqlite3
from scraper.beforeinfo_scraper import BeforeInfoScraper
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

print("="*80)
print("展示タイム・チルト・部品交換 補完（並列処理版）")
print("="*80)

# DBから展示タイムがNULLのrace_detailsを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

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
conn.close()

print(f"\n展示タイムが未収集のレース数: {len(rows)}件")

if len(rows) == 0:
    print("補完対象レースがありません")
    sys.exit(0)

print(f"{len(rows)}件のレースを並列補完します（10ワーカー）...\n")

# グローバルカウンター
success_count = 0
error_count = 0
skip_count = 0
lock = threading.Lock()

# 更新データをバッファリング
update_buffer = []
buffer_lock = threading.Lock()

def process_race(race_data):
    """1レースを処理する関数"""
    global success_count, error_count, skip_count

    venue_code, race_date, race_number, race_id = race_data
    date_str = race_date.replace('-', '')

    # 各スレッドで専用のスクレイパーを使用
    scraper = BeforeInfoScraper(delay=0.05)  # さらに短縮

    try:
        beforeinfo = scraper.get_race_beforeinfo(venue_code, date_str, race_number)

        if beforeinfo:
            exhibition_times = beforeinfo.get('exhibition_times', {})
            tilt_angles = beforeinfo.get('tilt_angles', {})
            parts_replacements = beforeinfo.get('parts_replacements', {})

            if exhibition_times:
                # 更新データをバッファに追加
                updates = []
                for pit in range(1, 7):
                    ex_time = exhibition_times.get(pit)
                    tilt = tilt_angles.get(pit)
                    parts = parts_replacements.get(pit)

                    if ex_time or tilt or parts:
                        updates.append((ex_time, tilt, parts, race_id, pit))

                with buffer_lock:
                    update_buffer.extend(updates)

                with lock:
                    success_count += 1
                return 'success'
            else:
                with lock:
                    skip_count += 1
                return 'skip'
        else:
            with lock:
                skip_count += 1
            return 'skip'

    except Exception as e:
        with lock:
            error_count += 1
        return 'error'
    finally:
        scraper.close()

# 並列処理
MAX_WORKERS = 10
batch_size = 500

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    # プログレスバーで進捗表示
    with tqdm(total=len(rows), desc="展示タイム補完") as pbar:
        futures = []

        for i, race_data in enumerate(rows):
            future = executor.submit(process_race, race_data)
            futures.append(future)

            # 定期的にバッファをDBに書き込み
            if (i + 1) % batch_size == 0 or i == len(rows) - 1:
                # 進行中のタスクが完了するまで待機
                for completed in as_completed(futures):
                    pbar.update(1)

                # バッファをDBに書き込み
                if update_buffer:
                    with buffer_lock:
                        conn = sqlite3.connect('data/boatrace.db')
                        cursor = conn.cursor()
                        cursor.executemany("""
                            UPDATE race_details
                            SET exhibition_time = COALESCE(?, exhibition_time),
                                tilt_angle = COALESCE(?, tilt_angle),
                                parts_replacement = COALESCE(?, parts_replacement)
                            WHERE race_id = ? AND pit_number = ?
                        """, update_buffer)
                        conn.commit()
                        conn.close()
                        update_buffer.clear()

                futures = []

print("\n" + "="*80)
print("補完完了")
print("="*80)
print(f"成功: {success_count}レース")
print(f"スキップ: {skip_count}レース（展示タイムなし）")
print(f"失敗: {error_count}レース")
if (success_count + error_count + skip_count) > 0:
    print(f"成功率: {success_count/(success_count+error_count+skip_count)*100:.1f}%")
