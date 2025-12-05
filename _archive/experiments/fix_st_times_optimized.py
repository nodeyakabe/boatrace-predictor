#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ST時間データ補充スクリプト（最適化版）

主な改善点:
1. タスク投入時の遅延を削除（スレッドプール側で制御）
2. DB更新をバッチ化
3. 修正後の確認を省略（レスポンスデータを信頼）
4. HTTPセッションの再利用を最適化
"""
import sys
import os
import sqlite3
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Semaphore
import queue

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

# データベースパス
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')

# スレッドセーフなロック
db_lock = Lock()
stats_lock = Lock()

# レート制限用セマフォ
rate_limiter = None


def count_st_times_in_race(race_id):
    """
    レースのST時間が何個あるか数える

    Returns:
        int: ST時間の数（0-6）
    """
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT COUNT(*)
            FROM race_details
            WHERE race_id = ? AND st_time IS NOT NULL AND st_time != ''
        ''', (race_id,))

        count = cursor.fetchone()[0]
        conn.close()

        return count


def get_incomplete_st_races(start_date, end_date, target_st_count=5):
    """
    ST時間が不完全なレースを取得

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        target_st_count: 対象とするST時間数（デフォルト5: 5/6のレースを対象）

    Returns:
        list: [(race_id, venue_code, date, race_number, st_count), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ST時間が指定数のレースを取得
    cursor.execute('''
        SELECT r.id, r.venue_code, r.race_date, r.race_number,
               COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
        GROUP BY r.id
        HAVING st_count = ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date, target_st_count))

    results = cursor.fetchall()
    conn.close()

    return results


def batch_update_db(update_queue, batch_size=100, flush_interval=5):
    """
    DB更新をバッチ処理するワーカー

    Args:
        update_queue: 更新データのキュー
        batch_size: バッチサイズ
        flush_interval: 強制フラッシュ間隔（秒）
    """
    batch = []
    last_flush = time.time()

    while True:
        try:
            # タイムアウト付きでキューから取得
            item = update_queue.get(timeout=1)

            if item is None:  # 終了シグナル
                break

            batch.append(item)

            # バッチサイズに達したか、時間経過したらフラッシュ
            if len(batch) >= batch_size or (time.time() - last_flush) >= flush_interval:
                if batch:
                    flush_batch(batch)
                    batch = []
                    last_flush = time.time()

        except queue.Empty:
            # タイムアウト時、バッチがあればフラッシュ
            if batch and (time.time() - last_flush) >= flush_interval:
                flush_batch(batch)
                batch = []
                last_flush = time.time()
            continue

    # 残りをフラッシュ
    if batch:
        flush_batch(batch)


def flush_batch(batch):
    """バッチをDBに書き込む"""
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for race_id, st_times in batch:
            for pit_num, st_time in st_times.items():
                cursor.execute('''
                    UPDATE race_details
                    SET st_time = ?
                    WHERE race_id = ? AND pit_number = ?
                ''', (st_time, race_id, pit_num))

        conn.commit()
        conn.close()


def fix_race_st_times_optimized(race_info, scraper, update_queue):
    """
    1レースのST時間を修正（最適化版）

    Args:
        race_info: (race_id, venue_code, date, race_number, st_count)
        scraper: ImprovedResultScraperV4インスタンス
        update_queue: 更新データのキュー

    Returns:
        dict: 修正結果 {'success': bool, 'before': int, 'after': int, ...}
    """
    global rate_limiter

    race_id, venue_code, date_str, race_number, st_count_before = race_info

    result = {
        'race_id': race_id,
        'venue_code': venue_code,
        'date': date_str,
        'race_number': race_number,
        'success': False,
        'before': st_count_before,
        'after': st_count_before,
        'error': None
    }

    try:
        # レート制限
        if rate_limiter:
            rate_limiter.acquire()

        # 日付形式を変換: YYYY-MM-DD -> YYYYMMDD
        date_yyyymmdd = date_str.replace('-', '')

        # V4スクレイパーでデータ取得
        race_data = scraper.get_race_result_complete(venue_code, date_yyyymmdd, race_number)

        if not race_data or 'st_times' not in race_data:
            result['error'] = 'データ取得失敗'
            return result

        st_times = race_data['st_times']

        if len(st_times) == 0:
            result['error'] = 'ST時間なし'
            return result

        # 更新データをキューに追加
        update_queue.put((race_id, st_times))

        # 修正後のST時間数を推定（レスポンスデータから）
        st_count_after = len(st_times)

        result['success'] = st_count_after > st_count_before
        result['after'] = st_count_after

    except Exception as e:
        result['error'] = str(e)

    return result


def fix_st_times_parallel_optimized(start_date, end_date, limit=None,
                                     workers=5, requests_per_second=10, target_st_count=5):
    """
    並列処理でST時間を補充（最適化版）

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        limit: 処理するレース数の上限
        workers: 並列処理数
        requests_per_second: 1秒あたりのリクエスト数（レート制限）
        target_st_count: 対象とするST時間数

    Returns:
        dict: 統計情報
    """
    global rate_limiter

    print(f'=== ST時間データ補充（最適化版） ===')
    print(f'期間: {start_date} ～ {end_date}')
    print(f'並列数: {workers}')
    print(f'リクエスト制限: {requests_per_second}req/sec')
    print(f'対象: ST時間{target_st_count}/6のレース')
    if limit:
        print(f'上限: {limit}レース')
    print()

    # 対象レースを取得
    races = get_incomplete_st_races(start_date, end_date, target_st_count)

    if limit:
        races = races[:limit]

    print(f'対象レース数: {len(races)}')
    print()

    if len(races) == 0:
        print('修正対象のレースがありません')
        return {}

    # レート制限用セマフォ（トークンバケット方式）
    rate_limiter = Semaphore(workers)

    # トークン補充スレッド
    def refill_tokens():
        while not stop_refill:
            time.sleep(1.0 / requests_per_second)
            try:
                rate_limiter.release()
            except ValueError:
                pass  # セマフォが最大値の場合

    stop_refill = False
    import threading
    refill_thread = threading.Thread(target=refill_tokens, daemon=True)
    refill_thread.start()

    # 統計情報
    stats = {
        'total': len(races),
        'success': 0,
        'failed': 0,
        'improved': 0,
        'complete': 0,
        'errors': []
    }

    # DB更新キュー
    update_queue = queue.Queue()

    # DB更新ワーカースレッド
    db_thread = threading.Thread(
        target=batch_update_db,
        args=(update_queue, 100, 5),
        daemon=True
    )
    db_thread.start()

    # スクレイパーインスタンスをスレッドごとに作成
    def create_scraper():
        return ImprovedResultScraperV4()

    # 並列処理
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # スクレイパーを各スレッドで作成
        scrapers = {i: create_scraper() for i in range(workers)}

        # タスクを投入（遅延なし！）
        futures = {}
        for i, race in enumerate(races):
            scraper = scrapers[i % workers]
            future = executor.submit(fix_race_st_times_optimized, race, scraper, update_queue)
            futures[future] = race

        # 結果を回収
        for i, future in enumerate(as_completed(futures)):
            race = futures[future]
            result = future.result()

            with stats_lock:
                if result['success']:
                    stats['success'] += 1

                    if result['after'] == 6:
                        stats['complete'] += 1
                        status_icon = '✓'
                    else:
                        stats['improved'] += 1
                        status_icon = '+'

                    if (i + 1) % 100 == 0:  # 100件ごとに表示
                        print(f'  [{status_icon}] 会場{result["venue_code"]} {result["date"]} {result["race_number"]}R: {result["before"]}/6->{result["after"]}/6')
                else:
                    stats['failed'] += 1
                    if result['error']:
                        stats['errors'].append((race, result['error']))

            # 進捗表示
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                remaining = (len(races) - i - 1) / rate if rate > 0 else 0
                print(f'  進捗: {i+1}/{len(races)} ({((i+1)/len(races)*100):.1f}%) - 処理速度: {rate:.1f}レース/秒 - 残り約{remaining/60:.1f}分')

    # DB更新スレッドを終了
    update_queue.put(None)
    db_thread.join(timeout=30)

    # トークン補充を停止
    stop_refill = True

    elapsed_time = time.time() - start_time

    # 結果サマリー
    print(f'\n=== 修正完了 ===')
    print(f'総レース数: {stats["total"]}')
    print(f'成功: {stats["success"]} ({stats["success"]/stats["total"]*100:.1f}%)')
    print(f'  完全修正(6/6): {stats["complete"]}')
    print(f'  改善: {stats["improved"]}')
    print(f'失敗: {stats["failed"]}')
    print(f'実行時間: {elapsed_time/60:.1f}分 ({elapsed_time:.1f}秒)')
    print(f'処理速度: {stats["total"]/elapsed_time:.2f}レース/秒')

    if stats['errors']:
        print(f'\nエラー詳細（最初の10件）:')
        for race, error in stats['errors'][:10]:
            print(f'  会場{race[1]} {race[2]} {race[3]}R: {error}')

    return stats


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='ST時間データ補充（最適化版）')
    parser.add_argument('--start', type=str, required=True, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, required=True, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--limit', type=int, help='処理するレース数の上限')
    parser.add_argument('--workers', type=int, default=5, help='並列処理数（デフォルト5）')
    parser.add_argument('--rps', type=int, default=10, help='リクエスト/秒（デフォルト10）')
    parser.add_argument('--target-st', type=int, default=5, help='対象ST時間数（デフォルト5: 5/6のレース）')

    args = parser.parse_args()

    try:
        fix_st_times_parallel_optimized(
            start_date=args.start,
            end_date=args.end,
            limit=args.limit,
            workers=args.workers,
            requests_per_second=args.rps,
            target_st_count=args.target_st
        )
    except KeyboardInterrupt:
        print('\n処理を中断しました')
        sys.exit(1)
    except Exception as e:
        print(f'\nエラーが発生しました: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
