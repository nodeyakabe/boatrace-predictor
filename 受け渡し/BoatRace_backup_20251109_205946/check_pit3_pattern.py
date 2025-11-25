"""
Pit 3が欠損しているパターンを調査
決まり手が混入している問題の影響範囲を確認
"""

import sqlite3

def check_pit3_pattern():
    """Pit 3だけが欠損しているレースを検索"""

    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 各レースでどのpitのSTタイムが欠損しているかを調査
    query = """
    WITH race_st_status AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
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
        GROUP BY r.id, r.venue_code, r.race_date, r.race_number
    )
    SELECT
        venue_code,
        race_date,
        race_number,
        total_st_count,
        pit1_has_st, pit2_has_st, pit3_has_st, pit4_has_st, pit5_has_st, pit6_has_st
    FROM race_st_status
    WHERE total_st_count = 5
      AND pit3_has_st = 0
    ORDER BY race_date DESC
    LIMIT 100
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print("="*80)
    print("Races with Pit 3 Missing (5/6 ST times)")
    print("="*80)
    print(f"Total found: {len(rows)} races (showing first 100)")
    print()

    if rows:
        print("Sample races:")
        for i, row in enumerate(rows[:20], 1):
            venue, date, race, total, p1, p2, p3, p4, p5, p6 = row
            pits_str = f"Pits: {p1}{p2}{p3}{p4}{p5}{p6}"
            print(f"  {i:2d}. {venue} {date} {race:2d}R ({total}/6) {pits_str}")

    # 全体の欠損パターン統計
    query2 = """
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
    """

    cursor.execute(query2)
    pattern_rows = cursor.fetchall()

    print()
    print("="*80)
    print("Missing Pattern for 5/6 ST Time Races")
    print("="*80)

    total_5_6 = sum(r[1] for r in pattern_rows)
    for pit, count in pattern_rows:
        pct = count / total_5_6 * 100 if total_5_6 > 0 else 0
        print(f"  {pit:8s}: {count:6d} races ({pct:5.1f}%)")

    print()
    print(f"Total 5/6 races: {total_5_6}")

    conn.close()

    # 推定影響範囲
    if pattern_rows:
        pit3_missing = next((r[1] for r in pattern_rows if r[0] == 'Pit3'), 0)
        print()
        print("="*80)
        print("Impact Analysis")
        print("="*80)
        print(f"Races with missing Pit 3: ~{pit3_missing} races")
        print(f"These races likely have kimarite text mixed in ST time")
        print(f"V3 scraper should fix all of these cases")

if __name__ == '__main__':
    check_pit3_pattern()
