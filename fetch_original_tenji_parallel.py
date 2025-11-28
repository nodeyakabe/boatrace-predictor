#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オリジナル展示データ並列収集スクリプト

並列処理で高速化（目標: 3-4分）
"""
import sys
import os
import time
import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper

# データベースパス
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')

# Boatersサイトでデータが取れない既知の会場（スキップリスト）
SKIP_VENUES = {
    '03',  # 江戸川（Boatersで非公開）
}


def save_to_db(venue_code: str, date_str: str, race_number: int, tenji_data: Dict) -> bool:
    """
    オリジナル展示データをDBに保存（スレッドセーフ）

    Returns:
        bool: 保存成功したかどうか
    """
    if not tenji_data or 'source' in tenji_data:
        # sourceキーを除外
        tenji_data = {k: v for k, v in tenji_data.items() if k != 'source'}

    if not tenji_data:
        return False

    # スレッドごとにDBコネクションを作成
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # race_details テーブルを更新
        update_count = 0
        for boat_num, data in tenji_data.items():
            # race_idを取得
            cursor.execute('''
                SELECT id FROM races
                WHERE venue_code = ? AND race_date = ? AND race_number = ?
            ''', (venue_code, date_str, race_number))

            race_result = cursor.fetchone()
            if not race_result:
                continue

            race_id = race_result[0]

            # race_details に該当レコードがあるか確認
            cursor.execute('''
                SELECT id FROM race_details
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, boat_num))

            detail_result = cursor.fetchone()

            if detail_result:
                # 既存レコードを更新
                cursor.execute('''
                    UPDATE race_details
                    SET chikusen_time = ?, isshu_time = ?, mawariashi_time = ?
                    WHERE race_id = ? AND pit_number = ?
                ''', (
                    data.get('chikusen_time'),
                    data.get('isshu_time'),
                    data.get('mawariashi_time'),
                    race_id,
                    boat_num
                ))
                update_count += 1
            else:
                # 新規レコードを挿入
                cursor.execute('''
                    INSERT INTO race_details (race_id, pit_number, chikusen_time, isshu_time, mawariashi_time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    race_id,
                    boat_num,
                    data.get('chikusen_time'),
                    data.get('isshu_time'),
                    data.get('mawariashi_time')
                ))
                update_count += 1

        conn.commit()
        return update_count > 0

    except Exception as e:
        conn.rollback()
        print(f'  [DB保存エラー] {e}')
        return False

    finally:
        conn.close()


def get_scheduled_races(target_date: str) -> List[Tuple[str, int, str]]:
    """
    指定日に開催されるレース一覧を取得

    Returns:
        [(venue_code, race_number, venue_name), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT r.venue_code, r.race_number, v.name
        FROM races r
        LEFT JOIN venues v ON r.venue_code = v.code
        WHERE r.race_date = ? AND r.venue_code NOT IN ({})
        ORDER BY r.venue_code, r.race_number
    """.format(','.join(['?' for _ in SKIP_VENUES])), (target_date, *SKIP_VENUES))

    races = cursor.fetchall()
    conn.close()

    return races


def fetch_single_race(args: Tuple) -> Dict:
    """
    1レース分のデータを取得（ワーカースレッド用）

    Args:
        args: (venue_code, race_number, venue_name, target_date, timeout, delay)

    Returns:
        結果辞書
    """
    venue_code, race_number, venue_name, target_date, timeout, delay = args

    result = {
        'venue_code': venue_code,
        'race_number': race_number,
        'venue_name': venue_name,
        'success': False,
        'boat_count': 0,
        'db_saved': False,
        'error': None
    }

    # レート制限対策: リクエスト前に遅延
    if delay > 0:
        time.sleep(delay)

    scraper = None
    try:
        # スレッドごとにスクレイパーを作成
        scraper = OriginalTenjiBrowserScraper(headless=True, timeout=timeout)

        data = scraper.get_original_tenji(venue_code, target_date, race_number)

        if data and len(data) > 0:
            result['success'] = True
            result['boat_count'] = len(data)

            # DB保存
            if save_to_db(venue_code, target_date, race_number, data):
                result['db_saved'] = True

    except Exception as e:
        result['error'] = str(e)[:100]

    finally:
        if scraper:
            scraper.close()

    return result


def fetch_parallel(target_date: str, max_workers: int = 2, timeout: int = 20, delay: float = 0.5) -> Dict:
    """
    並列処理でオリジナル展示データを収集

    Args:
        target_date: 対象日（YYYY-MM-DD）
        max_workers: 並列実行数（デフォルト2）
        timeout: タイムアウト時間（秒、デフォルト20）
        delay: リクエスト間遅延（秒、デフォルト0.5）

    Returns:
        統計情報
    """
    print('='*70)
    print('オリジナル展示データ並列収集')
    print('='*70)
    print(f'対象日: {target_date}')
    print(f'並列数: {max_workers}')
    print(f'タイムアウト: {timeout}秒')
    print(f'リクエスト遅延: {delay}秒')
    print()

    # 開催レース一覧を取得
    scheduled_races = get_scheduled_races(target_date)

    if not scheduled_races:
        print('[!] 対象レースが見つかりません')
        return {}

    print(f'[OK] 開催予定レース: {len(scheduled_races)}レース')

    # スキップされた会場を表示
    if SKIP_VENUES:
        skip_count = 0
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for venue in SKIP_VENUES:
            cursor.execute('''
                SELECT COUNT(*) FROM races
                WHERE race_date = ? AND venue_code = ?
            ''', (target_date, venue))
            count = cursor.fetchone()[0]
            skip_count += count
        conn.close()

        if skip_count > 0:
            print(f'[!] スキップ: {skip_count}レース（江戸川など既知の失敗会場）')

    print('='*70)
    print()

    # 統計情報
    stats = {
        'total': len(scheduled_races),
        'success': 0,
        'failed': 0,
        'db_saved': 0,
        'total_boats': 0
    }

    start_time = time.time()

    # 並列処理用のタスクリストを作成
    tasks = [
        (venue_code, race_number, venue_name, target_date, timeout, delay)
        for venue_code, race_number, venue_name in scheduled_races
    ]

    # 進捗カウンター（スレッドセーフ）
    progress_lock = threading.Lock()
    progress_count = [0]

    # 並列実行
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # タスクを投入
        future_to_task = {executor.submit(fetch_single_race, task): task for task in tasks}

        # 完了したタスクから順次処理
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            venue_code, race_number, venue_name, _, _ = task

            with progress_lock:
                progress_count[0] += 1
                current = progress_count[0]

            try:
                result = future.result()

                # 進捗表示
                elapsed = time.time() - start_time
                avg_time = elapsed / current if current > 0 else 0
                remaining = (stats['total'] - current) * avg_time

                status_icon = '✓' if result['success'] else '✗'
                print(f'[{current}/{stats["total"]}] {status_icon} {venue_name or f"会場{venue_code}"} {race_number}R', end='')

                if result['success']:
                    print(f' - {result["boat_count"]}艇', end='')
                    stats['success'] += 1
                    stats['total_boats'] += result['boat_count']

                    if result['db_saved']:
                        print(' [DB保存完了]', end='')
                        stats['db_saved'] += 1
                else:
                    stats['failed'] += 1
                    if result['error']:
                        print(f' - エラー: {result["error"][:50]}', end='')

                print(f' (残り: {int(remaining)}秒)')

            except Exception as e:
                print(f'[{current}/{stats["total"]}] ✗ {venue_name} {race_number}R - 例外: {str(e)[:50]}')
                stats['failed'] += 1

    elapsed_total = time.time() - start_time

    # 結果サマリー
    print()
    print('='*70)
    print('収集結果サマリー')
    print('='*70)
    print(f'総処理時間: {int(elapsed_total)}秒 ({int(elapsed_total//60)}分{int(elapsed_total%60)}秒)')
    print(f'対象レース: {stats["total"]}レース')
    print(f'成功: {stats["success"]}レース')
    print(f'取得艇数: {stats["total_boats"]}艇')
    print(f'失敗: {stats["failed"]}レース')
    print(f'DB保存: {stats["db_saved"]}レース')
    print()

    if stats['total'] > 0:
        success_rate = stats['success'] / stats['total'] * 100
        print(f'成功率: {success_rate:.1f}%')
        print(f'平均処理時間: {elapsed_total/stats["total"]:.1f}秒/レース')

    print('='*70)

    return stats


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='オリジナル展示データ並列収集')
    parser.add_argument('--date', type=str, help='対象日（YYYY-MM-DD）。未指定の場合は翌日')
    parser.add_argument('--workers', type=int, default=2, help='並列実行数（デフォルト2）')
    parser.add_argument('--timeout', type=int, default=20, help='タイムアウト時間（秒、デフォルト20）')
    parser.add_argument('--delay', type=float, default=0.5, help='リクエスト間遅延（秒、デフォルト0.5）')
    parser.add_argument('--today', action='store_true', help='当日のデータを取得')

    args = parser.parse_args()

    # 対象日の決定
    if args.date:
        target_date = args.date
    elif args.today:
        target_date = datetime.now().strftime('%Y-%m-%d')
    else:
        target_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        fetch_parallel(
            target_date=target_date,
            max_workers=args.workers,
            timeout=args.timeout,
            delay=args.delay
        )
    except KeyboardInterrupt:
        print('\n処理を中断しました')
        sys.exit(1)
    except Exception as e:
        print(f'エラー: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
