"""
データ品質の詳細分析スクリプト
取得成功しているデータ項目と欠損パターンを調査
"""

import sqlite3

def analyze_data_quality():
    """データ品質を詳細分析"""
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    print("="*100)
    print("Data Quality Analysis (2015-2021)")
    print("="*100)

    # 1. race_detailsテーブルの全カラムのデータ充足率
    print("\n[1] race_details table - Data Availability (2015-2021)")
    print("-"*100)

    cursor.execute("""
        SELECT COUNT(*) as total
        FROM race_details rd
        INNER JOIN races r ON rd.race_id = r.id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
    """)
    total_records = cursor.fetchone()[0]
    print(f"\nTotal race_details records: {total_records:,}")
    print(f"(Should be 6 records per race)")

    # 各カラムの充足率
    columns = ['exhibition_time', 'tilt_angle', 'parts_replacement', 'actual_course', 'st_time',
               'chikusen_time', 'isshu_time', 'mawariashi_time']

    print(f"\nColumn                    Records with data    Percentage")
    print("-"*70)

    for col in columns:
        cursor.execute(f"""
            SELECT COUNT(CASE WHEN rd.{col} IS NOT NULL THEN 1 END) as has_data
            FROM race_details rd
            INNER JOIN races r ON rd.race_id = r.id
            WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
        """)
        count = cursor.fetchone()[0]
        percentage = (count / total_records * 100) if total_records > 0 else 0
        status = "OK" if percentage > 95 else "WARN" if percentage > 50 else "NG"
        print(f"{col:25} {count:15,}    {percentage:6.1f}%  {status}")

    # 2. レース単位での完全性チェック（6艇すべてのデータが揃っているか）
    print(f"\n\n[2] Race Completeness - Races with complete data for all 6 boats")
    print("-"*100)

    # 各データ項目について、6艇すべてのデータが揃っているレース数
    completeness_checks = {
        'exhibition_time': 'Exhibition Time',
        'st_time': 'ST Time',
        'actual_course': 'Actual Course',
        'tilt_angle': 'Tilt Angle'
    }

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
    """)
    total_races = cursor.fetchone()[0]

    print(f"\nTotal races: {total_races:,}")
    print(f"\nData Field                Complete Races    Percentage    Missing Races")
    print("-"*80)

    for field, label in completeness_checks.items():
        cursor.execute(f"""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
              AND (
                SELECT COUNT(*)
                FROM race_details rd
                WHERE rd.race_id = r.id
                  AND rd.{field} IS NOT NULL
              ) = 6
        """)
        complete_races = cursor.fetchone()[0]
        percentage = (complete_races / total_races * 100) if total_races > 0 else 0
        missing = total_races - complete_races
        status = "OK" if percentage > 95 else "WARN" if percentage > 50 else "NG"
        print(f"{label:25} {complete_races:13,}    {percentage:6.1f}%    {missing:13,}  {status}")

    # 3. 年度別の詳細分析
    print(f"\n\n[3] Year-by-Year Analysis - ST Time Completeness")
    print("-"*100)
    print(f"\nYear    Total Races    Complete ST (6 boats)    Percentage    Missing")
    print("-"*75)

    for year in range(2015, 2022):
        cursor.execute(f"""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            WHERE r.race_date BETWEEN '{year}-01-01' AND '{year}-12-31'
        """)
        year_total = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            WHERE r.race_date BETWEEN '{year}-01-01' AND '{year}-12-31'
              AND (
                SELECT COUNT(*)
                FROM race_details rd
                WHERE rd.race_id = r.id
                  AND rd.st_time IS NOT NULL
              ) = 6
        """)
        year_complete = cursor.fetchone()[0]

        percentage = (year_complete / year_total * 100) if year_total > 0 else 0
        missing = year_total - year_complete
        print(f"{year}    {year_total:11,}    {year_complete:20,}    {percentage:6.1f}%    {missing:7,}")

    # 4. STタイムの部分的な欠損パターンを調査
    print(f"\n\n[4] ST Time Missing Pattern - Boats per race")
    print("-"*100)
    print(f"\nBoats with ST    Race Count    Percentage")
    print("-"*50)

    for boat_count in range(0, 7):
        cursor.execute(f"""
            SELECT COUNT(DISTINCT r.id)
            FROM races r
            WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
              AND (
                SELECT COUNT(*)
                FROM race_details rd
                WHERE rd.race_id = r.id
                  AND rd.st_time IS NOT NULL
              ) = {boat_count}
        """)
        race_count = cursor.fetchone()[0]
        percentage = (race_count / total_races * 100) if total_races > 0 else 0
        print(f"{boat_count}/6 boats      {race_count:10,}    {percentage:6.2f}%")

    # 5. resultsテーブルの充足率
    print(f"\n\n[5] results table - Data Availability")
    print("-"*100)

    cursor.execute("""
        SELECT COUNT(DISTINCT r.id) as total,
               COUNT(DISTINCT res.race_id) as with_results
        FROM races r
        LEFT JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
    """)
    result = cursor.fetchone()
    total_races_check = result[0]
    with_results = result[1]
    missing_results = total_races_check - with_results

    print(f"\nTotal races: {total_races_check:,}")
    print(f"With results: {with_results:,} ({with_results/total_races_check*100:.1f}%)")
    print(f"Missing results: {missing_results:,} ({missing_results/total_races_check*100:.1f}%)")

    # resultsテーブルのカラム充足率
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN rank IS NOT NULL THEN 1 END) as has_rank,
            COUNT(CASE WHEN kimarite IS NOT NULL THEN 1 END) as has_kimarite
        FROM results res
        INNER JOIN races r ON res.race_id = r.id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
    """)
    res_stats = cursor.fetchone()
    if res_stats[0] > 0:
        print(f"\nresults records: {res_stats[0]:,}")
        print(f"  With rank: {res_stats[1]:,} ({res_stats[1]/res_stats[0]*100:.1f}%)")
        print(f"  With kimarite: {res_stats[2]:,} ({res_stats[2]/res_stats[0]*100:.1f}%)")

    # 6. スクレイパーテスト用のサンプルレース情報
    print(f"\n\n[6] Sample Races for Testing")
    print("-"*100)

    # STタイムが完全に欠損しているレース
    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number, r.id
        FROM races r
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (
            SELECT COUNT(*)
            FROM race_details rd
            WHERE rd.race_id = r.id
              AND rd.st_time IS NOT NULL
          ) = 0
        LIMIT 5
    """)

    print("\nRaces with NO ST time (0/6 boats):")
    no_st_races = cursor.fetchall()
    for row in no_st_races:
        venue, date, race_num, race_id = row
        date_str = date.replace('-', '')
        print(f"  Venue: {venue}, Date: {date} ({date_str}), Race: {race_num}, ID: {race_id}")

    # STタイムが部分的に欠損しているレース
    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number, r.id,
               (SELECT COUNT(*) FROM race_details rd WHERE rd.race_id = r.id AND rd.st_time IS NOT NULL) as st_count
        FROM races r
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (
            SELECT COUNT(*)
            FROM race_details rd
            WHERE rd.race_id = r.id
              AND rd.st_time IS NOT NULL
          ) BETWEEN 1 AND 5
        LIMIT 5
    """)

    print("\nRaces with PARTIAL ST time (1-5/6 boats):")
    partial_st_races = cursor.fetchall()
    for row in partial_st_races:
        venue, date, race_num, race_id, st_count = row
        date_str = date.replace('-', '')
        print(f"  Venue: {venue}, Date: {date} ({date_str}), Race: {race_num}, ST: {st_count}/6, ID: {race_id}")

    conn.close()

    print("\n" + "="*100)
    print("Analysis Complete")
    print("="*100)


if __name__ == '__main__':
    analyze_data_quality()
