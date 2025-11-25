"""
並列データ収集の監視スクリプト
定期的に進捗を確認し、エラーがあれば報告
"""

import time
import sqlite3
from datetime import datetime

def check_progress():
    """データベースから進捗を確認"""
    try:
        conn = sqlite3.connect('data/boatrace.db')
        cursor = conn.cursor()

        # 収集済みレース数
        cursor.execute("SELECT COUNT(*) FROM races")
        total_races = cursor.fetchone()[0]

        # 結果あり件数
        cursor.execute("SELECT COUNT(DISTINCT race_id) FROM results")
        races_with_results = cursor.fetchone()[0]

        # 最新のレース日付
        cursor.execute("SELECT MAX(race_date) FROM races")
        latest_date = cursor.fetchone()[0]

        conn.close()

        return {
            'total_races': total_races,
            'races_with_results': races_with_results,
            'latest_date': latest_date
        }
    except Exception as e:
        return {'error': str(e)}

def main():
    """監視メインループ"""
    print("=" * 80)
    print("並列データ収集 監視")
    print("=" * 80)
    print()

    start_time = time.time()
    last_races = 0

    while True:
        progress = check_progress()

        if 'error' in progress:
            print(f"エラー: {progress['error']}")
        else:
            current_races = progress['total_races']
            elapsed = time.time() - start_time

            if last_races > 0:
                races_per_sec = (current_races - last_races) / 60  # 1分あたり

                print(f"[{datetime.now().strftime('%H:%M:%S')}]")
                print(f"  総レース数: {current_races:,}")
                print(f"  結果あり: {progress['races_with_results']:,}")
                print(f"  最新日付: {progress['latest_date']}")
                print(f"  速度: {races_per_sec:.2f} レース/分")
                print(f"  経過時間: {elapsed/3600:.2f} 時間")
                print()

            last_races = current_races

        # 1分待機
        time.sleep(60)

if __name__ == "__main__":
    main()
