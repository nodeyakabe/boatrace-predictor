"""
過去データ拡張スクリプト v3 - 最終保存日から実行日までの全レース自動取得

改善点:
- 最終保存日を自動検出
- 全24会場を常に対象
- 会場指定機能は削除（全会場取得のみ）
- データ有無を判断しながら柔軟に取得
- 2016年以降: 出走表 + 結果
- 2017年以降: 出走表 + 結果 + 直前情報
- エラーではなくスキップとして処理

取得内容（年代別）:
- 2016-2016: 出走表、結果のみ
- 2017-2022: 出走表、結果、直前情報

実行方法:
    python fetch_historical_data.py --workers 4
    # 開始日・終了日を省略すると、最終保存日から今日までを自動取得
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


def get_last_saved_date(db_path="data/boatrace.db"):
    """
    データベースから最終保存日を取得

    Args:
        db_path: データベースパス

    Returns:
        datetime: 最終保存日（データがない場合は2016-01-01）
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT MAX(race_date) FROM races
        """)
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            last_date = datetime.strptime(result[0], '%Y-%m-%d')
            # 最終保存日の翌日から開始
            return last_date + timedelta(days=1)
        else:
            # データがない場合は2016-01-01から
            return datetime(2016, 1, 1)
    except Exception as e:
        print(f"最終保存日の取得に失敗: {e}")
        return datetime(2016, 1, 1)


def generate_tasks(start_date_str, end_date_str):
    """
    開催スケジュールに基づいて取得タスクを生成

    Args:
        start_date_str: 開始日（YYYY-MM-DD）
        end_date_str: 終了日（YYYY-MM-DD）

    Returns:
        list: [(venue_code, date_str, race_number), ...]
    """
    # 開催スケジュールを取得
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    print("\n開催スケジュール取得中...")
    schedule_scraper = ScheduleScraper()
    schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)
    schedule_scraper.close()

    if not schedule:
        print("警告: 開催スケジュールが取得できませんでした。全会場を対象とします。")
        # フォールバック: 全会場を対象
        dates = generate_date_range(start_date_str, end_date_str)
        tasks = []
        for date_str in dates:
            for venue_code in ALL_VENUES:
                for race_number in range(1, 13):
                    tasks.append((venue_code, date_str, race_number))
        return tasks

    # スケジュールに基づいてタスクを生成
    tasks = []
    total_venue_days = 0
    for venue_code, dates in schedule.items():
        total_venue_days += len(dates)
        for date_str in dates:
            # 1会場あたり最大12レース
            for race_number in range(1, 13):
                tasks.append((venue_code, date_str, race_number))

    print(f"開催会場数: {len(schedule)} 会場")
    print(f"総開催日数: {total_venue_days} 日")
    print(f"生成タスク数: {len(tasks)} タスク")

    # 従来方式との比較
    days_in_period = (end_date - start_date).days + 1
    old_task_count = days_in_period * 24 * 12
    reduction_rate = (1 - len(tasks) / old_task_count) * 100 if old_task_count > 0 else 0
    print(f"効率化: {old_task_count} タスク → {len(tasks)} タスク (削減率: {reduction_rate:.1f}%)\n")

    return tasks


def fetch_http_only(args):
    """
    HTTP通信のみ実行（DB書き込みなし）- データ有無を柔軟に判断

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
        'skipped': False,
        'skip_reason': None,
        'race_data': None,
        'beforeinfo': None,
        'complete_result': None
    }

    try:
        # 年を判定
        year = int(date_str[:4])
        fetch_beforeinfo = year >= 2017  # 2017年以降は直前情報も取得試行

        # スクレイパー初期化
        race_scraper = RaceScraperV2()
        result_scraper = ResultScraper()

        # まず出走表を取得（レースの存在確認）
        try:
            race_data = race_scraper.fetch_race_data(venue_code, date_str, race_number)
        except Exception as e:
            # デバッグ: エラーの詳細を記録
            import traceback
            print(f"\n[DEBUG] Race data fetch error for {venue_code}-{date_str}-R{race_number}: {e}")
            traceback.print_exc()
            race_data = None

        # レースが存在しない場合はスキップ
        if not race_data or 'entries' not in race_data or len(race_data['entries']) == 0:
            result['skipped'] = True
            result['skip_reason'] = 'no_race'
            return result

        result['race_data'] = race_data

        # 結果を取得
        try:
            complete_result = result_scraper.fetch_result(venue_code, date_str, race_number)
            result['complete_result'] = complete_result
        except Exception as e:
            # 結果がない場合（未来のレースなど）もスキップ
            import traceback
            print(f"\n[DEBUG] Result fetch error for {venue_code}-{date_str}-R{race_number}: {e}")
            traceback.print_exc()
            result['skipped'] = True
            result['skip_reason'] = 'no_result'
            return result

        # 直前情報を取得（2017年以降のみ試行）
        if fetch_beforeinfo:
            try:
                beforeinfo_scraper = BeforeInfoScraper()
                beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)
                result['beforeinfo'] = beforeinfo
                beforeinfo_scraper.close()
            except Exception:
                # 直前情報がなくてもエラーにしない
                pass

        result['success'] = True

    except Exception as e:
        # 予期しないエラーの場合
        import traceback
        print(f"\n[DEBUG] Unexpected error for {venue_code}-{date_str}-R{race_number}: {e}")
        traceback.print_exc()
        result['skipped'] = True
        result['skip_reason'] = f'error: {str(e)[:100]}'

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
    if not data_item['success'] or data_item['skipped']:
        return False

    try:
        data_manager = DataManager(db_path)

        race_data = data_item['race_data']
        complete_result = data_item['complete_result']
        beforeinfo = data_item.get('beforeinfo')

        # レース基本情報保存（出走表）
        if not data_manager.save_race_data(race_data):
            return False

        # race_idを取得（既存レースから取得）
        import sqlite3
        from src.utils.date_utils import to_iso_format

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        venue_code = race_data['venue_code']
        race_date = race_data['race_date']
        race_number = race_data['race_number']

        # 日付をYYYY-MM-DD形式に変換
        race_date_formatted = to_iso_format(race_date)

        cursor.execute("""
            SELECT id FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, race_date_formatted, race_number))

        race_id = cursor.fetchone()[0]
        conn.close()

        # 直前情報保存（race_details）
        if beforeinfo:
            # BeforeInfoScraperの返り値を変換
            # 入力: {'exhibition_times': {1: 6.79, ...}, 'tilt_angles': {1: 0.0, ...}, 'parts_replacements': {1: 'R', ...}}
            # 出力: [{'pit_number': 1, 'exhibition_time': 6.79, 'tilt_angle': 0.0, 'parts_replacement': 'R'}, ...]
            race_details_list = []
            all_pits = set()

            if 'exhibition_times' in beforeinfo:
                all_pits.update(beforeinfo['exhibition_times'].keys())
            if 'tilt_angles' in beforeinfo:
                all_pits.update(beforeinfo['tilt_angles'].keys())
            if 'parts_replacements' in beforeinfo:
                all_pits.update(beforeinfo['parts_replacements'].keys())

            for pit in sorted(all_pits):
                detail = {
                    'pit_number': pit,
                    'exhibition_time': beforeinfo.get('exhibition_times', {}).get(pit),
                    'tilt_angle': beforeinfo.get('tilt_angles', {}).get(pit),
                    'parts_replacement': beforeinfo.get('parts_replacements', {}).get(pit),
                }
                race_details_list.append(detail)

            if race_details_list:
                data_manager.save_race_details(race_id, race_details_list)

        # 結果保存
        if complete_result:
            data_manager.save_race_result(complete_result)

        return True

    except Exception as e:
        print(f"\n[ERROR] DB保存エラー: {e}")
        import traceback
        traceback.print_exc()
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
    stats = {
        'success': 0,
        'error': 0,
        'skip_no_race': 0,
        'skip_no_result': 0,
        'skip_other': 0,
        'with_beforeinfo': 0
    }

    while True:
        try:
            data_item = result_queue.get(timeout=1)

            if data_item is None:  # 終了シグナル
                break

            # スキップされた場合
            if data_item['skipped']:
                reason = data_item.get('skip_reason', 'unknown')
                if reason == 'no_race':
                    stats['skip_no_race'] += 1
                elif reason == 'no_result':
                    stats['skip_no_result'] += 1
                else:
                    stats['skip_other'] += 1
            # DB保存
            elif data_item['success']:
                if save_to_db(data_item, db_path):
                    stats['success'] += 1
                    # 直前情報があるかチェック
                    if data_item.get('beforeinfo'):
                        stats['with_beforeinfo'] += 1
                else:
                    stats['error'] += 1
            else:
                stats['error'] += 1

            # 進捗コールバック
            if progress_callback:
                progress_callback(stats)

        except queue.Empty:
            continue
        except Exception as e:
            print(f"\n[ERROR] セーバーエラー: {e}")
            stats['error'] += 1


def main():
    parser = argparse.ArgumentParser(description='過去データ拡張スクリプト（最終保存日から自動取得）')
    parser.add_argument('--start-date', type=str, default=None,
                        help='開始日（YYYY-MM-DD）省略時は最終保存日の翌日')
    parser.add_argument('--end-date', type=str, default=None,
                        help='終了日（YYYY-MM-DD）省略時は今日')
    parser.add_argument('--workers', type=int, default=12,
                        help='並列ワーカー数')
    parser.add_argument('--db-path', type=str, default='data/boatrace.db',
                        help='データベースパス')

    args = parser.parse_args()

    # 開始日・終了日の自動設定
    if args.start_date is None:
        start_date = get_last_saved_date(args.db_path)
        start_date_str = start_date.strftime('%Y-%m-%d')
        print(f"📅 最終保存日を検出: {(start_date - timedelta(days=1)).strftime('%Y-%m-%d')}")
        print(f"📅 開始日を自動設定: {start_date_str}")
    else:
        start_date_str = args.start_date

    if args.end_date is None:
        end_date_str = datetime.now().strftime('%Y-%m-%d')
        print(f"📅 終了日を自動設定: {end_date_str}（今日）")
    else:
        end_date_str = args.end_date

    print("=" * 80)
    print("過去データ拡張スクリプト v3 - 全会場自動取得")
    print("=" * 80)
    print(f"期間: {start_date_str} ～ {end_date_str}")
    print(f"会場: 全24会場（固定）")
    print(f"ワーカー数: {args.workers}")
    print(f"データベース: {args.db_path}")
    print("=" * 80)

    # タスク生成
    print("\nタスクを生成中...")
    tasks = generate_tasks(start_date_str, end_date_str)
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
    stats_ref = [{'success': 0, 'error': 0, 'skip_no_race': 0, 'skip_no_result': 0,
                  'skip_other': 0, 'with_beforeinfo': 0}]

    def progress_callback(stats):
        stats_ref[0] = stats.copy()

        completed = (stats['success'] + stats['error'] + stats['skip_no_race'] +
                     stats['skip_no_result'] + stats['skip_other'])
        elapsed = time.time() - start_time
        rate = completed / elapsed if elapsed > 0 else 0
        remaining = (total_tasks - completed) / rate if rate > 0 else 0

        print(f"\r進捗: {completed}/{total_tasks} "
              f"(成功:{stats['success']}, 直前情報:{stats['with_beforeinfo']}, "
              f"スキップ:{stats['skip_no_race']+stats['skip_no_result']}, "
              f"エラー:{stats['error']}) "
              f"{rate:.1f}件/秒 残り:{remaining/60:.0f}分", end='')

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
    stats = stats_ref[0]

    print(f"\n\n完了!")
    print("=" * 80)
    print(f"総実行時間: {elapsed/60:.1f}分")
    print(f"平均速度: {total_tasks/elapsed:.1f}件/秒")
    print()
    print(f"成功: {stats['success']:,}件")
    print(f"  - うち直前情報あり: {stats['with_beforeinfo']:,}件 "
          f"({stats['with_beforeinfo']/stats['success']*100 if stats['success']>0 else 0:.1f}%)")
    print()
    print(f"スキップ: {stats['skip_no_race']+stats['skip_no_result']+stats['skip_other']:,}件")
    print(f"  - レース不存在: {stats['skip_no_race']:,}件")
    print(f"  - 結果未確定: {stats['skip_no_result']:,}件")
    print(f"  - その他: {stats['skip_other']:,}件")
    print()
    print(f"エラー: {stats['error']:,}件")
    print("=" * 80)


if __name__ == '__main__':
    main()
