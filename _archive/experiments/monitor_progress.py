"""
V3収集の進捗をリアルタイム監視
"""

import sqlite3
from datetime import datetime, timedelta

def monitor_progress():
    """進捗を監視"""

    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 全体の欠損数
    query_total = """
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
          AND (rd.race_id IS NULL
               OR rd.exhibition_time IS NULL
               OR rd.st_time IS NULL
               OR rd.actual_course IS NULL)
    """

    cursor.execute(query_total)
    total_missing = cursor.fetchone()[0]

    # 最近10分間の更新
    ten_min_ago = (datetime.now() - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')

    query_recent = """
        SELECT COUNT(*)
        FROM race_details
        WHERE updated_at >= ?
    """

    cursor.execute(query_recent, (ten_min_ago,))
    recent_updates = cursor.fetchone()[0]

    # 6/6 STタイムのレース数（2015-2021）
    query_perfect = """
        WITH race_st_count AS (
            SELECT
                r.id,
                SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as st_count
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
            GROUP BY r.id
        )
        SELECT COUNT(*)
        FROM race_st_count
        WHERE st_count = 6
    """

    cursor.execute(query_perfect)
    perfect_st = cursor.fetchone()[0]

    # 5/6 STタイムのレース数
    query_5_6 = """
        WITH race_st_count AS (
            SELECT
                r.id,
                SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as st_count
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
            GROUP BY r.id
        )
        SELECT COUNT(*)
        FROM race_st_count
        WHERE st_count = 5
    """

    cursor.execute(query_5_6)
    st_5_6 = cursor.fetchone()[0]

    print("="*80)
    print(f"V3 Collection Progress Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print(f"\nMissing data (2015-2021):        {total_missing:,} races")
    print(f"Recent updates (last 10 min):    {recent_updates:,} records")
    print(f"\n6/6 ST time races:               {perfect_st:,}")
    print(f"5/6 ST time races:               {st_5_6:,}")

    if recent_updates > 0:
        print(f"\n[STATUS] Collection is ACTIVE")
        rate = recent_updates / 10  # records per minute
        print(f"Update rate: ~{rate:.1f} records/min")
    else:
        print(f"\n[STATUS] No recent updates")

    conn.close()

if __name__ == '__main__':
    monitor_progress()
