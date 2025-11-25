#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不足データ補充スクリプト V3 - 高速版

主な改善:
1. バッチDB更新（100件単位）
2. 並列度を大幅に向上（workers=20）
3. レート制限の最適化
4. セッション再利用の強化
"""
import sys
import os
import sqlite3
import time
import queue
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore, Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')
db_lock = Lock()


def get_missing_races(start_date, end_date, data_type='all'):
    """不足しているレースを取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    missing_races = []

    if data_type in ['details', 'all']:
        cursor.execute('''
            SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= ? AND r.race_date <= ? AND rd.id IS NULL
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''', (start_date, end_date))
        for row in cursor.fetchall():
            missing_races.append((*row, 'details'))

    if data_type in ['results', 'all']:
        cursor.execute('''
            SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            LEFT JOIN results res ON r.id = res.race_id
            WHERE r.race_date >= ? AND r.race_date <= ? AND res.id IS NULL
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''', (start_date, end_date))
        for row in cursor.fetchall():
            missing_races.append((*row, 'results'))

    if data_type in ['payouts', 'all']:
        cursor.execute('''
            SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            LEFT JOIN payouts p ON r.id = p.race_id
            WHERE r.race_date >= ? AND r.race_date <= ? AND p.id IS NULL
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''', (start_date, end_date))
        for row in cursor.fetchall():
            missing_races.append((*row, 'payouts'))

    conn.close()
    return missing_races


def batch_db_worker(update_queue, stats, batch_size=100, flush_interval=5):
    """バッチDB更新ワーカー"""
    batch = []
    last_flush = time.time()

    while True:
        try:
            item = update_queue.get(timeout=1)
            if item is None:  # 終了シグナル
                break

            batch.append(item)

            # バッチサイズまたは時間経過でフラッシュ
            if len(batch) >= batch_size or (time.time() - last_flush) >= flush_interval:
                if batch:
                    flush_batch(batch, stats)
                    batch = []
                    last_flush = time.time()

        except queue.Empty:
            # タイムアウト時、バッチがあればフラッシュ
            if batch and (time.time() - last_flush) >= flush_interval:
                flush_batch(batch, stats)
                batch = []
                last_flush = time.time()
            continue

    # 残りをフラッシュ
    if batch:
        flush_batch(batch, stats)


