"""
データベース全体のデータ充足状況詳細調査
"""
import sqlite3
import sys
import os

# プロジェクトルートに移動
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

print('='*100)
print('データベース全体のデータ充足状況調査')
print('='*100)

# 1. races（レース基本情報）
print('\n【1. races - レース基本情報】')
cursor.execute('SELECT COUNT(*) FROM races')
total = cursor.fetchone()[0]
print(f'  総レース数: {total:,}件')

cursor.execute('SELECT COUNT(*) FROM races WHERE race_grade IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  グレード: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM races WHERE race_status IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  レース状態: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

# 2. race_details（レース詳細）
print('\n【2. race_details - レース詳細（艇別データ）】')
cursor.execute('SELECT COUNT(*) FROM race_details')
total = cursor.fetchone()[0]
print(f'  総レコード数: {total:,}件（= 総レース×6艇）')

cursor.execute('SELECT COUNT(*) FROM race_details WHERE st_time IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  STタイム: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_details WHERE actual_course IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  実際の進入コース: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_details WHERE exhibition_time IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  展示タイム: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_details WHERE chikusen_time IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  直前タイム: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_details WHERE tilt_angle IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  チルト角: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_details WHERE motor_number IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  モーター番号: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_details WHERE boat_number IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  ボート番号: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

# 3. race_conditions（レース条件）
print('\n【3. race_conditions - レース条件（天気・風・波等）】')
cursor.execute('SELECT COUNT(*) FROM race_conditions')
total = cursor.fetchone()[0]
print(f'  総レース数: {total:,}件')

cursor.execute('SELECT COUNT(*) FROM race_conditions WHERE weather IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  天気: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_conditions WHERE wind_speed IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  風速: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_conditions WHERE wave_height IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  波高: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_conditions WHERE water_temp IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  水温: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM race_conditions WHERE air_temp IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  気温: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

# 4. results（レース結果）
print('\n【4. results - レース結果】')
cursor.execute('SELECT COUNT(*) FROM results')
total = cursor.fetchone()[0]
print(f'  総レコード数: {total:,}件（= レース×最大6艇）')

cursor.execute('SELECT COUNT(*) FROM results WHERE rank IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  着順: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM results WHERE race_time IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  レースタイム: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM results WHERE kimarite IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  決まり手: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

# 5. entries（出走表）
print('\n【5. entries - 出走表（選手・モーター・ボート情報）】')
cursor.execute('SELECT COUNT(*) FROM entries')
total = cursor.fetchone()[0]
print(f'  総レコード数: {total:,}件（= レース×6艇）')

cursor.execute('SELECT COUNT(*) FROM entries WHERE racer_id IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  選手ID: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE racer_name IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  選手名: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE racer_rank IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  選手級別: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE winning_rate IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  勝率: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE second_rate IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  2連対率: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE third_rate IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  3連対率: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE motor_number IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  モーター番号: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE motor_winning_rate IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  モーター2連対率: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE boat_number IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  ボート番号: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM entries WHERE boat_winning_rate IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  ボート2連対率: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

# 6. trifecta_odds（三連単オッズ）
print('\n【6. trifecta_odds - 三連単オッズ】')
cursor.execute('SELECT COUNT(*) FROM trifecta_odds')
total = cursor.fetchone()[0]
print(f'  総レコード数: {total:,}件（= レース×120通り）')

cursor.execute('SELECT COUNT(DISTINCT race_id) FROM trifecta_odds')
races_with_odds = cursor.fetchone()[0]
print(f'  オッズ保持レース数: {races_with_odds:,}件')

cursor.execute('SELECT COUNT(*) FROM trifecta_odds WHERE odds IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  オッズ値: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

# 7. weather（天気テーブル）
print('\n【7. weather - 天気データ（会場×日別）】')
cursor.execute('SELECT COUNT(*) FROM weather')
total = cursor.fetchone()[0]
print(f'  総レコード数: {total:,}件')

cursor.execute('SELECT COUNT(*) FROM weather WHERE weather IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  天気: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM weather WHERE wind_direction IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  風向: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

cursor.execute('SELECT COUNT(*) FROM weather WHERE wind_speed IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  風速: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

# 8. exhibition_data（展示データ）
print('\n【8. exhibition_data - 展示データ（オリジナル展示）】')
cursor.execute('SELECT COUNT(*) FROM exhibition_data')
total = cursor.fetchone()[0]
print(f'  総レコード数: {total:,}件')

cursor.execute('SELECT COUNT(*) FROM exhibition_data WHERE exhibition_time IS NOT NULL')
filled = cursor.fetchone()[0]
print(f'  展示タイム: {filled:,}件 ({filled/total*100 if total else 0:.1f}%)')

# 9. payouts（払戻金）
print('\n【9. payouts - 払戻金データ】')
cursor.execute('SELECT COUNT(*) FROM payouts')
total = cursor.fetchone()[0]
print(f'  総レコード数: {total:,}件')

cursor.execute('SELECT COUNT(DISTINCT race_id) FROM payouts')
races_with_payouts = cursor.fetchone()[0]
print(f'  払戻データ保持レース数: {races_with_payouts:,}件')

# サマリー
print('\n' + '='*100)
print('データ充足サマリー')
print('='*100)

cursor.execute('SELECT COUNT(*) FROM races')
total_races = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(DISTINCT race_id) FROM trifecta_odds')
races_with_odds = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(DISTINCT race_id) FROM results')
races_with_results = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(DISTINCT race_id) FROM race_details WHERE st_time IS NOT NULL')
races_with_st = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(DISTINCT race_id) FROM race_details WHERE actual_course IS NOT NULL')
races_with_course = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(DISTINCT race_id) FROM results WHERE kimarite IS NOT NULL AND rank = "1"')
races_with_kimarite = cursor.fetchone()[0]

print(f'総レース数: {total_races:,}件')
print(f'  - オッズあり: {races_with_odds:,}件 ({races_with_odds/total_races*100:.1f}%)')
print(f'  - 結果あり: {races_with_results:,}件 ({races_with_results/total_races*100:.1f}%)')
print(f'  - STタイムあり: {races_with_st:,}件 ({races_with_st/total_races*100:.1f}%)')
print(f'  - 実進入コースあり: {races_with_course:,}件 ({races_with_course/total_races*100:.1f}%)')
print(f'  - 決まり手あり: {races_with_kimarite:,}件 ({races_with_kimarite/total_races*100:.1f}%)')

conn.close()
print('\n調査完了')
