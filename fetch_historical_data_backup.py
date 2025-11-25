"""
過去データ拡張スクリプト - 2020年～2022年10月のデータ取得

目的:
- 現在のデータ: 2022年11月～2025年10月（約3年）
- 拡張後: 2020年1月～2025年10月（約6年）
- 追加期間: 2020年1月～2022年10月（約2年10ヶ月）

取得内容:
1. レース基本情報
2. 出走表（選手情報）
3. 結果データ
4. レース詳細（展示タイム、決まり手等）

実行方法:
    python fetch_historical_data.py --start-date 2020-01-01 --end-date 2022-10-31 --workers 4
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
import os

# データベースとスクレイパーのインポート
from src.database.data_manager import DataManager
from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.result_scraper import ResultScraper
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.scraper.schedule_scraper import ScheduleScraper


# 全24会場コード
ALL_VENUES = [
    '01',  # 桐生
    '02',  # 戸田
    '03',  # 江戸川
    '04',  # 平和島
    '05',  # 多摩川
    '06',  # 浜名湖
    '07',  # 蒲郡
    '08',  # 常滑
    '09',  # 津
    '10',  # 三国
    '11',  # びわこ
    '12',  # 住之江
    '13',  # 尼崎
    '14',  # 鳴門
    '15',  # 丸亀
    '16',  # 児島
    '17',  # 宮島
    '18',  # 徳山
    '19',  # 下関
    '20',  # 若松
    '21',  # 芦屋
    '22',  # 福岡
    '23',  # 唐津
    '24',  # 大村
]


def generate_date_range(start_date_str, end_date_str):
    """
    期間内の全日付を生成

    Args:
        start_date_str: 開始日（YYYY-MM-DD）
        end_date_str: 終了日（YYYY-MM-DD）

    Returns:
        list: YYYYMMDD形式の日付リスト
    """
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.strftime('%Y%m%d'))
        current_date += timedelta(days=1)

    return dates


def generate_tasks(start_date_str, end_date_str, venues=None):
    """
    取得タスクを生成

    Args:
        start_date_str: 開始日（YYYY-MM-DD）
        end_date_str: 終了日（YYYY-MM-DD）
        venues: 会場コードリスト（Noneなら全会場）

    Returns:
        list: [(venue_code, date_str, race_number), ...]
    """
    if venues is None:
        venues = ALL_VENUES

    dates = generate_date_range(start_date_str, end_date_str)

    tasks = []
    for date_str in dates:
        for venue_code in venues:
            # 1会場あたり最大12レース
            for race_number in range(1, 13):
                tasks.append((venue_code, date_str, race_number))

    return tasks


def fetch_http_only(args):
    """
    HTTP通信のみ実行（DB書き込みなし）

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
        # スクレイパー初期化
        race_scraper = RaceScraperV2()
        result_scraper = ResultScraper()
        beforeinfo_scraper = BeforeInfoScraper()

        # 並列HTTP取得（ThreadPoolExecutorで3つ同時実行）
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_race = executor.submit(race_scraper.fetch_race_data, venue_code, date_str, race_number)
            future_result = executor.submit(result_scraper.fetch_result, venue_code, date_str, race_number)
            future_beforeinfo = executor.submit(beforeinfo_scraper.scrape, venue_code, date_str, race_number)

            # 結果取得
            race_data = future_race.result()
            complete_result = future_result.result()
            beforeinfo = future_beforeinfo.result()

        # データ検証
        if not race_data or 'entries' not in race_data or len(race_data['entries']) == 0:
            result['error'] = 'レースが存在しないか、エントリーがありません'
            return result

        result['race_data'] = race_data
        result['beforeinfo'] = beforeinfo
        result['complete_result'] = complete_result
        result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


def save_to_db(data_item, db_path="data/boatrace.db"):
    """
    データベースに保存

    Args:
        data_item: fetch_http_onlyの返り値
        db_path: データベースパス

    Returns:
        bool: 保存成功ならTrue
    """
    if not data_item['success']:
        return False

    try:
        data_manager = DataManager(db_path)

        race_data = data_item['race_data']
        beforeinfo = data_item['beforeinfo']
        complete_result = data_item['complete_result']

        # レース基本情報保存
        race_id = data_manager.save_race(race_data)

        if race_id:
            # race_details保存
            if beforeinfo:
                data_manager.save_race_details(race_id, beforeinfo)

            # 結果保存
            if complete_result and 'results' in complete_result:
                data_manager.save_results(race_id, complete_result['results'])

        return True

    except Exception as e:
        print(f"[ERROR] DB保存エラー: {e}")
        return False


