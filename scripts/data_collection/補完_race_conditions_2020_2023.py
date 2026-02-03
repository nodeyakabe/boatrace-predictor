#!/usr/bin/env python3
"""
2020-2023年のrace_conditions未登録データを補完するスクリプト

問題:
  2020-2023年のracesテーブルにrace_conditionsが紐づいていないレコードが5,534件存在
  内訳: 2020年=3,310件、2021年=772件、2022年=852件、2023年=600件

修正内容:
  - ResultScraperを使用して公式サイトから環境条件データを取得
  - race_conditionsテーブルに新規レコードを挿入
  - 並列処理で高速化
  - リトライ機能付き

使用方法:
  python scripts/data_collection/補完_race_conditions_2020_2023.py
  python scripts/data_collection/補完_race_conditions_2020_2023.py --dry-run  # 確認のみ
  python scripts/data_collection/補完_race_conditions_2020_2023.py --year 2020
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import argparse
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from config.settings import DATABASE_PATH
from src.scraper.result_scraper import ResultScraper

# スレッドローカルストレージ
thread_local = threading.local()


def get_scraper():
    """スレッドローカルなスクレイパーを取得"""
    if not hasattr(thread_local, "scraper"):
        thread_local.scraper = ResultScraper()
    return thread_local.scraper


def get_races_without_conditions(start_date=None, end_date=None):
    """
    race_conditionsが未登録のレースを取得

    Args:
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)

    Returns:
        list: [(race_id, venue_code, race_date, race_number), ...]
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 期間フィルター条件を構築
    date_filter = ""
    params = []

    if start_date and end_date:
        date_filter = "AND r.race_date BETWEEN ? AND ?"
        params = [start_date, end_date]
        print(f"期間フィルター: {start_date} ～ {end_date}")
    elif start_date:
        date_filter = "AND r.race_date >= ?"
        params = [start_date]
        print(f"期間フィルター: {start_date} 以降")
    elif end_date:
        date_filter = "AND r.race_date <= ?"
        params = [end_date]
        print(f"期間フィルター: {end_date} まで")
    else:
        # デフォルトは2020-2023年
        date_filter = "AND r.race_date >= '2020-01-01' AND r.race_date < '2024-01-01'"
        print("期間フィルター: 2020-2023年（デフォルト）")

    query = f"""
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rc.id IS NULL
          {date_filter}
        ORDER BY r.race_date, r.venue_code, r.race_number
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    print(f"race_conditionsが未登録のレース: {len(rows)}件")
    return rows


def fetch_race_conditions(race_info):
    """
    単一レースのrace_conditionsを取得

    Args:
        race_info: (race_id, venue_code, race_date, race_number)

    Returns:
        dict: race_conditionsデータ または None
    """
    race_id, venue_code, race_date, race_number = race_info

    scraper = get_scraper()

    try:
        # race_dateをYYYYMMDD形式に変換
        date_str = race_date.replace('-', '')

        # ResultScraperでレース結果を取得（正しいメソッド名を使用）
        result_data = scraper.get_race_result_complete(venue_code, date_str, race_number)

        if not result_data or not result_data.get('weather_data'):
            return None

        # weather_dataから環境情報を取得
        weather_data = result_data['weather_data']

        conditions = {
            'race_id': race_id,
            'weather': weather_data.get('weather', ''),
            'wind_direction': weather_data.get('wind_direction', ''),
            'wind_speed': weather_data.get('wind_speed'),
            'wave_height': weather_data.get('wave_height'),
            'water_temperature': weather_data.get('water_temperature'),
            'air_temperature': weather_data.get('temperature')  # 'temperature'フィールドを使用
        }

        # 必須フィールドがあるか確認（少なくとも天気か風速があればOK）
        if conditions['weather'] or conditions['wind_speed'] is not None:
            return conditions

        return None

    except Exception as e:
        print(f"  ERROR: エラー: {race_date} 会場{venue_code} R{race_number:02d} - {e}")
        return None


def insert_race_conditions(conditions_list, dry_run=False):
    """
    race_conditionsを一括挿入

    Args:
        conditions_list: [条件dict, ...]
        dry_run: Trueの場合、実際の挿入は行わず確認のみ
    """
    if dry_run:
        print(f"\n[DRY-RUN MODE] {len(conditions_list)}件の挿入をスキップします")
        if conditions_list:
            print("\n【挿入予定データのサンプル（先頭3件）】")
            for i, cond in enumerate(conditions_list[:3], 1):
                print(f"  {i}. race_id={cond['race_id']}, "
                      f"weather={cond['weather']}, "
                      f"wind_speed={cond['wind_speed']}m/s, "
                      f"wave_height={cond['wave_height']}cm")
        return

    if not conditions_list:
        print("\n挿入対象のデータがありません")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        for cond in conditions_list:
            cursor.execute("""
                INSERT INTO race_conditions (
                    race_id,
                    weather,
                    wind_direction,
                    wind_speed,
                    wave_height,
                    water_temperature,
                    air_temperature
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                cond['race_id'],
                cond['weather'],
                cond['wind_direction'],
                cond['wind_speed'],
                cond['wave_height'],
                cond['water_temperature'],
                cond['air_temperature']
            ))

        conn.commit()
        print(f"\nOK: 挿入完了: {len(conditions_list)}件のrace_conditionsを補完しました")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: エラーが発生しました: {e}")
        raise

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="2020-2023年のrace_conditions未登録データを補完",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 2020-2023年全体を補完（デフォルト）
  python scripts/data_collection/補完_race_conditions_2020_2023.py

  # dry-runで確認
  python scripts/data_collection/補完_race_conditions_2020_2023.py --dry-run

  # 特定年度を補完
  python scripts/data_collection/補完_race_conditions_2020_2023.py --year 2020

  # 期間を指定して補完
  python scripts/data_collection/補完_race_conditions_2020_2023.py --start-date 2020-01-01 --end-date 2020-06-30

  # 並列数を指定
  python scripts/data_collection/補完_race_conditions_2020_2023.py --workers 10
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際の挿入は行わず、確認のみ行う'
    )
    parser.add_argument(
        '--year',
        type=int,
        help='対象年度（例: 2020）'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        help='開始日（YYYY-MM-DD形式）'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='終了日（YYYY-MM-DD形式）'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=10,
        help='並列ワーカー数（デフォルト: 10）'
    )

    args = parser.parse_args()

    # 年度指定がある場合は日付範囲に変換
    start_date = args.start_date
    end_date = args.end_date

    if args.year:
        start_date = f"{args.year}-01-01"
        end_date = f"{args.year}-12-31"

    print("=" * 70)
    print("race_conditions 補完スクリプト")
    print("=" * 70)
    print(f"データベース: {DATABASE_PATH}")
    print(f"モード: {'DRY-RUN（確認のみ）' if args.dry_run else '実行モード（実際に挿入）'}")
    print(f"並列ワーカー数: {args.workers}")
    print("=" * 70)
    print()

    # 未登録データを取得
    races_to_fetch = get_races_without_conditions(
        start_date=start_date,
        end_date=end_date
    )

    if not races_to_fetch:
        print("\n補完が必要なレースはありません")
        return

    print(f"\n補完を開始します... (対象: {len(races_to_fetch)}件)")
    print()

    # 並列処理でrace_conditionsを取得
    conditions_list = []
    completed = 0
    failed = 0

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_race = {
            executor.submit(fetch_race_conditions, race_info): race_info
            for race_info in races_to_fetch
        }

        for future in as_completed(future_to_race):
            race_info = future_to_race[future]
            race_id, venue_code, race_date, race_number = race_info

            try:
                result = future.result()
                if result:
                    conditions_list.append(result)
                    completed += 1
                    print(f"  OK: {race_date} 会場{venue_code} R{race_number:02d} - "
                          f"{result['weather']}, 風速{result['wind_speed']}m/s")
                else:
                    failed += 1
                    print(f"  - {race_date} 会場{venue_code} R{race_number:02d} - データ取得失敗")

            except Exception as e:
                failed += 1
                print(f"  ERROR: {race_date} 会場{venue_code} R{race_number:02d} - エラー: {e}")

            # 進捗表示
            processed = completed + failed
            if processed % 100 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = len(races_to_fetch) - processed
                eta = remaining / rate if rate > 0 else 0
                print(f"\n進捗: {processed}/{len(races_to_fetch)} ({processed/len(races_to_fetch)*100:.1f}%) "
                      f"成功: {completed}, 失敗: {failed}, "
                      f"速度: {rate:.1f}件/秒, 残り時間: {eta/60:.1f}分\n")

    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print(f"取得完了: {elapsed:.1f}秒")
    print(f"  成功: {completed}件")
    print(f"  失敗: {failed}件")
    print(f"  成功率: {completed/(completed+failed)*100:.1f}%" if (completed+failed) > 0 else "N/A")
    print("=" * 70)

    # データベースに挿入
    insert_race_conditions(conditions_list, dry_run=args.dry_run)

    if not args.dry_run and conditions_list:
        # 検証: まだ未登録があるか確認
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        if args.year:
            cursor.execute("""
                SELECT COUNT(*)
                FROM races r
                LEFT JOIN race_conditions rc ON r.id = rc.race_id
                WHERE rc.id IS NULL
                  AND r.race_date >= ?
                  AND r.race_date < ?
            """, (f"{args.year}-01-01", f"{args.year+1}-01-01"))
            remaining = cursor.fetchone()[0]
            print(f"\n検証: {args.year}年の残存未登録件数 = {remaining}件")
        else:
            cursor.execute("""
                SELECT
                    SUBSTR(r.race_date, 1, 4) as year,
                    COUNT(*) as cnt
                FROM races r
                LEFT JOIN race_conditions rc ON r.id = rc.race_id
                WHERE rc.id IS NULL
                  AND r.race_date >= '2020-01-01'
                  AND r.race_date < '2024-01-01'
                GROUP BY year
                ORDER BY year
            """)
            results = cursor.fetchall()
            if results:
                print("\n検証: 残存未登録件数")
                for year, cnt in results:
                    print(f"  {year}年: {cnt}件")
            else:
                print("\n検証: 2020-2023年の未登録はすべて補完されました")

        conn.close()


if __name__ == "__main__":
    main()
