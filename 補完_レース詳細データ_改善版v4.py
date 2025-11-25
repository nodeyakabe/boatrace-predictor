"""
レース詳細データ補完スクリプト（改善版v4）
ST time、actual_course、チルト角、展示タイム等を一括補完
最適化: ワーカー数増加(12)、タイムアウト短縮(15秒)、バッチサイズ200維持
推定時間: 4-6時間（v3: 10.5時間）

改善点:
- max_workers: 6 → 12（サーバーレイテンシを並列化でマスク）
- timeout: (5, 25) → (5, 15)（失敗検出を高速化）
- 進捗表示: 500件 → 100件（より細かく進捗を確認）
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
import random

print("="*80)
print("レース詳細データ補完スクリプト（改善版v4）")
print("="*80)

# DBからST timeまたはactual_courseが欠けているレースを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
    FROM races r
    WHERE EXISTS (
        SELECT 1 FROM race_details rd
        WHERE rd.race_id = r.id
        AND (rd.st_time IS NULL OR rd.actual_course IS NULL)
    )
    ORDER BY r.race_date DESC, r.venue_code, r.race_number
""")

rows = cursor.fetchall()
conn.close()

print(f"\nST time/actual_courseが未収集のレース数: {len(rows):,}件")

if len(rows) == 0:
    print("補完対象データがありません")
    sys.exit(0)

print(f"\n{len(rows):,}件のレース詳細データを補完します...")
print("※改善版v4: ワーカー数12、バッチサイズ200、タイムアウト15秒、指数バックオフ")
print("※v3との差分: ワーカー6→12、タイムアウト25秒→15秒、進捗表示500件→100件\n")

# スレッドローカルスクレイパー
thread_local = threading.local()

def get_scraper():
    """スレッドごとのスクレイパーを取得（タイムアウト15秒）"""
    if not hasattr(thread_local, "scraper"):
        thread_local.scraper = ResultScraper(read_timeout=15)
    return thread_local.scraper

# グローバルカウンター
success_count = 0
error_count = 0
skip_count = 0
timeout_count = 0
counter_lock = Lock()

# データベース書き込みロック
db_lock = Lock()

def fetch_race_details(race_id, venue_code, race_date, race_number):
    """
    指定されたレースの詳細データを取得

    Args:
        race_id: レースID
        venue_code: 会場コード
        race_date: 日付（YYYY-MM-DD形式）
        race_number: レース番号

    Returns:
        tuple: (race_id, details_data, status)
               status: 'success', 'error', 'skip', 'timeout'
    """
    # 日付をYYYYMMDD形式に変換
    date_str = race_date.replace('-', '')

    scraper = get_scraper()

    # リトライ機能（指数バックオフ）
    max_retries = 2
    base_wait = 0.5  # 初期待機時間

    for attempt in range(max_retries):
        try:
            # レース結果の完全データを取得
            result = scraper.get_race_result_complete(venue_code, date_str, race_number)

            if result and 'race_details' in result and result['race_details']:
                return (race_id, result['race_details'], 'success')
            else:
                # レースデータが存在しない（未来のレースなど）
                return (race_id, None, 'skip')

        except Exception as e:
            # タイムアウトかどうか確認
            error_str = str(e).lower()
            if 'timeout' in error_str or 'timed out' in error_str:
                # タイムアウトの場合、リトライしない（サーバー負荷軽減）
                return (race_id, None, 'timeout')

            if attempt < max_retries - 1:
                # 指数バックオフ + ジッタ
                wait_time = base_wait * (2 ** attempt) + random.uniform(0, 0.3)
                time.sleep(wait_time)
                continue
            else:
                return (race_id, None, 'error')

    return (race_id, None, 'error')

# データベースコネクション（メインスレッド用）
db_conn = sqlite3.connect('data/boatrace.db')
db_cursor = db_conn.cursor()

# race_idごとのrace_details idをキャッシュ（事前にロード）
print("race_detailsキャッシュを構築中...")
race_details_cache = {}
db_cursor.execute("""
    SELECT rd.race_id, rd.pit_number, rd.id
    FROM race_details rd
    JOIN races r ON rd.race_id = r.id
    WHERE EXISTS (
        SELECT 1 FROM race_details rd2
        WHERE rd2.race_id = r.id
        AND (rd2.st_time IS NULL OR rd2.actual_course IS NULL)
    )
""")
for race_id, pit_number, detail_id in db_cursor.fetchall():
    if race_id not in race_details_cache:
        race_details_cache[race_id] = {}
    race_details_cache[race_id][pit_number] = detail_id
print(f"キャッシュ構築完了: {len(race_details_cache):,}レース\n")

