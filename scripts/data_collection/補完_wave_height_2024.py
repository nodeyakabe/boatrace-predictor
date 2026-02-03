#!/usr/bin/env python3
"""
2024年のwave_height欠損データを補完するスクリプト

問題:
  2024年のrace_conditionsテーブルにwave_heightがNULLのレコードが805件存在

修正内容:
  - ResultScraperを使用して公式サイトから波高データを再取得
  - 既存のrace_conditionsレコードのwave_heightフィールドのみを更新
  - 並列処理で高速化
  - リトライ機能付き

使用方法:
  python scripts/data_collection/補完_wave_height_2024.py
  python scripts/data_collection/補完_wave_height_2024.py --dry-run  # 確認のみ
  python scripts/data_collection/補完_wave_height_2024.py --start-date 2024-01-01 --end-date 2024-06-30
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


def get_races_without_wave_height(start_date=None, end_date=None):
    """
    wave_heightが欠損しているレースを取得

    Args:
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)

    Returns:
        list: [(race_id, venue_code, race_date, race_number, rc_id), ...]
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
        # デフォルトは2024年のみ
        date_filter = "AND r.race_date >= '2024-01-01' AND r.race_date < '2025-01-01'"
        print("期間フィルター: 2024年（デフォルト）")

    query = f"""
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            rc.id as rc_id
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rc.wave_height IS NULL
          {date_filter}
        ORDER BY r.race_date, r.venue_code, r.race_number
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    print(f"wave_heightが欠損しているレース: {len(rows)}件")
    return rows


def fetch_wave_height(race_info):
    """
    単一レースのwave_heightを取得

    Args:
        race_info: (race_id, venue_code, race_date, race_number, rc_id)

    Returns:
        tuple: (rc_id, wave_height) または None
    """
    race_id, venue_code, race_date, race_number, rc_id = race_info

    scraper = get_scraper()

    try:
        # race_dateをYYYYMMDD形式に変換
        date_str = race_date.replace('-', '')

        # ResultScraperでレース結果を取得
        results = scraper.scrape_race_results(venue_code, date_str, race_number)

        if not results:
            return None

        # 最初のresultから環境情報を取得
        if results and len(results) > 0:
            wave_height = results[0].get('wave_height')
            if wave_height is not None:
                return (rc_id, wave_height)

        return None

    except Exception as e:
        print(f"  ERROR: エラー: {race_date} 会場{venue_code:02d} R{race_number:02d} - {e}")
        return None


def update_wave_heights(updates, dry_run=False):
    """
    wave_heightを一括更新

    Args:
        updates: [(rc_id, wave_height), ...]
        dry_run: Trueの場合、実際の更新は行わず確認のみ
    """
    if dry_run:
        print(f"\n[DRY-RUN MODE] {len(updates)}件の更新をスキップします")
        return

    if not updates:
        print("\n更新対象のデータがありません")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        for rc_id, wave_height in updates:
            cursor.execute("""
                UPDATE race_conditions
                SET wave_height = ?
                WHERE id = ?
            """, (wave_height, rc_id))

        conn.commit()
        print(f"\nOK: 更新完了: {len(updates)}件のwave_heightを補完しました")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: エラーが発生しました: {e}")
        raise

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="2024年のwave_height欠損データを補完",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 2024年全体を補完（デフォルト）
  python scripts/data_collection/補完_wave_height_2024.py

  # dry-runで確認
  python scripts/data_collection/補完_wave_height_2024.py --dry-run

  # 期間を指定して補完
  python scripts/data_collection/補完_wave_height_2024.py --start-date 2024-01-01 --end-date 2024-06-30

  # 並列数を指定
  python scripts/data_collection/補完_wave_height_2024.py --workers 8
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際の更新は行わず、確認のみ行う'
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
        default=8,
        help='並列ワーカー数（デフォルト: 8）'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("wave_height 補完スクリプト")
    print("=" * 70)
    print(f"データベース: {DATABASE_PATH}")
    print(f"モード: {'DRY-RUN（確認のみ）' if args.dry_run else '実行モード（実際に更新）'}")
    print(f"並列ワーカー数: {args.workers}")
    print("=" * 70)
    print()

    # 欠損データを取得
    races_to_fetch = get_races_without_wave_height(
        start_date=args.start_date,
        end_date=args.end_date
    )

    if not races_to_fetch:
        print("\n補完が必要なレースはありません")
        return

    print(f"\n補完を開始します... (対象: {len(races_to_fetch)}件)")
    print()

    # 並列処理でwave_heightを取得
    updates = []
    completed = 0
    failed = 0

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_race = {
            executor.submit(fetch_wave_height, race_info): race_info
            for race_info in races_to_fetch
        }

        for future in as_completed(future_to_race):
            race_info = future_to_race[future]
            race_id, venue_code, race_date, race_number, rc_id = race_info

            try:
                result = future.result()
                if result:
                    updates.append(result)
                    completed += 1
                    print(f"  OK: {race_date} 会場{venue_code:02d} R{race_number:02d} - wave_height={result[1]}cm")
                else:
                    failed += 1
                    print(f"  - {race_date} 会場{venue_code:02d} R{race_number:02d} - データ取得失敗")

            except Exception as e:
                failed += 1
                print(f"  ERROR: {race_date} 会場{venue_code:02d} R{race_number:02d} - エラー: {e}")

            # 進捗表示
            processed = completed + failed
            if processed % 50 == 0:
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

    # データベースを更新
    update_wave_heights(updates, dry_run=args.dry_run)

    if not args.dry_run and updates:
        # 検証: まだ欠損があるか確認
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            WHERE rc.wave_height IS NULL
              AND r.race_date >= '2024-01-01'
              AND r.race_date < '2025-01-01'
        """)
        remaining = cursor.fetchone()[0]
        conn.close()

        print(f"\n検証: 2024年の残存欠損件数 = {remaining}件")


if __name__ == "__main__":
    main()
