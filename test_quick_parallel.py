"""
並列オッズ取得の簡易テスト（最新の未取得3件のみ）
"""
import os
import sys
import sqlite3
from datetime import datetime
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.odds_scraper import OddsScraper
from concurrent.futures import ThreadPoolExecutor


def test_quick():
    """簡易テスト（3件のみ）"""
    print("=" * 80)
    print("並列オッズ取得 簡易テスト（最新3件）")
    print("=" * 80)
    print()

    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    # 未取得レースの最新3件を取得
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE NOT EXISTS (
            SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
        )
        ORDER BY r.race_date DESC, r.venue_code, r.race_number
        LIMIT 3
    """)
    races = cursor.fetchall()
    conn.close()

    if not races:
        print("[INFO] 未取得レースがありません")
        return True

    print(f"[INFO] テスト対象: {len(races)}件")
    for race_id, venue_code, race_date, race_number in races:
        print(f"  - {race_date} {venue_code.zfill(2)}R{race_number}")
    print()

    # 並列処理テスト
    start_time = time.time()
    success = 0
    errors = 0

    def fetch_race(race_info):
        race_id, venue_code, race_date, race_number = race_info
        scraper = OddsScraper(delay=0.3, max_retries=2)
        date_str = race_date.replace('-', '')

        try:
            odds = scraper.get_trifecta_odds(venue_code, date_str, race_number)
            if odds:
                print(f"[OK] {race_date} {venue_code.zfill(2)}R{race_number}: {len(odds)}通り取得")
                return True
            else:
                print(f"[NG] {race_date} {venue_code.zfill(2)}R{race_number}: 取得失敗")
                return False
        except Exception as e:
            print(f"[ERROR] {race_date} {venue_code.zfill(2)}R{race_number}: {e}")
            return False

    # 3スレッドで並列実行
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(fetch_race, races))

    success = sum(results)
    errors = len(results) - success
    elapsed = time.time() - start_time

    print()
    print("=" * 80)
    print("[結果]")
    print(f"  成功: {success}件")
    print(f"  失敗: {errors}件")
    print(f"  処理時間: {elapsed:.1f}秒")
    if success > 0:
        print(f"  速度: {success/elapsed:.2f}件/秒")
    print("=" * 80)

    return success > 0


if __name__ == '__main__':
    try:
        success = test_quick()
        if success:
            print()
            print("[OK] 並列処理が正常に動作しています")
            print()
            print("夜間実行の準備OK:")
            print("  1. run_odds_parallel_night.bat を実行")
            print("  2. または python fetch_odds_parallel.py を直接実行")
            print()
        else:
            print()
            print("[WARNING] テストで一部エラーが発生しました")
            print("  ネットワークの問題か、対象レースにオッズがない可能性があります")
            print()
    except Exception as e:
        print(f"[ERROR] テスト失敗: {e}")
        import traceback
        traceback.print_exc()
