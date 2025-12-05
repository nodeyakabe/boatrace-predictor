import sqlite3

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

# 全テーブル一覧を取得
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print("データベース内のテーブル:")
print("=" * 60)
for table in tables:
    print(f"- {table[0]}")

    # 各テーブルのカラム情報
    cursor.execute(f"PRAGMA table_info({table[0]})")
    columns = cursor.fetchall()
    for col in columns:
        print(f"    {col[1]:30s} {col[2]:15s}")
    print()

conn.close()
