"""
並列データ取得スクリプト - 改善版
F/L対応のImprovedResultScraperを使用

使用方法:
  python fetch_parallel_improved.py --fill-missing --workers 10
  python fetch_parallel_improved.py --start 2015-01-01 --end 2021-12-31 --workers 10
"""

import argparse
import sys
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import Manager
from threading import Thread
import time
import sqlite3
import queue
import shutil
import os

# データベースとスクレイパーのインポート
from src.database.data_manager import DataManager
from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.result_scraper_improved import ImprovedResultScraper  # 改善版を使用
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.schedule_scraper import ScheduleScraper


def get_missing_data_tasks(db_path="data/boatrace.db"):
    """
    データベースから欠損データを検出してタスクリストを作成

    Returns:
        list: [(venue_code, date_str, race_number), ...]
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # race_detailsが不足しているレースを抽出
    query = """
        SELECT DISTINCT
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE rd.race_id IS NULL
           OR rd.exhibition_time IS NULL
           OR rd.st_time IS NULL
           OR rd.actual_course IS NULL
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    tasks = []
    for venue_code, race_date, race_number in rows:
        date_str = race_date.replace('-', '')
        tasks.append((venue_code, date_str, race_number))

    conn.close()

    return tasks


def fetch_http_only(args):
    """
    HTTP通信のみ実行（DB書き込みなし）
    改善版スクレイパーを使用してF/L対応

    Args:
        args: (venue_code, date_str, race_number) のタプル

    Returns:
        dict: 取得したデータ全て
    """
    venue_code, date_str, race_number = args

    result = {
        'venue_code': venue_code,
        'date_str': date_str,
        'race_number': race_number,
        'success': False,
        'error': None,
        'race_data': None,
        'beforeinfo': None,
        'complete_result': None
    }

    try:
        # スクレイパー初期化 (改善版を使用)
        race_scraper = RaceScraperV2()
        result_scraper = ImprovedResultScraper()  # 改善版
        beforeinfo_scraper = BeforeInfoScraper(delay=0.3)

        # 3つのHTTPリクエストを並列実行
        def fetch_race_data():
            return race_scraper.get_race_card(venue_code, date_str, race_number)

        def fetch_beforeinfo():
            return beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)

        def fetch_result():
            return result_scraper.get_race_result_complete(venue_code, date_str, race_number)

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_race = executor.submit(fetch_race_data)
            future_before = executor.submit(fetch_beforeinfo)
            future_result = executor.submit(fetch_result)

            race_data = future_race.result()
            beforeinfo = future_before.result()
            complete_result = future_result.result()

        # 出走表が空の場合はスキップ
        if not race_data or len(race_data.get('entries', [])) == 0:
            result['error'] = '出走表が空'
            race_scraper.close()
            result_scraper.close()
            beforeinfo_scraper.close()
            return result

        result['race_data'] = race_data
        result['beforeinfo'] = beforeinfo
        result['complete_result'] = complete_result

        # クリーンアップ
        race_scraper.close()
        result_scraper.close()
        beforeinfo_scraper.close()

        result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


