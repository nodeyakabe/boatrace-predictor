"""
リアルタイムでデータ収集を監視するスクリプト
10秒ごとに更新状況を表示
"""

import sqlite3
import time
from datetime import datetime

def monitor_collection():
    """データ収集をリアルタイム監視"""

    db_path = 'data/boatrace.db'

    print("="*80)
    print("Real-time Data Collection Monitor")
    print("="*80)
    print("Press Ctrl+C to stop monitoring\n")

    last_count = 0
    last_st_count = 0

    try:
        while True:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 総レコード数
            cursor.execute("SELECT COUNT(*) FROM race_details")
            total_count = cursor.fetchone()[0]

            # STタイム総数
            cursor.execute("SELECT COUNT(*) FROM race_details WHERE st_time IS NOT NULL")
            st_count = cursor.fetchone()[0]

            # 最新レコード
            cursor.execute("""
                SELECT r.venue_code, r.race_date, r.race_number, rd.created_at
                FROM race_details rd
                INNER JOIN races r ON rd.race_id = r.id
                ORDER BY rd.created_at DESC
                LIMIT 1
            """)
            latest = cursor.fetchone()

            # フライング・出遅れ
            cursor.execute("SELECT COUNT(*) FROM race_details WHERE st_time = -0.01")
            flying = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM race_details WHERE st_time = -0.02")
            late = cursor.fetchone()[0]

            # 増加数
            new_records = total_count - last_count
            new_st = st_count - last_st_count

            now = datetime.now().strftime('%H:%M:%S')

            print(f"[{now}] Total: {total_count:,} (+{new_records}) | ST: {st_count:,} (+{new_st}) | F: {flying} | L: {late}", end="")

            if latest:
                venue, date, race, created = latest
                print(f" | Latest: {venue} {date} {race}R ({created})")
            else:
                print()

            last_count = total_count
            last_st_count = st_count

            conn.close()

            time.sleep(10)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")


if __name__ == '__main__':
    monitor_collection()
