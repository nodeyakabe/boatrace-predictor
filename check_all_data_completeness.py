import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=== 2016-2025年のデータ完全性チェック ===\n')

# 1. レース基本情報
cursor.execute('''
    SELECT COUNT(*) FROM races
    WHERE race_date >= '2016-01-01' AND race_date <= '2025-11-12'
''')
total_races = cursor.fetchone()[0]

# 2. race_details（選手・ST時間データ）
cursor.execute('''
    SELECT
        COUNT(DISTINCT r.id) as races_with_details,
        COUNT(DISTINCT CASE WHEN rd_count.cnt = 6 THEN r.id END) as races_with_6_details
    FROM races r
    LEFT JOIN (
        SELECT race_id, COUNT(*) as cnt
        FROM race_details
        GROUP BY race_id
    ) rd_count ON r.id = rd_count.race_id
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
''')
races_with_details, races_with_6_details = cursor.fetchone()

# 3. results（レース結果）
cursor.execute('''
    SELECT COUNT(DISTINCT race_id) FROM results
    WHERE race_id IN (SELECT id FROM races WHERE race_date >= '2016-01-01' AND race_date <= '2025-11-12')
''')
races_with_results = cursor.fetchone()[0]

# 4. payouts（払戻金）
cursor.execute('''
    SELECT COUNT(DISTINCT race_id) FROM payouts
    WHERE race_id IN (SELECT id FROM races WHERE race_date >= '2016-01-01' AND race_date <= '2025-11-12')
''')
races_with_payouts = cursor.fetchone()[0]

# 5. ST時間の詳細
cursor.execute('''
    SELECT
        COUNT(DISTINCT r.id) as total,
        COUNT(DISTINCT CASE WHEN st_count.cnt = 6 THEN r.id END) as st_6,
        COUNT(DISTINCT CASE WHEN st_count.cnt = 5 THEN r.id END) as st_5,
        COUNT(DISTINCT CASE WHEN st_count.cnt < 5 THEN r.id END) as st_less_5
    FROM races r
    LEFT JOIN (
        SELECT race_id, COUNT(*) as cnt
        FROM race_details
        WHERE st_time IS NOT NULL AND st_time != ''
        GROUP BY race_id
    ) st_count ON r.id = st_count.race_id
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
''')
st_total, st_6, st_5, st_less_5 = cursor.fetchone()

print('【基本データ】')
print(f'総レース数: {total_races:,}')
print()

print('【race_details（選手情報・ST時間）】')
print(f'  データ有り: {races_with_details:,}/{total_races:,} ({races_with_details/total_races*100:.1f}%)')
print(f'  6艇分完全: {races_with_6_details:,}/{total_races:,} ({races_with_6_details/total_races*100:.1f}%)')
if races_with_details < total_races:
    missing = total_races - races_with_details
    print(f'  [WARNING] 不足: {missing:,}レース')
print()

print('【results（レース結果）】')
print(f'  データ有り: {races_with_results:,}/{total_races:,} ({races_with_results/total_races*100:.1f}%)')
if races_with_results < total_races:
    missing = total_races - races_with_results
    print(f'  [WARNING] 不足: {missing:,}レース')
print()

print('【payouts（払戻金）】')
print(f'  データ有り: {races_with_payouts:,}/{total_races:,} ({races_with_payouts/total_races*100:.1f}%)')
if races_with_payouts < total_races:
    missing = total_races - races_with_payouts
    print(f'  [WARNING] 不足: {missing:,}レース')
print()

print('【ST時間データ】')
print(f'  ST 6/6（完全）: {st_6:,}/{st_total:,} ({st_6/st_total*100:.1f}%)')
print(f'  ST 5/6（あと1つ）: {st_5:,}/{st_total:,} ({st_5/st_total*100:.2f}%)')
print(f'  ST <5（不完全）: {st_less_5:,}/{st_total:,} ({st_less_5/st_total*100:.1f}%)')
print()

# 6. 不足データの詳細分析
print('【データ不足の詳細】\n')

# race_details不足
cursor.execute('''
    SELECT COUNT(*) FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM race_details)
''')
no_details = cursor.fetchone()[0]
if no_details > 0:
    print(f'1. race_detailsが全くないレース: {no_details:,}')
    cursor.execute('''
        SELECT race_date, venue_code, race_number
        FROM races r
        WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
        AND r.id NOT IN (SELECT DISTINCT race_id FROM race_details)
        LIMIT 10
    ''')
    print('   サンプル（最初の10件）:')
    for row in cursor.fetchall():
        print(f'     {row[0]} 会場{int(row[1]):02d} {int(row[2]):2d}R')
    print()

# results不足
cursor.execute('''
    SELECT COUNT(*) FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM results)
''')
no_results = cursor.fetchone()[0]
if no_results > 0:
    print(f'2. resultsがないレース: {no_results:,}')
    cursor.execute('''
        SELECT race_date, venue_code, race_number
        FROM races r
        WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
        AND r.id NOT IN (SELECT DISTINCT race_id FROM results)
        ORDER BY race_date DESC
        LIMIT 10
    ''')
    print('   サンプル（最新の10件）:')
    for row in cursor.fetchall():
        print(f'     {row[0]} 会場{int(row[1]):02d} {int(row[2]):2d}R')
    print()

# payouts不足
cursor.execute('''
    SELECT COUNT(*) FROM races r
    WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
    AND r.id NOT IN (SELECT DISTINCT race_id FROM payouts)
''')
no_payouts = cursor.fetchone()[0]
if no_payouts > 0:
    print(f'3. payoutsがないレース: {no_payouts:,}')
    cursor.execute('''
        SELECT race_date, venue_code, race_number
        FROM races r
        WHERE r.race_date >= '2016-01-01' AND r.race_date <= '2025-11-12'
        AND r.id NOT IN (SELECT DISTINCT race_id FROM payouts)
        ORDER BY race_date DESC
        LIMIT 10
    ''')
    print('   サンプル（最新の10件）:')
    for row in cursor.fetchall():
        print(f'     {row[0]} 会場{int(row[1]):02d} {int(row[2]):2d}R')
    print()

print('【総合評価】')
if no_details == 0 and no_results == 0 and no_payouts == 0:
    print('[OK] すべての基本データが揃っています！')
else:
    issues = []
    if no_details > 0:
        issues.append(f'race_details: {no_details:,}レース')
    if no_results > 0:
        issues.append(f'results: {no_results:,}レース')
    if no_payouts > 0:
        issues.append(f'payouts: {no_payouts:,}レース')

    print('[WARNING] 以下のデータに不足があります:')
    for issue in issues:
        print(f'  - {issue}')

conn.close()
