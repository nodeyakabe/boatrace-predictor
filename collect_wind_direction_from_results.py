# -*- coding: utf-8 -*-
"""
レース結果ページから風向データを収集してrace_conditionsテーブルに保存

既存のレース結果ページから風速・風向・波高データを自動収集
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

from config.settings import DATABASE_PATH
from src.scraper.result_scraper import ResultScraper


def collect_wind_direction_data(limit: int = None, skip_existing: bool = True):
    """
    レース結果ページから風向データを収集

    Args:
        limit: 収集するレース数の上限（Noneで全件）
        skip_existing: 既存データがある場合はスキップするか
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

    # 対象レースを取得（結果があり、weather/race_conditionsにデータがないもの）
    if skip_existing:
        cursor.execute("""
            SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
            FROM races r
            JOIN results res ON r.id = res.race_id
            LEFT JOIN race_conditions rc ON r.id = rc.race_id
            WHERE rc.id IS NULL
            ORDER BY r.race_date DESC, r.venue_code, r.race_number
        """)
    else:
        cursor.execute("""
            SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
            FROM races r
            JOIN results res ON r.id = res.race_id
            ORDER BY r.race_date DESC, r.venue_code, r.race_number
        """)

    races = cursor.fetchall()

    if limit:
        races = races[:limit]

    print("=" * 80)
    print("風向データ収集（レース結果ページから）")
    print("=" * 80)
    print(f"対象レース数: {len(races)}件")
    print(f"スキップ既存: {skip_existing}")
    print()

    scraper = ResultScraper()

    stats = {
        'total': len(races),
        'success': 0,
        'no_weather': 0,
        'error': 0
    }

    for race_id, race_date, venue_code, race_number in tqdm(races, desc="収集中"):
        try:
            # race_dateをYYYYMMDD形式に変換
            if '-' in race_date:
                date_formatted = race_date.replace('-', '')
            else:
                date_formatted = race_date

            # レース結果ページを取得
            result_data = scraper.get_race_result(venue_code, date_formatted, race_number)

            if result_data and result_data.get('weather_data'):
                weather = result_data['weather_data']

                collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                # データベースに保存
                cursor.execute("""
                    INSERT OR REPLACE INTO race_conditions (
                        race_id,
                        weather,
                        wind_direction,
                        wind_speed,
                        wave_height,
                        temperature,
                        water_temperature,
                        collected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    race_id,
                    weather.get('weather_condition'),
                    weather.get('wind_direction'),
                    weather.get('wind_speed'),
                    weather.get('wave_height'),
                    weather.get('temperature'),
                    weather.get('water_temperature'),
                    collected_at
                ))
                conn.commit()
                stats['success'] += 1
            else:
                stats['no_weather'] += 1

            # レート制限
            time.sleep(0.5)

        except Exception as e:
            stats['error'] += 1
            print(f"\nエラー: {race_date} {venue_code} {race_number}R - {e}")
            continue

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

    # race_conditionsの件数
    cursor.execute("SELECT COUNT(*) FROM race_conditions")
    rc_count = cursor.fetchone()[0]
    print(f"race_conditions: {rc_count}件")

    # 風向データがある件数
    cursor.execute("SELECT COUNT(*) FROM race_conditions WHERE wind_direction IS NOT NULL")
    wind_dir_count = cursor.fetchone()[0]
    print(f"  うち風向あり: {wind_dir_count}件")

    # 風向の種類
    cursor.execute("""
        SELECT wind_direction, COUNT(*) as cnt
        FROM race_conditions
        WHERE wind_direction IS NOT NULL
        GROUP BY wind_direction
        ORDER BY cnt DESC
    """)
    wind_dirs = cursor.fetchall()
    if wind_dirs:
        print("\n風向の分布:")
        for wd, cnt in wind_dirs:
            print(f"  {wd}: {cnt}件")

    # 結果があるがrace_conditionsにないレース数
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        JOIN results res ON r.id = res.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rc.id IS NULL
    """)
    missing = cursor.fetchone()[0]
    print(f"\n収集可能なレース: {missing}件")

    conn.close()
    print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='風向データ収集')
    parser.add_argument('--limit', type=int, default=None, help='収集するレース数の上限')
    parser.add_argument('--status', action='store_true', help='現在の状況を確認')
    parser.add_argument('--force', action='store_true', help='既存データも上書き')

    args = parser.parse_args()

    if args.status:
        check_current_status()
    else:
        collect_wind_direction_data(
            limit=args.limit,
            skip_existing=not args.force
        )
