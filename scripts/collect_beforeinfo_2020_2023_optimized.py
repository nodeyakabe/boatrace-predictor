#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020-2023年の直前情報一括収集（最適化版）

最適化ポイント:
1. ワーカー数: 8 → 12（控えめに増加、エラー回避）
2. 遅延: 0.5秒 → 0.3秒（サーバー負荷を考慮）
3. DB保存: バッチ処理（100件単位）
4. HTTPセッション: ワーカー単位で再利用
5. 再開機能: 収集済みレースをスキップ
"""
import sys
import os

# 最初に文字コード設定（他のインポート前）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import time
import sqlite3
import warnings
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.scraper.beforeinfo_scraper import BeforeInfoScraper

# スレッドローカルストレージ（各ワーカーのScraperを保持）
thread_local = threading.local()

# DB保存用キュー
save_queue = Queue()
save_results = {'success': 0, 'failed': 0}
save_lock = threading.Lock()


def get_scraper():
    """スレッドローカルなScraperインスタンスを取得（再利用）"""
    if not hasattr(thread_local, 'scraper'):
        thread_local.scraper = BeforeInfoScraper(delay=0.3)  # 0.5→0.3に短縮
    return thread_local.scraper


def collect_single_race(args):
    """
    1レース分の直前情報を収集（最適化版）
    """
    race_id, venue_code, race_date, race_number = args

    scraper = get_scraper()  # スレッドローカルなインスタンスを再利用

    result = {
        'race_id': race_id,
        'venue_code': venue_code,
        'race_date': race_date,
        'race_number': race_number,
        'success': False,
        'data': None,
        'error': None
    }

    try:
        date_str = race_date.replace('-', '')

        beforeinfo = scraper.get_race_beforeinfo(
            venue_code=f"{int(venue_code):02d}",
            date_str=date_str,
            race_number=race_number
        )

        if beforeinfo and beforeinfo.get('is_published'):
            result['success'] = True
            result['data'] = beforeinfo
        else:
            result['error'] = 'データ未公開'

    except Exception as e:
        result['error'] = str(e)[:100]

    return result


def db_saver_worker(db_path, stop_event):
    """
    DB保存専用ワーカー（バッチ処理）
    """
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL")  # WALモードで並列書き込み改善
    cursor = conn.cursor()

    batch = []
    batch_size = 50  # 50件単位でコミット

    while not stop_event.is_set() or not save_queue.empty():
        try:
            # キューからデータを取得（タイムアウト付き）
            item = save_queue.get(timeout=1.0)
            batch.append(item)

            # バッチサイズに達したらコミット
            if len(batch) >= batch_size:
                _save_batch(cursor, batch)
                conn.commit()
                with save_lock:
                    save_results['success'] += len(batch)
                batch = []

        except Exception:
            # タイムアウト時は残りのバッチを処理
            if batch:
                _save_batch(cursor, batch)
                conn.commit()
                with save_lock:
                    save_results['success'] += len(batch)
                batch = []

    # 終了時に残りを保存
    if batch:
        _save_batch(cursor, batch)
        conn.commit()
        with save_lock:
            save_results['success'] += len(batch)

    conn.close()


def _save_batch(cursor, batch):
    """バッチデータをDBに保存"""
    for item in batch:
        race_id = item['race_id']
        beforeinfo = item['data']

        try:
            # race_details更新
            exhibition_times = beforeinfo.get('exhibition_times', {})
            tilt_angles = beforeinfo.get('tilt_angles', {})
            parts = beforeinfo.get('parts_replacements', {})
            weights = beforeinfo.get('adjusted_weights', {})
            st_times = beforeinfo.get('start_timings', {})
            courses = beforeinfo.get('exhibition_courses', {})
            prev_race = beforeinfo.get('previous_race', {})

            for pit in range(1, 7):
                cursor.execute('''
                    UPDATE race_details
                    SET exhibition_time = COALESCE(?, exhibition_time),
                        tilt_angle = COALESCE(?, tilt_angle),
                        parts_replacement = COALESCE(?, parts_replacement),
                        adjusted_weight = COALESCE(?, adjusted_weight),
                        st_time = COALESCE(?, st_time),
                        exhibition_course = COALESCE(?, exhibition_course),
                        prev_race_course = COALESCE(?, prev_race_course),
                        prev_race_st = COALESCE(?, prev_race_st),
                        prev_race_rank = COALESCE(?, prev_race_rank)
                    WHERE race_id = ? AND pit_number = ?
                ''', (
                    exhibition_times.get(pit),
                    tilt_angles.get(pit),
                    parts.get(pit, '') or None,
                    weights.get(pit),
                    st_times.get(pit),
                    courses.get(pit),
                    prev_race.get(pit, {}).get('course'),
                    prev_race.get(pit, {}).get('st'),
                    prev_race.get(pit, {}).get('rank'),
                    race_id, pit
                ))

            # race_conditions更新
            weather = beforeinfo.get('weather', {})
            if weather:
                cursor.execute('DELETE FROM race_conditions WHERE race_id = ?', (race_id,))
                cursor.execute('''
                    INSERT INTO race_conditions (
                        race_id, temperature, water_temperature,
                        wind_speed, wind_direction, wave_height, weather
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    race_id,
                    weather.get('temperature'),
                    weather.get('water_temperature'),
                    weather.get('wind_speed'),
                    weather.get('wind_direction'),
                    weather.get('wave_height'),
                    weather.get('weather')
                ))

        except Exception as e:
            print(f"DB保存エラー (race_id={race_id}): {e}")


def get_already_collected_races(db_path):
    """既に収集済みのレースIDを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # exhibition_timeが入っているレースは収集済みとみなす
    cursor.execute("""
        SELECT DISTINCT race_id FROM race_details
        WHERE exhibition_time IS NOT NULL
    """)
    collected = set(row[0] for row in cursor.fetchall())
    conn.close()

    return collected