def db_writer_worker(data_queue, stats, stop_event):
    """
    DB書き込み専用ワーカー（1スレッドで直列実行）
    改善版: st_statusも保存

    Args:
        data_queue: データキュー
        stats: 統計情報の共有dict
        stop_event: 停止イベント
    """
    db = DataManager()
    retry_max = 3
    retry_delay = 0.5

    while not stop_event.is_set() or not data_queue.empty():
        try:
            data = data_queue.get(timeout=1.0)

            if data is None:
                break

            venue_code = data['venue_code']
            date_str = data['date_str']
            race_number = data['race_number']

            # リトライ機構付きDB書き込み
            for attempt in range(retry_max):
                try:
                    # 1. 出走表保存
                    race_data = data['race_data']
                    if race_data:
                        success = db.save_race_data(race_data)
                        if not success:
                            if attempt < retry_max - 1:
                                time.sleep(retry_delay * (attempt + 1))
                                continue
                            else:
                                print(f"[ERROR] DB保存失敗: {venue_code} {date_str} {race_number}R (出走表)")
                                stats['errors'] += 1
                                break

                    # レースIDを取得
                    race_date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    race_record = db.get_race_data(venue_code, race_date_formatted, race_number)

                    if not race_record:
                        if attempt < retry_max - 1:
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        else:
                            print(f"[ERROR] レースID取得失敗: {venue_code} {date_str} {race_number}R")
                            stats['errors'] += 1
                            break

                    race_id = race_record['id']

                    # 2. 事前情報保存
                    beforeinfo = data['beforeinfo']
                    if beforeinfo:
                        detail_updates = []
                        for pit in range(1, 7):
                            pit_detail = {'pit_number': pit}

                            if pit in beforeinfo.get('exhibition_times', {}):
                                pit_detail['exhibition_time'] = beforeinfo['exhibition_times'][pit]
                            if pit in beforeinfo.get('tilt_angles', {}):
                                pit_detail['tilt_angle'] = beforeinfo['tilt_angles'][pit]
                            if pit in beforeinfo.get('parts_replacements', {}):
                                pit_detail['parts_replacement'] = beforeinfo['parts_replacements'][pit]

                            if len(pit_detail) > 1:
                                detail_updates.append(pit_detail)

                        if detail_updates:
                            db.save_race_details(race_id, detail_updates)

                    # 3. 結果保存
                    complete_result = data['complete_result']
                    if complete_result and not complete_result.get('is_invalid'):
                        # 決まり手を数値コードに変換
                        kimarite_text = complete_result.get('kimarite')
                        winning_technique = None
                        if kimarite_text:
                            kimarite_map = {
                                '逃げ': 1,
                                '差し': 2,
                                'まくり': 3,
                                'まくり差し': 4,
                                '抜き': 5,
                                '恵まれ': 6
                            }
                            winning_technique = kimarite_map.get(kimarite_text)

                        # 結果データ保存
                        result_data_for_save = {
                            'venue_code': venue_code,
                            'race_date': date_str,
                            'race_number': race_number,
                            'results': complete_result.get('results', []),
                            'trifecta_odds': complete_result.get('trifecta_odds'),
                            'is_invalid': complete_result.get('is_invalid', False),
                            'winning_technique': winning_technique,
                            'kimarite': kimarite_text
                        }
                        db.save_race_result(result_data_for_save)

                        # 進入コース・STタイム保存 (改善版: F/L対応)
                        actual_courses = complete_result.get('actual_courses', {})
                        st_times = complete_result.get('st_times', {})
                        st_status = complete_result.get('st_status', {})  # 新規

                        if actual_courses or st_times:
                            detail_updates = []
                            for pit in range(1, 7):
                                pit_detail = {'pit_number': pit}

                                if pit in actual_courses:
                                    pit_detail['actual_course'] = actual_courses[pit]
                                if pit in st_times:
                                    pit_detail['st_time'] = st_times[pit]

                                if len(pit_detail) > 1:
                                    detail_updates.append(pit_detail)

                            if detail_updates:
                                db.save_race_details(race_id, detail_updates)

                            # STステータスをログ出力 (デバッグ用)
                            if st_status:
                                flying_pits = [p for p, s in st_status.items() if s == 'flying']
                                late_pits = [p for p, s in st_status.items() if s == 'late']
                                if flying_pits:
                                    print(f"  [F] {venue_code} {date_str} {race_number}R - フライング: {flying_pits}")
                                if late_pits:
                                    print(f"  [L] {venue_code} {date_str} {race_number}R - 出遅れ: {late_pits}")

                        # 天気データ保存
                        weather_data = complete_result.get('weather_data')
                        if weather_data:
                            race_date_obj = datetime.strptime(date_str, '%Y%m%d')
                            db.save_weather_data(
                                venue_code=venue_code,
                                weather_date=race_date_obj.strftime('%Y-%m-%d'),
                                weather_data=weather_data
                            )

                        # 払戻金保存
                        payouts = complete_result.get('payouts', {})
                        if payouts:
                            db.save_payouts(race_id, payouts)

                    # 成功
                    stats['saved'] += 1
                    st_count = len(complete_result.get('st_times', {})) if complete_result else 0
                    print(f"[OK] {venue_code} {date_str} {race_number:2d}R 保存完了 (ST: {st_count}/6)")
                    break

                except sqlite3.OperationalError as e:
                    if 'locked' in str(e) and attempt < retry_max - 1:
                        print(f"[RETRY {attempt+1}] DB locked: {venue_code} {date_str} {race_number}R")
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        print(f"[ERROR] DB保存失敗: {venue_code} {date_str} {race_number}R - {e}")
                        stats['errors'] += 1
                        break

                except Exception as e:
                    print(f"[ERROR] 保存中にエラー: {venue_code} {date_str} {race_number}R - {e}")
                    stats['errors'] += 1
                    break

        except queue.Empty:
            continue
        except Exception as e:
            print(f"[ERROR] DBワーカー: {e}")
            continue

    print(f"\n[DBワーカー終了] 保存: {stats['saved']}件, エラー: {stats['errors']}件")


