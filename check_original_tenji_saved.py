"""
オリジナル展示データがrace_detailsに保存されているか確認
"""

import sqlite3

def check_original_tenji():
    """オリジナル展示データの確認"""
    print("=" * 70)
    print("オリジナル展示データ保存確認")
    print("=" * 70)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 2025-11-13のレースIDを取得
    query = """
    SELECT id, race_number
    FROM races
    WHERE venue_code = '10' AND race_date = '2025-11-13'
    ORDER BY race_number
    """

    cursor.execute(query)
    races = cursor.fetchall()

    if not races:
        print("\n[ERROR] 2025-11-13のレースが見つかりません")
        conn.close()
        return

    print(f"\n対象: 2025-11-13 若松 (会場コード10)")
    print(f"レース数: {len(races)}\n")

    # race_detailsテーブルの構造を確認
    cursor.execute("PRAGMA table_info(race_details)")
    columns = cursor.fetchall()

    has_tenji_columns = False
    for col in columns:
        if 'chikusen' in col[1] or 'isshu' in col[1] or 'mawariashi' in col[1]:
            has_tenji_columns = True
            break

    if not has_tenji_columns:
        print("[INFO] race_detailsテーブルにオリジナル展示カラムがありません")
        print("       (chikusen_time, isshu_time, mawariashi_time)")
        print("\n利用可能なカラム:")
        for col in columns:
            print(f"  - {col[1]}")
    else:
        print("[OK] race_detailsテーブルにオリジナル展示カラムが存在します\n")

        # 各レースのオリジナル展示データを確認
        total_with_data = 0
        for race_id, race_num in races:
            query = """
            SELECT pit_number, chikusen_time, isshu_time, mawariashi_time
            FROM race_details
            WHERE race_id = ?
            ORDER BY pit_number
            """

            cursor.execute(query, (race_id,))
            results = cursor.fetchall()

            if results:
                has_data = False
                data_count = 0
                for pit, chikusen, isshu, mawari in results:
                    if chikusen is not None or isshu is not None or mawari is not None:
                        has_data = True
                        data_count += 1

                if has_data:
                    total_with_data += 1
                    print(f"  {race_num}R: [OK] オリジナル展示データあり ({data_count}艇)")
                else:
                    print(f"  {race_num}R: [INFO] レコードはあるがデータなし")
            else:
                print(f"  {race_num}R: [NG] race_detailsにレコードなし")

        print(f"\n保存状況: {total_with_data}/{len(races)}レース")

    conn.close()

    print("\n" + "=" * 70)


if __name__ == "__main__":
    check_original_tenji()
