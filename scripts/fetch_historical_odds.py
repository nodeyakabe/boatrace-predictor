"""
過去のオッズデータを一括取得するスクリプト

公式サイトから取得可能な期間（約1ヶ月分）のオッズを収集し、DBに保存する

使用方法:
    python scripts/fetch_historical_odds.py --start-date 2025-11-01 --end-date 2025-12-06
    python scripts/fetch_historical_odds.py --missing-only  # 未取得のレースのみ
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timedelta
import time
import warnings

warnings.filterwarnings('ignore')

# 出力をバッファリングしない
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.odds_scraper import OddsScraper


def get_races_to_fetch(db_path, start_date, end_date, missing_only=False):
    """取得対象のレースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if missing_only:
        # trifecta_oddsテーブルにデータがないレースのみ
        query = """
            SELECT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            WHERE r.race_date BETWEEN ? AND ?
              AND NOT EXISTS (
                  SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
              )
            ORDER BY r.race_date, r.venue_code, r.race_number
        """
    else:
        query = """
            SELECT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            WHERE r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date, r.venue_code, r.race_number
        """

    cursor.execute(query, (start_date, end_date))
    races = cursor.fetchall()
    conn.close()
    return races


def save_odds_to_db(db_path, race_id, odds_data):
    """オッズデータをDBに保存"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    saved_count = 0
    for combination, odds_value in odds_data.items():
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO trifecta_odds (race_id, combination, odds, fetched_at)
                VALUES (?, ?, ?, datetime('now'))
            """, (race_id, combination, odds_value))
            saved_count += 1
        except Exception as e:
            pass  # 重複など

    conn.commit()
    conn.close()
    return saved_count


def fetch_historical_odds(db_path, start_date, end_date, missing_only=False, delay=0.5):
    """
    過去のオッズデータを一括取得

    Args:
        db_path: DBパス
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        missing_only: 未取得レースのみ
        delay: リクエスト間隔（秒）
    """
    print("=" * 60)
    print("過去オッズデータ一括取得")
    print(f"期間: {start_date} ～ {end_date}")
    if missing_only:
        print("モード: 未取得レースのみ")
    print("=" * 60)

    # 対象レースを取得
    races = get_races_to_fetch(db_path, start_date, end_date, missing_only)
    total = len(races)
    print(f"対象レース数: {total}")

    if total == 0:
        print("取得対象のレースがありません")
        return

    # スクレイパー初期化
    scraper = OddsScraper(delay=delay)

    success_count = 0
    skip_count = 0
    error_count = 0
    total_odds = 0

    start_time = time.time()

    for i, (race_id, venue_code, race_date, race_number) in enumerate(races):
        try:
            # 日付形式変換
            date_str = race_date.replace('-', '')

            # オッズ取得
            odds = scraper.get_trifecta_odds(venue_code, date_str, race_number)

            if odds:
                # DB保存
                saved = save_odds_to_db(db_path, race_id, odds)
                success_count += 1
                total_odds += saved

                if success_count <= 5 or success_count % 100 == 0:
                    print(f"  OK: {race_date} {venue_code} {race_number}R - {saved}件")
            else:
                skip_count += 1

        except Exception as e:
            error_count += 1
            if error_count <= 5:
                print(f"  ERROR: {race_date} {venue_code} {race_number}R - {str(e)[:50]}")

        # 進捗表示
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (total - i - 1) / rate if rate > 0 else 0
            print(f"進捗: {i + 1}/{total} ({(i+1)/total*100:.1f}%) "
                  f"- 成功: {success_count}, スキップ: {skip_count}, エラー: {error_count} "
                  f"- 残り: {remaining/60:.1f}分")

        # 負荷軽減
        time.sleep(delay)

    scraper.close()

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("取得完了")
    print(f"  成功: {success_count} レース ({total_odds} 件のオッズ)")
    print(f"  スキップ: {skip_count} レース (データなし)")
    print(f"  エラー: {error_count} レース")
    print(f"  処理時間: {elapsed/60:.1f}分")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='過去のオッズデータを一括取得')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end-date', help='終了日（YYYY-MM-DD）')
    parser.add_argument('--missing-only', action='store_true', help='未取得レースのみ')
    parser.add_argument('--delay', type=float, default=0.5, help='リクエスト間隔（秒）')

    args = parser.parse_args()

    # DBパスを絶対パスに
    db_path = os.path.join(PROJECT_ROOT, args.db)
    if not os.path.exists(db_path):
        print(f"データベースが見つかりません: {db_path}")
        return

    # デフォルト期間（1ヶ月前から今日まで）
    if not args.start_date:
        args.start_date = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d')
    if not args.end_date:
        args.end_date = datetime.now().strftime('%Y-%m-%d')

    fetch_historical_odds(
        db_path,
        args.start_date,
        args.end_date,
        args.missing_only,
        args.delay
    )


if __name__ == '__main__':
    main()
