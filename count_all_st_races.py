import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 全期間のST 5/6レース数をカウント
cursor.execute('''
    SELECT COUNT(*)
    FROM (
        SELECT r.id
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        GROUP BY r.id
        HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) = 5
    )
''')

count_5 = cursor.fetchone()[0]

# 全期間のST <5レース数をカウント
cursor.execute('''
    SELECT COUNT(*)
    FROM (
        SELECT r.id
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        GROUP BY r.id
        HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) < 5
    )
''')

count_less = cursor.fetchone()[0]

# 全期間のST 6/6レース数をカウント
cursor.execute('''
    SELECT COUNT(*)
    FROM (
        SELECT r.id
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        GROUP BY r.id
        HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) = 6
    )
''')

count_6 = cursor.fetchone()[0]

# データの年代範囲を確認
cursor.execute('SELECT MIN(race_date), MAX(race_date) FROM races')
date_range = cursor.fetchone()

print('=== 全期間 ST時間状況 ===')
print(f'データ期間: {date_range[0]} ～ {date_range[1]}')
print()
print(f'ST 6/6（完全）: {count_6:,}レース ({count_6/(count_6+count_5+count_less)*100:.1f}%)')
print(f'ST 5/6（補充対象）: {count_5:,}レース ({count_5/(count_6+count_5+count_less)*100:.1f}%)')
print(f'ST <5: {count_less:,}レース ({count_less/(count_6+count_5+count_less)*100:.1f}%)')
print(f'合計: {count_6 + count_5 + count_less:,}レース')
print()
print(f'補充可能レース: {count_5:,}レース')
print(f'推定実行時間: {count_5 * 0.3 / 60:.1f}分（0.3秒/レース × {count_5:,}レース）')
print(f'推定実行時間: {count_5 * 0.3 / 3600:.1f}時間')

conn.close()
