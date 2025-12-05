"""
データベースのテーブル一覧を確認
"""

import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# テーブル一覧を取得
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

print("=" * 70)
print("データベーステーブル一覧")
print("=" * 70)

for table in tables:
    table_name = table[0]
    print(f"\n[{table_name}]")

    # 各テーブルのレコード数を取得
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  レコード数: {count}")
    except Exception as e:
        print(f"  エラー: {e}")

conn.close()

print("\n" + "=" * 70)
