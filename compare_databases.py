import sqlite3
import os

def get_db_info(db_path):
    """データベースの情報を取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # テーブル一覧を取得
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    info = {}
    for table in tables:
        # 各テーブルのレコード数を取得
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]

        # テーブルのスキーマを取得
        cursor.execute(f"PRAGMA table_info({table})")
        schema = cursor.fetchall()

        info[table] = {
            'count': count,
            'schema': schema
        }

    conn.close()
    return info, tables

def compare_databases(current_db, backup_db):
    """2つのデータベースを比較"""
    print("=" * 80)
    print("データベース比較レポート")
    print("=" * 80)

    current_info, current_tables = get_db_info(current_db)
    backup_info, backup_tables = get_db_info(backup_db)

    print(f"\n現在のDB: {current_db}")
    print(f"バックアップDB: {backup_db}")

    # テーブルの比較
    print("\n" + "=" * 80)
    print("テーブル比較")
    print("=" * 80)

    only_current = set(current_tables) - set(backup_tables)
    only_backup = set(backup_tables) - set(current_tables)
    common_tables = set(current_tables) & set(backup_tables)

    if only_current:
        print(f"\n【現在のDBのみに存在するテーブル】: {len(only_current)}")
        for table in sorted(only_current):
            print(f"  - {table}: {current_info[table]['count']} レコード")

    if only_backup:
        print(f"\n【バックアップDBのみに存在するテーブル】: {len(only_backup)}")
        for table in sorted(only_backup):
            print(f"  - {table}: {backup_info[table]['count']} レコード")

    # 共通テーブルのレコード数比較
    print("\n" + "=" * 80)
    print("共通テーブルのレコード数比較")
    print("=" * 80)
    print(f"\nテーブル数: {len(common_tables)}")
    print("\nテーブル名 | 現在のDB | バックアップDB | 差分")
    print("-" * 80)

    tables_with_more_in_backup = []
    tables_with_same_count = []
    tables_with_more_in_current = []

    for table in sorted(common_tables):
        current_count = current_info[table]['count']
        backup_count = backup_info[table]['count']
        diff = backup_count - current_count

        status = ""
        if diff > 0:
            status = f"← バックアップに {diff} 件多い"
            tables_with_more_in_backup.append((table, current_count, backup_count, diff))
        elif diff < 0:
            status = f"→ 現在に {abs(diff)} 件多い"
            tables_with_more_in_current.append((table, current_count, backup_count, diff))
        else:
            status = "同じ"
            tables_with_same_count.append(table)

        print(f"{table:30} | {current_count:10,} | {backup_count:10,} | {status}")

    # サマリー
    print("\n" + "=" * 80)
    print("サマリー")
    print("=" * 80)

    print(f"\n【バックアップDBの方がデータが多いテーブル】: {len(tables_with_more_in_backup)}")
    if tables_with_more_in_backup:
        print("\n優先度順（差分が大きい順）:")
        for table, current_count, backup_count, diff in sorted(tables_with_more_in_backup, key=lambda x: x[3], reverse=True):
            print(f"  {table:30}: +{diff:,} 件 (現在: {current_count:,}, バックアップ: {backup_count:,})")

    print(f"\n【現在のDBの方がデータが多いテーブル】: {len(tables_with_more_in_current)}")
    if tables_with_more_in_current:
        for table, current_count, backup_count, diff in sorted(tables_with_more_in_current, key=lambda x: x[3]):
            print(f"  {table:30}: {diff:,} 件 (現在: {current_count:,}, バックアップ: {backup_count:,})")

    print(f"\n【同じレコード数のテーブル】: {len(tables_with_same_count)}")

    # スキーマの違いをチェック
    print("\n" + "=" * 80)
    print("スキーマの違い")
    print("=" * 80)

    schema_differences = []
    for table in common_tables:
        current_schema = current_info[table]['schema']
        backup_schema = backup_info[table]['schema']

        if current_schema != backup_schema:
            schema_differences.append(table)
            print(f"\n【{table}】のスキーマが異なります")
            print("  現在のDB:")
            for col in current_schema:
                print(f"    {col}")
            print("  バックアップDB:")
            for col in backup_schema:
                print(f"    {col}")

    if not schema_differences:
        print("\nすべての共通テーブルでスキーマは同じです")

    return tables_with_more_in_backup, tables_with_more_in_current, only_backup

if __name__ == "__main__":
    current_db = r"C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"
    backup_db = r"C:\Users\User\Desktop\boatrace_db_backup\boatrace.db"

    if not os.path.exists(current_db):
        print(f"エラー: 現在のDBが見つかりません: {current_db}")
        exit(1)

    if not os.path.exists(backup_db):
        print(f"エラー: バックアップDBが見つかりません: {backup_db}")
        exit(1)

    compare_databases(current_db, backup_db)
