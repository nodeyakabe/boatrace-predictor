"""
entriesテーブルの詳細確認
級別データ（racer_rank）の有無を確認
"""

import sqlite3

def check_entries_table(db_path="data/boatrace.db"):
    """entriesテーブルを詳細確認"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("entriesテーブル詳細確認")
    print("=" * 80)

    # スキーマ確認
    print("\n[1] スキーマ:")
    cursor.execute("PRAGMA table_info(entries)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]:30s} {col[2]:15s} {'NOT NULL' if col[3] else ''}")

    # レコード数
    cursor.execute("SELECT COUNT(*) FROM entries")
    total_count = cursor.fetchone()[0]
    print(f"\n[2] 総レコード数: {total_count:,}")

    # racer_numberとrace_idの関係確認
    print("\n[3] データサンプル（最新10件）:")
    cursor.execute("""
        SELECT race_id, pit_number, racer_number, racer_name, racer_rank
        FROM entries
        ORDER BY race_id DESC
        LIMIT 10
    """)
    samples = cursor.fetchall()

    if samples:
        print(f"  {'race_id':<10} {'pit':<5} {'racer_number':<8} {'name':<15} {'rank':<5}")
        print(f"  {'-'*50}")
        for sample in samples:
            print(f"  {sample[0]:<10} {sample[1]:<5} {sample[2]:<8} {sample[3]:<15} {sample[4] or 'NULL':<5}")

    # 級別関連カラムの確認
    print("\n[4] 級別関連カラムの確認:")
    rank_related = [col for col in columns if 'rank' in col[1].lower()]
    if rank_related:
        print("  級別関連カラムが存在:")
        for col in rank_related:
            col_name = col[1]
            print(f"\n  カラム名: {col_name}")

            # NULL値統計
            cursor.execute(f"SELECT COUNT(*) FROM entries WHERE {col_name} IS NULL")
            null_count = cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM entries WHERE {col_name} IS NOT NULL")
            not_null_count = cursor.fetchone()[0]

            print(f"    NULL: {null_count:,} ({null_count/total_count*100:.1f}%)")
            print(f"    NOT NULL: {not_null_count:,} ({not_null_count/total_count*100:.1f}%)")

            if not_null_count > 0:
                # 値の分布
                cursor.execute(f"""
                    SELECT {col_name}, COUNT(*) as cnt
                    FROM entries
                    WHERE {col_name} IS NOT NULL
                    GROUP BY {col_name}
                    ORDER BY cnt DESC
                    LIMIT 10
                """)
                distribution = cursor.fetchall()
                print(f"    分布:")
                for dist in distribution:
                    print(f"      {dist[0]}: {dist[1]:,} ({dist[1]/not_null_count*100:.1f}%)")
    else:
        print("  [X] 級別関連カラムは存在しません")
        print("\n  利用可能なカラム:")
        for col in columns:
            print(f"    - {col[1]}")

    # racer_numberからracersテーブルとのJOINで級別取得可能か確認
    print("\n[5] racersテーブルとのJOIN確認:")
    cursor.execute("""
        SELECT
            e.race_id,
            e.pit_number,
            e.racer_number,
            r.rank as racer_rank
        FROM entries e
        LEFT JOIN racers r ON e.racer_number = r.racer_number
        WHERE r.rank IS NOT NULL
        LIMIT 10
    """)
    join_samples = cursor.fetchall()

    if join_samples:
        print("  [OK] racersテーブルとJOINで級別取得可能:")
        for sample in join_samples:
            print(f"    race_id={sample[0]}, pit={sample[1]}, racer={sample[2]}, rank={sample[3]}")

        # JOIN成功率
        cursor.execute("""
            SELECT COUNT(*)
            FROM entries e
            INNER JOIN racers r ON e.racer_number = r.racer_number
            WHERE r.rank IS NOT NULL
        """)
        join_count = cursor.fetchone()[0]
        print(f"\n  JOIN成功レコード数: {join_count:,} ({join_count/total_count*100:.1f}%)")
    else:
        print("  [X] racersテーブルとのJOIN失敗")

    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print("確認完了")
    print("=" * 80)


if __name__ == '__main__':
    check_entries_table()
