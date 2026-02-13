#!/usr/bin/env python3
"""
シンプルなデータ充足率チェック
"""

import sqlite3
from datetime import datetime

DB_PATH = "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032/data/boatrace.db"

def main():
    print("データ充足率調査開始...\n")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 各テーブルの総レコード数
    print("="*80)
    print("テーブル別レコード数")
    print("="*80)

    tables = ['races', 'entries', 'results', 'trifecta_odds', 'race_details', 'race_predictions']

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"{table:<20}: {count:>15,} レコード")

    # 年度別レース数
    print("\n" + "="*80)
    print("年度別レース数")
    print("="*80)

    cursor.execute("""
        SELECT strftime('%Y', race_date) as year, COUNT(*) as count
        FROM races
        WHERE race_date >= '2020-01-01' AND race_date <= '2025-12-31'
        GROUP BY year
        ORDER BY year
    """)

    for row in cursor.fetchall():
        year, count = row
        print(f"{year}: {count:,} レース")

    # 2021年9-12月のレース数
    print("\n" + "="*80)
    print("2021年9-12月のレース数")
    print("="*80)

    for month in ['09', '10', '11', '12']:
        cursor.execute(f"""
            SELECT COUNT(*) FROM races
            WHERE race_date >= '2021-{month}-01'
            AND race_date < '2021-{int(month)+1:02d}-01'
        """)
        count = cursor.fetchone()[0]
        print(f"2021-{month}: {count:,} レース")

    # 2023年月別レース数
    print("\n" + "="*80)
    print("2023年月別レース数")
    print("="*80)

    for month_num in range(1, 13):
        month = f"{month_num:02d}"
        if month_num < 12:
            next_month = f"2023-{month_num+1:02d}-01"
        else:
            next_month = "2024-01-01"

        cursor.execute(f"""
            SELECT COUNT(*) FROM races
            WHERE race_date >= '2023-{month}-01'
            AND race_date < '{next_month}'
        """)
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"2023-{month}: {count:,} レース")

    # 簡易充足率（サンプリング）
    print("\n" + "="*80)
    print("充足率（年度別サンプリング）")
    print("="*80)

    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        # その年のレース数
        cursor.execute(f"""
            SELECT COUNT(*) FROM races
            WHERE race_date >= '{year}-01-01' AND race_date < '{int(year)+1}-01-01'
        """)
        race_count = cursor.fetchone()[0]

        if race_count == 0:
            continue

        # entriesが存在するレース数（race_idベースで最初の1件だけ）
        cursor.execute(f"""
            SELECT COUNT(DISTINCT e.race_id) FROM races r
            JOIN entries e ON r.id = e.race_id
            WHERE r.race_date >= '{year}-01-01' AND r.race_date < '{int(year)+1}-01-01'
        """)
        entries_count = cursor.fetchone()[0]

        # resultsが存在するレース数
        cursor.execute(f"""
            SELECT COUNT(DISTINCT res.race_id) FROM races r
            JOIN results res ON r.id = res.race_id
            WHERE r.race_date >= '{year}-01-01' AND r.race_date < '{int(year)+1}-01-01'
        """)
        results_count = cursor.fetchone()[0]

        # trifecta_oddsが存在するレース数
        cursor.execute(f"""
            SELECT COUNT(DISTINCT t.race_id) FROM races r
            JOIN trifecta_odds t ON r.id = t.race_id
            WHERE r.race_date >= '{year}-01-01' AND r.race_date < '{int(year)+1}-01-01'
        """)
        odds_count = cursor.fetchone()[0]

        # race_detailsが存在するレース数
        cursor.execute(f"""
            SELECT COUNT(DISTINCT rd.race_id) FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= '{year}-01-01' AND r.race_date < '{int(year)+1}-01-01'
        """)
        details_count = cursor.fetchone()[0]

        # race_predictionsが存在するレース数
        cursor.execute(f"""
            SELECT COUNT(DISTINCT rp.race_id) FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date >= '{year}-01-01' AND r.race_date < '{int(year)+1}-01-01'
        """)
        preds_count = cursor.fetchone()[0]

        print(f"\n{year}年:")
        print(f"  レース数: {race_count:,}")
        print(f"  出走表: {entries_count:,} ({entries_count/race_count*100:.1f}%)")
        print(f"  結果: {results_count:,} ({results_count/race_count*100:.1f}%)")
        print(f"  オッズ: {odds_count:,} ({odds_count/race_count*100:.1f}%)")
        print(f"  詳細: {details_count:,} ({details_count/race_count*100:.1f}%)")
        print(f"  予測: {preds_count:,} ({preds_count/race_count*100:.1f}%)")

    conn.close()

    print("\n" + "="*80)
    print("調査完了")
    print("="*80)

if __name__ == "__main__":
    main()
