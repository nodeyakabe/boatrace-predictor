"""
データ収集状況の確認スクリプト
2015年~2021年のデータ収集状況を年度別、会場別に確認
"""

import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

def check_data_coverage():
    """データ収集状況を確認"""
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 会場コードと名前のマッピング
    cursor.execute("SELECT code, name FROM venues ORDER BY code")
    venues = {code: name for code, name in cursor.fetchall()}

    print("=" * 100)
    print("データ収集状況レポート (2015-2021)")
    print("=" * 100)

    # 年度別のデータ状況を確認
    for year in range(2015, 2022):
        print(f"\n{'='*100}")
        print(f"{year}年のデータ状況")
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

        print(f"\n【全体統計】")
        print(f"  総レース数: {total_races:,}")
        print(f"  詳細データあり: {races_with_details:,} ({races_with_details/total_races*100:.1f}%)" if total_races > 0 else "  詳細データあり: 0")
        print(f"  結果データあり: {races_with_results:,} ({races_with_results/total_races*100:.1f}%)" if total_races > 0 else "  結果データあり: 0")
        print(f"  展示タイムあり: {has_exhibition_time:,} ({has_exhibition_time/total_races*100:.1f}%)" if total_races > 0 else "  展示タイムあり: 0")
        print(f"  STタイムあり: {has_st_time:,} ({has_st_time/total_races*100:.1f}%)" if total_races > 0 else "  STタイムあり: 0")
        print(f"  進入コースあり: {has_actual_course:,} ({has_actual_course/total_races*100:.1f}%)" if total_races > 0 else "  進入コースあり: 0")

        # 会場別の統計
        print(f"\n【会場別詳細】")
        print(f"{'会場コード':<8} {'会場名':<15} {'レース数':<10} {'詳細データ':<12} {'結果データ':<12} {'展示タイム':<12} {'STタイム':<12} {'進入コース':<12}")
        print("-" * 100)

        cursor.execute("""
            SELECT r.venue_code,
                   COUNT(DISTINCT r.id) as total_races,
                   COUNT(DISTINCT rd.race_id) as races_with_details,
                   COUNT(DISTINCT res.race_id) as races_with_results,
                   COUNT(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 END) as has_exhibition_time,
                   COUNT(CASE WHEN rd.st_time IS NOT NULL THEN 1 END) as has_st_time,
                   COUNT(CASE WHEN rd.actual_course IS NOT NULL THEN 1 END) as has_actual_course
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            LEFT JOIN results res ON r.id = res.race_id
            WHERE r.race_date BETWEEN ? AND ?
            GROUP BY r.venue_code
            ORDER BY r.venue_code
        """, (start_date, end_date))

        for row in cursor.fetchall():
            venue_code = row[0]
            venue_name = venues.get(venue_code, "不明")
            total = row[1]
            details = row[2]
            results = row[3]
            exh_time = row[4]
            st = row[5]
            course = row[6]

            print(f"{venue_code:<8} {venue_name:<15} {total:<10,} "
                  f"{details:<6,}({details/total*100:>4.1f}%) "
                  f"{results:<6,}({results/total*100:>4.1f}%) "
                  f"{exh_time:<6,}({exh_time/total*100:>4.1f}%) "
                  f"{st:<6,}({st/total*100:>4.1f}%) "
                  f"{course:<6,}({course/total*100:>4.1f}%)")

    # 欠損データの詳細分析
    print(f"\n{'='*100}")
    print("欠損データ詳細分析 (全期間)")
    print(f"{'='*100}")

    # race_detailsが不足しているレースを抽出
    cursor.execute("""
        SELECT
            SUBSTR(r.race_date, 1, 4) as year,
            r.venue_code,
            COUNT(*) as missing_count
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date BETWEEN '2015-01-01' AND '2021-12-31'
          AND (rd.race_id IS NULL
               OR rd.exhibition_time IS NULL
               OR rd.st_time IS NULL
               OR rd.actual_course IS NULL)
        GROUP BY year, r.venue_code
        ORDER BY year, r.venue_code
    """)

    missing_data = cursor.fetchall()

    if missing_data:
        print(f"\n詳細データが不足しているレース:")
        print(f"{'年度':<8} {'会場コード':<10} {'会場名':<15} {'不足数':<10}")
        print("-" * 50)

        year_totals = defaultdict(int)
        for year, venue_code, count in missing_data:
            venue_name = venues.get(venue_code, "不明")
            print(f"{year:<8} {venue_code:<10} {venue_name:<15} {count:,}")
            year_totals[year] += count

        print("-" * 50)
        print(f"\n年度別不足数:")
        for year in sorted(year_totals.keys()):
            print(f"  {year}年: {year_totals[year]:,}件")

        total_missing = sum(year_totals.values())
        print(f"\n  合計: {total_missing:,}件")
    else:
        print("\n欠損データはありません!")

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
        print(f"\n結果データが不足しているレース:")
        print(f"{'年度':<8} {'不足数':<10}")
        print("-" * 20)

        for year, count in missing_results:
            print(f"{year:<8} {count:,}")

        total_missing_results = sum(count for _, count in missing_results)
        print(f"\n  合計: {total_missing_results:,}件")
    else:
        print("\n結果データの欠損はありません!")

    conn.close()

    print("\n" + "=" * 100)
    print("レポート終了")
    print("=" * 100)


if __name__ == '__main__':
    check_data_coverage()
