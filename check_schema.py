import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()

# race_predictionsのサンプルを確認
cur.execute('SELECT * FROM race_predictions WHERE confidence = "B" LIMIT 3')
cols = [d[0] for d in cur.description]
print('race_predictions カラム:')
print(cols)
print('\nサンプルデータ:')
for row in cur.fetchall():
    print(row)

# racesテーブルとの結合キーを確認
print('\n\nracesテーブルのカラム:')
cur.execute('PRAGMA table_info(races)')
for row in cur.fetchall():
    print(row)

conn.close()
