"""
データ収集状況の確認スクリプト - シンプル版
2015年~2021年のデータ収集状況を確認
"""

import sqlite3
from collections import defaultdict

def check_data_coverage():
    """データ収集状況を確認"""
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    print("="*100)
    print("Data Collection Status Report (2015-2021)")
    print("="*100)

    # 年度別のデータ状況を確認
    for year in range(2015, 2022):
        print(f"\n{'='*100}")
        print(f"Year: {year}")
        print(f"{'='*100}")

        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        # 全体の統計
        cursor.execute("""
            SELECT COUNT(DISTINCT r.id) as total_races,
                   COUNT(DISTINCT rd.race_id) as races_with_details,
                   COUNT(DISTINCT res.race_id) as races_with_results,
                   COUNT(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 END) as has_exhibition_time,
                   COUNT(CASE WHEN rd.st_time IS NOT NULL THEN 1 END) as has_st_time,
                   COUNT(CASE WHEN rd.actual_course IS NOT NULL THEN 1 END) as has_actual_course
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id
            WHERE r.race_date BETWEEN ? AND ?
        """, (start_date, end_date))

        stats = cursor.fetchone()
        total_races = stats[0]
        races_with_details = stats[1]
        races_with_results = stats[2]
        has_exhibition_time = stats[3]
        has_st_time = stats[4]
        has_actual_course = stats[5]

        print(f"\nOverall Statistics:")
        print(f"  Total Races: {total_races:,}")
        print(f"  With Details: {races_with_details:,} ({races_with_details/total_races*100:.1f}%)" if total_races > 0 else "  With Details: 0")
        print(f"  With Results: {races_with_results:,} ({races_with_results/total_races*100:.1f}%)" if total_races > 0 else "  With Results: 0")
        print(f"  Has Exhibition Time: {has_exhibition_time:,} ({has_exhibition_time/total_races*100:.1f}%)" if total_races > 0 else "  Has Exhibition Time: 0")
        print(f"  Has ST Time: {has_st_time:,} ({has_st_time/total_races*100:.1f}%)" if total_races > 0 else "  Has ST Time: 0")
        print(f"  Has Actual Course: {has_actual_course:,} ({has_actual_course/total_races*100:.1f}%)" if total_races > 0 else "  Has Actual Course: 0")

    # 欠損データの詳細分析
    print(f"\n{'='*100}")
    print("Missing Data Analysis (All Periods)")
    print(f"{'='*100}")

    # race_detailsが不足しているレースを抽出
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(*) as missing_count
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (rd.race_id IS NULL
               OR rd.exhibition_time IS NULL
               OR rd.st_time IS NULL
               OR rd.actual_course IS NULL)
        GROUP BY year
        ORDER BY year
    """)

    missing_data = cursor.fetchall()

    if missing_data:
        print(f"\nRaces with missing detail data:")
        print(f"Year        Missing Count")
        print("-" * 30)

        total_missing = 0
        for year, count in missing_data:
            print(f"{year}        {count:,}")
            total_missing += count

        print("-" * 30)
        print(f"Total:      {total_missing:,}")
    else:
        print("\nNo missing data!")

    # 結果データが不足しているレースを抽出
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(*) as missing_count
        FROM races r
        LEFT JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND res.race_id IS NULL
        GROUP BY year
        ORDER BY year
    """)

    missing_results = cursor.fetchall()

    if missing_results:
        print(f"\nRaces with missing result data:")
        print(f"Year        Missing Count")
        print("-" * 30)

        total_missing_results = 0
        for year, count in missing_results:
            print(f"{year}        {count:,}")
            total_missing_results += count

        print("-" * 30)
        print(f"Total:      {total_missing_results:,}")
    else:
        print("\nNo missing result data!")

    # 最も重要な情報: 完全なデータがないレース数
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(*) as incomplete_count
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (rd.race_id IS NULL
               OR rd.exhibition_time IS NULL
               OR rd.st_time IS NULL
               OR rd.actual_course IS NULL
               OR res.race_id IS NULL)
        GROUP BY year
        ORDER BY year
    """)

    incomplete_data = cursor.fetchall()

    if incomplete_data:
        print(f"\n{'='*100}")
        print("SUMMARY: Incomplete Races (missing details OR results)")
        print(f"{'='*100}")
        print(f"Year        Incomplete Count")
        print("-" * 30)

        total_incomplete = 0
        for year, count in incomplete_data:
            print(f"{year}        {count:,}")
            total_incomplete += count

        print("-" * 30)
        print(f"Total:      {total_incomplete:,}")
        print(f"\nRecommendation: Run fetch_parallel_v6.py with --fill-missing flag")
    else:
        print("\nAll data is complete!")

    conn.close()

    print("\n" + "="*100)
    print("Report Complete")
    print("="*100)


if __name__ == '__main__':
    check_data_coverage()
