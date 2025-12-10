# -*- coding: utf-8 -*-
"""
2連単オッズ収集スクリプト

過去のレースから2連単オッズを取得してDBに保存する。
Seleniumを使用してJavaScriptで動的に生成されるオッズを取得。

使用方法:
    python scripts/fetch_exacta_odds.py --start 2025-01-01 --end 2025-01-31
    python scripts/fetch_exacta_odds.py --date 2025-11-01  # 特定日のみ
    python scripts/fetch_exacta_odds.py --recent 7  # 直近7日間
"""

import sys
import os
import argparse
import sqlite3
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def get_races_without_exacta_odds(db_path: str, start_date: str, end_date: str) -> list:
    """2連単オッズが未取得のレースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        LEFT JOIN exacta_odds eo ON r.id = eo.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND eo.race_id IS NULL
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date, end_date))

    races = cursor.fetchall()
    conn.close()
    return races


def get_races_with_results(db_path: str, start_date: str, end_date: str) -> list:
    """結果があるレースを取得（払戻金がある = レース終了済み）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        JOIN payouts p ON r.id = p.race_id
        LEFT JOIN exacta_odds eo ON r.id = eo.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND eo.race_id IS NULL
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start_date, end_date))

    races = cursor.fetchall()
    conn.close()
    return races


def save_exacta_odds(db_path: str, race_id: int, odds_data: dict) -> int:
    """2連単オッズをDBに保存"""
    if not odds_data:
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    saved = 0
    for combination, odds in odds_data.items():
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO exacta_odds (race_id, combination, odds)
                VALUES (?, ?, ?)
            """, (race_id, combination, odds))
            saved += 1
        except Exception as e:
            print(f"[ERROR] DB保存エラー: {e}")

    conn.commit()
    conn.close()
    return saved


def fetch_exacta_odds_batch(races: list, db_path: str, delay: float = 3.0):
    """バッチで2連単オッズを取得"""
    from src.scraper.selenium_odds_scraper import SeleniumOddsScraper

    total = len(races)
    success = 0
    failed = 0
    skipped = 0

    print(f"=== 2連単オッズ収集開始 ===")
    print(f"対象レース数: {total}")
    print(f"リクエスト間隔: {delay}秒")
    print()

    with SeleniumOddsScraper(headless=True, wait_timeout=15) as scraper:
        for idx, (race_id, venue_code, race_date, race_number) in enumerate(races, 1):
            # 日付形式を変換（YYYY-MM-DD -> YYYYMMDD）
            race_date_fmt = race_date.replace('-', '')

            print(f"[{idx}/{total}] {venue_code} {race_date} {race_number}R (race_id={race_id})")

            try:
                # 2連単オッズを取得
                odds_data = scraper.get_exacta_odds(venue_code, race_date_fmt, race_number)

                if odds_data and len(odds_data) > 0:
                    # DBに保存
                    saved = save_exacta_odds(db_path, race_id, odds_data)
                    print(f"  -> {saved}通り保存")
                    success += 1
                else:
                    print(f"  -> オッズデータなし")
                    skipped += 1

            except Exception as e:
                print(f"  -> エラー: {e}")
                failed += 1

            # 次のリクエストまで待機
            if idx < total:
                time.sleep(delay)

    print()
    print(f"=== 収集完了 ===")
    print(f"成功: {success}")
    print(f"失敗: {failed}")
    print(f"スキップ: {skipped}")

    return success, failed, skipped


def main():
    parser = argparse.ArgumentParser(description='2連単オッズ収集')
    parser.add_argument('--start', type=str, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--date', type=str, help='特定日 (YYYY-MM-DD)')
    parser.add_argument('--recent', type=int, help='直近N日間')
    parser.add_argument('--delay', type=float, default=3.0, help='リクエスト間隔（秒）')
    parser.add_argument('--limit', type=int, default=0, help='最大取得レース数（0=無制限）')

    args = parser.parse_args()

    # 日付範囲を決定
    if args.date:
        start_date = args.date
        end_date = args.date
    elif args.recent:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.recent)).strftime('%Y-%m-%d')
    elif args.start and args.end:
        start_date = args.start
        end_date = args.end
    else:
        # デフォルト: 直近30日
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    print(f"期間: {start_date} ~ {end_date}")

    # 対象レースを取得（結果があるレースのみ）
    races = get_races_with_results(DATABASE_PATH, start_date, end_date)

    if not races:
        print("対象レースがありません（全て取得済み or レースなし）")
        return

    # 件数制限
    if args.limit > 0:
        races = races[:args.limit]

    print(f"対象レース: {len(races)}件")

    # 確認
    confirm = input("実行しますか？ (y/n): ")
    if confirm.lower() != 'y':
        print("キャンセルしました")
        return

    # 収集実行
    fetch_exacta_odds_batch(races, DATABASE_PATH, delay=args.delay)


if __name__ == '__main__':
    main()
