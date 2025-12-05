"""
潮位イベント抽出v3のテストスクリプト
シンプルな転換点検出アルゴリズムを使用
"""
import sys
import io
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
from datetime import datetime

print("="*80)
print("潮位イベント抽出テストv3 - シンプルな転換点検出")
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

# シンプルなピーク検出
# 1. 10分間隔でダウンサンプリング (20ポイント = 30秒×20 = 10分)
sample_interval = 20
sampled_times = []
sampled_levels = []

for i in range(0, len(levels), sample_interval):
    sampled_times.append(times[i])
    sampled_levels.append(levels[i])

print(f"\nダウンサンプリング後: {len(sampled_levels)}ポイント (10分間隔)")

# 2. 移動平均でさらに平滑化 (3ポイント = 30分)
smoothed_levels = []
window = 3

for i in range(len(sampled_levels)):
    start = max(0, i - window // 2)
    end = min(len(sampled_levels), i + window // 2 + 1)
    avg = sum(sampled_levels[start:end]) / (end - start)
    smoothed_levels.append(avg)

# 3. 転換点を検出 (上昇から下降、下降から上昇)
tide_events = []
rising = None  # None, True (上昇中), False (下降中)

for i in range(1, len(smoothed_levels)):
    diff = smoothed_levels[i] - smoothed_levels[i-1]

    if diff > 0.5:  # 上昇
        if rising == False:  # 下降から上昇に転換 = 干潮
            tide_events.append({
                'time': sampled_times[i-1].strftime('%H:%M'),
                'type': '干潮',
                'level': sampled_levels[i-1]
            })
        rising = True
    elif diff < -0.5:  # 下降
        if rising == True:  # 上昇から下降に転換 = 満潮
            tide_events.append({
                'time': sampled_times[i-1].strftime('%H:%M'),
                'type': '満潮',
                'level': sampled_levels[i-1]
            })
        rising = False

print(f"\n転換点検出: {len(tide_events)}イベント")

# 結果表示
tide_events.sort(key=lambda x: x['time'])

print("\n【時系列順】")
for event in tide_events:
    print(f"  {event['time']} {event['type']}: {event['level']:.1f}cm")

conn.close()

print("\n" + "="*80)
print("テスト完了")
print("="*80)
