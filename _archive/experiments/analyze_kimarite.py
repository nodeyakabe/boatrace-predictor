"""決まり手データの詳細調査"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('=' * 80)
print('決まり手（kimarite）データの詳細調査')
print('=' * 80)

# 総レース数
cursor.execute('SELECT COUNT(*) FROM races')
total_races = cursor.fetchone()[0]
print(f'\n総レース数: {total_races:,}件')

# resultsテーブルの構造を確認
print('\n【resultsテーブルの構造】')
cursor.execute('PRAGMA table_info(results)')
columns = [col[1] for col in cursor.fetchall()]
print(f'カラム: {columns}')

# resultsテーブルの件数
cursor.execute('SELECT COUNT(*) FROM results')
results_total = cursor.fetchone()[0]
print(f'\nresults総件数: {results_total:,}件')

# サンプルデータを確認
print('\n【resultsのサンプルデータ】')
cursor.execute('SELECT * FROM results LIMIT 3')
for row in cursor.fetchall():
    print(row)

# 決まり手データの状況
cursor.execute('''
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN kimarite IS NOT NULL AND kimarite != '' THEN 1 END) as with_kimarite,
        COUNT(CASE WHEN kimarite IS NULL OR kimarite = '' THEN 1 END) as without_kimarite
    FROM results
''')
row = cursor.fetchone()
print(f'\nresults内の決まり手データ:')
print(f'  総件数: {row[0]:,}件')
print(f'  決まり手あり: {row[1]:,}件 ({row[1]/row[0]*100:.1f}%)')
print(f'  決まり手なし: {row[2]:,}件 ({row[2]/row[0]*100:.1f}%)')

# 決まり手の種類を確認
print('\n【決まり手の種類と件数】')
cursor.execute('''
    SELECT kimarite, COUNT(*) as count
    FROM results
    WHERE kimarite IS NOT NULL AND kimarite != ''
    GROUP BY kimarite
    ORDER BY count DESC
''')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]:,}件')

# 着順別の決まり手データ有無
print('\n【着順別の決まり手データ保有率】')
cursor.execute('''
    SELECT
        rank,
        COUNT(*) as total,
        COUNT(CASE WHEN kimarite IS NOT NULL AND kimarite != '' THEN 1 END) as with_kimarite
    FROM results
    WHERE rank IS NOT NULL
    GROUP BY rank
    ORDER BY rank
''')
for row in cursor.fetchall():
    total = row[1]
    with_k = row[2]
    pct = with_k / total * 100 if total > 0 else 0
    print(f'  {row[0]}着: {total:,}件中 {with_k:,}件 ({pct:.1f}%)')

# レース単位での決まり手データ有無
print('\n【レース単位での決まり手データ】')
cursor.execute('''
    SELECT
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT CASE WHEN res.kimarite IS NOT NULL AND res.kimarite != '' THEN res.race_id END) as races_with_kimarite
    FROM races r
    LEFT JOIN results res ON r.id = res.race_id
''')
row = cursor.fetchone()
races_with = row[1]
print(f'総レース数: {total_races:,}件')
print(f'決まり手データのあるレース: {races_with:,}件 ({races_with/total_races*100:.1f}%)')

# 期間別の決まり手データ保有率
print('\n【期間別の決まり手データ保有率（直近10年）】')
cursor.execute('''
    SELECT
        strftime('%Y', r.race_date) as year,
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT CASE WHEN res.kimarite IS NOT NULL AND res.kimarite != '' THEN res.race_id END) as races_with_kimarite
    FROM races r
    LEFT JOIN results res ON r.id = res.race_id
    GROUP BY year
    ORDER BY year DESC
    LIMIT 10
''')
for row in cursor.fetchall():
    total_r = row[1]
    with_r = row[2]
    pct = with_r / total_r * 100 if total_r > 0 else 0
    print(f'  {row[0]}年: {total_r:,}件中 {with_r:,}件 ({pct:.1f}%)')

# 会場別の決まり手データ保有率
print('\n【会場別の決まり手データ保有率（上位10会場）】')
cursor.execute('''
    SELECT
        v.name,
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT CASE WHEN res.kimarite IS NOT NULL AND res.kimarite != '' THEN res.race_id END) as races_with_kimarite
    FROM races r
    INNER JOIN venues v ON r.venue_code = v.code
    LEFT JOIN results res ON r.id = res.race_id
    GROUP BY r.venue_code, v.name
    ORDER BY total_races DESC
    LIMIT 10
''')
for row in cursor.fetchall():
    venue = row[0]
    total_r = row[1]
    with_r = row[2]
    pct = with_r / total_r * 100 if total_r > 0 else 0
    print(f'  {venue}: {total_r:,}件中 {with_r:,}件 ({pct:.1f}%)')

# winning_techniqueカラムも確認
print('\n【winning_techniqueカラムの状況】')
cursor.execute('''
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN winning_technique IS NOT NULL AND winning_technique != '' THEN 1 END) as with_wt,
        COUNT(CASE WHEN winning_technique IS NULL OR winning_technique = '' THEN 1 END) as without_wt
    FROM results
''')
row = cursor.fetchone()
print(f'  総件数: {row[0]:,}件')
print(f'  winning_techniqueあり: {row[1]:,}件 ({row[1]/row[0]*100:.1f}%)')
print(f'  winning_techniqueなし: {row[2]:,}件 ({row[2]/row[0]*100:.1f}%)')

# 両方のカラムの関係を確認
print('\n【kimariteとwinning_techniqueの関係】')
cursor.execute('''
    SELECT
        COUNT(CASE WHEN (kimarite IS NOT NULL AND kimarite != '') AND (winning_technique IS NOT NULL AND winning_technique != '') THEN 1 END) as both,
        COUNT(CASE WHEN (kimarite IS NOT NULL AND kimarite != '') AND (winning_technique IS NULL OR winning_technique = '') THEN 1 END) as only_kimarite,
        COUNT(CASE WHEN (kimarite IS NULL OR kimarite = '') AND (winning_technique IS NOT NULL AND winning_technique != '') THEN 1 END) as only_wt,
        COUNT(CASE WHEN (kimarite IS NULL OR kimarite = '') AND (winning_technique IS NULL OR winning_technique = '') THEN 1 END) as neither
    FROM results
''')
row = cursor.fetchone()
total = sum(row)
print(f'  両方あり: {row[0]:,}件 ({row[0]/total*100:.1f}%)')
print(f'  kimariteのみ: {row[1]:,}件 ({row[1]/total*100:.1f}%)')
print(f'  winning_techniqueのみ: {row[2]:,}件 ({row[2]/total*100:.1f}%)')
print(f'  両方なし: {row[3]:,}件 ({row[3]/total*100:.1f}%)')

conn.close()
print('\n' + '=' * 80)
