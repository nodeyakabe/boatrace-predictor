"""RDMDB潮位データの構造調査とレース紐付け"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=' * 80)
print('RDMDB潮位データ構造調査')
print('=' * 80)

# 1. rdmdb_tideテーブルの構造とサンプル
print('\n【1. rdmdb_tideテーブル】')
cursor.execute('PRAGMA table_info(rdmdb_tide)')
columns = cursor.fetchall()
print(f'カラム構造:')
for col in columns:
    print(f'  {col[1]}: {col[2]}')

cursor.execute('SELECT COUNT(*) FROM rdmdb_tide')
rdmdb_count = cursor.fetchone()[0]
print(f'\n総レコード数: {rdmdb_count:,}件')

cursor.execute('SELECT * FROM rdmdb_tide LIMIT 5')
print(f'\nサンプルデータ（最初の5件）:')
for row in cursor.fetchall():
    print(f'  {row}')

# 2. 観測地点（station_name）別の分布
cursor.execute('''
    SELECT station_name, COUNT(*) as count
    FROM rdmdb_tide
    GROUP BY station_name
    ORDER BY count DESC
''')
print(f'\n【2. 観測地点別のデータ数】')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]:,}件')

# 3. 日付範囲
cursor.execute('SELECT MIN(observation_datetime), MAX(observation_datetime) FROM rdmdb_tide')
min_date, max_date = cursor.fetchone()
print(f'\n【3. データ期間】')
print(f'  最古: {min_date}')
print(f'  最新: {max_date}')

# 4. 競艇場とRDMDB観測地点のマッピング（調査結果より）
venue_station_map = {
    '15': 'Hiroshima',  # 児島 → 広島
    '16': 'Tokuyama',   # 鳴門 → 徳山
    '17': 'Hiroshima',  # 丸亀 → 広島
    '18': 'Hiroshima',  # 宮島 → 広島
    '20': 'Hakata',     # 若松 → 博多
    '22': 'Hakata',     # 福岡 → 博多
    '24': 'Sasebo',     # 大村 → 佐世保
}

print(f'\n【4. 競艇場とRDMDB観測地点のマッピング】')
for venue, station in venue_station_map.items():
    print(f'  会場{venue} → {station}')

# 5. レースとの紐付け可能性チェック
print(f'\n【5. レースとの紐付け可能性】')
cursor.execute('SELECT COUNT(*) FROM races WHERE race_status = "completed"')
total_races = cursor.fetchone()[0]
print(f'  総レース数: {total_races:,}件')

# 各会場ごとにチェック
for venue, station in venue_station_map.items():
    cursor.execute('''
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_status = 'completed'
        AND r.venue_code = ?
    ''', (venue,))
    venue_races = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        JOIN rdmdb_tide rt ON
            rt.station_name = ? AND
            DATE(r.race_date) = DATE(rt.observation_datetime)
        WHERE r.race_status = 'completed'
        AND r.venue_code = ?
    ''', (station, venue))
    matched_races = cursor.fetchone()[0]

    if venue_races > 0:
        coverage = matched_races / venue_races * 100
        print(f'  会場{venue}: {matched_races}/{venue_races} = {coverage:.1f}%')

# 6. レース時刻との精密マッチング例（最初の5レース）
print(f'\n【6. レース時刻での精密マッチング例】')
cursor.execute('''
    SELECT
        r.id,
        r.venue_code,
        r.race_date,
        r.race_time,
        rt.observation_datetime,
        rt.sea_level_cm
    FROM races r
    JOIN rdmdb_tide rt ON
        rt.station_name = 'Hakata' AND
        DATE(r.race_date) = DATE(rt.observation_datetime) AND
        TIME(r.race_time) = TIME(rt.observation_datetime)
    WHERE r.race_status = 'completed'
    AND r.venue_code = '22'
    AND r.race_time IS NOT NULL
    LIMIT 5
''')
print('  (レースID, 会場, 日付, レース時刻, 観測日時, 潮位[cm])')
for row in cursor.fetchall():
    print(f'  {row}')

# 7. 時刻が完全一致しない場合の最近接マッチング
print(f'\n【7. 最近接時刻マッチング（±5分以内）】')
cursor.execute('''
    SELECT
        r.id,
        r.venue_code,
        r.race_date,
        r.race_time,
        rt.observation_datetime,
        rt.sea_level_cm,
        ROUND((JULIANDAY(r.race_date || ' ' || r.race_time) - JULIANDAY(rt.observation_datetime)) * 1440) as time_diff_minutes
    FROM races r
    JOIN rdmdb_tide rt ON
        rt.station_name = 'Hakata' AND
        DATE(r.race_date) = DATE(rt.observation_datetime) AND
        ABS(ROUND((JULIANDAY(r.race_date || ' ' || r.race_time) - JULIANDAY(rt.observation_datetime)) * 1440)) <= 5
    WHERE r.race_status = 'completed'
    AND r.venue_code = '22'
    AND r.race_time IS NOT NULL
    ORDER BY r.id
    LIMIT 5
''')
print('  (レースID, 会場, 日付, レース時刻, 観測日時, 潮位[cm], 時刻差[分])')
for row in cursor.fetchall():
    print(f'  {row}')

# 8. 全会場の紐付け可能レース数を集計
print(f'\n【8. 全会場の潮位データ紐付け可能性まとめ】')
total_matched = 0
for venue, station in venue_station_map.items():
    cursor.execute('''
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        JOIN rdmdb_tide rt ON
            rt.station_name = ? AND
            DATE(r.race_date) = DATE(rt.observation_datetime) AND
            ABS(ROUND((JULIANDAY(r.race_date || ' ' || r.race_time) - JULIANDAY(rt.observation_datetime)) * 1440)) <= 5
        WHERE r.race_status = 'completed'
        AND r.venue_code = ?
        AND r.race_time IS NOT NULL
    ''', (station, venue))
    matched = cursor.fetchone()[0]
    total_matched += matched

print(f'  紐付け可能レース総数: {total_matched:,}件 / {total_races:,}件 = {total_matched/total_races*100:.1f}%')

conn.close()
print('\n' + '=' * 80)
