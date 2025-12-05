"""RDMDB潮位データの簡易調査"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=' * 80)
print('RDMDB潮位データ簡易調査')
print('=' * 80)

# 1. 基本情報
cursor.execute('SELECT COUNT(*) FROM rdmdb_tide')
print(f'\nrdmdb_tide総レコード数: {cursor.fetchone()[0]:,}件')

cursor.execute('SELECT station_name, COUNT(*) FROM rdmdb_tide GROUP BY station_name')
print(f'\n観測地点別:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]:,}件')

cursor.execute('SELECT MIN(observation_datetime), MAX(observation_datetime) FROM rdmdb_tide')
min_dt, max_dt = cursor.fetchone()
print(f'\n期間: {min_dt} ~ {max_dt}')

# 2. レース総数
cursor.execute('SELECT COUNT(*) FROM races WHERE race_status = "completed"')
total_races = cursor.fetchone()[0]
print(f'\n総レース数: {total_races:,}件')

# 3. 会場とRDMDB観測地点のマッピング
venue_map = {
    '15': 'Hiroshima', '16': 'Tokuyama', '17': 'Hiroshima',
    '18': 'Hiroshima', '20': 'Hakata', '22': 'Hakata', '24': 'Sasebo'
}

# 4. サンプル: 福岡（会場22）の直近5レースで潮位データがあるか確認
print(f'\n【サンプル: 福岡(会場22)の最新5レースで潮位マッチング】')
cursor.execute('''
    SELECT r.id, r.race_date, r.race_time
    FROM races r
    WHERE r.venue_code = '22'
    AND r.race_status = 'completed'
    AND r.race_time IS NOT NULL
    ORDER BY r.race_date DESC, r.race_number DESC
    LIMIT 5
''')
races = cursor.fetchall()

for race_id, race_date, race_time in races:
    # 各レースに対して最も近い潮位データを検索（±5分）
    cursor.execute('''
        SELECT
            observation_datetime,
            sea_level_cm,
            ABS(ROUND((JULIANDAY(? || ' ' || ?) - JULIANDAY(observation_datetime)) * 1440)) as diff_min
        FROM rdmdb_tide
        WHERE station_name = 'Hakata'
        AND DATE(observation_datetime) = ?
        AND ABS(ROUND((JULIANDAY(? || ' ' || ?) - JULIANDAY(observation_datetime)) * 1440)) <= 5
        ORDER BY diff_min
        LIMIT 1
    ''', (race_date, race_time, race_date, race_date, race_time))

    tide_data = cursor.fetchone()
    if tide_data:
        obs_dt, sea_level, diff = tide_data
        print(f'  レースID {race_id}: {race_date} {race_time} → 潮位{sea_level}cm (差{diff}分)')
    else:
        print(f'  レースID {race_id}: {race_date} {race_time} → 潮位データなし')

# 5. 全会場の大まかな紐付け可能性（サンプリング方式）
print(f'\n【全会場の潮位データ紐付け可能性（サンプリング）】')
for venue_code, station in venue_map.items():
    # 各会場の最新100レースをサンプルとして確認
    cursor.execute('''
        SELECT r.id, r.race_date, r.race_time
        FROM races r
        WHERE r.venue_code = ?
        AND r.race_status = 'completed'
        AND r.race_time IS NOT NULL
        ORDER BY r.race_date DESC
        LIMIT 100
    ''', (venue_code,))

    sample_races = cursor.fetchall()
    matched_count = 0

    for race_id, race_date, race_time in sample_races:
        cursor.execute('''
            SELECT 1
            FROM rdmdb_tide
            WHERE station_name = ?
            AND DATE(observation_datetime) = ?
            AND ABS(ROUND((JULIANDAY(? || ' ' || ?) - JULIANDAY(observation_datetime)) * 1440)) <= 5
            LIMIT 1
        ''', (station, race_date, race_date, race_time))

        if cursor.fetchone():
            matched_count += 1

    if sample_races:
        coverage = matched_count / len(sample_races) * 100
        print(f'  会場{venue_code} ({station}): {matched_count}/{len(sample_races)} = {coverage:.1f}%')

conn.close()
print('\n' + '=' * 80)
