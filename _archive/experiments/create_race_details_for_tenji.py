"""
オリジナル展示データ保存のためにrace_detailsレコードを作成
entriesテーブルのデータを基にrace_detailsを初期化
"""

import sqlite3

def create_race_details_from_entries():
    """entriesからrace_detailsを作成"""
    print("=" * 70)
    print("race_detailsレコード作成")
    print("=" * 70)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 2025-11-13のレースを取得
    query = """
    SELECT id, race_number
    FROM races
    WHERE venue_code = '10' AND race_date = '2025-11-13'
    ORDER BY race_number
    """

    cursor.execute(query)
    races = cursor.fetchall()

    if not races:
        print("\n[ERROR] レースが見つかりません")
        conn.close()
        return

    print(f"\n対象: 2025-11-13 若松")
    print(f"レース数: {len(races)}\n")

    total_created = 0

    for race_id, race_num in races:
        # entriesから選手情報を取得
        cursor.execute("""
            SELECT pit_number
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))

        entries = cursor.fetchall()

        if not entries:
            print(f"  {race_num}R: [SKIP] entriesデータなし")
            continue

        # race_detailsに既存レコードがあるか確認
        cursor.execute("""
            SELECT COUNT(*)
            FROM race_details
            WHERE race_id = ?
        """, (race_id,))

        existing_count = cursor.fetchone()[0]

        if existing_count > 0:
            print(f"  {race_num}R: [SKIP] race_detailsに既にレコードあり ({existing_count}件)")
            continue

        # race_detailsレコードを作成
        created = 0
        for (pit_number,) in entries:
            cursor.execute("""
                INSERT INTO race_details (
                    race_id, pit_number,
                    chikusen_time, isshu_time, mawariashi_time
                )
                VALUES (?, ?, NULL, NULL, NULL)
            """, (race_id, pit_number))
            created += 1

        conn.commit()
        total_created += created
        print(f"  {race_num}R: [OK] {created}件のレコードを作成")

    conn.close()

    print(f"\n合計: {total_created}件のrace_detailsレコードを作成")
    print("=" * 70)


if __name__ == "__main__":
    create_race_details_from_entries()
