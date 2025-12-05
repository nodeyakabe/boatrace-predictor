"""
データ収集状況の確認スクリプト - 正確版
2015年~2021年のデータ収集状況を正確に確認
race_detailsは各レースにつき6艇(pit_number 1-6)のデータが入る
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
                COUNT(DISTINCT res.race_id) as races_with_results
            FROM races r
            LEFT JOIN results res ON r.id = res.race_id
            WHERE r.race_date BETWEEN ? AND ?
        """, (start_date, end_date))

        stats = cursor.fetchone()
        total_races = stats[0]
        races_with_results = stats[1]

        # 展示タイム、ST、進入コースが完全に揃っているレース数をチェック
        # 各レースは6艇分のデータが必要
        cursor.execute("""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            WHERE r.race_date BETWEEN ? AND ?
              AND (
                SELECT COUNT(*)
                FROM race_details rd
                WHERE rd.race_id = r.id
                  AND rd.exhibition_time IS NOT NULL
              ) = 6
        """, (start_date, end_date))
        has_full_exhibition = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            WHERE r.race_date BETWEEN ? AND ?
              AND (
                SELECT COUNT(*)
                FROM race_details rd
                WHERE rd.race_id = r.id
                  AND rd.st_time IS NOT NULL
              ) = 6
        """, (start_date, end_date))
        has_full_st = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            WHERE r.race_date BETWEEN ? AND ?
              AND (
                SELECT COUNT(*)
                FROM race_details rd
                WHERE rd.race_id = r.id
                  AND rd.actual_course IS NOT NULL
              ) = 6
        """, (start_date, end_date))
        has_full_course = cursor.fetchone()[0]

        print(f"\nOverall Statistics:")
        print(f"  Total Races: {total_races:,}")
        if total_races > 0:
            print(f"  With Results: {races_with_results:,} ({races_with_results/total_races*100:.1f}%)")
            print(f"  Complete Exhibition Time (6 boats): {has_full_exhibition:,} ({has_full_exhibition/total_races*100:.1f}%)")
            print(f"  Complete ST Time (6 boats): {has_full_st:,} ({has_full_st/total_races*100:.1f}%)")
            print(f"  Complete Actual Course (6 boats): {has_full_course:,} ({has_full_course/total_races*100:.1f}%)")

            # 不足数を表示
            missing_results = total_races - races_with_results
            missing_exhibition = total_races - has_full_exhibition
            missing_st = total_races - has_full_st
            missing_course = total_races - has_full_course

            print(f"\n  Missing:")
            print(f"    Results: {missing_results:,}")
            print(f"    Exhibition Time: {missing_exhibition:,}")
            print(f"    ST Time: {missing_st:,}")
            print(f"    Actual Course: {missing_course:,}")
        else:
            print("  No data")

    # 欠損データの詳細分析
    print(f"\n{'='*100}")
    print("Missing Data Summary")
    print(f"{'='*100}")

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
        print(f"\n1. Races with missing RESULT data:")
        print(f"   Year        Missing Count")
        print(f"   " + "-" * 30)

        total_missing_results = 0
        for year, count in missing_results:
            print(f"   {year}        {count:,}")
            total_missing_results += count

        print(f"   " + "-" * 30)
        print(f"   Total:      {total_missing_results:,}")
    else:
        print("\n1. No missing result data!")

    # 展示タイムが不完全なレース
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as missing_count
        FROM races r
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (
            SELECT COUNT(*)
            FROM race_details rd
            WHERE rd.race_id = r.id
              AND rd.exhibition_time IS NOT NULL
          ) < 6
        GROUP BY year
        ORDER BY year
    """)

    missing_exhibition = cursor.fetchall()

    if missing_exhibition:
        print(f"\n2. Races with incomplete EXHIBITION TIME (less than 6 boats):")
        print(f"   Year        Missing Count")
        print(f"   " + "-" * 30)

        total_missing = 0
        for year, count in missing_exhibition:
            print(f"   {year}        {count:,}")
            total_missing += count

        print(f"   " + "-" * 30)
        print(f"   Total:      {total_missing:,}")
    else:
        print("\n2. All races have complete exhibition time!")

    # STタイムが不完全なレース
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as missing_count
        FROM races r
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (
            SELECT COUNT(*)
            FROM race_details rd
            WHERE rd.race_id = r.id
              AND rd.st_time IS NOT NULL
          ) < 6
        GROUP BY year
        ORDER BY year
    """)

    missing_st = cursor.fetchall()

    if missing_st:
        print(f"\n3. Races with incomplete ST TIME (less than 6 boats):")
        print(f"   Year        Missing Count")
        print(f"   " + "-" * 30)

        total_missing = 0
        for year, count in missing_st:
            print(f"   {year}        {count:,}")
            total_missing += count

        print(f"   " + "-" * 30)
        print(f"   Total:      {total_missing:,}")
    else:
        print("\n3. All races have complete ST time!")

    # 進入コースが不完全なレース
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as missing_count
        FROM races r
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (
            SELECT COUNT(*)
            FROM race_details rd
            WHERE rd.race_id = r.id
              AND rd.actual_course IS NOT NULL
          ) < 6
        GROUP BY year
        ORDER BY year
    """)

    missing_course = cursor.fetchall()

    if missing_course:
        print(f"\n4. Races with incomplete ACTUAL COURSE (less than 6 boats):")
        print(f"   Year        Missing Count")
        print(f"   " + "-" * 30)

        total_missing = 0
        for year, count in missing_course:
            print(f"   {year}        {count:,}")
            total_missing += count

        print(f"   " + "-" * 30)
        print(f"   Total:      {total_missing:,}")
    else:
        print("\n4. All races have complete actual course!")

    # 何らかのデータが不完全なレース
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as incomplete_count
        FROM races r
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (
            r.id NOT IN (SELECT race_id FROM results WHERE race_id IS NOT NULL)
            OR (SELECT COUNT(*) FROM race_details rd WHERE rd.race_id = r.id AND rd.exhibition_time IS NOT NULL) < 6
            OR (SELECT COUNT(*) FROM race_details rd WHERE rd.race_id = r.id AND rd.st_time IS NOT NULL) < 6
            OR (SELECT COUNT(*) FROM race_details rd WHERE rd.race_id = r.id AND rd.actual_course IS NOT NULL) < 6
          )
        GROUP BY year
        ORDER BY year
    """)

    incomplete_data = cursor.fetchall()

    if incomplete_data:
        print(f"\n{'='*100}")
        print("OVERALL SUMMARY: Races with ANY missing data")
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

        # 総レース数を計算
        total_all_races = sum(year_totals.values())
        overall_percentage = (total_incomplete / total_all_races * 100) if total_all_races > 0 else 0
        print(f"\nOverall: {total_incomplete:,} incomplete races out of {total_all_races:,} total ({overall_percentage:.1f}%)")

        print(f"\n{'='*100}")
        print("RECOMMENDATION:")
        print(f"{'='*100}")
        print(f"To fill the missing data, run:")
        print(f"  python fetch_parallel_v6.py --fill-missing --workers 10")
        print(f"\nThis will fetch approximately {total_incomplete:,} races.")
        estimated_time = total_incomplete * 2 / 10 / 60  # 1レース2秒、10並列
        print(f"Estimated time: {estimated_time:.0f} minutes")
    else:
        print("\n{'='*100}")
        print("All data is complete!")
        print(f"{'='*100}")

    conn.close()

    print("\n" + "="*100)
    print("Report Complete")
    print("="*100)


if __name__ == '__main__':
    check_data_coverage()