def main(test_mode=False, test_count=100, resume=True, worker_count=12):
    """
    メイン処理

    Args:
        test_mode: テストモード（少数で動作確認）
        test_count: テストモード時の処理件数
        resume: 収集済みをスキップするか
        worker_count: 並列ワーカー数
    """
    print("=" * 80)
    print("2020-2023年 直前情報一括収集（最適化版）")
    print("=" * 80)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"モード: {'テスト' if test_mode else '本番'}")
    print(f"ワーカー数: {worker_count}")
    print(f"再開モード: {'有効' if resume else '無効'}")
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # 対象レース取得
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2020-01-01' AND r.race_date < '2024-01-01'
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)

    all_races = cursor.fetchall()
    conn.close()

    # 収集済みをスキップ
    if resume:
        collected = get_already_collected_races(str(db_path))
        races = [r for r in all_races if r[0] not in collected]
        print(f"全レース数: {len(all_races):,}件")
        print(f"収集済み: {len(collected):,}件")
        print(f"残り: {len(races):,}件")
    else:
        races = all_races
        print(f"対象レース数: {len(races):,}件")

    if test_mode:
        races = races[:test_count]
        print(f"テストモード: {test_count}件に制限")

    print()

    if len(races) == 0:
        print("処理対象がありません")
        return True

    # 確認（--auto-startオプションで自動開始）
    # バックグラウンド実行時はinputがエラーになるため、tryで囲む
    if not test_mode:
        try:
            if sys.stdin.isatty():
                response = input("収集を開始しますか？ (y/N): ")
                if response.lower() != 'y':
                    print("キャンセルしました")
                    return False
        except (EOFError, OSError):
            # バックグラウンド実行時は自動で開始
            print("（バックグラウンド実行: 自動開始）")
            pass

    print("収集開始...")
    print()

    start_time = time.time()

    # 統計
    total_stats = {
        'total': len(races),
        'success': 0,
        'failed': 0,
        'unpublished': 0
    }

    # DB保存ワーカー起動
    stop_event = threading.Event()
    saver_thread = threading.Thread(
        target=db_saver_worker,
        args=(str(db_path), stop_event)
    )
    saver_thread.start()

    # タスク準備
    tasks = [
        (race_id, venue_code, race_date, race_number)
        for race_id, venue_code, race_date, race_number in races
    ]

    completed = 0
    error_count = 0
    consecutive_errors = 0  # 連続エラー数

    # 並列処理
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(collect_single_race, task): task for task in tasks}

        for future in as_completed(futures):
            completed += 1

            try:
                result = future.result()

                if result['success']:
                    # キューに追加（DB保存ワーカーが処理）
                    save_queue.put({
                        'race_id': result['race_id'],
                        'data': result['data']
                    })
                    total_stats['success'] += 1
                    consecutive_errors = 0
                elif result['error'] == 'データ未公開':
                    total_stats['unpublished'] += 1
                    consecutive_errors = 0
                else:
                    total_stats['failed'] += 1
                    error_count += 1
                    consecutive_errors += 1

                    # 連続エラーが多い場合は警告
                    if consecutive_errors >= 10:
                        print(f"\n⚠️ 連続エラー {consecutive_errors}回検出")

                # 進捗表示（100件ごと）
                if completed % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (total_stats['total'] - completed) / rate if rate > 0 else 0

                    print(f"[{completed:6}/{total_stats['total']}] "
                          f"成功:{total_stats['success']:5} 失敗:{total_stats['failed']:4} "
                          f"未公開:{total_stats['unpublished']:5} "
                          f"[{elapsed/60:.1f}分経過, {rate:.1f}件/秒, 残り{remaining/60:.1f}分]",
                          flush=True)

            except Exception as e:
                total_stats['failed'] += 1
                error_count += 1
                print(f"エラー: {str(e)[:50]}")

    # DB保存ワーカー終了待ち
    stop_event.set()
    saver_thread.join()

    elapsed = time.time() - start_time

    # 結果サマリー
    print()
    print("=" * 80)
    print("収集完了")
    print("=" * 80)
    print()
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"所要時間: {elapsed/60:.1f}分 ({elapsed:.0f}秒)")
    print()
    print(f"処理レース数: {total_stats['total']:,}件")
    print(f"成功: {total_stats['success']:,}件")
    print(f"失敗: {total_stats['failed']:,}件")
    print(f"未公開: {total_stats['unpublished']:,}件")
    print(f"処理速度: {total_stats['total']/elapsed:.2f}件/秒")

    if total_stats['total'] > 0:
        print(f"成功率: {total_stats['success']/total_stats['total']*100:.1f}%")

    print()
    print("=" * 80)

    # テストモードの場合、エラー率をチェック
    if test_mode:
        error_rate = total_stats['failed'] / total_stats['total'] if total_stats['total'] > 0 else 0
        if error_rate > 0.1:  # 10%以上エラーなら失敗
            print(f"⚠️ エラー率が高い: {error_rate*100:.1f}%")
            return False
        else:
            print(f"✅ テスト成功（エラー率: {error_rate*100:.1f}%）")
            return True

    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='2020-2023年直前情報収集（最適化版）')
    parser.add_argument('--test', action='store_true', help='テストモード（100件のみ）')
    parser.add_argument('--test-count', type=int, default=100, help='テスト件数')
    parser.add_argument('--no-resume', action='store_true', help='最初から収集（収集済みもスキップしない）')
    parser.add_argument('--workers', type=int, default=12, help='並列ワーカー数')

    args = parser.parse_args()

    success = main(
        test_mode=args.test,
        test_count=args.test_count,
        resume=not args.no_resume,
        worker_count=args.workers
    )

    sys.exit(0 if success else 1)
