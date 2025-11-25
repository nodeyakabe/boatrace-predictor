"""
データベース詳細分析スクリプト
現在のデータベースの状態を詳細に確認
"""

import sqlite3
from datetime import datetime

def check_database_status():
    """データベースの詳細状態を確認"""

    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("="*80)
    print("ボートレースデータベース 詳細分析レポート")
    print("="*80)
    print(f"分析日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"データベース: {db_path}")
    print("="*80)

    # 1. テーブル一覧
    print("\n【1. データベース構造】")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    print(f"テーブル数: {len(tables)}")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
        count = cursor.fetchone()[0]
        print(f"  - {table[0]:30s}: {count:8d} レコード")

    # 2. 期間別レース数
    print("\n【2. レースデータ期間】")
    cursor.execute("SELECT MIN(race_date), MAX(race_date), COUNT(*) FROM races")
    min_date, max_date, total_races = cursor.fetchone()
    print(f"  期間: {min_date} ～ {max_date}")
    print(f"  総レース数: {total_races:,} レース")

    # 3. 2015-2021年のデータ分析
    print("\n【3. 対象期間（2015-2021）の詳細分析】")

    # 3-1. 総レース数
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date >= '2015-01-01' AND race_date <= '2021-12-31'
    """)
    target_races = cursor.fetchone()[0]
    print(f"  総レース数: {target_races:,} レース")

    # 3-2. 完全なデータを持つレース数
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        INNER JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
        GROUP BY r.id
        HAVING COUNT(rd.pit_number) = 6
           AND SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) = 6
           AND SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) = 6
           AND SUM(CASE WHEN rd.actual_course IS NOT NULL THEN 1 ELSE 0 END) = 6
    """)
    complete_races = cursor.fetchone()
    complete_count = complete_races[0] if complete_races else 0
    print(f"  完全データ: {complete_count:,} レース ({complete_count/target_races*100:.1f}%)")

    # 3-3. 欠損データの詳細
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
          AND (rd.race_id IS NULL
               OR rd.exhibition_time IS NULL
               OR rd.st_time IS NULL
               OR rd.actual_course IS NULL)
    """)
    missing_count = cursor.fetchone()[0]
    print(f"  欠損データ: {missing_count:,} レース ({missing_count/target_races*100:.1f}%)")

    # 4. STタイム欠損パターン分析
    print("\n【4. STタイム欠損パターン分析（2015-2021）】")

    cursor.execute("""
        WITH race_st_status AS (
            SELECT
                r.id as race_id,
                SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as st_count
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
            GROUP BY r.id
        )
        SELECT st_count, COUNT(*) as race_count
        FROM race_st_status
        GROUP BY st_count
        ORDER BY st_count DESC
    """)

    st_patterns = cursor.fetchall()
    print(f"  STタイム完全性:")
    for st_count, race_count in st_patterns:
        pct = race_count / target_races * 100
        print(f"    {st_count}/6 STタイム: {race_count:6d} レース ({pct:5.1f}%)")

    # 5. Pit別STタイム欠損数（5/6のケース）
    print("\n【5. Pit別STタイム欠損パターン（5/6のケースのみ）】")

    cursor.execute("""
        WITH race_st_status AS (
            SELECT
                r.id as race_id,
                SUM(CASE WHEN rd.pit_number = 1 AND rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as pit1_has_st,
                SUM(CASE WHEN rd.pit_number = 2 AND rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as pit2_has_st,
                SUM(CASE WHEN rd.pit_number = 3 AND rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as pit3_has_st,
                SUM(CASE WHEN rd.pit_number = 4 AND rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as pit4_has_st,
                SUM(CASE WHEN rd.pit_number = 5 AND rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as pit5_has_st,
                SUM(CASE WHEN rd.pit_number = 6 AND rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as pit6_has_st,
                SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as total_st_count
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
            GROUP BY r.id
        )
        SELECT
            CASE
                WHEN pit1_has_st = 0 THEN 'Pit1'
                WHEN pit2_has_st = 0 THEN 'Pit2'
                WHEN pit3_has_st = 0 THEN 'Pit3'
                WHEN pit4_has_st = 0 THEN 'Pit4'
                WHEN pit5_has_st = 0 THEN 'Pit5'
                WHEN pit6_has_st = 0 THEN 'Pit6'
                ELSE 'Other'
            END as missing_pit,
            COUNT(*) as count
        FROM race_st_status
        WHERE total_st_count = 5
        GROUP BY missing_pit
        ORDER BY count DESC
    """)

    pit_patterns = cursor.fetchall()
    total_5_6 = sum(r[1] for r in pit_patterns)

    print(f"  5/6 STタイム総数: {total_5_6:,} レース")
    for pit, count in pit_patterns:
        pct = count / total_5_6 * 100 if total_5_6 > 0 else 0

        # Pit3は決まり手混入バグの可能性が高い
        note = " ← 決まり手混入バグの可能性" if pit == 'Pit3' else ""
        note = " ← F/L多数" if pit == 'Pit1' else note

        print(f"    {pit:8s}: {count:6d} レース ({pct:5.1f}%){note}")

    # 6. 会場別データ状況
    print("\n【6. 会場別データ状況（2015-2021）】")

    cursor.execute("""
        SELECT
            r.venue_code,
            COUNT(*) as total_races,
            SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as st_data_count
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
        GROUP BY r.venue_code
        ORDER BY r.venue_code
    """)

    venue_data = cursor.fetchall()
    print(f"  会場数: {len(venue_data)}")
    print(f"  {'会場':4s} {'総レース数':>10s} {'ST取得数':>10s} {'取得率':>8s}")
    print("  " + "-"*40)

    for venue_code, total, st_count in venue_data[:10]:  # 上位10会場のみ表示
        rate = st_count / (total * 6) * 100 if total > 0 else 0
        print(f"  {venue_code:4s} {total:10d} {st_count:10d} {rate:7.1f}%")

    if len(venue_data) > 10:
        print(f"  ... 他 {len(venue_data) - 10} 会場")

    # 7. 推定再収集時間
    print("\n【7. 再収集推定時間】")

    est_time_per_race = 15  # 秒/レース
    est_total_seconds = missing_count * est_time_per_race
    est_hours = est_total_seconds / 3600

    print(f"  欠損レース数: {missing_count:,}")
    print(f"  推定時間（1ワーカー）: {est_hours:.1f} 時間")

    for workers in [3, 5, 10]:
        parallel_hours = est_hours / workers
        print(f"  推定時間（{workers}ワーカー）: {parallel_hours:.1f} 時間")

    # 8. サンプルデータの確認
    print("\n【8. サンプルデータ確認】")

    cursor.execute("""
        SELECT r.venue_code, r.race_date, r.race_number, r.id
        FROM races r
        WHERE r.race_date >= '2015-01-01' AND r.race_date <= '2021-12-31'
        ORDER BY r.race_date DESC
        LIMIT 1
    """)

    sample_race = cursor.fetchone()
    if sample_race:
        venue, date, race_num, race_id = sample_race
        print(f"  最新レース: {venue} {date} {race_num}R (ID: {race_id})")

        # このレースの詳細データを確認
        cursor.execute("""
            SELECT pit_number, exhibition_time, st_time, actual_course
            FROM race_details
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))

        details = cursor.fetchall()
        if details:
            print(f"  レース詳細データ:")
            print(f"    {'Pit':4s} {'展示':>8s} {'ST':>8s} {'進入':>6s}")
            for pit, ex_time, st_time, course in details:
                ex_str = f"{ex_time:.2f}" if ex_time else "---"
                st_str = f"{st_time:.2f}" if st_time else "---"
                course_str = str(course) if course else "---"
                print(f"    {pit:4d} {ex_str:>8s} {st_str:>8s} {course_str:>6s}")
        else:
            print(f"  レース詳細データ: なし")

    conn.close()

    print("\n" + "="*80)
    print("分析完了")
    print("="*80)


if __name__ == '__main__':
    check_database_status()