def sync_database():
    """書き込み用DBを参照用DBに同期"""
    source_db = "data/boatrace.db"
    target_db = "data/boatrace_readonly.db"

    print("\n" + "=" * 80)
    print("データベース同期開始")
    print("=" * 80)

    try:
        if os.path.exists(source_db):
            shutil.copy2(source_db, target_db)
            print(f"[OK] {source_db} -> {target_db}")
        else:
            print(f"[NG] ソースDBが見つかりません: {source_db}")
            return False

        source_wal = f"{source_db}-wal"
        target_wal = f"{target_db}-wal"
        if os.path.exists(source_wal):
            shutil.copy2(source_wal, target_wal)
            print(f"[OK] {source_wal} -> {target_wal}")

        source_shm = f"{source_db}-shm"
        target_shm = f"{target_db}-shm"
        if os.path.exists(source_shm):
            shutil.copy2(source_shm, target_shm)
            print(f"[OK] {source_shm} -> {target_shm}")

        if os.path.exists(target_db):
            source_size = os.path.getsize(source_db)
            target_size = os.path.getsize(target_db)
            print(f"\n同期完了:")
            print(f"  書き込み用DB: {source_size:,} bytes")
            print(f"  参照用DB: {target_size:,} bytes")
            print(f"\n参照用DBパス: {target_db}")
            print("=" * 80)
            return True
        else:
            print("[NG] 同期に失敗しました")
            return False

    except Exception as e:
        print(f"[NG] 同期エラー: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='競艇データ並列取得 - 改善版 (F/L対応)')
    parser.add_argument('--start', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=10, help='HTTPワーカー数 (デフォルト: 10)')
    parser.add_argument('--venues', help='会場コード (カンマ区切り)')
    parser.add_argument('--fill-missing', action='store_true', help='欠損データ補完モード')
    parser.add_argument('--limit', type=int, help='補完モード時の最大取得件数')

    args = parser.parse_args()

    if args.fill_missing:
        print("=" * 80)
        print(f"競艇データ並列取得 - 改善版 (F/L対応) - 欠損データ補完モード")
        print("=" * 80)
        print(f"HTTPワーカー数: {args.workers}")
        print("=" * 80)

        print("\n[1] 欠損データ検出中...")
        tasks = get_missing_data_tasks()

        if args.limit:
            tasks = tasks[:args.limit]
            print(f"  欠損データ: {len(tasks)}件（制限: {args.limit}件）")
        else:
            print(f"  欠損データ: {len(tasks)}件")

        if len(tasks) == 0:
            print("\n欠損データはありません!")
            return

        estimated_time = len(tasks) * 2 / args.workers / 60
        print(f"  推定処理時間: 約{estimated_time:.0f}分\n")

    else:
        if not args.start or not args.end:
            print("エラー: 新規取得モードでは --start と --end が必要です")
            print("または --fill-missing で欠損データ補完モードを使用してください")
            return

        start_date = datetime.strptime(args.start, '%Y-%m-%d')
        end_date = datetime.strptime(args.end, '%Y-%m-%d')

        if args.venues:
            venue_codes = args.venues.split(',')
        else:
            venue_codes = [f"{i:02d}" for i in range(1, 25)]

        print("=" * 80)
        print(f"競艇データ並列取得 - 改善版 (F/L対応) - 新規取得モード")
        print("=" * 80)
        print(f"期間: {args.start} ～ {args.end}")
        print(f"HTTPワーカー数: {args.workers}")
        print(f"会場: {len(venue_codes)}会場")
        print("=" * 80)

        print("\n[1] 開催スケジュール取得中...")
        schedule_scraper = ScheduleScraper()
        schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)
        schedule_scraper.close()

        tasks = []

        if args.venues:
            for venue_code in venue_codes:
                if venue_code in schedule:
                    for date_str in schedule[venue_code]:
                        for race_number in range(1, 13):
                            tasks.append((venue_code, date_str, race_number))
        else:
            for venue_code, dates in schedule.items():
                for date_str in dates:
                    for race_number in range(1, 13):
                        tasks.append((venue_code, date_str, race_number))

        total_days = sum(len(dates) for dates in schedule.values())
        print(f"  開催日数: {total_days}日")
        print(f"  総タスク数: {len(tasks)}件")

        estimated_time = len(tasks) * 2 / args.workers / 60
        print(f"  推定処理時間: 約{estimated_time:.0f}分\n")

    # 共有キューと統計情報
    manager = Manager()
    data_queue = manager.Queue(maxsize=args.workers * 2)
    stats = manager.dict()
    stats['fetched'] = 0
    stats['saved'] = 0
    stats['errors'] = 0
    stop_event = manager.Event()

    start_time = time.time()

    # DB書き込みスレッド開始
    db_thread = Thread(target=db_writer_worker, args=(data_queue, stats, stop_event))
    db_thread.start()

    # HTTPワーカープロセス実行
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_http_only, task): task for task in tasks}

        completed = 0
        for future in as_completed(futures):
            task = futures[future]
            venue_code, date_str, race_number = task

            try:
                result = future.result()
                completed += 1

                if result['success']:
                    data_queue.put(result)
                    stats['fetched'] += 1
                else:
                    error_msg = result.get('error', 'Unknown')
                    if '出走表が空' not in error_msg:
                        print(f"[SKIP] {venue_code} {date_str} {race_number:2d}R - {error_msg}")

                if completed % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (len(tasks) - completed) / rate if rate > 0 else 0
                    print(f"\n[進捗] {completed}/{len(tasks)} ({completed/len(tasks)*100:.1f}%) - {rate:.1f}件/秒 - 残り約{remaining/60:.0f}分")
                    print(f"  取得: {stats['fetched']}件, 保存: {stats['saved']}件, エラー: {stats['errors']}件\n")

            except Exception as e:
                print(f"[ERROR] {venue_code} {date_str} {race_number:2d}R - {e}")
                completed += 1

    print("\n全HTTPワーカー完了。DB書き込み完了待ち...")
    stop_event.set()
    db_thread.join(timeout=300)

    elapsed = time.time() - start_time

    print("\n" + "=" * 80)
    print("処理完了")
    print("=" * 80)
    print(f"総タスク数: {len(tasks)}件")
    print(f"取得成功: {stats['fetched']}件")
    print(f"保存成功: {stats['saved']}件")
    print(f"エラー: {stats['errors']}件")
    print(f"処理時間: {elapsed/60:.1f}分")
    print(f"処理速度: {len(tasks)/elapsed*60:.1f}件/分")
    if len(tasks) > 0:
        print(f"成功率: {stats['saved']/len(tasks)*100:.1f}%")
    print("=" * 80)

    sync_database()


if __name__ == '__main__':
    main()
