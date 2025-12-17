"""
シンプルなオッズ取得スクリプト（2020～2024年対応）
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.odds_scraper import OddsScraper


def get_races_to_fetch(db_path, start_date, end_date):
    """未取得レースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    """
    cursor.execute(query, (start_date, end_date))
    races = cursor.fetchall()
    conn.close()
    return races


def save_odds_to_db(db_path, race_id, odds_data):
    """オッズをDBに保存"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for combination, odds_value in odds_data.items():
        cursor.execute("""
            INSERT OR REPLACE INTO trifecta_odds (race_id, combination, odds, fetched_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (race_id, combination, odds_value))

    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='オッズ取得（2020～2024年対応）')
    parser.add_argument('--db', default='data/boatrace.db')
    parser.add_argument('--start-date', required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--delay', type=float, default=1.0, help='リクエスト間隔（秒）')
    parser.add_argument('--limit', type=int, default=None, help='取得上限レース数')

    args = parser.parse_args()

    db_path = os.path.join(PROJECT_ROOT, args.db)
    if not os.path.exists(db_path):
        print(f"エラー: DB not found: {db_path}")
        return

    print("=" * 80)
    print("オッズ取得スクリプト（2020～2024年対応）")
    print(f"期間: {args.start_date} ～ {args.end_date}")
    print(f"リクエスト間隔: {args.delay}秒")
    print("=" * 80)

    # 未取得レースを取得
    races = get_races_to_fetch(db_path, args.start_date, args.end_date)
    total = len(races)

    if args.limit:
        races = races[:args.limit]
        print(f"対象レース数: {len(races)} / {total} (上限: {args.limit})")
    else:
        print(f"対象レース数: {total}")

    if total == 0:
        print("取得対象なし")
        return

    # スクレイパー初期化
    scraper = OddsScraper(delay=args.delay, max_retries=3)

    success_count = 0
    error_count = 0
    start_time = time.time()

    # 逐次処理
    for i, (race_id, venue_code, race_date, race_number) in enumerate(races):
        date_str = race_date.replace('-', '')

        # オッズ取得
        odds_data = scraper.get_trifecta_odds(venue_code, date_str, race_number)

        if odds_data:
            # DB保存
            save_odds_to_db(db_path, race_id, odds_data)
            success_count += 1
            status = "OK"
        else:
            error_count += 1
            status = "ERROR"

        # 進捗表示
        if (i + 1) % 10 == 0 or (i + 1) == len(races):
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(races) - i - 1) / rate if rate > 0 else 0

            print(f"[{i+1}/{len(races)}] {race_date} {venue_code.zfill(2)}R{race_number} - {status} "
                  f"| 成功: {success_count}, エラー: {error_count} "
                  f"| 速度: {rate:.2f}件/秒 | 残り: {remaining/60:.1f}分")

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print("完了")
    print(f"  成功: {success_count}レース")
    print(f"  エラー: {error_count}レース")
    print(f"  処理時間: {elapsed/60:.1f}分")
    print(f"  平均速度: {len(races)/elapsed:.2f}件/秒")
    print("=" * 80)


if __name__ == '__main__':
    main()