def flush_batch(batch, stats):
    """バッチをDBに書き込む"""
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for item in batch:
            success = item['success']
            if not success:
                continue

            race_id = item['race_id']
            missing_type = item['missing_type']
            race_data = item['race_data']

            try:
                if missing_type == 'details' and 'st_times' in race_data and 'results' in race_data:
                    for result in race_data['results']:
                        pit_number = result.get('pit_number')
                        if pit_number is None:
                            continue
                        st_time = race_data['st_times'].get(pit_number)
                        cursor.execute('''
                            INSERT OR REPLACE INTO race_details (race_id, pit_number, st_time)
                            VALUES (?, ?, ?)
                        ''', (race_id, pit_number, st_time))

                elif missing_type == 'results' and 'results' in race_data:
                    for result in race_data['results']:
                        pit_number = result.get('pit_number')
                        rank = result.get('rank')
                        if pit_number is None:
                            continue
                        cursor.execute('''
                            INSERT OR REPLACE INTO results (race_id, pit_number, rank)
                            VALUES (?, ?, ?)
                        ''', (race_id, pit_number, rank))

                elif missing_type == 'payouts' and 'payouts' in race_data:
                    for bet_type, payout_list in race_data['payouts'].items():
                        if not isinstance(payout_list, list):
                            continue
                        for payout in payout_list:
                            combination = payout.get('combination')
                            if combination is None and 'pit_number' in payout:
                                combination = str(payout['pit_number'])
                            amount = payout.get('amount')
                            popularity = payout.get('popularity')
                            if combination is None or amount is None:
                                continue
                            cursor.execute('''
                                INSERT OR REPLACE INTO payouts (race_id, bet_type, combination, amount, popularity)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (race_id, bet_type, combination, amount, popularity))

                stats['db_success'] += 1

            except Exception as e:
                stats['db_failed'] += 1
                stats['db_errors'].append((item['race_info'], str(e)))

        conn.commit()
        conn.close()


def process_race(race_info, semaphore, scraper):
    """1レースの処理（データ取得のみ）"""
    race_id, venue_code, date_str, race_number, missing_type = race_info

    try:
        # レート制限
        semaphore.acquire()

        date_yyyymmdd = date_str.replace('-', '')
        race_data = scraper.get_race_result_complete(venue_code, date_yyyymmdd, race_number)

        if not race_data:
            return {
                'success': False,
                'race_info': race_info,
                'race_id': race_id,
                'missing_type': missing_type,
                'race_data': None,
                'error': 'データ取得失敗'
            }

        return {
            'success': True,
            'race_info': race_info,
            'race_id': race_id,
            'missing_type': missing_type,
            'race_data': race_data,
            'error': None
        }

    except Exception as e:
        return {
            'success': False,
            'race_info': race_info,
            'race_id': race_id,
            'missing_type': missing_type,
            'race_data': None,
            'error': str(e)
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description='不足データ補充 V3 高速版')
    parser.add_argument('--start', type=str, required=True, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, required=True, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--type', type=str, default='all', choices=['details', 'results', 'payouts', 'all'],
                        help='補充するデータタイプ')
    parser.add_argument('--limit', type=int, help='処理するレース数の上限')
    parser.add_argument('--workers', type=int, default=20, help='並列処理数（デフォルト20）')
    parser.add_argument('--rps', type=int, default=20, help='リクエスト/秒（デフォルト20）')
    parser.add_argument('--batch-size', type=int, default=100, help='DBバッチサイズ（デフォルト100）')

    args = parser.parse_args()

    print(f'=== 不足データ補充 V3 高速版 ===')
    print(f'期間: {args.start} - {args.end}')
    print(f'データタイプ: {args.type}')
    print(f'並列数: {args.workers}')
    print(f'リクエスト制限: {args.rps}req/sec')
    print(f'バッチサイズ: {args.batch_size}')
    if args.limit:
        print(f'上限: {args.limit}レース')
    print()

    # 不足レースを取得
    print('不足レースを検索中...')
    races = get_missing_races(args.start, args.end, args.type)
    if args.limit:
        races = races[:args.limit]

    print(f'対象レース数: {len(races)}')
    print()

    if len(races) == 0:
        print('補充対象のレースがありません')
        return

    # レート制限用セマフォ
    semaphore = Semaphore(args.rps)

    # トークン補充スレッド
    def refill_tokens():
        while not stop_refill:
            time.sleep(1.0)
            for _ in range(args.rps):
                try:
                    semaphore.release()
                except ValueError:
                    pass

    stop_refill = False
    refill_thread = threading.Thread(target=refill_tokens, daemon=True)
    refill_thread.start()

    # バッチDB更新キュー
    update_queue = queue.Queue(maxsize=1000)

    # 統計
    stats = {
        'total': len(races),
        'fetch_success': 0,
        'fetch_failed': 0,
        'db_success': 0,
        'db_failed': 0,
        'fetch_errors': [],
        'db_errors': []
    }

    # バッチDB更新ワーカー起動
    db_thread = threading.Thread(
        target=batch_db_worker,
        args=(update_queue, stats, args.batch_size),
        daemon=True
    )
    db_thread.start()

    # スクレイパーを各ワーカー用に作成
    scrapers = [ImprovedResultScraperV4() for _ in range(args.workers)]

    # 並列処理
    print('処理開始...')
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # タスク投入
        futures = {}
        for i, race in enumerate(races):
            scraper = scrapers[i % args.workers]
            future = executor.submit(process_race, race, semaphore, scraper)
            futures[future] = race

        # 結果回収
        for i, future in enumerate(as_completed(futures)):
            result = future.result()

            if result['success']:
                stats['fetch_success'] += 1
                # DB更新キューに追加
                update_queue.put(result)
            else:
                stats['fetch_failed'] += 1
                stats['fetch_errors'].append((result['race_info'], result.get('error', 'unknown')))

            # 進捗表示
            if (i + 1) % 100 == 0 or (i + 1) == len(races):
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                remaining = (len(races) - i - 1) / rate if rate > 0 else 0

                race_info = result['race_info']
                status = 'OK' if result['success'] else 'NG'
                print(f'  [{status}] {i+1}/{len(races)} ({(i+1)/len(races)*100:.1f}%) | '
                      f'会場{race_info[1]} {race_info[2]} {race_info[3]}R | '
                      f'{rate:.1f}レース/秒 | 残り{remaining/60:.1f}分')

    # 終了シグナルをキューに送信
    print('\nDB更新完了待機中...')
    update_queue.put(None)
    db_thread.join()

    # 停止
    stop_refill = True
    elapsed_time = time.time() - start_time

    # サマリー
    print(f'\n=== 完了 ===')
    print(f'総レース数: {stats["total"]}')
    print(f'データ取得成功: {stats["fetch_success"]} ({stats["fetch_success"]/stats["total"]*100:.1f}%)')
    print(f'データ取得失敗: {stats["fetch_failed"]}')
    print(f'DB保存成功: {stats["db_success"]}')
    print(f'DB保存失敗: {stats["db_failed"]}')
    print(f'実行時間: {elapsed_time/60:.1f}分')
    print(f'処理速度: {stats["total"]/elapsed_time:.2f}レース/秒')

    if stats['fetch_errors']:
        print(f'\n取得エラー（最初の10件）:')
        for race_info, error in stats['fetch_errors'][:10]:
            print(f'  会場{race_info[1]} {race_info[2]} {race_info[3]}R: {error}')

    if stats['db_errors']:
        print(f'\nDB保存エラー（最初の10件）:')
        for race_info, error in stats['db_errors'][:10]:
            print(f'  会場{race_info[1]} {race_info[2]} {race_info[3]}R: {error}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n中断しました')
        sys.exit(1)
    except Exception as e:
        print(f'\nエラー: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
