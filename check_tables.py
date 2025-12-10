import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%odd%' ORDER BY name;")
tables = cursor.fetchall()

print("オッズ関連テーブル:")
for table in tables:
    print(f"  - {table[0]}")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%prediction%' ORDER BY name;")
tables = cursor.fetchall()

print("\n予想関連テーブル:")
for table in tables:
    print(f"  - {table[0]}")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%result%' ORDER BY name;")
tables = cursor.fetchall()

print("\n結果関連テーブル:")
for table in tables:
    print(f"  - {table[0]}")

conn.close()
