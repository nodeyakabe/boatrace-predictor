"""
潮位イベント抽出v2のテストスクリプト
手動ピーク検出アルゴリズムを使用
"""
import sys
import io
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
from datetime import datetime

print("="*80)
print("潮位イベント抽出テストv2")
print("="*80)

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# テスト: 2022-11-01のHakataデータ
test_date = '2022-11-01'
station_name = 'Hakata'

print(f"\nテスト対象: {station_name} {test_date}")

# データ取得
cursor.execute("""
    SELECT observation_datetime, sea_level_smoothed_cm
    FROM rdmdb_tide
    WHERE station_name = ?
    AND observation_datetime >= ?
    AND observation_datetime < ?
    AND sea_level_smoothed_cm IS NOT NULL
    ORDER BY observation_datetime
""", (station_name, test_date + ' 00:00:00', test_date + ' 23:59:59'))

rows = cursor.fetchall()

print(f"データ件数: {len(rows)}件")

if len(rows) == 0:
    print("データが見つかりません")
    sys.exit(1)

# データを配列に変換
times = []
levels = []

for dt_str, level in rows:
    dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    times.append(dt)
    levels.append(level)

print(f"潮位範囲: {min(levels):.1f}cm ～ {max(levels):.1f}cm")

# 手動ピーク検出
window = 120  # 60分間隔のウィンドウ
tide_events = []

print(f"\nウィンドウサイズ: {window}ポイント (60分)")

for i in range(window, len(levels) - window):
    start = i - window
    end = i + window + 1

    local_levels = levels[start:end]
    local_max = max(local_levels)
    local_min = min(local_levels)

    # 現在のポイントが局所的な最大値か
    if levels[i] == local_max and levels[i] > levels[i-1] and levels[i] > levels[i+1]:
        tide_events.append({
            'time': times[i].strftime('%H:%M'),
            'type': '満潮',
            'level': levels[i],
            'index': i
        })

    # 現在のポイントが局所的な最小値か
    elif levels[i] == local_min and levels[i] < levels[i-1] and levels[i] < levels[i+1]:
        tide_events.append({
            'time': times[i].strftime('%H:%M'),
            'type': '干潮',
            'level': levels[i],
            'index': i
        })

print(f"初期検出: {len(tide_events)}イベント")

# 近接イベント除外
filtered_events = []
last_index_by_type = {'満潮': -999, '干潮': -999}

for event in tide_events:
    time_diff = event['index'] - last_index_by_type[event['type']]

    if time_diff > window:  # 60分以上離れている
        filtered_events.append(event)
        last_index_by_type[event['type']] = event['index']

print(f"フィルタ後: {len(filtered_events)}イベント")

# 結果表示
filtered_events.sort(key=lambda x: x['time'])

print("\n【時系列順】")
for event in filtered_events:
    print(f"  {event['time']} {event['type']}: {event['level']:.1f}cm")

conn.close()

print("\n" + "="*80)
print("テスト完了")
print("="*80)
