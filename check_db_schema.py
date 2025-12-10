import sqlite3
import sys
import io

# UTF-8出力設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# データベース接続
db_path = 'data/boatrace.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# racesテーブルのスキーマ確認
cursor.execute("PRAGMA table_info(races)")
columns = cursor.fetchall()

print("=" * 80)
print("racesテーブルのカラム一覧")
print("=" * 80)
for col in columns:
    print(f"{col[1]:<20} {col[2]:<15} (nullable: {not col[3]})")

# サンプルデータを確認
cursor.execute("SELECT * FROM races LIMIT 1")
sample = cursor.fetchone()
print("\n" + "=" * 80)
print("サンプルレコード")
print("=" * 80)
if sample:
    for i, col in enumerate(columns):
        print(f"{col[1]:<20}: {sample[i]}")

conn.close()
