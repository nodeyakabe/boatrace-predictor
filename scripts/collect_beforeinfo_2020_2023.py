#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020-2023年の直前情報一括収集（並列版）

全ての直前情報を収集：
- 展示タイム
- チルト角度
- 部品交換
- 調整重量
- ST（スタート展示）
- 展示進入コース
- 前走成績（進入・ST・着順）
- 気象データ（気温・水温・風速・風向・波高・天候）
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
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.scraper.beforeinfo_scraper import BeforeInfoScraper


def collect_single_race(args):
    """
    1レース分の直前情報を収集（ワーカー用）

    Args:
        args: (race_id, venue_code, race_date, race_number, db_path)

    Returns:
        dict: 収集結果
    """
    race_id, venue_code, race_date, race_number, db_path = args

    scraper = BeforeInfoScraper(delay=0.5)  # 並列処理のため短縮

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
        # YYYYMMDD形式に変換
        date_str = race_date.replace('-', '')

        # 直前情報取得
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


def save_beforeinfo_to_db(race_id, beforeinfo, db_path):
    """
    直前情報をDBに保存

    Args:
        race_id: レースID
        beforeinfo: 直前情報データ
        db_path: DB パス

    Returns:
        bool: 成功したらTrue
    """
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()

        # 1. race_details テーブルに保存（直前情報）
        exhibition_times = beforeinfo.get('exhibition_times', {})
        tilt_angles = beforeinfo.get('tilt_angles', {})
        parts = beforeinfo.get('parts_replacements', {})
        weights = beforeinfo.get('adjusted_weights', {})
        st_times = beforeinfo.get('start_timings', {})
        courses = beforeinfo.get('exhibition_courses', {})
        prev_race = beforeinfo.get('previous_race', {})

        for pit in range(1, 7):
            # race_details テーブル更新（全ての直前情報）
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

        # 2. race_conditions テーブルに保存
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

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"DB保存エラー (race_id={race_id}): {e}")
        return False


def main():
    print("=" * 80)
    print("2020-2023年 直前情報一括収集（並列版）")
    print("=" * 80)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # 2020-2023年の全レースを取得
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2020-01-01' AND r.race_date < '2024-01-01'
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)

    races = cursor.fetchall()
    conn.close()

    print(f"対象レース数: {len(races):,}件")
    print(f"並列ワーカー: 8")
    print()

    # 確認（環境変数でスキップ可能）
    if not os.environ.get('AUTO_START'):
        response = input("収集を開始しますか？ (y/N): ")
        if response.lower() != 'y':
            print("キャンセルしました")
            return

    print()
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

    # タスクを準備
    tasks = [
        (race_id, venue_code, race_date, race_number, str(db_path))
        for race_id, venue_code, race_date, race_number in races
    ]

    completed = 0

    # 並列処理（ThreadPool - I/O bound）
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(collect_single_race, task): task for task in tasks}

        for future in as_completed(futures):
            completed += 1

            try:
                result = future.result()

                if result['success']:
                    # DBに保存
                    if save_beforeinfo_to_db(result['race_id'], result['data'], str(db_path)):
                        total_stats['success'] += 1
                    else:
                        total_stats['failed'] += 1
                elif result['error'] == 'データ未公開':
                    total_stats['unpublished'] += 1
                else:
                    total_stats['failed'] += 1

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
                print(f"エラー: {str(e)[:50]}")

    elapsed = time.time() - start_time

    # 結果サマリー
    print()
    print("=" * 80)
    print("収集完了")
    print("=" * 80)
    print()
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"所要時間: {elapsed/3600:.2f}時間 ({elapsed/60:.1f}分)")
    print()
    print(f"総レース数: {total_stats['total']:,}件")
    print(f"成功: {total_stats['success']:,}件")
    print(f"失敗: {total_stats['failed']:,}件")
    print(f"未公開: {total_stats['unpublished']:,}件")
    print(f"成功率: {total_stats['success']/total_stats['total']*100:.1f}%")
    print()

    # 収集データの確認
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(DISTINCT ed.race_id) as exhibition_count,
            COUNT(DISTINCT rc.race_id) as weather_count,
            COUNT(DISTINCT r.id) as total_races
        FROM races r
        LEFT JOIN exhibition_data ed ON r.id = ed.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date >= '2020-01-01' AND r.race_date < '2024-01-01'
        GROUP BY year
        ORDER BY year
    """)

    print("年別収集状況:")
    for year, exh, weather, total in cursor.fetchall():
        print(f"  {year}年: 展示{exh:,}件 ({exh/total*100:.1f}%), "
              f"気象{weather:,}件 ({weather/total*100:.1f}%), "
              f"全{total:,}レース")

    conn.close()

    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
