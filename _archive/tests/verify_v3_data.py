"""
V3で収集したデータの検証
"""

import sqlite3

def verify_v3_data():
    """V3で収集したデータを確認"""

    db_path = "data/boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2025-10-31のレースを確認
    query = """
    SELECT
        r.race_number,
        r.venue_code,
        r.race_date,
        COUNT(DISTINCT rd.pit_number) as total_pits,
        SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as st_count,
        SUM(CASE WHEN rd.actual_course IS NOT NULL THEN 1 ELSE 0 END) as course_count,
        SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) as exh_count
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.venue_code = '01' AND r.race_date = '2025-10-31'
    GROUP BY r.id, r.race_number, r.venue_code, r.race_date
    ORDER BY r.race_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print("="*80)
    print("V3 Collection Verification - 2025-10-31 桐生")
    print("="*80)

    if not rows:
        print("No data found!")
        return

    print(f"\n{'Race':<8} {'Pits':<8} {'ST':<8} {'Course':<8} {'Exh':<8}")
    print("-"*80)

    total_perfect_st = 0
    for row in rows:
        race_num, venue, date, pits, st, course, exh = row

        st_status = "OK" if st == 6 else f"MISSING({st}/6)"
        if st == 6:
            total_perfect_st += 1

        print(f"{race_num:2d}R      {pits}/6      {st}/6      {course}/6      {exh}/6      {st_status}")

    print("-"*80)
    print(f"\nPerfect ST times (6/6): {total_perfect_st}/{len(rows)} races")

    if total_perfect_st == len(rows):
        print("\n[SUCCESS] All races have complete 6/6 ST times!")
    else:
        print(f"\n[WARN] {len(rows) - total_perfect_st} races missing ST times")

    # Pit 3の詳細確認
    print("\n" + "="*80)
    print("Pit 3 ST Time Detail (Previously Missing)")
    print("="*80)

    query2 = """
    SELECT
        r.race_number,
        rd.pit_number,
        rd.st_time
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    WHERE r.venue_code = '01' AND r.race_date = '2025-10-31'
      AND rd.pit_number = 3
    ORDER BY r.race_number
    """

    cursor.execute(query2)
    pit3_rows = cursor.fetchall()

    for race_num, pit, st in pit3_rows:
        if st is not None:
            print(f"  Race {race_num:2d}R, Pit {pit}: ST={st:.2f}")
        else:
            print(f"  Race {race_num:2d}R, Pit {pit}: ST=MISSING")

    conn.close()

if __name__ == '__main__':
    verify_v3_data()
