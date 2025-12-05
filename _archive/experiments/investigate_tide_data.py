"""潮汐データの構造調査"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=' * 80)
print('潮汐データ構造調査')
print('=' * 80)

# 1. tideテーブルの構造とサンプル
print('\n【1. tideテーブル】')
cursor.execute('PRAGMA table_info(tide)')
columns = cursor.fetchall()
print(f'カラム構造:')
for col in columns:
    print(f'  {col[1]}: {col[2]}')

cursor.execute('SELECT COUNT(*) FROM tide')
tide_count = cursor.fetchone()[0]
print(f'\n総レコード数: {tide_count:,}件')

cursor.execute('SELECT * FROM tide LIMIT 5')
print(f'\nサンプルデータ（最初の5件）:')
for row in cursor.fetchall():
    print(f'  {row}')

# 2. venue_code別の分布
cursor.execute('''
    SELECT venue_code, COUNT(*) as count
    FROM tide
    GROUP BY venue_code
    ORDER BY count DESC
''')
print(f'\n【2. 会場別の潮位データ数】')
for row in cursor.fetchall():
    print(f'  会場{row[0]}: {row[1]:,}件')

# 3. 日付範囲
cursor.execute('SELECT MIN(tide_date), MAX(tide_date) FROM tide')
min_date, max_date = cursor.fetchone()
print(f'\n【3. データ期間】')
print(f'  最古: {min_date}')
print(f'  最新: {max_date}')

# 4. racesテーブルとの重複確認（日付・会場で紐付け可能か）
print(f'\n【4. レースとの紐付け可能性】')
cursor.execute('SELECT COUNT(*) FROM races WHERE race_status = "completed"')
total_races = cursor.fetchone()[0]
print(f'  総レース数: {total_races:,}件')

cursor.execute('''
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    JOIN tide t ON r.venue_code = t.venue_code AND r.race_date = t.tide_date
    WHERE r.race_status = 'completed'
''')
matched_races = cursor.fetchone()[0]
print(f'  潮位データと日付・会場が一致するレース: {matched_races:,}件 ({matched_races/total_races*100:.1f}%)')

# 5. レースとの紐付けサンプル
print(f'\n【5. 紐付けサンプル（最初の3レース）】')
cursor.execute('''
    SELECT
        r.id,
        r.venue_code,
        r.race_date,
        r.race_time,
        t.tide_time,
        t.tide_type,
        t.tide_level
    FROM races r
    JOIN tide t ON r.venue_code = t.venue_code AND r.race_date = t.tide_date
    WHERE r.race_status = 'completed' AND r.race_time IS NOT NULL
    LIMIT 3
''')
for row in cursor.fetchall():
    print(f'  レースID:{row[0]} 会場:{row[1]} 日付:{row[2]} レース時刻:{row[3]}')
    print(f'    → 潮汐時刻:{row[4]} 潮汐タイプ:{row[5]} 潮位:{row[6]}')

# 6. tide_typeの種類確認
cursor.execute('SELECT DISTINCT tide_type FROM tide')
tide_types = cursor.fetchall()
print(f'\n【6. tide_typeの種類】')
for tt in tide_types:
    cursor.execute('SELECT COUNT(*) FROM tide WHERE tide_type = ?', (tt[0],))
    count = cursor.fetchone()[0]
    print(f'  {tt[0]}: {count:,}件')

# 7. レース時刻に最も近い潮位を取得する例
print(f'\n【7. レース時刻に最も近い潮位の取得例】')
cursor.execute('''
    SELECT
        r.id,
        r.venue_code,
        r.race_date,
        r.race_time,
        MIN(ABS(
            (CAST(substr(r.race_time, 1, 2) AS INTEGER) * 60 + CAST(substr(r.race_time, 4, 2) AS INTEGER)) -
            (CAST(substr(t.tide_time, 1, 2) AS INTEGER) * 60 + CAST(substr(t.tide_time, 4, 2) AS INTEGER))
        )) as time_diff_minutes,
        t.tide_level
    FROM races r
    JOIN tide t ON r.venue_code = t.venue_code AND r.race_date = t.tide_date
    WHERE r.race_status = 'completed'
        AND r.race_time IS NOT NULL
        AND t.tide_time IS NOT NULL
    GROUP BY r.id
    LIMIT 5
''')
print('  (レースID, 会場, 日付, レース時刻, 時刻差[分], 潮位)')
for row in cursor.fetchall():
    print(f'  {row}')

conn.close()
print('\n' + '=' * 80)
