"""
開催中止と推定されているレースの実際の状態を確認

'cancelled'とマークされているレースをサンプリングして、
実際にWebサイトをチェックし、正しいステータスを判定する
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.scraper.result_scraper import ResultScraper
import time

db_path = 'C:/Users/seizo/Desktop/BoatRace/data/boatrace.db'

def check_cancelled_races(sample_size=20):
    """
    cancelledとマークされているレースをサンプリングしてチェック

    Args:
        sample_size: チェックするレース数
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # cancelledレースをサンプリング
    cursor.execute('''
        SELECT id, venue_code, race_date, race_number
        FROM races
        WHERE race_status = 'cancelled'
        ORDER BY race_date DESC
        LIMIT ?
    ''', (sample_size,))

    races = cursor.fetchall()
    conn.close()

    print(f"チェック対象レース: {len(races)}件\n")

    scraper = ResultScraper()
    status_counts = {}

    for race_id, venue_code, race_date, race_number in races:
        print(f"チェック中: race_id={race_id}, {venue_code} {race_date} {race_number}R")

        # 日付をYYYYMMDD形式に変換
        race_date_str = race_date.replace('-', '')

        try:
            # レース結果を取得
            result = scraper.get_race_result(venue_code, race_date_str, race_number)

            if result:
                race_status = result.get('race_status', 'unknown')
                num_results = len(result.get('results', []))

                print(f"  ステータス: {race_status}, 結果数: {num_results}")

                # 統計をカウント
                status_counts[race_status] = status_counts.get(race_status, 0) + 1
            else:
                print(f"  データ取得失敗（おそらく本当に中止）")
                status_counts['fetch_failed'] = status_counts.get('fetch_failed', 0) + 1

            time.sleep(1)  # レート制限

        except Exception as e:
            print(f"  エラー: {e}")
            status_counts['error'] = status_counts.get('error', 0) + 1

        print()

    # 統計を表示
    print("\n=== ステータス統計 ===")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}件")

    print(f"\n総チェック数: {len(races)}件")

if __name__ == '__main__':
    print("開催中止レースのステータス確認開始\n")
    print("=" * 60)
    check_cancelled_races(sample_size=20)
    print("=" * 60)
    print("\n確認完了")
