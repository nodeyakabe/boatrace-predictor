"""
潮位イベント抽出のテストスクリプト
1日分のデータで満潮/干潮を正しく検出できるか確認
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from datetime import datetime
import numpy as np
from scipy.signal import argrelextrema

print("="*80)
print("潮位イベント抽出テスト")
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

levels_array = np.array(levels)

print(f"潮位範囲: {min(levels):.1f}cm ～ {max(levels):.1f}cm")

# 潮位の変化パターンを確認
print("\n潮位変化サンプル(1時間ごと):")
for i in range(0, min(24, len(levels)), 120):  # 120 = 2分間隔 * 60 = 1時間
    print(f"  {times[i].strftime('%H:%M')}: {levels[i]:.1f}cm")

# 局所的な最大値(満潮)と最小値(干潮)を検出
# order値を変更してテスト
for order in [10, 30, 60, 120]:
    max_indices = argrelextrema(levels_array, np.greater, order=order)[0]
    min_indices = argrelextrema(levels_array, np.less, order=order)[0]
    print(f"\norder={order}: 満潮{len(max_indices)}回, 干潮{len(min_indices)}回")

# 最終的にorder=120を使用
order = 120  # 120個のデータポイント = 60分(1時間)範囲で極値検出

max_indices = argrelextrema(levels_array, np.greater, order=order)[0]
min_indices = argrelextrema(levels_array, np.less, order=order)[0]

print(f"\n【最終設定: order={order}】")
print(f"検出された満潮: {len(max_indices)}回")
print(f"検出された干潮: {len(min_indices)}回")

# 満潮イベント
print("\n【満潮】")
for idx in max_indices:
    print(f"  {times[idx].strftime('%H:%M')}: {levels[idx]:.1f}cm")

# 干潮イベント
print("\n【干潮】")
for idx in min_indices:
    print(f"  {times[idx].strftime('%H:%M')}: {levels[idx]:.1f}cm")

# 時系列順に表示
tide_events = []

for idx in max_indices:
    tide_events.append({
        'time': times[idx],
        'type': '満潮',
        'level': levels[idx]
    })

for idx in min_indices:
    tide_events.append({
        'time': times[idx],
        'type': '干潮',
        'level': levels[idx]
    })

tide_events.sort(key=lambda x: x['time'])

print("\n【時系列順】")
for event in tide_events:
    print(f"  {event['time'].strftime('%H:%M')} {event['type']}: {event['level']:.1f}cm")

conn.close()

print("\n" + "="*80)
print("テスト完了")
print("="*80)
