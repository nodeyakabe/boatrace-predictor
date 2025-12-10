import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 問題のあったテーブルの実際のカラムを確認
tables = ['results', 'payouts', 'race_predictions', 'entries']

for table in tables:
    print(f"\n### {table} テーブルの実際のカラム:")
    cursor.execute(f"PRAGMA table_info({table})")
    cols = cursor.fetchall()
    for col in cols:
        print(f"  - {col[1]} ({col[2]})")

# exacta_oddsテーブルの存在確認
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exacta_odds'")
if cursor.fetchone():
    print("\n### exacta_odds テーブル: 存在します")
    cursor.execute("PRAGMA table_info(exacta_odds)")
    cols = cursor.fetchall()
    for col in cols:
        print(f"  - {col[1]} ({col[2]})")
else:
    print("\n### exacta_odds テーブル: 存在しません（ドキュメントが間違い）")

conn.close()
