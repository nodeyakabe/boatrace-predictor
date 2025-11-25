"""データベース内のテーブル確認"""
import sqlite3

conn = sqlite3.connect('boatrace.db')
cursor = conn.cursor()

# 全テーブル一覧
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

with open('db_tables_list.txt', 'w', encoding='utf-8') as f:
    f.write('=' * 80 + '\n')
    f.write('データベース内のテーブル一覧\n')
    f.write('=' * 80 + '\n\n')

    for table in tables:
        table_name = table[0]
        cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
        count = cursor.fetchone()[0]
        f.write(f'{table_name}: {count:,}件\n')

        # カラム構造も出力
        cursor.execute(f'PRAGMA table_info({table_name})')
        columns = cursor.fetchall()
        f.write('  カラム:\n')
        for col in columns:
            f.write(f'    - {col[1]} ({col[2]})\n')
        f.write('\n')

conn.close()
print('db_tables_list.txt に出力しました')
