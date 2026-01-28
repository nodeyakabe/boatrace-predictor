"""
本日のレースのオッズ自動収集スクリプト

daily_schedulerから呼び出されて、本日のレースの3連単オッズを収集します。
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
import time

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.scraper.odds_scraper import OddsScraper


def fetch_todays_odds(db_path=None, headless=True):
    """
    本日のレースの3連単オッズを収集

    Args:
        db_path: DBパス（省略時はデフォルト）
        headless: ヘッドレスモード

    Returns:
        int: 収集したレース数
    """
    if db_path is None:
        db_path = project_root / 'data' / 'boatrace.db'

    today = datetime.now().strftime('%Y-%m-%d')

    print(f"本日のオッズ収集開始: {today}")

    # 本日のレース一覧を取得
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY race_time
    """, (today,))

    races = cursor.fetchall()
    conn.close()

    if not races:
        print(f"  本日のレースが見つかりません: {today}")
        return 0

    print(f"  対象レース: {len(races)}レース")

    # オッズ収集
    scraper = OddsScraper(headless=headless)
    success_count = 0
    error_count = 0

    for race_id, venue_code, race_number in races:
        try:
            odds_data = scraper.get_trifecta_odds(venue_code, today, race_number)

            if odds_data:
                # DB保存
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                for combo, odds in odds_data.items():
                    pit1, pit2, pit3 = combo.split('-')

                    cursor.execute("""
                        INSERT OR REPLACE INTO trifecta_odds
                        (race_id, pit1, pit2, pit3, odds, combination, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        race_id,
                        int(pit1),
                        int(pit2),
                        int(pit3),
                        odds,
                        combo,
                        datetime.now().isoformat()
                    ))

                conn.commit()
                conn.close()

                success_count += 1
                print(f"  [{venue_code:02d}場 {race_number:2d}R] OK - {len(odds_data)}通り")

            else:
                print(f"  [{venue_code:02d}場 {race_number:2d}R] データなし")

        except Exception as e:
            error_count += 1
            print(f"  [{venue_code:02d}場 {race_number:2d}R] エラー: {e}")

        # レート制限対策
        time.sleep(0.5)

    scraper.close()

    print(f"\n収集完了: {success_count}/{len(races)}レース（エラー: {error_count}）")

    return success_count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='本日のオッズ自動収集')
    parser.add_argument('--show-browser', action='store_true', help='ブラウザを表示')
    args = parser.parse_args()

    fetch_todays_odds(headless=not args.show_browser)
