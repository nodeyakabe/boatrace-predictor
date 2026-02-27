"""
データ補完統合スクリプト（放置実行対応）
Phase 1: 決まり手データ補完（kimarite）
Phase 2: レース詳細データ補完（st_time, chikusen_time, etc.）

使用方法:
  python scripts/data_collection/補完_統合版_決まり手_レース詳細.py
  python scripts/data_collection/補完_統合版_決まり手_レース詳細.py --start-date 2020-01-01 --end-date 2023-12-31

特徴:
- 2つの補完処理を自動的に順次実行
- 放置実行可能（エラーでも継続）
- 詳細ログファイル出力
- 完了レポート自動生成
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import argparse
import sqlite3
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from datetime import datetime
from threading import Lock

# プロジェクトルートを取得
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')

# ログディレクトリの作成
os.makedirs(LOG_DIR, exist_ok=True)

# ログファイル名
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_FILE = os.path.join(LOG_DIR, f'data_completion_{timestamp}.log')

def log_print(message):
    """コンソールとログファイルに同時出力"""
    print(message)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(message + '\n')

# =============================================================================
# Phase 1: 決まり手データ補完
# =============================================================================

# スレッドローカルセッション
thread_local = threading.local()

def get_session():
    """スレッドローカルなセッションを取得"""
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    return thread_local.session

def get_races_without_kimarite(db_path, start_date=None, end_date=None):
    """決まり手が欠損しているレースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    date_filter = ""
    params = []

    if start_date and end_date:
        date_filter = "AND r.race_date BETWEEN ? AND ?"
        params = [start_date, end_date]
        log_print(f"  期間フィルター: {start_date} ～ {end_date}")
    elif start_date:
        date_filter = "AND r.race_date >= ?"
        params = [start_date]
        log_print(f"  期間フィルター: {start_date} 以降")
    elif end_date:
        date_filter = "AND r.race_date <= ?"
        params = [end_date]
        log_print(f"  期間フィルター: {end_date} まで")
    else:
        log_print("  期間フィルターなし（全期間対象）")

    query = f"""
        SELECT DISTINCT
            r.id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE res.kimarite IS NULL
          AND res.rank = '1'
          AND res.is_invalid = 0
          {date_filter}
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    log_print(f"  決まり手が欠損しているレース: {len(rows):,}件")
    return rows

def fetch_kimarite_fast(args, retry=3):
    """1レースの決まり手を高速取得"""
    race_id, venue_code, race_date, race_number = args
    date_str = race_date.replace('-', '')
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={int(venue_code):02d}&hd={date_str}"

    for attempt in range(retry):
        try:
            session = get_session()
            response = session.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, 'lxml')
            kimarite = None
            tables = soup.find_all('table')

            for table in tables:
                thead = table.find('thead')
                if not thead:
                    continue

                headers = [th.get_text(strip=True) for th in thead.find_all('th')]

                if '決まり手' in headers:
                    tbody = table.find('tbody')
                    if tbody:
                        td = tbody.find('td')
                        if td:
                            kimarite_text = td.get_text(strip=True)
                            if kimarite_text and kimarite_text not in ['', ' ']:
                                kimarite = kimarite_text
                                break

            if kimarite:
                kimarite_map = {
                    '逃げ': 1,
                    '差し': 2,
                    'まくり': 3,
                    'まくり差し': 4,
                    '抜き': 5,
                    '恵まれ': 6
                }
                winning_technique = kimarite_map.get(kimarite)

                return {
                    'race_id': race_id,
                    'kimarite': kimarite,
                    'winning_technique': winning_technique
                }
            else:
                if attempt < retry - 1:
                    time.sleep(1)
                    continue
                else:
                    return None

        except Exception as e:
            if attempt < retry - 1:
                time.sleep(1)
                continue
            else:
                return None

    return None

def update_kimarite_batch(conn, results):
    """決まり手をバッチ更新"""
    cursor = conn.cursor()
    for result in results:
        cursor.execute("""
            UPDATE results
            SET kimarite = ?
            WHERE race_id = ? AND rank = '1'
        """, (result['kimarite'], result['race_id']))
    conn.commit()

def run_phase1_kimarite(start_date=None, end_date=None):
    """Phase 1: 決まり手データ補完を実行"""
    log_print("\n" + "="*80)
    log_print("Phase 1: 決まり手データ補完")
    log_print("="*80)

    races = get_races_without_kimarite(DB_PATH, start_date, end_date)

    if len(races) == 0:
        log_print("  補完が必要なレースはありません。Phase 1をスキップします。\n")
        return {
            'phase': 'Phase 1: 決まり手データ補完',
            'total': 0,
            'success': 0,
            'error': 0,
            'elapsed': 0,
            'skipped': True
        }

    log_print(f"  補完対象: {len(races):,}件")
    log_print("  処理を開始します...")
    log_print("  仕様: 16ワーカー並列、リトライ3回、バッチサイズ100\n")

    success_count = 0
    error_count = 0
    start_time = time.time()

    batch = []
    batch_size = 100
    max_workers = 16

    conn = sqlite3.connect(DB_PATH)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_kimarite_fast, race): race for race in races}

        for i, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()

                if result:
                    batch.append(result)
                    success_count += 1

                    if len(batch) >= batch_size:
                        update_kimarite_batch(conn, batch)
                        log_print(f"  [{i}/{len(races)}] 保存完了: {len(batch)}件 ({success_count}/{len(races)}件)")
                        batch = []

                    if i % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = i / elapsed
                        remaining = (len(races) - i) / rate if rate > 0 else 0
                        log_print(f"  進捗: {i}/{len(races)} ({i/len(races)*100:.1f}%) - {rate:.1f}件/秒 - 残り約{remaining/60:.1f}分")
                else:
                    error_count += 1

            except Exception as e:
                error_count += 1

    if batch:
        update_kimarite_batch(conn, batch)
        log_print(f"  最終バッチ保存完了: {len(batch)}件")

    conn.close()

    elapsed_total = time.time() - start_time

    log_print("\n" + "-"*80)
    log_print("Phase 1 完了")
    log_print("-"*80)
    log_print(f"  対象レース数: {len(races):,}")
    log_print(f"  取得成功: {success_count:,}件")
    log_print(f"  取得失敗: {error_count:,}件")
    log_print(f"  成功率: {success_count/len(races)*100:.1f}%")
    log_print(f"  処理時間: {elapsed_total/60:.1f}分")
    log_print(f"  処理速度: {len(races)/elapsed_total:.1f}件/秒")
    log_print("-"*80 + "\n")

    return {
        'phase': 'Phase 1: 決まり手データ補完',
        'total': len(races),
        'success': success_count,
        'error': error_count,
        'elapsed': elapsed_total,
        'skipped': False
    }

# =============================================================================
# Phase 2: レース詳細データ補完
# =============================================================================

from src.scraper.result_scraper import ResultScraper
import random

def get_races_without_details(db_path, start_date=None, end_date=None):
    """レース詳細が欠損しているレースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    date_filter = ""
    params = []

    if start_date and end_date:
        date_filter = "AND r.race_date BETWEEN ? AND ?"
        params = [start_date, end_date]
        log_print(f"  期間フィルター: {start_date} ～ {end_date}")
    elif start_date:
        date_filter = "AND r.race_date >= ?"
        params = [start_date]
        log_print(f"  期間フィルター: {start_date} 以降")
    elif end_date:
        date_filter = "AND r.race_date <= ?"
        params = [end_date]
        log_print(f"  期間フィルター: {end_date} まで")
    else:
        log_print("  期間フィルターなし（全期間対象）")

    query = f"""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE EXISTS (
            SELECT 1 FROM race_details rd
            WHERE rd.race_id = r.id
            AND (rd.st_time IS NULL OR rd.actual_course IS NULL)
        )
        {date_filter}
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    log_print(f"  ST time/actual_courseが未収集のレース数: {len(rows):,}件")
    return rows

# スレッドローカルスクレイパー
def get_scraper():
    """スレッドごとのスクレイパーを取得"""
    if not hasattr(thread_local, "scraper"):
        thread_local.scraper = ResultScraper(read_timeout=15)
    return thread_local.scraper

def fetch_race_details(race_id, venue_code, race_date, race_number):
    """指定されたレースの詳細データを取得"""
    date_str = race_date.replace('-', '')
    scraper = get_scraper()

    max_retries = 2
    base_wait = 0.5

    for attempt in range(max_retries):
        try:
            result = scraper.get_race_result_complete(venue_code, date_str, race_number)

            if result:
                # resultから各艇ごとのrace_details形式に変換
                st_times = result.get('st_times', {})
                actual_courses = result.get('actual_courses', {})

                # データがない場合はskip
                if not st_times and not actual_courses:
                    return (race_id, None, 'skip')

                # pit_numberごとのデータを構築
                details_data = []
                all_pit_numbers = set(st_times.keys()) | set(actual_courses.keys())

                for pit_number in all_pit_numbers:
                    detail = {'pit_number': pit_number}

                    if pit_number in st_times:
                        detail['st_time'] = st_times[pit_number]
                    if pit_number in actual_courses:
                        detail['actual_course'] = actual_courses[pit_number]

                    # 他のフィールド（将来の拡張用）
                    # tilt_angle, exhibition_time, chikusen_time等は
                    # result_scraperが対応していないため現時点では取得不可

                    details_data.append(detail)

                return (race_id, details_data, 'success')
            else:
                return (race_id, None, 'skip')

        except Exception as e:
            error_str = str(e).lower()
            if 'timeout' in error_str or 'timed out' in error_str:
                return (race_id, None, 'timeout')

            if attempt < max_retries - 1:
                wait_time = base_wait * (2 ** attempt) + random.uniform(0, 0.3)
                time.sleep(wait_time)
                continue
            else:
                return (race_id, None, 'error')

    return (race_id, None, 'error')

def run_phase2_race_details(start_date=None, end_date=None):
    """Phase 2: レース詳細データ補完を実行"""
    log_print("\n" + "="*80)
    log_print("Phase 2: レース詳細データ補完（st_time, chikusen_time等）")
    log_print("="*80)

    rows = get_races_without_details(DB_PATH, start_date, end_date)

    if len(rows) == 0:
        log_print("  補完が必要なレースはありません。Phase 2をスキップします。\n")
        return {
            'phase': 'Phase 2: レース詳細データ補完',
            'total': 0,
            'success': 0,
            'skip': 0,
            'timeout': 0,
            'error': 0,
            'elapsed': 0,
            'skipped': True
        }

    log_print(f"  補完対象: {len(rows):,}件")
    log_print("  処理を開始します...")
    log_print("  仕様: 12ワーカー並列、バッチサイズ200、タイムアウト15秒\n")

    # カウンター
    success_count = 0
    error_count = 0
    skip_count = 0
    timeout_count = 0
    counter_lock = Lock()
    db_lock = Lock()

    # race_detailsキャッシュを構築
    log_print("  race_detailsキャッシュを構築中...")
    db_conn = sqlite3.connect(DB_PATH)
    db_cursor = db_conn.cursor()

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

    log_print(f"  キャッシュ構築完了: {len(race_details_cache):,}レース\n")

    # バッチ更新用バッファ
    update_buffer = []
    BATCH_SIZE = 200

    def save_batch():
        """バッファのデータをDBに保存"""
        nonlocal update_buffer
        if update_buffer:
            with db_lock:
                for race_id, details_data in update_buffer:
                    for detail in details_data:
                        pit_number = detail.get('pit_number')
                        if not pit_number:
                            continue

                        if race_id in race_details_cache and pit_number in race_details_cache[race_id]:
                            detail_id = race_details_cache[race_id][pit_number]

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

    # 並列処理（メモリ負荷軽減のため6ワーカーに削減）
    start_time = time.time()
    max_workers = 6

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_race_details, race_id, venue_code, race_date, race_number): (race_id, venue_code, race_date, race_number)
            for race_id, venue_code, race_date, race_number in rows
        }

        processed = 0

        for future in as_completed(futures):
            race_id, details_data, status = future.result()
            processed += 1

            if status == 'success':
                update_buffer.append((race_id, details_data))
                with counter_lock:
                    success_count += 1

                if len(update_buffer) >= BATCH_SIZE:
                    saved = save_batch()
                    if saved:
                        log_print(f"  [{processed}/{len(rows)}] 保存完了: {BATCH_SIZE}レース ({success_count}/{len(rows)}件)")

            elif status == 'skip':
                with counter_lock:
                    skip_count += 1
            elif status == 'timeout':
                with counter_lock:
                    timeout_count += 1
            else:
                with counter_lock:
                    error_count += 1

            if processed % 100 == 0:
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                remaining = (len(rows) - processed) / speed if speed > 0 else 0
                log_print(f"  進捗: {processed}/{len(rows)} ({processed/len(rows)*100:.1f}%) - {speed:.1f}件/秒 - 残り約{remaining/60:.1f}分")

    # 残りのバッファを保存
    if update_buffer:
        saved = save_batch()
        if saved:
            log_print(f"  最終バッチ保存完了: {saved}レース")

    db_conn.close()

    elapsed_total = time.time() - start_time

    log_print("\n" + "-"*80)
    log_print("Phase 2 完了")
    log_print("-"*80)
    log_print(f"  対象レース数: {len(rows):,}")
    log_print(f"  取得成功: {success_count:,}件")
    log_print(f"  スキップ: {skip_count:,}件（レースデータなし）")
    log_print(f"  タイムアウト: {timeout_count:,}件")
    log_print(f"  取得失敗: {error_count:,}件")
    total = success_count + error_count + skip_count + timeout_count
    if total > 0:
        log_print(f"  成功率: {success_count/total*100:.1f}%")
    log_print(f"  処理時間: {elapsed_total/60:.1f}分")
    log_print(f"  処理速度: {len(rows)/elapsed_total:.1f}件/秒")
    log_print("-"*80 + "\n")

    return {
        'phase': 'Phase 2: レース詳細データ補完',
        'total': len(rows),
        'success': success_count,
        'skip': skip_count,
        'timeout': timeout_count,
        'error': error_count,
        'elapsed': elapsed_total,
        'skipped': False
    }

# =============================================================================
# メイン処理
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='データ補完統合スクリプト（放置実行対応）')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    args = parser.parse_args()

    log_print("="*80)
    log_print("データ補完統合スクリプト（放置実行対応）")
    log_print("="*80)
    log_print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"ログファイル: {LOG_FILE}")
    log_print("="*80 + "\n")

    overall_start = time.time()

    # Phase 1: 決まり手データ補完
    phase1_result = run_phase1_kimarite(args.start_date, args.end_date)

    # Phase 2: レース詳細データ補完
    phase2_result = run_phase2_race_details(args.start_date, args.end_date)

    overall_elapsed = time.time() - overall_start

    # 最終レポート
    log_print("\n" + "="*80)
    log_print("最終レポート")
    log_print("="*80)
    log_print(f"実行完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"総処理時間: {overall_elapsed/3600:.2f}時間（{overall_elapsed/60:.1f}分）")
    log_print("\n" + "-"*80)
    log_print("Phase 1: 決まり手データ補完")
    log_print("-"*80)
    if phase1_result['skipped']:
        log_print("  スキップ（補完対象なし）")
    else:
        log_print(f"  対象: {phase1_result['total']:,}件")
        log_print(f"  成功: {phase1_result['success']:,}件")
        log_print(f"  失敗: {phase1_result['error']:,}件")
        log_print(f"  成功率: {phase1_result['success']/phase1_result['total']*100:.1f}%")
        log_print(f"  処理時間: {phase1_result['elapsed']/60:.1f}分")

    log_print("\n" + "-"*80)
    log_print("Phase 2: レース詳細データ補完")
    log_print("-"*80)
    if phase2_result['skipped']:
        log_print("  スキップ（補完対象なし）")
    else:
        log_print(f"  対象: {phase2_result['total']:,}件")
        log_print(f"  成功: {phase2_result['success']:,}件")
        log_print(f"  スキップ: {phase2_result['skip']:,}件")
        log_print(f"  タイムアウト: {phase2_result['timeout']:,}件")
        log_print(f"  失敗: {phase2_result['error']:,}件")
        total = phase2_result['success'] + phase2_result['skip'] + phase2_result['timeout'] + phase2_result['error']
        if total > 0:
            log_print(f"  成功率: {phase2_result['success']/total*100:.1f}%")
        log_print(f"  処理時間: {phase2_result['elapsed']/60:.1f}分")

    log_print("\n" + "="*80)
    log_print(f"ログファイル: {LOG_FILE}")
    log_print("="*80)

if __name__ == "__main__":
    main()
