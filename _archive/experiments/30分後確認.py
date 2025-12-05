"""
30分後の進捗確認スクリプト
"""
import sqlite3
from datetime import datetime

print("="*80)
print(f"データ収集進捗確認 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 風向データの状況
cursor.execute("SELECT COUNT(*) FROM weather")
total_weather = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM weather WHERE wind_direction IS NOT NULL")
wind_with_direction = cursor.fetchone()[0]

print(f"\n【風向データ】")
print(f"  総天候レコード: {total_weather}")
print(f"  風向あり: {wind_with_direction}")
print(f"  風向なし: {total_weather - wind_with_direction}")
print(f"  風向カバー率: {wind_with_direction/total_weather*100:.1f}%")

# 最新レースの確認
cursor.execute("""
    SELECT r.venue_code, r.race_date, r.race_number, r.created_at
    FROM races r
    ORDER BY r.created_at DESC
    LIMIT 1
""")
latest = cursor.fetchone()

if latest:
    venue, date, rno, created = latest
    print(f"\n【最新収集レース】")
    print(f"  場{venue} {date} R{rno}")
    print(f"  収集時刻: {created}")

    # 風向チェック
    cursor.execute("""
        SELECT wind_direction FROM weather
        WHERE venue_code = ? AND weather_date = ?
    """, (venue, date))
    result = cursor.fetchone()
    wind_dir = result[0] if result and result[0] else "NULL"
    print(f"  風向: {wind_dir}")

# 2023-2025のデータ
cursor.execute("""
    SELECT COUNT(*) FROM races
    WHERE race_date >= '2023-11-01' AND race_date <= '2025-10-31'
""")
target_races = cursor.fetchone()[0]

print(f"\n【2023-2025データ】")
print(f"  レース数: {target_races}")

conn.close()

print("\n" + "="*80)
print("次回確認: 1時間後")
print("="*80)
