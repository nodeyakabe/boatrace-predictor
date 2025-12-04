import sqlite3

conn = sqlite3.connect("data/boatrace.db")
cursor = conn.cursor()

# race_detailsテーブルのカラム一覧を取得
cursor.execute("PRAGMA table_info(race_details)")
columns = cursor.fetchall()

print("race_detailsテーブルのカラム:")
print("=" * 60)
for col in columns:
    print(f"{col[1]:30s} {col[2]:15s}")

conn.close()
