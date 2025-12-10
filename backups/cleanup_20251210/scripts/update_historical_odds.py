"""
過去レースの払戻金（オッズ）を一括更新するスクリプト

結果ページから三連単払戻金を取得し、DBを更新する
払戻金 ÷ 100 = オッズ倍率

使用方法:
    python scripts/update_historical_odds.py --start-date 2025-11-01 --end-date 2025-11-30
    python scripts/update_historical_odds.py --missing-only  # オッズがNULLのレースのみ
"""
import os
import sys

# 出力をバッファリングしない
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
import sqlite3
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.result_scraper import ResultScraper


def get_races_to_update(db_path, start_date=None, end_date=None, missing_only=False):
    """更新対象のレースを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if missing_only:
        # オッズがNULLのレースのみ
        query = """
            SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            JOIN results res ON r.id = res.race_id
            WHERE res.rank = '1' AND res.trifecta_odds IS NULL
            ORDER BY r.race_date DESC, r.venue_code, r.race_number
        """
        cursor.execute(query)
    else:
        # 期間指定
        query = """
            SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number
            FROM races r
            JOIN results res ON r.id = res.race_id
            WHERE r.race_date BETWEEN ? AND ?
              AND res.rank = '1'
            ORDER BY r.race_date, r.venue_code, r.race_number
        """
        cursor.execute(query, (start_date, end_date))

    races = cursor.fetchall()
    conn.close()
    return races


def update_odds_for_race(race_info, scraper, db_path):
    """1レースのオッズを更新"""
    race_id, venue_code, race_date, race_number = race_info

    try:
        # 日付形式を変換（YYYY-MM-DD → YYYYMMDD）
        date_str = race_date.replace('-', '')

        # 結果を取得
        result = scraper.get_race_result(venue_code, date_str, race_number)

        if result and result.get('trifecta_odds'):
            odds = result['trifecta_odds']

            # DBを更新
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 1着のレコードを更新
            cursor.execute("""
                UPDATE results
                SET trifecta_odds = ?
                WHERE race_id = ? AND rank = '1'
            """, (odds, race_id))

            conn.commit()
            conn.close()

            return True, race_id, odds
        else:
            return False, race_id, None

    except Exception as e:
        return False, race_id, str(e)


def update_historical_odds(db_path, start_date=None, end_date=None, missing_only=False, workers=4):
    """
    過去データの払戻金を一括更新

    Args:
        db_path: DBパス
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        missing_only: NULLのレースのみ更新
        workers: 並列数
    """
    print("=" * 60)
    print("過去データ払戻金更新")
    if missing_only:
        print("モード: オッズがNULLのレースのみ")
    else:
        print(f"期間: {start_date} - {end_date}")
    print("=" * 60)

    # 対象レースを取得
    races = get_races_to_update(db_path, start_date, end_date, missing_only)
    total = len(races)
    print(f"対象レース数: {total}")

    if total == 0:
        print("更新対象のレースがありません")
        return

    # スクレイパーを準備（スレッドごとに1つ）
    success_count = 0
    error_count = 0
    scraper = ResultScraper()

    start_time = time.time()

    # 順次処理（サーバー負荷軽減のため）
    for i, race_info in enumerate(races):
        success, race_id, result = update_odds_for_race(race_info, scraper, db_path)

        if success:
            success_count += 1
            if success_count <= 10 or success_count % 50 == 0:
                print(f"  更新: race_id={race_id}, odds={result}")
        else:
            error_count += 1

        # 進捗表示
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (total - i - 1) / rate if rate > 0 else 0
            print(f"進捗: {i + 1}/{total} ({(i+1)/total*100:.1f}%) "
                  f"- 成功: {success_count}, エラー: {error_count} "
                  f"- 残り: {remaining/60:.1f}分")

        # サーバー負荷軽減
        time.sleep(0.3)

    scraper.close()

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("更新完了")
    print(f"  成功: {success_count}/{total}")
    print(f"  エラー: {error_count}/{total}")
    print(f"  処理時間: {elapsed/60:.1f}分")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='過去データの払戻金を更新')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end-date', help='終了日（YYYY-MM-DD）')
    parser.add_argument('--missing-only', action='store_true',
                        help='オッズがNULLのレースのみ更新')
    parser.add_argument('--workers', type=int, default=4, help='並列数')

    args = parser.parse_args()

    # DBパスを絶対パスに
    db_path = os.path.join(PROJECT_ROOT, args.db)
    if not os.path.exists(db_path):
        print(f"データベースが見つかりません: {db_path}")
        return

    # 引数チェック
    if not args.missing_only and (not args.start_date or not args.end_date):
        print("--start-date と --end-date を指定するか、--missing-only を使用してください")
        return

    update_historical_odds(
        db_path,
        args.start_date,
        args.end_date,
        args.missing_only,
        args.workers
    )


if __name__ == '__main__':
    main()
