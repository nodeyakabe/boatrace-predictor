import sqlite3
import os
from datetime import datetime
import sys

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def get_primary_key_columns(cursor, table_name):
    """テーブルの主キーカラムを取得"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = cursor.fetchall()
    pk_columns = [col[1] for col in columns_info if col[5] > 0]  # col[5]がpk番号
    return pk_columns if pk_columns else [columns_info[0][1]]  # PKがない場合は最初のカラム

def import_missing_rows_smart(current_conn, backup_conn, table_name):
    """不足しているレコードをスマートにインポート"""
    current_cursor = current_conn.cursor()
    backup_cursor = backup_conn.cursor()

    # テーブルの全カラムを取得
    backup_cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = backup_cursor.fetchall()
    columns = [col[1] for col in columns_info]
    columns_str = ", ".join(columns)

    # 主キーを自動検出
    key_columns = get_primary_key_columns(backup_cursor, table_name)

    print(f"  主キー: {', '.join(key_columns)}")

    # バックアップDBからデータを取得
    backup_cursor.execute(f"SELECT {columns_str} FROM {table_name}")
    all_rows = backup_cursor.fetchall()

    if not all_rows:
        print(f"  - データなし（スキップ）")
        return 0

    # 現在のDBの既存キーを取得（高速化のためセットに変換）
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
        current_cursor.executemany(f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})", to_insert)
        current_conn.commit()

    return len(to_insert)

def import_race_predictions(current_conn, backup_conn):
    """race_predictionsテーブルの特別処理（idカラムがUNIQUE制約）"""
    current_cursor = current_conn.cursor()
    backup_cursor = backup_conn.cursor()

    # テーブルの全カラムを取得
    backup_cursor.execute(f"PRAGMA table_info(race_predictions)")
    columns_info = backup_cursor.fetchall()
    columns = [col[1] for col in columns_info]
    columns_str = ", ".join(columns)

    # バックアップDBからデータを取得
    backup_cursor.execute(f"SELECT {columns_str} FROM race_predictions")
    all_rows = backup_cursor.fetchall()

    if not all_rows:
        print(f"  - データなし（スキップ）")
        return 0

    # 現在のDBの既存race_idを取得
    current_cursor.execute(f"SELECT race_id FROM race_predictions")
    existing_race_ids = set(row[0] for row in current_cursor.fetchall())

    # 挿入対象を抽出（race_idが存在しないもの）
    race_id_idx = columns.index('race_id')
    to_insert = []
    for row in all_rows:
        if row[race_id_idx] not in existing_race_ids:
            to_insert.append(row)

    # 一括挿入
    if to_insert:
        placeholders = ", ".join(["?" for _ in columns])
        current_cursor.executemany(f"INSERT INTO race_predictions ({columns_str}) VALUES ({placeholders})", to_insert)
        current_conn.commit()

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
    print("データインポート開始（修正版）")
    print("=" * 80)

    # DB接続
    current_conn = sqlite3.connect(current_db)
    backup_conn = sqlite3.connect(backup_db)

    # インポート設定
    tables_to_import = [
        "actual_courses",
        "entries",
        "results",
        "races",
        "weather",
        "exhibition_data",
        "win_odds",
    ]

    print("\n" + "=" * 80)
    print("既存テーブルへのデータ追加")
    print("=" * 80)

    total_imported = 0

    # race_predictionsは特別処理
    print(f"\n処理中: race_predictions（特別処理）")
    try:
        imported = import_race_predictions(current_conn, backup_conn)
        total_imported += imported
        print(f"  ✓ {imported:,} 件のレコードを追加")
    except Exception as e:
        print(f"  ✗ エラー: {e}")

    # その他のテーブル
    for table_name in tables_to_import:
        try:
            print(f"\n処理中: {table_name}")
            imported = import_missing_rows_smart(current_conn, backup_conn, table_name)
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
