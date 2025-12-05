"""
データ収集の稼働状況確認スクリプト
"""

import sqlite3
import os
from datetime import datetime, timedelta

def check_collection_status():
    """データ収集の稼働状況を確認"""

    db_path = 'data/boatrace.db'

    if not os.path.exists(db_path):
        print("Database not found!")
        return

    # DBの最終更新時刻
    mod_time = os.path.getmtime(db_path)
    last_modified = datetime.fromtimestamp(mod_time)
    now = datetime.now()
    time_diff = now - last_modified

    print("="*80)
    print("Data Collection Status Check")
    print("="*80)
    print(f"\nCurrent time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Database last modified: {last_modified.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Time since last update: {time_diff}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 最近1時間のデータ追加状況
    print("\n" + "="*80)
    print("Activity in Last Hour")
    print("="*80)

    cursor.execute("""
        SELECT COUNT(*), MAX(created_at)
        FROM race_details
        WHERE created_at > datetime('now', '-1 hour')
    """)
    count, latest = cursor.fetchone()
    print(f"\nrace_details records created: {count}")
    if latest:
        print(f"Latest record: {latest}")

    cursor.execute("""
        SELECT COUNT(*)
        FROM race_details
        WHERE st_time IS NOT NULL
          AND created_at > datetime('now', '-1 hour')
    """)
    st_count = cursor.fetchone()[0]
    print(f"ST times collected: {st_count}")

    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE created_at > datetime('now', '-1 hour')
    """)
    race_count = cursor.fetchone()[0]
    print(f"Races created: {race_count}")

    cursor.execute("""
        SELECT COUNT(*)
        FROM results
        WHERE created_at > datetime('now', '-1 hour')
    """)
    result_count = cursor.fetchone()[0]
    print(f"Results created: {result_count}")

    # 今日のデータ追加状況
    print("\n" + "="*80)
    print("Activity Today")
    print("="*80)

    cursor.execute("""
        SELECT COUNT(*)
        FROM race_details
        WHERE DATE(created_at) = DATE('now')
    """)
    today_details = cursor.fetchone()[0]
    print(f"\nrace_details records: {today_details:,}")

    cursor.execute("""
        SELECT COUNT(*)
        FROM race_details
        WHERE st_time IS NOT NULL
          AND DATE(created_at) = DATE('now')
    """)
    today_st = cursor.fetchone()[0]
    print(f"ST times collected: {today_st:,}")

    # 最新10件のレコード
    print("\n" + "="*80)
    print("Latest 10 Records")
    print("="*80)

    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number, rd.pit_number, rd.st_time, rd.created_at
        FROM race_details rd
        INNER JOIN races r ON rd.race_id = r.id
        ORDER BY rd.created_at DESC
        LIMIT 10
    """)

    print(f"\n{'Venue':<6} {'Date':<12} {'Race':<6} {'Pit':<4} {'ST Time':<8} {'Created At':<20}")
    print("-"*80)
    for row in cursor.fetchall():
        venue, date, race, pit, st, created = row
        st_str = f"{st:.2f}" if st else "None"
        print(f"{venue:<6} {date:<12} {race:<6} {pit:<4} {st_str:<8} {created:<20}")

    # フライング・出遅れの検出状況
    print("\n" + "="*80)
    print("Flying/Late Detection (if using improved scraper)")
    print("="*80)

    cursor.execute("""
        SELECT COUNT(*)
        FROM race_details
        WHERE st_time = -0.01
    """)
    flying_count = cursor.fetchone()[0]
    print(f"\nFlying (F) detected: {flying_count:,}")

    cursor.execute("""
        SELECT COUNT(*)
        FROM race_details
        WHERE st_time = -0.02
    """)
    late_count = cursor.fetchone()[0]
    print(f"Late (L) detected: {late_count:,}")

    if flying_count > 0 or late_count > 0:
        print("\n[OK] Improved scraper is working! F/L detection active.")
    else:
        print("\n[INFO] No F/L detected yet. May be using standard scraper.")

    # 全体の統計
    print("\n" + "="*80)
    print("Overall Statistics (2015-2021)")
    print("="*80)

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
    """)
    total_races = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        INNER JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (
            SELECT COUNT(*)
            FROM race_details rd2
            WHERE rd2.race_id = r.id
              AND rd2.st_time IS NOT NULL
          ) = 6
    """)
    complete_st = cursor.fetchone()[0]

    print(f"\nTotal races: {total_races:,}")
    print(f"Races with complete ST (6/6): {complete_st:,} ({complete_st/total_races*100:.2f}%)")
    print(f"Races still incomplete: {total_races - complete_st:,}")

    # 収集の進捗状況
    if time_diff.total_seconds() < 300:  # 5分以内
        print("\n[STATUS] Data collection appears to be ACTIVE")
    elif time_diff.total_seconds() < 3600:  # 1時間以内
        print(f"\n[STATUS] Data collection may be PAUSED (last update {int(time_diff.total_seconds()/60)} min ago)")
    else:
        print(f"\n[STATUS] Data collection appears to be STOPPED (last update {int(time_diff.total_seconds()/3600)} hours ago)")

    conn.close()

    print("\n" + "="*80)
    print("Status Check Complete")
    print("="*80)


if __name__ == '__main__':
    check_collection_status()
