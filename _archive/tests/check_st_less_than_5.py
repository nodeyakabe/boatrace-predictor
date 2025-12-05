import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# ST <5のレースを10個ピックアップ
cursor.execute('''
    SELECT r.id, r.venue_code, r.race_date, r.race_number,
           COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2020-01-01'
    GROUP BY r.id
    HAVING st_count < 5
    ORDER BY r.race_date DESC
    LIMIT 10
''')

print('=== ST <5のレースサンプル（2020年以降、最新10件）===')
print()

races = cursor.fetchall()
for race in races:
    race_id, venue_code, race_date, race_number, st_count = race
    # 日付をYYYYMMDD形式に変換
    date_yyyymmdd = race_date.replace('-', '')
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={venue_code}&hd={date_yyyymmdd}"

    print(f'Race ID: {race_id}')
    print(f'  会場: {venue_code}, 日付: {race_date}, レース: {race_number}R')
    print(f'  ST時間数: {st_count}/6')
    print(f'  URL: {url}')
    print()

conn.close()
