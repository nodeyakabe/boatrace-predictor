"""
天候・水面データの状況を確認
"""
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('data/boatrace.db')
c = conn.cursor()

print("=" * 80)
print("天候・水面データ状況確認")
print("=" * 80)
print()

# racesテーブル構造
print("【racesテーブル構造】")
c.execute('PRAGMA table_info(races)')
for row in c.fetchall():
    print(f"  {row[1]:20s} {row[2]}")
print()

# 天候データのサンプル
print("【天候データサンプル】")
c.execute("""
    SELECT weather, wind_direction, wind_speed, water_temp, wave_height
    FROM races
    WHERE weather IS NOT NULL
    LIMIT 5
""")
for row in c.fetchall():
    print(f"  天気:{row[0]:6s} 風向:{row[1]:6s} 風速:{row[2] if row[2] else 'N/A':>4}m  水温:{row[3] if row[3] else 'N/A':>4}℃  波高:{row[4] if row[4] else 'N/A':>4}cm")
print()

# データ充足率
print("【データ充足率】")
c.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN weather IS NOT NULL THEN 1 ELSE 0 END) as has_weather,
        SUM(CASE WHEN wind_speed IS NOT NULL THEN 1 ELSE 0 END) as has_wind_speed,
        SUM(CASE WHEN water_temp IS NOT NULL THEN 1 ELSE 0 END) as has_water_temp,
        SUM(CASE WHEN wave_height IS NOT NULL THEN 1 ELSE 0 END) as has_wave
    FROM races
""")

total, has_weather, has_wind, has_water, has_wave = c.fetchone()

print(f"  全レース数: {total:,}レース")
print(f"  天気データ: {has_weather:,}件 ({has_weather/total*100:5.1f}%)")
print(f"  風速データ: {has_wind:,}件 ({has_wind/total*100:5.1f}%)")
print(f"  水温データ: {has_water:,}件 ({has_water/total*100:5.1f}%)")
print(f"  波高データ: {has_wave:,}件 ({has_wave/total*100:5.1f}%)")
print()

# 月別の充足率
print("【月別データ充足率】")
c.execute("""
    SELECT
        substr(race_date, 1, 7) as month,
        COUNT(*) as total,
        SUM(CASE WHEN weather IS NOT NULL THEN 1 ELSE 0 END) as has_weather,
        SUM(CASE WHEN wind_speed IS NOT NULL THEN 1 ELSE 0 END) as has_wind
    FROM races
    GROUP BY month
    ORDER BY month DESC
    LIMIT 12
""")

print(f"  {'月':8s} {'レース数':>8s} {'天気':>8s} {'風速':>8s}")
print("  " + "-" * 36)
for month, total, weather, wind in c.fetchall():
    print(f"  {month:8s} {total:8d} {weather/total*100:7.1f}% {wind/total*100:7.1f}%")

conn.close()

print()
print("=" * 80)