# バッチ更新用のバッファ
update_buffer = []
BATCH_SIZE = 200

def save_batch():
    """バッファのデータをDBに保存"""
    global update_buffer
    if update_buffer:
        with db_lock:
            for race_id, details_data in update_buffer:
                # 各艇のデータを更新
                for detail in details_data:
                    pit_number = detail.get('pit_number')
                    if not pit_number:
                        continue

                    # キャッシュから detail_id を取得
                    if race_id in race_details_cache and pit_number in race_details_cache[race_id]:
                        detail_id = race_details_cache[race_id][pit_number]

                        # 更新
                        update_fields = []
                        update_values = []

                        if detail.get('st_time') is not None:
                            update_fields.append('st_time = ?')
                            update_values.append(detail['st_time'])

                        if detail.get('actual_course') is not None:
                            update_fields.append('actual_course = ?')
                            update_values.append(detail['actual_course'])

                        if detail.get('tilt_angle') is not None:
                            update_fields.append('tilt_angle = ?')
                            update_values.append(detail['tilt_angle'])

                        if detail.get('exhibition_time') is not None:
                            update_fields.append('exhibition_time = ?')
                            update_values.append(detail['exhibition_time'])

                        if detail.get('chikusen_time') is not None:
                            update_fields.append('chikusen_time = ?')
                            update_values.append(detail['chikusen_time'])

                        if detail.get('isshu_time') is not None:
                            update_fields.append('isshu_time = ?')
                            update_values.append(detail['isshu_time'])

                        if detail.get('mawariashi_time') is not None:
                            update_fields.append('mawariashi_time = ?')
                            update_values.append(detail['mawariashi_time'])

                        if update_fields:
                            update_values.append(detail_id)
                            db_cursor.execute(f"""
                                UPDATE race_details
                                SET {', '.join(update_fields)}
                                WHERE id = ?
                            """, update_values)

            db_conn.commit()
            count = len(update_buffer)
            update_buffer = []
            return count
    return 0

# 並列処理でレース詳細データを取得（ワーカー数を12に増加）
start_time = time.time()

with ThreadPoolExecutor(max_workers=12) as executor:
    # タスクを投入
    futures = {
        executor.submit(fetch_race_details, race_id, venue_code, race_date, race_number): (race_id, venue_code, race_date, race_number)
        for race_id, venue_code, race_date, race_number in rows
    }

    # 進捗バー
    with tqdm(total=len(rows), desc="レース詳細データ補完") as pbar:
        processed = 0

        for future in as_completed(futures):
            race_id, details_data, status = future.result()
            processed += 1

            if status == 'success':
                # バッファに追加
                update_buffer.append((race_id, details_data))

                with counter_lock:
                    success_count += 1

                # バッチサイズに達したら保存
                if len(update_buffer) >= BATCH_SIZE:
                    saved = save_batch()
                    if saved:
                        tqdm.write(f"[{processed}/{len(rows)}] 保存完了: {BATCH_SIZE}レース ({success_count}/{len(rows)}件)")

            elif status == 'skip':
                with counter_lock:
                    skip_count += 1
            elif status == 'timeout':
                with counter_lock:
                    timeout_count += 1
            else:  # error
                with counter_lock:
                    error_count += 1

            pbar.update(1)

            # 進捗表示（100件ごと、v3は500件ごと）
            if processed % 100 == 0:
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                remaining = (len(rows) - processed) / speed if speed > 0 else 0
                tqdm.write(f"進捗: {processed}/{len(rows)} ({processed/len(rows)*100:.1f}%) - {speed:.1f}件/秒 - 残り約{remaining/60:.1f}分")

# 残りのバッファを保存
if update_buffer:
    saved = save_batch()
    if saved:
        print(f"最終バッチ保存完了: {saved}レース")

# スクレイパーをクローズ
if hasattr(thread_local, "scraper"):
    thread_local.scraper.close()

db_conn.close()

elapsed_time = time.time() - start_time

print("\\n" + "="*80)
print("最終集計")
print("="*80)
print(f"対象レース数: {len(rows):,}")
print(f"取得成功: {success_count:,}件")
print(f"スキップ: {skip_count:,}件（レースデータなし）")
print(f"タイムアウト: {timeout_count:,}件")
print(f"取得失敗: {error_count:,}件")
if (success_count + error_count + skip_count + timeout_count) > 0:
    print(f"成功率: {success_count/(success_count+error_count+skip_count+timeout_count)*100:.1f}%")
print(f"処理時間: {elapsed_time/60:.1f}分")
print(f"処理速度: {len(rows)/elapsed_time:.1f}件/秒")
print("="*80)
