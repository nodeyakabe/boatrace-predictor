"""
データ収集状況の確認スクリプト - 最終版
2015年~2021年のデータ収集状況を正確に確認
"""

import sqlite3

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
            SELECT
                COUNT(DISTINCT r.id) as total_races,
                COUNT(DISTINCT CASE WHEN rd.race_id IS NOT NULL THEN r.id END) as races_with_details,
                COUNT(DISTINCT CASE WHEN res.race_id IS NOT NULL THEN r.id END) as races_with_results,
                COUNT(DISTINCT CASE WHEN rd.exhibition_time IS NOT NULL THEN r.id END) as has_exhibition,
                COUNT(DISTINCT CASE WHEN rd.st_time IS NOT NULL THEN r.id END) as has_st,
                COUNT(DISTINCT CASE WHEN rd.actual_course IS NOT NULL THEN r.id END) as has_course
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id
            WHERE r.race_date BETWEEN ? AND ?
        """, (start_date, end_date))

        stats = cursor.fetchone()
        total_races = stats[0]
        races_with_details = stats[1]
        races_with_results = stats[2]
        has_exhibition = stats[3]
        has_st = stats[4]
        has_course = stats[5]

        print(f"\nOverall Statistics:")
        print(f"  Total Races: {total_races:,}")
        if total_races > 0:
            print(f"  With Details: {races_with_details:,} ({races_with_details/total_races*100:.1f}%)")
            print(f"  With Results: {races_with_results:,} ({races_with_results/total_races*100:.1f}%)")
            print(f"  Has Exhibition Time: {has_exhibition:,} ({has_exhibition/total_races*100:.1f}%)")
            print(f"  Has ST Time: {has_st:,} ({has_st/total_races*100:.1f}%)")
            print(f"  Has Actual Course: {has_course:,} ({has_course/total_races*100:.1f}%)")
        else:
            print("  No data")

    # 欠損データの詳細分析
    print(f"\n{'='*100}")
    print("Missing Data Analysis (All Periods)")
    print(f"{'='*100}")

    # race_detailsが不足しているレースを抽出
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as missing_count
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
        print("\nNo missing detail data!")

    # 結果データが不足しているレースを抽出
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as missing_count
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
            COUNT(DISTINCT r.id) as incomplete_count
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
        print(f"Year        Incomplete Count    % of Year")
        print("-" * 50)

        # 各年のtotal racesを取得
        year_totals = {}
        for year in range(2015, 2022):
            cursor.execute("""
                SELECT COUNT(DISTINCT r.id)
                FROM races r
                WHERE r.race_date BETWEEN ? AND ?
            """, (f"{year}-01-01", f"{year}-12-31"))
            year_totals[str(year)] = cursor.fetchone()[0]

        total_incomplete = 0
        for year, count in incomplete_data:
            total_races_year = year_totals.get(year, 1)
            percentage = (count / total_races_year * 100) if total_races_year > 0 else 0
            print(f"{year}        {count:,}                {percentage:.1f}%")
            total_incomplete += count

        print("-" * 50)
        print(f"Total:      {total_incomplete:,}")
        print(f"\nRecommendation: Run the following command to fill missing data:")
        print(f"  python fetch_parallel_v6.py --fill-missing --workers 10")
    else:
        print("\nAll data is complete!")

    # データ完全性の詳細確認
    print(f"\n{'='*100}")
    print("Data Completeness Details")
    print(f"{'='*100}")

    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT CASE WHEN res.race_id IS NOT NULL THEN r.id END) as with_results,
            COUNT(DISTINCT CASE WHEN rd.exhibition_time IS NOT NULL THEN r.id END) as with_exhibition,
            COUNT(DISTINCT CASE WHEN rd.st_time IS NOT NULL THEN r.id END) as with_st,
            COUNT(DISTINCT CASE WHEN rd.actual_course IS NOT NULL THEN r.id END) as with_course
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
        GROUP BY year
        ORDER BY year
    """)

    print(f"\nYear    Total    Results    Exhibition    ST Time    Course")
    print("-" * 65)
    for row in cursor.fetchall():
        year, total, results, exh, st, course = row
        print(f"{year}    {total:5,}    {results:5,} ({results/total*100:4.1f}%)    "
              f"{exh:5,} ({exh/total*100:4.1f}%)    "
              f"{st:5,} ({st/total*100:4.1f}%)    "
              f"{course:5,} ({course/total*100:4.1f}%)")

    conn.close()

    print("\n" + "="*100)
    print("Report Complete")
    print("="*100)


if __name__ == '__main__':
    check_data_coverage()
