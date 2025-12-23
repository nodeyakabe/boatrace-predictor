import sqlite3
import os
from datetime import datetime
import sys

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def create_backup(db_path):
    """現在のDBをバックアップ"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.replace(".db", f"_before_import_{timestamp}.db")

    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"✓ バックアップ作成: {backup_path}")
    return backup_path

def get_table_schema(cursor, table_name):
    """テーブルのスキーマを取得"""
    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    result = cursor.fetchone()
    return result[0] if result else None

def create_table_if_not_exists(current_conn, backup_conn, table_name):
    """テーブルが存在しない場合は作成"""
    current_cursor = current_conn.cursor()
    backup_cursor = backup_conn.cursor()

    # 現在のDBにテーブルが存在するか確認
    current_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    if current_cursor.fetchone() is None:
        # バックアップDBからスキーマを取得して作成
        schema = get_table_schema(backup_cursor, table_name)
        if schema:
            current_cursor.execute(schema)
            current_conn.commit()
            print(f"  ✓ テーブル作成: {table_name}")
            return True
    return False

def import_missing_rows(current_conn, backup_conn, table_name, key_columns):
    """不足しているレコードをインポート（キー重複を避ける）"""
    current_cursor = current_conn.cursor()
    backup_cursor = backup_conn.cursor()

    # テーブルの全カラムを取得
    backup_cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = backup_cursor.fetchall()
    columns = [col[1] for col in columns_info]
    columns_str = ", ".join(columns)

    # バックアップDBからデータを取得
    backup_cursor.execute(f"SELECT {columns_str} FROM {table_name}")
    all_rows = backup_cursor.fetchall()

    if not all_rows:
        print(f"  - {table_name}: データなし（スキップ）")
        return 0

    # キーカラムで重複チェックして挿入
    inserted = 0
    skipped = 0

    for row in all_rows:
        # キーで存在チェック
        where_clause = " AND ".join([f"{col} = ?" for col in key_columns])
        key_values = [row[columns.index(col)] for col in key_columns]

        current_cursor.execute(f"SELECT 1 FROM {table_name} WHERE {where_clause}", key_values)

        if current_cursor.fetchone() is None:
            # 存在しない場合のみ挿入
            placeholders = ", ".join(["?" for _ in columns])
            current_cursor.execute(f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})", row)
            inserted += 1
        else:
            skipped += 1

    current_conn.commit()
    return inserted

def import_all_rows(current_conn, backup_conn, table_name):
    """全レコードをインポート（新規テーブル用）"""
    current_cursor = current_conn.cursor()
    backup_cursor = backup_conn.cursor()

    # テーブルの全カラムを取得
    backup_cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = backup_cursor.fetchall()
    columns = [col[1] for col in columns_info]
    columns_str = ", ".join(columns)

    # バックアップDBからデータを取得
    backup_cursor.execute(f"SELECT {columns_str} FROM {table_name}")
    all_rows = backup_cursor.fetchall()

    if not all_rows:
        print(f"  - {table_name}: データなし（スキップ）")
        return 0

    # 全件挿入
    placeholders = ", ".join(["?" for _ in columns])
    current_cursor.executemany(f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})", all_rows)
    current_conn.commit()

    return len(all_rows)

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
    print("データインポート開始")
    print("=" * 80)

    # 現在のDBをバックアップ
    backup_path = create_backup(current_db)

    # DB接続
    current_conn = sqlite3.connect(current_db)
    backup_conn = sqlite3.connect(backup_db)

    # インポート設定（テーブル名、キーカラム）
    tables_to_import = [
        # 優先度高：既存テーブルに不足データを追加
        ("race_predictions", ["race_id"]),
        ("actual_courses", ["race_id", "racer_id"]),
        ("entries", ["race_id", "racer_id"]),
        ("results", ["race_id", "racer_id"]),
        ("races", ["race_id"]),
        ("weather", ["date", "venue_id"]),
        ("exhibition_data", ["race_id", "racer_id"]),
        ("win_odds", ["race_id", "racer_id"]),
    ]

    # 新規テーブル（全件コピー）
    new_tables = [
        "compound_rules",
        "discovered_patterns",
        "exacta_odds",
        "pattern_counter_conditions",
        "race_tide_data",
        "venue_racer_patterns",
        "racer_attack_patterns",
        "venue_attack_patterns",
    ]

    print("\n" + "=" * 80)
    print("既存テーブルへのデータ追加")
    print("=" * 80)

    total_imported = 0
    for table_name, key_columns in tables_to_import:
        try:
            print(f"\n処理中: {table_name}")
            imported = import_missing_rows(current_conn, backup_conn, table_name, key_columns)
            total_imported += imported
            print(f"  ✓ {imported:,} 件のレコードを追加")
        except Exception as e:
            print(f"  ✗ エラー: {e}")

    print("\n" + "=" * 80)
    print("新規テーブルの作成とデータコピー")
    print("=" * 80)

    for table_name in new_tables:
        try:
            print(f"\n処理中: {table_name}")

            # テーブル作成
            is_new = create_table_if_not_exists(current_conn, backup_conn, table_name)

            # データコピー
            imported = import_all_rows(current_conn, backup_conn, table_name)
            total_imported += imported

            if is_new:
                print(f"  ✓ 新規テーブル作成 + {imported:,} 件のレコードを追加")
            else:
                print(f"  ✓ {imported:,} 件のレコードを追加")
        except Exception as e:
            print(f"  ✗ エラー: {e}")

    # クリーンアップ
    current_conn.close()
    backup_conn.close()

    print("\n" + "=" * 80)
    print("インポート完了")
    print("=" * 80)
    print(f"\n合計: {total_imported:,} 件のレコードをインポートしました")
    print(f"\n元のDBバックアップ: {backup_path}")
    print("\n問題があれば、上記のバックアップから復元できます")

if __name__ == "__main__":
    main()
