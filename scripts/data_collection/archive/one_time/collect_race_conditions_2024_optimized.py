#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年race_conditions一括収集（最適化版）

最適化ポイント:
1. レース開催日のみ処理（DBから取得）
2. 既にrace_conditionsがある日はスキップ
3. 並列処理（ThreadPool）
4. 会場ごとではなくレースごとに処理
"""
import sys
import os

# 最初に文字コード設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import time
import sqlite3
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.scraper.beforeinfo_scraper import BeforeInfoScraper


def get_races_needing_conditions(db_path, start_date=None, end_date=None):
    """race_conditionsが欠けているレースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # デフォルトは2024年
    if start_date is None:
        start_date = '2024-01-01'
    if end_date is None:
        end_date = '2025-01-01'

    # race_conditionsがないレースを取得
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date >= ? AND r.race_date < ?
          AND rc.race_id IS NULL
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date, end_date))

    races = cursor.fetchall()
    conn.close()

    return races


def collect_single_race_conditions(args):
    """1レースの気象データを収集"""
    race_id, venue_code, race_date, race_number = args

    scraper = BeforeInfoScraper(delay=0.3)

    result = {
        'race_id': race_id,
        'venue_code': venue_code,
        'race_date': race_date,
        'race_number': race_number,
        'success': False,
        'weather': None,
        'error': None
    }

    try:
        date_str = race_date.replace('-', '')

        # 直前情報から気象データを取得
        beforeinfo = scraper.get_race_beforeinfo(
            venue_code=f"{int(venue_code):02d}",
            date_str=date_str,
            race_number=race_number
        )

        if beforeinfo and beforeinfo.get('weather'):
            result['success'] = True
            result['weather'] = beforeinfo['weather']
        else:
            result['error'] = 'データなし'

    except Exception as e:
        result['error'] = str(e)[:50]

    return result


def save_race_conditions(db_path, race_id, weather):
    """気象データをDBに保存"""
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()

        # UPSERT操作
        cursor.execute('''
            INSERT OR REPLACE INTO race_conditions (
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

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='race_conditions一括収集')
    parser.add_argument('--start-date', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='終了日 (YYYY-MM-DD)')
    args = parser.parse_args()

    print("=" * 80)
    print("race_conditions 一括収集（最適化版）")
    print("=" * 80)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.start_date or args.end_date:
        print(f"期間: {args.start_date or '指定なし'} ～ {args.end_date or '指定なし'}")
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # race_conditionsが欠けているレースを取得
    races = get_races_needing_conditions(str(db_path), args.start_date, args.end_date)

    if not races:
        print("全てのレースにrace_conditionsがあります。処理不要です。")
        return

    # 日付ごとの件数を表示
    from collections import defaultdict
    date_counts = defaultdict(int)
    for _, _, date, _ in races:
        date_counts[date] += 1

    print(f"対象レース数: {len(races):,}件")
    print(f"対象日数: {len(date_counts)}日")
    print(f"並列ワーカー: 12")
    print()

    # 確認（バックグラウンド実行対応）
    try:
        if sys.stdin.isatty():
            response = input("収集を開始しますか？ (y/N): ")
            if response.lower() != 'y':
                print("キャンセルしました")
                return
    except (EOFError, OSError):
        print("（バックグラウンド実行: 自動開始）")

    print()
    print("収集開始...")
    print()

    start_time = time.time()

    stats = {
        'total': len(races),
        'success': 0,
        'failed': 0
    }

    completed = 0
    current_date = None

    # 並列処理
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(collect_single_race_conditions, race): race for race in races}

        for future in as_completed(futures):
            completed += 1

            try:
                result = future.result()

                # 日付が変わったら表示
                if result['race_date'] != current_date:
                    if current_date:
                        print()
                    current_date = result['race_date']
                    print(f"[{current_date}] ", end='', flush=True)

                if result['success']:
                    if save_race_conditions(str(db_path), result['race_id'], result['weather']):
                        stats['success'] += 1
                        print('.', end='', flush=True)
                    else:
                        stats['failed'] += 1
                        print('x', end='', flush=True)
                else:
                    stats['failed'] += 1
                    # エラーは表示しない（多すぎる）

                # 100件ごとに進捗
                if completed % 500 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (stats['total'] - completed) / rate / 60 if rate > 0 else 0
                    print(f"\n  進捗: {completed}/{stats['total']} ({completed/stats['total']*100:.1f}%) "
                          f"成功:{stats['success']} 残り約{remaining:.1f}分", flush=True)

            except Exception as e:
                stats['failed'] += 1

    elapsed = time.time() - start_time

    print()
    print()
    print("=" * 80)
    print("収集完了")
    print("=" * 80)
    print()
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"所要時間: {elapsed/60:.1f}分")
    print()
    print(f"対象レース: {stats['total']:,}件")
    print(f"成功: {stats['success']:,}件")
    print(f"失敗: {stats['failed']:,}件")
    print(f"成功率: {stats['success']/stats['total']*100:.1f}%")
    print()

    # 結果確認
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(DISTINCT r.id) as total,
            COUNT(DISTINCT rc.race_id) as with_conditions
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'
    """)
    total, with_cond = cursor.fetchone()
    conn.close()

    print(f"2024年データ状況: {with_cond:,}/{total:,}レース ({with_cond/total*100:.1f}%)")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
