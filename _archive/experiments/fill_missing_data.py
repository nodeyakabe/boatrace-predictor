#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不足データ補充スクリプト

race_details、results、payouts の不足レースを検索し、データを補充する
fix_st_times_optimized.pyをベースに作成
"""
import sys
import os
import sqlite3
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Semaphore

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


def get_missing_data_races(start_date, end_date, data_type='all'):
    """
    データが不足しているレースを取得

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        data_type: 'details', 'results', 'payouts', 'all'

    Returns:
        list: [(race_id, venue_code, date, race_number, missing_type), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    missing_races = []

    # race_details の不足をチェック
    if data_type in ['details', 'all']:
        # race_detailsにレコードが存在しないレース
        cursor.execute('''
            SELECT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
            GROUP BY r.id
            HAVING COUNT(rd.id) = 0
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''', (start_date, end_date))

        for row in cursor.fetchall():
            missing_races.append((*row, 'details'))

    # results の不足をチェック
    if data_type in ['results', 'all']:
        cursor.execute('''
            SELECT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            LEFT JOIN results res ON r.id = res.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
            GROUP BY r.id
            HAVING COUNT(res.id) = 0
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''', (start_date, end_date))

        for row in cursor.fetchall():
            missing_races.append((*row, 'results'))

    # payouts の不足をチェック
    if data_type in ['payouts', 'all']:
        cursor.execute('''
            SELECT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            LEFT JOIN payouts p ON r.id = p.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
            GROUP BY r.id
            HAVING COUNT(p.id) = 0
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''', (start_date, end_date))

        for row in cursor.fetchall():
            missing_races.append((*row, 'payouts'))

    conn.close()

    return missing_races


def save_race_details(race_id, race_data):
    """
    race_detailsデータをDBに保存

    Args:
        race_id: レースID
        race_data: スクレイピングしたレースデータ
    """
    if 'results' not in race_data or 'st_times' not in race_data:
        return False

    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # racer_numberを取得（entriesテーブルから）
        cursor.execute('''
            SELECT pit_number, racer_number
            FROM entries
            WHERE race_id = ?
        ''', (race_id,))

        racer_map = {row[0]: row[1] for row in cursor.fetchall()}

        # race_detailsに保存（pit_number, racer_id, st_time）
        results = race_data['results']
        st_times = race_data['st_times']

        for result in results:
            pit_number = result.get('pit_number')
            if pit_number is None:
                continue

            racer_number = racer_map.get(pit_number)
            st_time = st_times.get(pit_number)

            # 既存レコードをチェック
            cursor.execute('''
                SELECT id FROM race_details
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            existing = cursor.fetchone()

            if existing:
                # UPDATE
                cursor.execute('''
                    UPDATE race_details
                    SET st_time = ?
                    WHERE race_id = ? AND pit_number = ?
                ''', (st_time, race_id, pit_number))
            else:
                # INSERT
                cursor.execute('''
                    INSERT INTO race_details (race_id, pit_number, st_time)
                    VALUES (?, ?, ?)
                ''', (race_id, pit_number, st_time))

        conn.commit()
        conn.close()

        return True


def save_results(race_id, race_data):
    """
    resultsデータをDBに保存

    Args:
        race_id: レースID
        race_data: スクレイピングしたレースデータ
    """
    if 'results' not in race_data:
        return False

    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        results = race_data['results']

        for result in results:
            pit_number = result.get('pit_number')
            rank = result.get('rank')

            if pit_number is None:
                continue

            # 既存レコードをチェック
            cursor.execute('''
                SELECT id FROM results
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            existing = cursor.fetchone()

            if existing:
                # UPDATE
                cursor.execute('''
                    UPDATE results
                    SET rank = ?
                    WHERE race_id = ? AND pit_number = ?
                ''', (rank, race_id, pit_number))
            else:
                # INSERT
                cursor.execute('''
                    INSERT INTO results (race_id, pit_number, rank)
                    VALUES (?, ?, ?)
                ''', (race_id, pit_number, rank))

        conn.commit()
        conn.close()

        return True


def save_payouts(race_id, race_data):
    """
    payoutsデータをDBに保存

    Args:
        race_id: レースID
        race_data: スクレイピングしたレースデータ
    """
    if 'payouts' not in race_data:
        return False

    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        payouts_dict = race_data['payouts']

        # payoutsはdict型で、各bet_typeがキー、値はリスト
        for bet_type, payout_list in payouts_dict.items():
            if not isinstance(payout_list, list):
                continue

            for payout in payout_list:
                # combinationまたはpit_numberを取得
                combination = payout.get('combination')
                if combination is None and 'pit_number' in payout:
                    combination = str(payout['pit_number'])

                amount = payout.get('amount')
                popularity = payout.get('popularity')

                if combination is None or amount is None:
                    continue

                # 既存レコードをチェック
                cursor.execute('''
                    SELECT id FROM payouts
                    WHERE race_id = ? AND bet_type = ? AND combination = ?
                ''', (race_id, bet_type, combination))

                existing = cursor.fetchone()

                if existing:
                    # UPDATE
                    cursor.execute('''
                        UPDATE payouts
                        SET amount = ?, popularity = ?
                        WHERE race_id = ? AND bet_type = ? AND combination = ?
                    ''', (amount, popularity, race_id, bet_type, combination))
                else:
                    # INSERT
                    cursor.execute('''
                        INSERT INTO payouts (race_id, bet_type, combination, amount, popularity)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (race_id, bet_type, combination, amount, popularity))

        conn.commit()
        conn.close()

        return True


def fill_missing_data(race_info, scraper, data_type):
    """
    1レースの不足データを補充

    Args:
        race_info: (race_id, venue_code, date, race_number, missing_type)
        scraper: ImprovedResultScraperV4インスタンス
        data_type: 保存するデータタイプ

    Returns:
        dict: 修正結果 {'success': bool, ...}
    """
    global rate_limiter

    race_id, venue_code, date_str, race_number, missing_type = race_info

    result = {
        'race_id': race_id,
        'venue_code': venue_code,
        'date': date_str,
        'race_number': race_number,
        'missing_type': missing_type,
        'success': False,
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

        if not race_data:
            result['error'] = 'データ取得失敗'
            return result

        # データタイプに応じて保存
        save_success = False

        if data_type == 'details':
            save_success = save_race_details(race_id, race_data)
        elif data_type == 'results':
            save_success = save_results(race_id, race_data)
        elif data_type == 'payouts':
            save_success = save_payouts(race_id, race_data)
        elif data_type == 'all':
            # 全タイプを保存
            if missing_type == 'details':
                save_success = save_race_details(race_id, race_data)
            elif missing_type == 'results':
                save_success = save_results(race_id, race_data)
            elif missing_type == 'payouts':
                save_success = save_payouts(race_id, race_data)

        result['success'] = save_success

        if not save_success:
            result['error'] = '保存失敗'

    except Exception as e:
        result['error'] = str(e)

    return result


def fill_missing_data_parallel(start_date, end_date, data_type='all', limit=None,
                                workers=5, requests_per_second=10):
    """
    並列処理で不足データを補充

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        data_type: 'details', 'results', 'payouts', 'all'
        limit: 処理するレース数の上限
        workers: 並列処理数
        requests_per_second: 1秒あたりのリクエスト数（レート制限）

    Returns:
        dict: 統計情報
    """
    global rate_limiter

    print(f'=== 不足データ補充スクリプト ===')
    print(f'期間: {start_date} ～ {end_date}')
    print(f'データタイプ: {data_type}')
    print(f'並列数: {workers}')
    print(f'リクエスト制限: {requests_per_second}req/sec')
    if limit:
        print(f'上限: {limit}レース')
    print()

    # 対象レースを取得
    races = get_missing_data_races(start_date, end_date, data_type)

    if limit:
        races = races[:limit]

    print(f'対象レース数: {len(races)}')
    print()

    if len(races) == 0:
        print('補充対象のレースがありません')
        return {}

    # レート制限用セマフォ（トークンバケット方式）
    # 初期値をrequests_per_secondに設定
    rate_limiter = Semaphore(requests_per_second)

    # トークン補充スレッド
    def refill_tokens():
        while not stop_refill:
            # 1秒ごとにrequests_per_second個のトークンを補充
            time.sleep(1.0)
            for _ in range(requests_per_second):
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
        'errors': []
    }

    # スクレイパーインスタンスをスレッドごとに作成
    def create_scraper():
        return ImprovedResultScraperV4()

    # 並列処理
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # スクレイパーを各スレッドで作成
        scrapers = {i: create_scraper() for i in range(workers)}

        # タスクを投入
        futures = {}
        for i, race in enumerate(races):
            scraper = scrapers[i % workers]
            future = executor.submit(fill_missing_data, race, scraper, data_type)
            futures[future] = race

        # 結果を回収
        for i, future in enumerate(as_completed(futures)):
            race = futures[future]
            result = future.result()

            with stats_lock:
                if result['success']:
                    stats['success'] += 1
                    status_icon = '✓'
                else:
                    stats['failed'] += 1
                    status_icon = '✗'
                    if result['error']:
                        stats['errors'].append((race, result['error']))

                # 進捗表示（100件ごとにサンプル表示）
                if (i + 1) % 100 == 0:
                    print(f'  [{status_icon}] 会場{result["venue_code"]} {result["date"]} {result["race_number"]}R ({result["missing_type"]})')

                # 進捗統計（100件ごと）
                if (i + 1) % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed
                    remaining = (len(races) - i - 1) / rate if rate > 0 else 0
                    print(f'  進捗: {i+1}/{len(races)} ({((i+1)/len(races)*100):.1f}%) - 処理速度: {rate:.1f}レース/秒 - 残り約{remaining/60:.1f}分')

    # トークン補充を停止
    stop_refill = True

    elapsed_time = time.time() - start_time

    # 結果サマリー
    print(f'\n=== 補充完了 ===')
    print(f'総レース数: {stats["total"]}')
    print(f'成功: {stats["success"]} ({stats["success"]/stats["total"]*100:.1f}%)')
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

    parser = argparse.ArgumentParser(description='不足データ補充スクリプト')
    parser.add_argument('--start', type=str, required=True, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, required=True, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--type', type=str, default='all', choices=['details', 'results', 'payouts', 'all'],
                        help='補充するデータタイプ（デフォルト: all）')
    parser.add_argument('--limit', type=int, help='処理するレース数の上限')
    parser.add_argument('--workers', type=int, default=5, help='並列処理数（デフォルト5）')
    parser.add_argument('--rps', type=int, default=10, help='リクエスト/秒（デフォルト10）')

    args = parser.parse_args()

    try:
        fill_missing_data_parallel(
            start_date=args.start,
            end_date=args.end,
            data_type=args.type,
            limit=args.limit,
            workers=args.workers,
            requests_per_second=args.rps
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
