"""
データベース更新スクリプト
entriesテーブルに不足しているカラムを追加
"""

import sqlite3
from pathlib import Path

DATABASE_PATH = "data/boatrace.db"


def main():
    print("=" * 60)
    print("データベース更新スクリプト")
    print("=" * 60)

    # データベースファイルの存在確認
    if not Path(DATABASE_PATH).exists():
        print(f"エラー: データベースファイルが見つかりません: {DATABASE_PATH}")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 追加するカラムのリスト
    new_columns = [
        ("f_count", "INTEGER"),
        ("l_count", "INTEGER"),
        ("avg_st", "REAL"),
        ("local_win_rate", "REAL"),
        ("local_second_rate", "REAL"),
        ("local_third_rate", "REAL"),
        ("motor_second_rate", "REAL"),
        ("motor_third_rate", "REAL"),
        ("boat_second_rate", "REAL"),
        ("boat_third_rate", "REAL")
    ]

    print("\nentriesテーブルにカラムを追加します...\n")

    for column_name, column_type in new_columns:
        try:
            # カラムが既に存在するかチェック
            cursor.execute(f"PRAGMA table_info(entries)")
            existing_columns = [row[1] for row in cursor.fetchall()]

            if column_name in existing_columns:
                print(f"  ✓ {column_name} - 既に存在")
            else:
                # カラムを追加
                cursor.execute(f"""
                    ALTER TABLE entries
                    ADD COLUMN {column_name} {column_type}
                """)
                print(f"  ✓ {column_name} - 追加完了")

        except Exception as e:
            print(f"  ✗ {column_name} - エラー: {e}")

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("データベース更新完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
