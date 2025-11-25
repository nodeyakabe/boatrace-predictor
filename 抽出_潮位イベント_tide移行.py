"""
rdmdb_tideの時系列データから潮位イベント(満潮/干潮)を抽出してtideテーブルに移行

アルゴリズム:
1. 日ごとにrdmdb_tideのsea_level_smoothed_cmデータを取得
2. 局所的な最大値(満潮)と最小値(干潮)を検出
3. tideテーブルに保存(venue_code, tide_date, tide_time, tide_type, tide_level)

観測地点→会場マッピング:
- Hakata → 福岡(22)
- Hiroshima → 宮島(17)
- Sasebo → 佐世保は無いため、近隣の大村(24)を使用
- Tokuyama → 徳山(18)
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from datetime import datetime, timedelta
from tqdm import tqdm

print("="*80)
print("潮位イベント抽出スクリプト")
print("="*80)

# 観測地点→会場コードマッピング
STATION_TO_VENUE = {
    'Hakata': '22',      # 福岡
    'Hiroshima': '17',   # 宮島
    'Sasebo': '24',      # 大村(佐世保の近隣)
    'Tokuyama': '18'     # 徳山
}

def extract_tide_events_for_day(cursor, station_name, date_str):
    """
    指定日の潮位イベント(満潮/干潮)を抽出

    Args:
        cursor: DBカーソル
        station_name: 観測地点名
        date_str: 日付(YYYY-MM-DD)

    Returns:
        list: [{'time': 'HH:MM', 'type': '満潮'/'干潮', 'level': float}, ...]
    """
    # その日の潮位データを取得(平滑値を使用)
    cursor.execute("""
        SELECT observation_datetime, sea_level_smoothed_cm
        FROM rdmdb_tide
        WHERE station_name = ?
        AND observation_datetime >= ?
        AND observation_datetime < ?
        AND sea_level_smoothed_cm IS NOT NULL
        ORDER BY observation_datetime
    """, (station_name, date_str + ' 00:00:00', date_str + ' 23:59:59'))

    rows = cursor.fetchall()

    if len(rows) < 100:  # データが少なすぎる場合はスキップ
        return []

    # データを配列に変換
    times = []
    levels = []

    for dt_str, level in rows:
        dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        times.append(dt)
        levels.append(level)

    # シンプルなピーク検出アルゴリズム
    # 1. 10分間隔でダウンサンプリング (20ポイント = 30秒×20 = 10分)
    sample_interval = 20
    sampled_times = []
    sampled_levels = []

    for i in range(0, len(levels), sample_interval):
        sampled_times.append(times[i])
        sampled_levels.append(levels[i])

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

    # 時刻でソート
    tide_events.sort(key=lambda x: x['time'])

    return tide_events


# データベース接続
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# rdmdb_tideの期間を取得
cursor.execute('SELECT MIN(observation_datetime), MAX(observation_datetime) FROM rdmdb_tide')
min_dt_str, max_dt_str = cursor.fetchone()

min_date = datetime.strptime(min_dt_str[:10], '%Y-%m-%d')
max_date = datetime.strptime(max_dt_str[:10], '%Y-%m-%d')

print(f"\nrdmdb_tideデータ期間: {min_date.strftime('%Y-%m-%d')} ～ {max_date.strftime('%Y-%m-%d')}")
print(f"対象日数: {(max_date - min_date).days + 1}日")

# 観測地点ごとに処理
total_days = 0
total_events = 0

for station_name, venue_code in STATION_TO_VENUE.items():
    print(f"\n{'='*80}")
    print(f"{station_name} → 会場{venue_code}")
    print(f"{'='*80}")

    # 日ごとに処理
    current_date = min_date
    days_processed = 0
    events_inserted = 0

    with tqdm(total=(max_date - min_date).days + 1, desc=f"{station_name} 処理中") as pbar:
        while current_date <= max_date:
            date_str = current_date.strftime('%Y-%m-%d')

            # すでにtideテーブルにデータがあるかチェック
            cursor.execute("""
                SELECT COUNT(*) FROM tide
                WHERE venue_code = ? AND tide_date = ?
            """, (venue_code, date_str))

            existing_count = cursor.fetchone()[0]

            if existing_count == 0:
                # 潮位イベントを抽出
                tide_events = extract_tide_events_for_day(cursor, station_name, date_str)

                # tideテーブルに挿入
                for event in tide_events:
                    cursor.execute("""
                        INSERT INTO tide (venue_code, tide_date, tide_time, tide_type, tide_level, created_at)
                        VALUES (?, ?, ?, ?, ?, datetime('now'))
                    """, (venue_code, date_str, event['time'], event['type'], event['level']))
                    events_inserted += 1

                if len(tide_events) > 0:
                    days_processed += 1

            current_date += timedelta(days=1)
            pbar.update(1)

            # 100日ごとにコミット
            if days_processed % 100 == 0 and days_processed > 0:
                conn.commit()

    # 最終コミット
    conn.commit()

    print(f"  処理日数: {days_processed}日")
    print(f"  抽出イベント数: {events_inserted}件")

    total_days += days_processed
    total_events += events_inserted

# 結果確認
print("\n" + "="*80)
print("最終集計")
print("="*80)
print(f"総処理日数: {total_days}日")
print(f"総イベント数: {total_events}件")

# tideテーブルの内容を確認
print("\n" + "="*80)
print("tideテーブル確認")
print("="*80)

cursor.execute("""
    SELECT venue_code, COUNT(DISTINCT tide_date) as days, COUNT(*) as events
    FROM tide
    GROUP BY venue_code
    ORDER BY venue_code
""")

rows = cursor.fetchall()
for venue_code, days, events in rows:
    print(f"  会場{venue_code}: {days}日分 ({events}件)")

# サンプルデータ表示
print("\n最新10件のサンプル:")
cursor.execute("""
    SELECT venue_code, tide_date, tide_time, tide_type, tide_level
    FROM tide
    ORDER BY tide_date DESC, tide_time DESC
    LIMIT 10
""")

for venue_code, tide_date, tide_time, tide_type, tide_level in cursor.fetchall():
    print(f"  会場{venue_code} {tide_date} {tide_time} {tide_type}: {tide_level:.1f}cm")

conn.close()

print("\n" + "="*80)
print("処理完了")
print("="*80)
