import sqlite3
import os
from datetime import datetime
import sys

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def get_unique_constraints(cursor, table_name):
    """テーブルのUNIQUE制約を取得"""
    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    create_sql = cursor.fetchone()[0]

    # UNIQUE制約を探す
    unique_columns = []
    if 'UNIQUE' in create_sql:
        # 例: UNIQUE(race_id, pit_number)
        import re
        matches = re.findall(r'UNIQUE\s*\((.*?)\)', create_sql, re.IGNORECASE)
        for match in matches:
            cols = [col.strip() for col in match.split(',')]
            unique_columns.append(cols)

    return unique_columns

def import_with_composite_key(current_conn, backup_conn, table_name, key_columns):
    """複合キーを考慮してインポート"""
    current_cursor = current_conn.cursor()
    backup_cursor = backup_conn.cursor()

    # テーブルの全カラムを取得
    backup_cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = backup_cursor.fetchall()
    columns = [col[1] for col in columns_info]
    columns_str = ", ".join(columns)

    print(f"  キーカラム: {', '.join(key_columns)}")

    # バックアップDBからデータを取得
    backup_cursor.execute(f"SELECT {columns_str} FROM {table_name}")
    all_rows = backup_cursor.fetchall()

    if not all_rows:
        print(f"  - データなし（スキップ）")
        return 0

    # 現在のDBの既存キーを取得
    key_columns_str = ", ".join(key_columns)
    current_cursor.execute(f"SELECT {key_columns_str} FROM {table_name}")
    existing_keys = set(current_cursor.fetchall())

    # 挿入対象を抽出
    to_insert = []
    for row in all_rows:
        key_values = tuple(row[columns.index(col)] for col in key_columns)
        if key_values not in existing_keys:
            to_insert.append(row)

    # 一括挿入
    if to_insert:
        placeholders = ", ".join(["?" for _ in columns])
        try:
            current_cursor.executemany(f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})", to_insert)
            current_conn.commit()
        except Exception as e:
            print(f"    警告: 一括挿入失敗、1件ずつ試行します - {e}")
            # 1件ずつ挿入を試みる
            inserted = 0
            for row in to_insert:
                try:
                    current_cursor.execute(f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})", row)
                    inserted += 1
                except:
                    pass  # スキップ
            current_conn.commit()
            return inserted

    return len(to_insert)

def import_race_predictions_safe(current_conn, backup_conn):
    """race_predictionsテーブルの安全なインポート"""
    current_cursor = current_conn.cursor()
    backup_cursor = backup_conn.cursor()

    # テーブルの全カラムを取得
    backup_cursor.execute(f"PRAGMA table_info(race_predictions)")
    columns_info = backup_cursor.fetchall()
    columns = [col[1] for col in columns_info]
    columns_str = ", ".join(columns)

    print(f"  キーカラム: race_id")

    # バックアップDBからデータを取得
    backup_cursor.execute(f"SELECT {columns_str} FROM race_predictions")
    all_rows = backup_cursor.fetchall()

    if not all_rows:
        print(f"  - データなし（スキップ）")
        return 0

    # 現在のDBの既存race_idを取得
    current_cursor.execute(f"SELECT race_id FROM race_predictions")
    existing_race_ids = set(row[0] for row in current_cursor.fetchall())

    # 挿入対象を抽出
    race_id_idx = columns.index('race_id')
    to_insert = []
    for row in all_rows:
        if row[race_id_idx] not in existing_race_ids:
            to_insert.append(row)

    # 一括挿入
    if to_insert:
        placeholders = ", ".join(["?" for _ in columns])
        # idカラムを除外してインポート（自動採番させる）
        columns_without_id = [col for col in columns if col != 'id']
        columns_without_id_str = ", ".join(columns_without_id)
        placeholders_without_id = ", ".join(["?" for _ in columns_without_id])
        id_idx = columns.index('id')

        to_insert_without_id = []
        for row in to_insert:
            row_list = list(row)
            row_list.pop(id_idx)
            to_insert_without_id.append(tuple(row_list))

        try:
            current_cursor.executemany(
                f"INSERT INTO race_predictions ({columns_without_id_str}) VALUES ({placeholders_without_id})",
                to_insert_without_id
            )
            current_conn.commit()
        except Exception as e:
            print(f"    警告: 一括挿入失敗、1件ずつ試行します - {e}")
            inserted = 0
            for row in to_insert_without_id:
                try:
                    current_cursor.execute(
                        f"INSERT INTO race_predictions ({columns_without_id_str}) VALUES ({placeholders_without_id})",
                        row
                    )
                    inserted += 1
                except:
                    pass
            current_conn.commit()
            return inserted

    return len(to_insert)

def main():
    current_db = r"C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"
    backup_db = r"C:\Users\User\Desktop\boatrace_db_backup\boatrace.db"

    if not os.path.exists(current_db):
        print(f"エラー: 現在のDBが見つかりません: {current_db}")
        return

    if not os.path.exists(backup_db):
        print(f"エラー: バックアップDBが見つかりません: {backup_db}")
        return

    print("=" * 80)
    print("残りデータのインポート")
    print("=" * 80)

    # DB接続
    current_conn = sqlite3.connect(current_db)
    backup_conn = sqlite3.connect(backup_db)

    # 複合キーを持つテーブルの設定
    tables_with_composite_keys = [
        ("results", ["race_id", "pit_number"]),
        ("races", ["venue_code", "race_date", "race_number"]),
        ("weather", ["venue_code", "weather_date"]),
    ]

    print("\n" + "=" * 80)
    print("複合キーテーブルへのデータ追加")
    print("=" * 80)

    total_imported = 0

    # race_predictionsは特別処理
    print(f"\n処理中: race_predictions")
    try:
        imported = import_race_predictions_safe(current_conn, backup_conn)
        total_imported += imported
        print(f"  ✓ {imported:,} 件のレコードを追加")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()

    # 複合キーテーブル
    for table_name, key_columns in tables_with_composite_keys:
        try:
            print(f"\n処理中: {table_name}")
            imported = import_with_composite_key(current_conn, backup_conn, table_name, key_columns)
            total_imported += imported
            print(f"  ✓ {imported:,} 件のレコードを追加")
        except Exception as e:
            print(f"  ✗ エラー: {e}")
            import traceback
            traceback.print_exc()

    # クリーンアップ
    current_conn.close()
    backup_conn.close()

    print("\n" + "=" * 80)
    print("インポート完了")
    print("=" * 80)
    print(f"\n合計: {total_imported:,} 件のレコードを追加しました")

if __name__ == "__main__":
    main()
