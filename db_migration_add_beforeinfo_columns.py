"""
DBスキーマ拡張: 直前情報の新規カラム追加

追加内容:
- race_details: 調整重量、展示進入コース、前走成績
- weather: 天候コード、風向コード
"""

import sqlite3
import sys

DATABASE_PATH = 'data/boatrace.db'

def migrate_database():
    """データベースマイグレーション実行"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("="*70)
    print("DBスキーマ拡張: 直前情報の新規カラム追加")
    print("="*70)

    try:
        # 1. race_detailsテーブルに新カラム追加
        print("\n[1] race_detailsテーブルを拡張...")

        new_columns = [
            ("adjusted_weight", "REAL", "調整重量"),
            ("exhibition_course", "INTEGER", "展示進入コース"),
            ("prev_race_course", "INTEGER", "前走進入コース"),
            ("prev_race_st", "REAL", "前走ST"),
            ("prev_race_rank", "INTEGER", "前走着順")
        ]

        for col_name, col_type, description in new_columns:
            try:
                cursor.execute(f"ALTER TABLE race_details ADD COLUMN {col_name} {col_type}")
                print(f"  [OK] {col_name} ({description}) を追加")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"  [SKIP] {col_name} は既に存在（スキップ）")
                else:
                    raise

        # 2. weatherテーブルに新カラム追加
        print("\n[2] weatherテーブルを拡張...")

        weather_columns = [
            ("weather_code", "INTEGER", "天候コード (1=晴, 2=曇, 3=雨...)"),
            ("wind_dir_code", "INTEGER", "風向コード")
        ]

        for col_name, col_type, description in weather_columns:
            try:
                cursor.execute(f"ALTER TABLE weather ADD COLUMN {col_name} {col_type}")
                print(f"  [OK] {col_name} ({description}) を追加")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"  [SKIP] {col_name} は既に存在（スキップ）")
                else:
                    raise

        conn.commit()

        print("\n" + "="*70)
        print("[SUCCESS] マイグレーション完了")
        print("="*70)

        # 確認: 各テーブルのスキーマ表示
        print("\n[確認] race_detailsテーブルのスキーマ:")
        cursor.execute("PRAGMA table_info(race_details)")
        for row in cursor.fetchall():
            print(f"  {row[1]} ({row[2]})")

        print("\n[確認] weatherテーブルのスキーマ:")
        cursor.execute("PRAGMA table_info(weather)")
        for row in cursor.fetchall():
            print(f"  {row[1]} ({row[2]})")

        return True

    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)
