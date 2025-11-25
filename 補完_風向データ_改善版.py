"""
風向データ補完スクリプト（改善版）
ThreadPoolExecutorによる並列処理で高速化
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.append('src')

import sqlite3
from scraper.result_scraper import ResultScraper
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import threading

print("="*80)
print("風向データ補完スクリプト（改善版）")
print("="*80)

# DBから風向がNULLのweatherレコードを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT w.venue_code, w.weather_date
    FROM weather w
    WHERE w.wind_direction IS NULL OR w.wind_direction = ''
    ORDER BY w.weather_date DESC
""")

rows = cursor.fetchall()
conn.close()

print(f"\n風向データが未収集の日数: {len(rows)}件")

if len(rows) == 0:
    print("補完対象データがありません")
    sys.exit(0)

print(f"\n{len(rows)}件のデータを補完します...")
print("※改善版: ThreadPoolExecutor、セッション再利用、リトライ機能搭載\n")

# スレッドローカルスクレイパー
thread_local = threading.local()

def get_scraper():
    """スレッドごとのスクレイパーを取得"""
    if not hasattr(thread_local, "scraper"):
        thread_local.scraper = ResultScraper()
    return thread_local.scraper

# グローバルカウンター
success_count = 0
error_count = 0
skip_count = 0
counter_lock = Lock()

# データベース書き込みロック
db_lock = Lock()

def fetch_wind_direction(venue_code, weather_date):
    """
    指定された会場・日付の風向データを取得

    Args:
        venue_code: 会場コード
        weather_date: 日付（YYYY-MM-DD形式）

    Returns:
        tuple: (venue_code, weather_date, wind_direction, status)
               status: 'success', 'error', 'skip'
    """
    # 日付をYYYYMMDD形式に変換
    date_str = weather_date.replace('-', '')

    scraper = get_scraper()

    # リトライ機能
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 1Rのデータから天候情報を取得
            result = scraper.get_race_result_complete(venue_code, date_str, 1)

            if result and 'weather_data' in result and result['weather_data']:
                weather = result['weather_data']
                wind_direction = weather.get('wind_direction')

                if wind_direction:
                    return (venue_code, weather_date, wind_direction, 'success')
                else:
                    return (venue_code, weather_date, None, 'error')
            else:
                # レースデータが存在しない（未来のレースなど）
                return (venue_code, weather_date, None, 'skip')

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)  # リトライ前に待機
                continue
            else:
                return (venue_code, weather_date, None, 'error')

    return (venue_code, weather_date, None, 'error')

# データベースコネクション（メインスレッド用）
db_conn = sqlite3.connect('data/boatrace.db')
db_cursor = db_conn.cursor()

# バッチ更新用のバッファ
update_buffer = []
BATCH_SIZE = 100

def save_batch():
    """バッファのデータをDBに保存"""
    global update_buffer
    if update_buffer:
        with db_lock:
            for venue_code, weather_date, wind_direction in update_buffer:
                db_cursor.execute("""
                    UPDATE weather
                    SET wind_direction = ?
                    WHERE venue_code = ? AND weather_date = ?
                """, (wind_direction, venue_code, weather_date))
            db_conn.commit()
            count = len(update_buffer)
            update_buffer = []
            return count
    return 0

# 並列処理で風向データを取得
start_time = time.time()

with ThreadPoolExecutor(max_workers=16) as executor:
    # タスクを投入
    futures = {
        executor.submit(fetch_wind_direction, venue_code, weather_date): (venue_code, weather_date)
        for venue_code, weather_date in rows
    }

    # 進捗バー
    with tqdm(total=len(rows), desc="風向データ補完") as pbar:
        processed = 0

        for future in as_completed(futures):
            venue_code, weather_date, wind_direction, status = future.result()
            processed += 1

            if status == 'success':
                # バッファに追加
                update_buffer.append((venue_code, weather_date, wind_direction))

                with counter_lock:
                    success_count += 1

                # バッチサイズに達したら保存
                if len(update_buffer) >= BATCH_SIZE:
                    saved = save_batch()
                    if saved:
                        tqdm.write(f"[{processed}/{len(rows)}] 保存完了: {BATCH_SIZE}件 ({success_count}/{len(rows)}件)")

            elif status == 'skip':
                with counter_lock:
                    skip_count += 1
            else:  # error
                with counter_lock:
                    error_count += 1

            pbar.update(1)

            # 進捗表示（100件ごと）
            if processed % 100 == 0:
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                remaining = (len(rows) - processed) / speed if speed > 0 else 0
                tqdm.write(f"進捗: {processed}/{len(rows)} ({processed/len(rows)*100:.1f}%) - {speed:.1f}件/秒 - 残り約{remaining/60:.1f}分")

# 残りのバッファを保存
if update_buffer:
    saved = save_batch()
    if saved:
        print(f"最終バッチ保存完了: {saved}件")

# スクレイパーをクローズ
if hasattr(thread_local, "scraper"):
    thread_local.scraper.close()

db_conn.close()

elapsed_time = time.time() - start_time

print("\n" + "="*80)
print("最終集計")
print("="*80)
print(f"対象日数: {len(rows)}")
print(f"取得成功: {success_count}件")
print(f"スキップ: {skip_count}件（レースデータなし）")
print(f"取得失敗: {error_count}件")
if (success_count + error_count + skip_count) > 0:
    print(f"成功率: {success_count/(success_count+error_count+skip_count)*100:.1f}%")
print(f"処理時間: {elapsed_time/60:.1f}分")
print(f"処理速度: {len(rows)/elapsed_time:.1f}件/秒")
print("="*80)
