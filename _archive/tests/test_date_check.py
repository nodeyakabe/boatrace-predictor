"""
日付チェックのテスト
"""
import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH

today = datetime.now().strftime('%Y%m%d')
print(f"今日の日付: {today}")
print(f"型: {type(today)}")

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# すべての日付を確認
cursor.execute("SELECT DISTINCT race_date FROM races ORDER BY race_date DESC LIMIT 10")
dates = cursor.fetchall()

print("\n最近のrace_date:")
for date_tuple in dates:
    date_str = date_tuple[0]
    print(f"  {date_str} (型: {type(date_str)}, 一致: {date_str == today})")

# 今日のデータを取得（厳密な一致）
cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (today,))
count = cursor.fetchone()[0]
print(f"\n今日のレース（race_date = '{today}'）: {count}件")

# LIKE検索
cursor.execute("SELECT COUNT(*) FROM races WHERE race_date LIKE ?", (f"{today}%",))
count_like = cursor.fetchone()[0]
print(f"今日のレース（LIKE検索）: {count_like}件")

# すべての2025-11-14のデータ
cursor.execute("SELECT race_date, COUNT(*) FROM races WHERE race_date LIKE '20251114%' GROUP BY race_date")
results = cursor.fetchall()
print(f"\n2025-11-14を含むrace_date:")
for race_date, count in results:
    print(f"  {race_date}: {count}件")

conn.close()
