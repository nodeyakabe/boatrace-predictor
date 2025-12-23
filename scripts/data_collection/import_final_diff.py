import sqlite3
import os
import sys

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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

    if not to_insert:
        print(f"  - 追加するデータなし（すべて存在済み）")
        return 0

    # idカラムを除外してインポート（自動採番させる）
    columns_without_id = [col for col in columns if col != 'id']
    columns_without_id_str = ", ".join(columns_without_id)
    placeholders_without_id = ", ".join(["?" for _ in columns_without_id])

    try:
        id_idx = columns.index('id')
        to_insert_without_id = []
        for row in to_insert:
            row_list = list(row)
            row_list.pop(id_idx)
            to_insert_without_id.append(tuple(row_list))
    except ValueError:
        # idカラムがない場合はそのまま
        to_insert_without_id = to_insert
        columns_without_id_str = columns_str
        placeholders_without_id = ", ".join(["?" for _ in columns])

    # 1件ずつ挿入
    inserted = 0
    for row in to_insert_without_id:
        try:
            current_cursor.execute(
                f"INSERT INTO {table_name} ({columns_without_id_str}) VALUES ({placeholders_without_id})",
                row
            )
            inserted += 1
        except Exception as e:
            # スキップ（既存の可能性）
            pass

    current_conn.commit()
    return inserted

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
    print("最終差分データのインポート")
    print("=" * 80)

    # DB接続
    current_conn = sqlite3.connect(current_db)
    backup_conn = sqlite3.connect(backup_db)

    # 残りの差分テーブル
    tables_to_import = [
        ("races", ["venue_code", "race_date", "race_number"]),
        ("weather", ["venue_code", "weather_date"]),
    ]

    total_imported = 0

    for table_name, key_columns in tables_to_import:
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
    print("最終インポート完了")
    print("=" * 80)
    print(f"\n合計: {total_imported:,} 件のレコードを追加しました")

if __name__ == "__main__":
    main()
