import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=== 残りST 5/6のレース詳細 ===\n')

# 残りのST 5/6レースを確認
cursor.execute('''
    SELECT r.id, r.venue_code, r.race_date, r.race_number,
           COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) as st_count,
           GROUP_CONCAT(CASE WHEN rd.st_time IS NULL OR rd.st_time = '' THEN rd.pit_number END) as missing_pits
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    GROUP BY r.id
    HAVING st_count = 5
    ORDER BY r.race_date, r.venue_code, r.race_number
''')

remaining = cursor.fetchall()

print(f'残り件数: {len(remaining)}レース\n')

if len(remaining) > 0:
    print('詳細:')
    for race in remaining:
        race_id, venue, date, num, st_count, missing = race
        venue_int = int(venue) if venue else 0
        num_int = int(num) if num else 0
        print(f'  {date} 会場{venue_int:02d} {num_int:2d}R (race_id={race_id}): ST {st_count}/6 - 不足Pit: {missing}')

    print('\n【分析】')
    print('これらのレースは以下の理由で6/6にならない可能性があります:')
    print('  1. Web上にST時間データが存在しない（フライング等）')
    print('  2. データが破損している')
    print('  3. レースが中止になった')
    print('  4. HTMLパースに失敗している')
else:
    print('すべて完了しました！')

# 全体のサマリー
cursor.execute('''
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN (
            SELECT COUNT(*) FROM race_details rd
            WHERE rd.race_id = r.id AND rd.st_time IS NOT NULL AND rd.st_time != ''
        ) = 6 THEN 1 END) as complete,
        COUNT(CASE WHEN (
            SELECT COUNT(*) FROM race_details rd
            WHERE rd.race_id = r.id AND rd.st_time IS NOT NULL AND rd.st_time != ''
        ) < 5 THEN 1 END) as incomplete
    FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
''')

total, complete, incomplete = cursor.fetchone()

print('\n=== 全体サマリー ===')
print(f'総レース数: {total:,}')
print(f'ST 6/6（完全）: {complete:,} ({complete/total*100:.1f}%)')
print(f'ST 5/6（あと1つ）: {len(remaining):,} ({len(remaining)/total*100:.2f}%)')
print(f'ST <5（データ不足）: {incomplete:,} ({incomplete/total*100:.1f}%)')
print(f'\n補充可能なデータの完了率: {complete/(total-incomplete)*100:.1f}%')

conn.close()
