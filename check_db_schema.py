"""
データベーススキーマ確認スクリプト
race_entriesテーブルとracer_rankカラムの存在を確認
"""

import sqlite3

def check_database_schema(db_path="data/boatrace.db"):
    """データベーススキーマを確認"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("データベーススキーマ確認")
    print("=" * 80)

    # 全テーブルリスト
    print("\n[1] 全テーブル一覧:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    for table in tables:
        print(f"  - {table[0]}")

    # race_entriesテーブルの存在確認
    print("\n[2] race_entriesテーブルの確認:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='race_entries'")
    race_entries_exists = cursor.fetchone()

    if race_entries_exists:
        print("  [OK] race_entriesテーブルは存在します")

        # スキーマ確認
        print("\n  スキーマ:")
        cursor.execute("PRAGMA table_info(race_entries)")
        columns = cursor.fetchall()
        for col in columns:
            print(f"    {col[1]} ({col[2]})")

        # レコード数確認
        cursor.execute("SELECT COUNT(*) FROM race_entries")
        count = cursor.fetchone()[0]
        print(f"\n  レコード数: {count:,}")

        # racer_rankカラムの確認
        cursor.execute("PRAGMA table_info(race_entries)")
        columns = cursor.fetchall()
        racer_rank_exists = any(col[1] == 'racer_rank' for col in columns)

        if racer_rank_exists:
            print("\n  [OK] racer_rankカラムは存在します")

            # データサンプル
            print("\n  データサンプル:")
            cursor.execute("""
                SELECT race_id, pit_number, racer_rank
                FROM race_entries
                WHERE racer_rank IS NOT NULL
                LIMIT 10
            """)
            samples = cursor.fetchall()
            for sample in samples:
                print(f"    race_id={sample[0]}, pit={sample[1]}, rank={sample[2]}")

            # NULL値の統計
            cursor.execute("SELECT COUNT(*) FROM race_entries WHERE racer_rank IS NULL")
            null_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM race_entries WHERE racer_rank IS NOT NULL")
            not_null_count = cursor.fetchone()[0]

            print(f"\n  racer_rank統計:")
            print(f"    NULL: {null_count:,} ({null_count/count*100:.1f}%)")
            print(f"    NOT NULL: {not_null_count:,} ({not_null_count/count*100:.1f}%)")

            # 級別分布
            if not_null_count > 0:
                print(f"\n  級別分布:")
                cursor.execute("""
                    SELECT racer_rank, COUNT(*) as cnt
                    FROM race_entries
                    WHERE racer_rank IS NOT NULL
                    GROUP BY racer_rank
                    ORDER BY cnt DESC
                """)
                ranks = cursor.fetchall()
                for rank in ranks:
                    print(f"    {rank[0]}: {rank[1]:,} ({rank[1]/not_null_count*100:.1f}%)")
        else:
            print("\n  [X] racer_rankカラムは存在しません")
    else:
        print("  [X] race_entriesテーブルは存在しません")
        print("\n  代替として確認するテーブル:")

        # 選手情報が含まれる可能性のあるテーブルを確認
        for table_name in ['racers', 'race_details', 'results']:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if cursor.fetchone():
                print(f"\n  {table_name}テーブル:")
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                for col in columns:
                    print(f"    {col[1]} ({col[2]})")

                # racer_rankまたはrankカラムの確認
                rank_cols = [col for col in columns if 'rank' in col[1].lower()]
                if rank_cols:
                    print(f"\n  級別関連カラム:")
                    for col in rank_cols:
                        print(f"    - {col[1]}")

    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print("確認完了")
    print("=" * 80)


if __name__ == '__main__':
    check_database_schema()
