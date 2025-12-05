import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# entriesテーブルの構造確認
cursor.execute('PRAGMA table_info(entries)')
cols = cursor.fetchall()

print('entriesテーブルのカラム一覧:')
print('-' * 80)
print(f"{'No.':<5} {'カラム名':<30} {'型':<15}")
print('-' * 80)

for col in cols:
    print(f"{col[0]:<5} {col[1]:<30} {col[2]:<15}")

print()
print(f"合計: {len(cols)}カラム")

# サンプルデータ確認
print('\n' + '=' * 80)
print('サンプルデータ（最新5件）')
print('=' * 80)

cursor.execute('''
SELECT
    racer_number, racer_name, racer_rank,
    win_rate, second_rate, third_rate,
    f_count, l_count, avg_st,
    motor_number, motor_second_rate,
    boat_number, boat_second_rate
FROM entries
ORDER BY created_at DESC
LIMIT 5
''')

rows = cursor.fetchall()
for row in rows:
    print(f"選手番号: {row[0]}, 名前: {row[1]}, 級別: {row[2]}")
    print(f"  勝率: {row[3]}, 2連率: {row[4]}, 3連率: {row[5]}")
    print(f"  F回数: {row[6]}, L回数: {row[7]}, 平均ST: {row[8]}")
    print(f"  モーター番号: {row[9]}, モーター2連率: {row[10]}")
    print(f"  ボート番号: {row[11]}, ボート2連率: {row[12]}")
    print()

conn.close()