def worker_process(task_queue, result_queue, total_tasks):
    """
    ワーカープロセス: HTTP取得のみ実行

    Args:
        task_queue: タスクキュー
        result_queue: 結果キュー
        total_tasks: 総タスク数
    """
    while True:
        try:
            task = task_queue.get(timeout=1)
            if task is None:  # 終了シグナル
                break

            result = fetch_http_only(task)
            result_queue.put(result)

        except queue.Empty:
            continue
        except Exception as e:
            print(f"[ERROR] ワーカーエラー: {e}")


def saver_thread(result_queue, db_path, progress_callback=None):
    """
    セーバースレッド: DB書き込み専用

    Args:
        result_queue: 結果キュー
        db_path: データベースパス
        progress_callback: 進捗コールバック関数
    """
    success_count = 0
    error_count = 0

    while True:
        try:
            data_item = result_queue.get(timeout=1)

            if data_item is None:  # 終了シグナル
                break

            # DB保存
            if save_to_db(data_item, db_path):
                success_count += 1
            else:
                error_count += 1

            # 進捗コールバック
            if progress_callback:
                progress_callback(success_count, error_count)

        except queue.Empty:
            continue
        except Exception as e:
            print(f"[ERROR] セーバーエラー: {e}")
            error_count += 1


def main():
    parser = argparse.ArgumentParser(description='過去データ拡張スクリプト')
    parser.add_argument('--start-date', type=str, default='2020-01-01',
                        help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end-date', type=str, default='2022-10-31',
                        help='終了日（YYYY-MM-DD）')
    parser.add_argument('--workers', type=int, default=4,
                        help='並列ワーカー数')
    parser.add_argument('--venues', type=str, default=None,
                        help='会場コード（カンマ区切り）。未指定なら全会場')
    parser.add_argument('--db-path', type=str, default='data/boatrace.db',
                        help='データベースパス')

    args = parser.parse_args()

    # 会場リスト
    if args.venues:
        venues = args.venues.split(',')
    else:
        venues = ALL_VENUES

    print("=" * 80)
    print("過去データ拡張スクリプト")
    print("=" * 80)
    print(f"期間: {args.start_date} ～ {args.end_date}")
    print(f"会場: {len(venues)}会場")
    print(f"ワーカー数: {args.workers}")
    print(f"データベース: {args.db_path}")
    print("=" * 80)

    # タスク生成
    print("\nタスクを生成中...")
    tasks = generate_tasks(args.start_date, args.end_date, venues)
    total_tasks = len(tasks)
    print(f"総タスク数: {total_tasks:,}件")

    # マネージャーとキュー作成
    manager = Manager()
    task_queue = manager.Queue()
    result_queue = manager.Queue()

    # タスクをキューに投入
    for task in tasks:
        task_queue.put(task)

    # 終了シグナル（ワーカー数分）
    for _ in range(args.workers):
        task_queue.put(None)

    # 進捗表示用
    start_time = time.time()
    success_count = [0]
    error_count = [0]

    def progress_callback(success, error):
        success_count[0] = success
        error_count[0] = error

        completed = success + error
        elapsed = time.time() - start_time
        rate = completed / elapsed if elapsed > 0 else 0
        remaining = (total_tasks - completed) / rate if rate > 0 else 0

        print(f"\r進捗: {completed}/{total_tasks} "
              f"(成功: {success}, エラー: {error}) "
              f"速度: {rate:.1f}件/秒 残り: {remaining/60:.1f}分", end='')

    # セーバースレッド起動
    saver = Thread(target=saver_thread, args=(result_queue, args.db_path, progress_callback))
    saver.start()

    # ワーカープロセス起動
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for i in range(args.workers):
            future = executor.submit(worker_process, task_queue, result_queue, total_tasks)
            futures.append(future)

        # 全ワーカーの完了待ち
        for future in futures:
            future.result()

    # セーバー終了シグナル
    result_queue.put(None)
    saver.join()

    # 結果表示
    elapsed = time.time() - start_time
    print(f"\n\n完了!")
    print(f"総実行時間: {elapsed/60:.1f}分")
    print(f"成功: {success_count[0]}件")
    print(f"エラー: {error_count[0]}件")
    print(f"平均速度: {total_tasks/elapsed:.1f}件/秒")


if __name__ == '__main__':
    main()
