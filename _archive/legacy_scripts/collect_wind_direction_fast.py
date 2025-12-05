# -*- coding: utf-8 -*-
"""
風向データ高速収集スクリプト

最適化ポイント:
1. 日付・会場単位で一括取得（12レース分を1リクエストで）
2. 並列処理（ThreadPoolExecutor）
3. バッチINSERT
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from datetime import datetime
import time
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from config.settings import DATABASE_PATH
from src.scraper.result_scraper import ResultScraper


# スレッドローカルなスクレイパー
thread_local = threading.local()


def get_scraper():
    """スレッドごとにスクレイパーを取得"""
    if not hasattr(thread_local, 'scraper'):
        thread_local.scraper = ResultScraper()
    return thread_local.scraper


def fetch_weather_for_date_venue(venue_code, race_date, race_ids_map):
    """
    指定日・会場の全レース天気情報を取得

    Args:
        venue_code: 会場コード
        race_date: 日付（YYYY-MM-DD形式）
        race_ids_map: {race_number: race_id} のマップ

    Returns:
        [(race_id, weather_data), ...]
    """
    scraper = get_scraper()
    results = []

    try:
        # YYYYMMDD形式に変換
        date_formatted = race_date.replace('-', '')

        # 1Rの結果ページから天気情報を取得（同日は同じ天気）
        result_data = scraper.get_race_result(venue_code, date_formatted, 1)

        if result_data and result_data.get('weather_data'):
            weather = result_data['weather_data']

            # 全レースに同じ天気データを適用
            for race_number, race_id in race_ids_map.items():
                results.append((race_id, weather))

        # レート制限（サーバー負荷軽減）
        time.sleep(0.3)

    except Exception as e:
        pass  # エラーは無視して続行

    return results


def collect_wind_direction_fast(limit: int = None, workers: int = 5):
    """
    風向データを高速収集

    Args:
        limit: 収集する日付・会場ペアの上限
        workers: 並列ワーカー数
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # race_conditionsテーブルがなければ作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS race_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER UNIQUE,
            weather TEXT,
            wind_direction TEXT,
            wind_speed REAL,
            wave_height INTEGER,
            temperature REAL,
            water_temperature REAL,
            collected_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # 未収集の日付・会場ペアを取得
    cursor.execute("""
        SELECT r.race_date, r.venue_code, r.race_number, r.id
        FROM races r
        JOIN results res ON r.id = res.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rc.id IS NULL
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
    """)
    rows = cursor.fetchall()

    # 日付・会場ごとにグループ化
    date_venue_map = {}  # {(date, venue): {race_number: race_id}}
    for race_date, venue_code, race_number, race_id in rows:
        key = (race_date, venue_code)
        if key not in date_venue_map:
            date_venue_map[key] = {}
        date_venue_map[key][race_number] = race_id

    date_venue_list = list(date_venue_map.items())

    if limit:
        date_venue_list = date_venue_list[:limit]

    total_races = sum(len(v) for _, v in date_venue_list)

    print("=" * 80)
    print("風向データ高速収集")
    print("=" * 80)
    print(f"対象日付・会場ペア: {len(date_venue_list)}件")
    print(f"対象レース数: {total_races}件")
    print(f"並列ワーカー数: {workers}")
    print()

    stats = {
        'success': 0,
        'no_weather': 0,
        'error': 0
    }

    collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    insert_buffer = []

    def process_batch():
        """バッファのデータをDBに挿入"""
        nonlocal insert_buffer
        if not insert_buffer:
            return

        cursor.executemany("""
            INSERT OR IGNORE INTO race_conditions (
                race_id, weather, wind_direction, wind_speed,
                wave_height, temperature, water_temperature, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, insert_buffer)
        conn.commit()
        insert_buffer = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}

        for (race_date, venue_code), race_ids_map in date_venue_list:
            future = executor.submit(
                fetch_weather_for_date_venue,
                venue_code, race_date, race_ids_map
            )
            futures[future] = (race_date, venue_code, len(race_ids_map))

        with tqdm(total=len(date_venue_list), desc="収集中") as pbar:
            for future in as_completed(futures):
                race_date, venue_code, race_count = futures[future]

                try:
                    results = future.result()

                    if results:
                        for race_id, weather in results:
                            insert_buffer.append((
                                race_id,
                                weather.get('weather_condition'),
                                weather.get('wind_direction'),
                                weather.get('wind_speed'),
                                weather.get('wave_height'),
                                weather.get('temperature'),
                                weather.get('water_temperature'),
                                collected_at
                            ))
                            stats['success'] += 1

                        # 100件ごとにバッチ挿入
                        if len(insert_buffer) >= 100:
                            process_batch()
                    else:
                        stats['no_weather'] += race_count

                except Exception as e:
                    stats['error'] += race_count

                pbar.update(1)

    # 残りをコミット
    process_batch()
    conn.close()

    print("\n" + "=" * 80)
    print("収集完了")
    print("=" * 80)
    print(f"成功: {stats['success']}件")
    print(f"天候データなし: {stats['no_weather']}件")
    print(f"エラー: {stats['error']}件")
    print("=" * 80)

    return stats


def check_current_status():
    """現在のデータ状況を確認"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("現在のデータ状況")
    print("=" * 80)

    cursor.execute("SELECT COUNT(*) FROM race_conditions")
    rc_count = cursor.fetchone()[0]
    print(f"race_conditions: {rc_count:,}件")

    cursor.execute("SELECT COUNT(*) FROM race_conditions WHERE wind_direction IS NOT NULL")
    wind_dir_count = cursor.fetchone()[0]
    print(f"  うち風向あり: {wind_dir_count:,}件")

    # 未収集レース数
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        JOIN results res ON r.id = res.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rc.id IS NULL
    """)
    missing = cursor.fetchone()[0]
    print(f"\n収集可能なレース: {missing:,}件")

    # 日付・会場ペア数
    cursor.execute("""
        SELECT COUNT(DISTINCT r.race_date || '_' || r.venue_code)
        FROM races r
        JOIN results res ON r.id = res.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rc.id IS NULL
    """)
    pairs = cursor.fetchone()[0]
    print(f"収集対象の日付・会場ペア: {pairs:,}件")
    print(f"推定所要時間: 約{pairs * 0.5 / 60:.0f}分（0.5秒/ペア、並列5）")

    conn.close()
    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='風向データ高速収集')
    parser.add_argument('--limit', type=int, default=None, help='収集する日付・会場ペアの上限')
    parser.add_argument('--status', action='store_true', help='現在の状況を確認')
    parser.add_argument('--workers', type=int, default=5, help='並列ワーカー数')
    parser.add_argument('--test', action='store_true', help='テスト実行（10件のみ）')

    args = parser.parse_args()

    if args.status:
        check_current_status()
    elif args.test:
        collect_wind_direction_fast(limit=10, workers=3)
    else:
        collect_wind_direction_fast(limit=args.limit, workers=args.workers)
