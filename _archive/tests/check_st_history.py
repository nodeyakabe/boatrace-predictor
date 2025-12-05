import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=== ST時間データ収集履歴 ===\n')

# 全体の進捗
cursor.execute('''
    SELECT COUNT(*) FROM races
    WHERE race_date >= '2016-01-01' AND race_date <= '2025-11-12'
''')
total = cursor.fetchone()[0]

cursor.execute('''
    SELECT COUNT(*) FROM (
        SELECT r.id FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
        GROUP BY r.id
        HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) = 6
    )
''')
complete = cursor.fetchone()[0]

cursor.execute('''
    SELECT COUNT(*) FROM (
        SELECT r.id FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
        GROUP BY r.id
        HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) = 5
    )
''')
incomplete = cursor.fetchone()[0]

cursor.execute('''
    SELECT COUNT(*) FROM (
        SELECT r.id FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
        GROUP BY r.id
        HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) < 5
    )
''')
very_incomplete = cursor.fetchone()[0]

print('【全体状況: 2016-2025年】')
print(f'  総レース: {total:,}')
print(f'  ST 6/6（完全）: {complete:,} ({complete/total*100:.1f}%)')
print(f'  ST 5/6（補充対象）: {incomplete:,} ({incomplete/total*100:.1f}%)')
print(f'  ST <5（補充困難）: {very_incomplete:,} ({very_incomplete/total*100:.1f}%)')
print()

# 年度別の状況
print('【年度別の状況】')
for year in range(2016, 2026):
    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31' if year < 2025 else '2025-11-12'

    cursor.execute(f'''
        SELECT COUNT(*) FROM races
        WHERE race_date >= ? AND race_date <= ?
    ''', (start_date, end_date))
    year_total = cursor.fetchone()[0]

    if year_total == 0:
        continue

    cursor.execute(f'''
        SELECT COUNT(*) FROM (
            SELECT r.id FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
            GROUP BY r.id
            HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) = 6
        )
    ''', (start_date, end_date))
    year_complete = cursor.fetchone()[0]

    cursor.execute(f'''
        SELECT COUNT(*) FROM (
            SELECT r.id FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
            GROUP BY r.id
            HAVING COUNT(CASE WHEN rd.st_time IS NOT NULL AND rd.st_time != '' THEN 1 END) = 5
        )
    ''', (start_date, end_date))
    year_incomplete = cursor.fetchone()[0]

    bar_length = int(year_complete / year_total * 50) if year_total > 0 else 0
    bar = '#' * bar_length + '-' * (50 - bar_length)

    print(f'{year}年: {bar} {year_complete:5,}/{year_total:5,} ({year_complete/year_total*100:5.1f}%) [残り5/6: {year_incomplete:4,}]')

print()
print('【最適化版テスト結果】')
print(f'  テスト範囲: 2024-12-01 ~ 2024-12-31')
print(f'  テスト件数: 30レース（limit指定）')
print(f'  成功率: 100% (30/30)')
print(f'  処理時間: 3.0分')
print(f'  処理速度: 約10レース/分')
print()
print('【旧版との比較】')
print(f'  旧版速度: 約2レース/分')
print(f'  新版速度: 約10レース/分')
print(f'  改善率: 約5倍高速化')
print()
print('【推定完了時間】')
remaining = incomplete
old_time = remaining / 2  # 旧版: 2レース/分
new_time_3workers = remaining / 10  # 新版: 10レース/分 (3ワーカー)
new_time_5workers = remaining / 15  # 新版: 15レース/分 (5ワーカー想定)
print(f'  残りレース: {remaining:,}')
print(f'  旧版（現在実行中）: 約{old_time:.1f}分 ({old_time/60:.1f}時間)')
print(f'  新版（3ワーカー）: 約{new_time_3workers:.1f}分 ({new_time_3workers/60:.1f}時間)')
print(f'  新版（5ワーカー）: 約{new_time_5workers:.1f}分 ({new_time_5workers/60:.1f}時間)')

conn.close()
