"""
環境データ収集スクリプト
天気・風向・風速・波高・気温・水温・潮位などの環境データを収集

使用方法:
  python collect_environmental_data.py --start 2015-01-01 --end 2021-12-31 --workers 5
  python collect_environmental_data.py --fill-missing --workers 5
"""

import argparse
import sys
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager
from threading import Thread
import time
import sqlite3
import queue

from src.database.data_manager import DataManager
from src.scraper.schedule_scraper import ScheduleScraper


def get_missing_weather_tasks(db_path="data/boatrace.db"):
    """
    天気データが欠損している日付を検出

    Returns:
        list: [(venue_code, date_str), ...]
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT DISTINCT
            r.venue_code,
            r.race_date
        FROM races r
        LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
        WHERE w.id IS NULL
        ORDER BY r.race_date DESC, r.venue_code
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    tasks = []
    for venue_code, race_date in rows:
        date_str = race_date.replace('-', '')
        tasks.append((venue_code, date_str))

    conn.close()

    return tasks


def fetch_environmental_data_only(args):
    """
    環境データのみ取得 (HTTP通信のみ、DB書き込みなし)

    Args:
        args: (venue_code, date_str) のタプル

    Returns:
        dict: 取得した環境データ
    """
    venue_code, date_str = args

    result = {
        'venue_code': venue_code,
        'date_str': date_str,
        'success': False,
        'error': None,
        'weather_data': None
    }

    try:
        # ResultScraperを使って環境データを取得
        # 任意のレース(1R)から天気データを抽出
        from src.scraper.result_scraper import ResultScraper

        scraper = ResultScraper()

        # 1Rの結果ページから天気情報を取得
        race_result = scraper.get_race_result_complete(venue_code, date_str, 1)

        if race_result and race_result.get('weather_data'):
            result['weather_data'] = race_result['weather_data']
            result['success'] = True
        else:
            result['error'] = '天気データなし'

        scraper.close()

    except Exception as e:
        result['error'] = str(e)

    return result


def db_writer_worker(data_queue, stats, stop_event):
    """
    DB書き込み専用ワーカー

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
            weather_data = data['weather_data']

            # 日付フォーマット変換
            race_date_obj = datetime.strptime(date_str, '%Y%m%d')
            race_date_formatted = race_date_obj.strftime('%Y-%m-%d')

            # リトライ機構付きDB書き込み
            for attempt in range(retry_max):
                try:
                    if weather_data:
                        success = db.save_weather_data(
                            venue_code=venue_code,
                            weather_date=race_date_formatted,
                            weather_data=weather_data
                        )

                        if success:
                            stats['saved'] += 1
                            print(f"[OK] {venue_code} {date_str} 環境データ保存完了")
                            break
                        else:
                            if attempt < retry_max - 1:
                                time.sleep(retry_delay * (attempt + 1))
                                continue
                            else:
                                print(f"[ERROR] 環境データ保存失敗: {venue_code} {date_str}")
                                stats['errors'] += 1
                                break

                except sqlite3.OperationalError as e:
                    if 'locked' in str(e) and attempt < retry_max - 1:
                        print(f"[RETRY {attempt+1}] DB locked: {venue_code} {date_str}")
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        print(f"[ERROR] DB保存失敗: {venue_code} {date_str} - {e}")
                        stats['errors'] += 1
                        break

                except Exception as e:
                    print(f"[ERROR] 保存中にエラー: {venue_code} {date_str} - {e}")
                    stats['errors'] += 1
                    break

        except queue.Empty:
            continue
        except Exception as e:
            print(f"[ERROR] DBワーカー: {e}")
            continue

    print(f"\n[DBワーカー終了] 保存: {stats['saved']}件, エラー: {stats['errors']}件")


def main():
    parser = argparse.ArgumentParser(description='競艇環境データ収集')
    parser.add_argument('--start', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=5, help='ワーカー数 (デフォルト: 5)')
    parser.add_argument('--venues', help='会場コード (カンマ区切り)')
    parser.add_argument('--fill-missing', action='store_true', help='欠損データ補完モード')

    args = parser.parse_args()

    # モード判定
    if args.fill_missing:
        print("=" * 80)
        print(f"環境データ収集 - 欠損データ補完モード")
        print("=" * 80)
        print(f"ワーカー数: {args.workers}")
        print("=" * 80)

        print("\n[1] 欠損データ検出中...")
        tasks = get_missing_weather_tasks()

        print(f"  欠損データ: {len(tasks)}件")

        if len(tasks) == 0:
            print("\n欠損データはありません!")
            return

        estimated_time = len(tasks) * 1 / args.workers / 60
        print(f"  推定処理時間: 約{estimated_time:.0f}分\n")

    else:
        if not args.start or not args.end:
            print("エラー: --start と --end が必要です")
            print("または --fill-missing で欠損データ補完モードを使用してください")
            return

        start_date = datetime.strptime(args.start, '%Y-%m-%d')
        end_date = datetime.strptime(args.end, '%Y-%m-%d')

        # 会場リスト
        if args.venues:
            venue_codes = args.venues.split(',')
        else:
            venue_codes = [f"{i:02d}" for i in range(1, 25)]

        print("=" * 80)
        print(f"環境データ収集 - 新規取得モード")
        print("=" * 80)
        print(f"期間: {args.start} ～ {args.end}")
        print(f"ワーカー数: {args.workers}")
        print(f"会場: {len(venue_codes)}会場")
        print("=" * 80)

        print("\n[1] 開催スケジュール取得中...")
        schedule_scraper = ScheduleScraper()
        schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)
        schedule_scraper.close()

        # タスクリスト作成（開催日ごと、会場ごと）
        tasks = []

        if args.venues:
            for venue_code in venue_codes:
                if venue_code in schedule:
                    for date_str in schedule[venue_code]:
                        tasks.append((venue_code, date_str))
        else:
            for venue_code, dates in schedule.items():
                for date_str in dates:
                    tasks.append((venue_code, date_str))

        # 重複除去
        tasks = list(set(tasks))

        print(f"  総タスク数: {len(tasks)}件")

        estimated_time = len(tasks) * 1 / args.workers / 60
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
        futures = {executor.submit(fetch_environmental_data_only, task): task for task in tasks}

        completed = 0
        for future in as_completed(futures):
            task = futures[future]
            venue_code, date_str = task

            try:
                result = future.result()
                completed += 1

                if result['success']:
                    data_queue.put(result)
                    stats['fetched'] += 1
                else:
                    error_msg = result.get('error', 'Unknown')
                    print(f"[SKIP] {venue_code} {date_str} - {error_msg}")

                if completed % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (len(tasks) - completed) / rate if rate > 0 else 0
                    print(f"\n[進捗] {completed}/{len(tasks)} ({completed/len(tasks)*100:.1f}%) - {rate:.1f}件/秒 - 残り約{remaining/60:.0f}分")
                    print(f"  取得: {stats['fetched']}件, 保存: {stats['saved']}件, エラー: {stats['errors']}件\n")

            except Exception as e:
                print(f"[ERROR] {venue_code} {date_str} - {e}")
                completed += 1

    # DB書き込みスレッド終了待ち
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


if __name__ == '__main__':
    main()
