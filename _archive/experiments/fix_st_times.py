#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ST時間データ補充スクリプト（高速化・並列処理版）

V3スクレイパーを使用して、ST時間が不完全なレースデータを修正
Pit3のST時間に決まり手テキストが混入しているバグを修正
"""
import sys
import os
import sqlite3
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.result_scraper_improved_v4 import ImprovedResultScraperV4

# データベースパス
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')

# スレッドセーフなロック
db_lock = Lock()
stats_lock = Lock()


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


def fix_race_st_times(race_info, scraper, test_mode=False):
    """
    1レースのST時間を修正

    Args:
        race_info: (race_id, venue_code, date, race_number, st_count)
        scraper: ImprovedResultScraperV3インスタンス
        test_mode: Trueの場合はDB更新をスキップ

    Returns:
        dict: 修正結果 {'success': bool, 'before': int, 'after': int, ...}
    """
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
        # 日付形式を変換: YYYY-MM-DD -> YYYYMMDD
        date_yyyymmdd = date_str.replace('-', '')

        # V4スクレイパーでデータ取得
        race_data = scraper.get_race_result_complete(venue_code, date_yyyymmdd, race_number)

        if not race_data or 'st_times' not in race_data:
            result['error'] = 'データ取得失敗'
            return result

        st_times = race_data['st_times']
        st_status = race_data.get('st_status', {})

        if len(st_times) == 0:
            result['error'] = 'ST時間なし'
            return result

        # DB更新
        if not test_mode:
            with db_lock:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                update_count = 0
                for pit_num, st_time in st_times.items():
                    cursor.execute('''
                        UPDATE race_details
                        SET st_time = ?
                        WHERE race_id = ? AND pit_number = ?
                    ''', (st_time, race_id, pit_num))

                    if cursor.rowcount > 0:
                        update_count += 1

                conn.commit()
                conn.close()

        # 修正後のST時間数を取得
        st_count_after = count_st_times_in_race(race_id)

        result['success'] = st_count_after > st_count_before
        result['after'] = st_count_after

    except Exception as e:
        result['error'] = str(e)

    return result


def fix_st_times_parallel(start_date, end_date, test_mode=False, limit=None,
                           workers=3, delay=0.3, target_st_count=5):
    """
    並列処理でST時間を補充

    Args:
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        test_mode: Trueの場合はDB更新をスキップ
        limit: 処理するレース数の上限
        workers: 並列処理数
        delay: リクエスト間隔（秒）
        target_st_count: 対象とするST時間数

    Returns:
        dict: 統計情報
    """
    print(f'=== ST時間データ補充 ===')
    print(f'期間: {start_date} ～ {end_date}')
    print(f'モード: {"テスト" if test_mode else "本番"}')
    print(f'並列数: {workers}')
    print(f'遅延: {delay}秒')
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

    # 統計情報
    stats = {
        'total': len(races),
        'success': 0,
        'failed': 0,
        'improved': 0,
        'complete': 0,
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
            future = executor.submit(fix_race_st_times, race, scraper, test_mode)
            futures[future] = race

            # 遅延
            time.sleep(delay)

        # 結果を回収
        for i, future in enumerate(as_completed(futures)):
            race = futures[future]
            result = future.result()

            with stats_lock:
                if result['success']:
                    stats['success'] += 1

                    if result['after'] == 6:
                        stats['complete'] += 1
                        status_icon = 'OK'
                    else:
                        stats['improved'] += 1
                        status_icon = 'IMPROVED'

                    print(f'  [{status_icon}] 会場{result["venue_code"]} {result["date"]} {result["race_number"]}R: {result["before"]}/6->{result["after"]}/6')
                else:
                    stats['failed'] += 1
                    if result['error']:
                        stats['errors'].append((race, result['error']))

            # 進捗表示
            if (i + 1) % 50 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                remaining = (len(races) - i - 1) / rate if rate > 0 else 0
                print(f'  進捗: {i+1}/{len(races)} ({((i+1)/len(races)*100):.1f}%) - 残り約{remaining/60:.1f}分')

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

    parser = argparse.ArgumentParser(description='ST時間データ補充（高速並列版）')
    parser.add_argument('--start', type=str, required=True, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, required=True, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--test', action='store_true', help='テストモード（DB更新なし）')
    parser.add_argument('--limit', type=int, help='処理するレース数の上限')
    parser.add_argument('--workers', type=int, default=3, help='並列処理数（デフォルト3）')
    parser.add_argument('--delay', type=float, default=0.3, help='リクエスト間隔（秒、デフォルト0.3）')
    parser.add_argument('--target-st', type=int, default=5, help='対象ST時間数（デフォルト5: 5/6のレース）')

    args = parser.parse_args()

    try:
        fix_st_times_parallel(
            start_date=args.start,
            end_date=args.end,
            test_mode=args.test,
            limit=args.limit,
            workers=args.workers,
            delay=args.delay,
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
