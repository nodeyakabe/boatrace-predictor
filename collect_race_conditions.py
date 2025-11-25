"""
レース条件データの手動入力スクリプト
天候、風向、風速、波高などのレース当日のコンディションを入力
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH


def input_race_conditions(race_id: int):
    """レース条件を対話的に入力"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # レース情報を取得
    cursor.execute("""
        SELECT r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.id = ?
    """, (race_id,))

    race_info = cursor.fetchone()
    if not race_info:
        print(f"エラー: レースID {race_id} が見つかりません")
        conn.close()
        return

    race_date, venue_code, race_number = race_info

    print("=" * 80)
    print(f"レース条件入力: {race_date} 会場{int(venue_code):02d} {int(race_number):2d}R")
    print("=" * 80)

    # 天候
    print("\n天候を選択してください:")
    print("  1. 晴")
    print("  2. 曇")
    print("  3. 雨")
    print("  4. 雪")

    while True:
        weather_input = input("天候 (1-4): ").strip()
        weather_map = {'1': '晴', '2': '曇', '3': '雨', '4': '雪'}
        if weather_input in weather_map:
            weather = weather_map[weather_input]
            break
        print("  ※ 1～4で選択してください")

    # 風向
    print("\n風向を選択してください:")
    print("  1. 無風")
    print("  2. 向い風")
    print("  3. 追い風")
    print("  4. 横風")

    while True:
        wind_dir_input = input("風向 (1-4): ").strip()
        wind_dir_map = {'1': '無風', '2': '向い風', '3': '追い風', '4': '横風'}
        if wind_dir_input in wind_dir_map:
            wind_direction = wind_dir_map[wind_dir_input]
            break
        print("  ※ 1～4で選択してください")

    # 風速
    while True:
        wind_speed_input = input("風速 (m/s、例: 3.5): ").strip()
        if not wind_speed_input:
            wind_speed = None
            break
        try:
            wind_speed = float(wind_speed_input)
            if 0 <= wind_speed <= 20.0:
                break
            else:
                print("  ※ 0～20.0m/sの範囲で入力してください")
        except ValueError:
            print("  ※ 数値で入力してください")

    # 波高
    while True:
        wave_input = input("波高 (cm、例: 3): ").strip()
        if not wave_input:
            wave_height = None
            break
        try:
            wave_height = int(wave_input)
            if 0 <= wave_height <= 30:
                break
            else:
                print("  ※ 0～30cmの範囲で入力してください")
        except ValueError:
            print("  ※ 整数で入力してください")

    # 気温
    while True:
        temp_input = input("気温 (℃、例: 25.5): ").strip()
        if not temp_input:
            temperature = None
            break
        try:
            temperature = float(temp_input)
            if -10.0 <= temperature <= 45.0:
                break
            else:
                print("  ※ -10.0～45.0℃の範囲で入力してください")
        except ValueError:
            print("  ※ 数値で入力してください")

    # 水温
    while True:
        water_temp_input = input("水温 (℃、例: 20.0): ").strip()
        if not water_temp_input:
            water_temperature = None
            break
        try:
            water_temperature = float(water_temp_input)
            if 0 <= water_temperature <= 40.0:
                break
            else:
                print("  ※ 0～40.0℃の範囲で入力してください")
        except ValueError:
            print("  ※ 数値で入力してください")

    collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # データベースに保存
    cursor.execute("""
        INSERT OR REPLACE INTO race_conditions (
            race_id,
            weather,
            wind_direction,
            wind_speed,
            wave_height,
            temperature,
            water_temperature,
            collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (race_id, weather, wind_direction, wind_speed, wave_height,
          temperature, water_temperature, collected_at))

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("レース条件の入力が完了しました")
    print("=" * 80)
    print(f"\n入力内容:")
    print(f"  天候: {weather}")
    print(f"  風向: {wind_direction}")
    print(f"  風速: {wind_speed}m/s" if wind_speed else "  風速: (未入力)")
    print(f"  波高: {wave_height}cm" if wave_height else "  波高: (未入力)")
    print(f"  気温: {temperature}℃" if temperature else "  気温: (未入力)")
    print(f"  水温: {water_temperature}℃" if water_temperature else "  水温: (未入力)")
    print("=" * 80)


def main():
    if len(sys.argv) < 2:
        print("使用方法: python collect_race_conditions.py <race_id>")
        print("例: python collect_race_conditions.py 12345")
        return

    try:
        race_id = int(sys.argv[1])
        input_race_conditions(race_id)
    except ValueError:
        print("エラー: race_id は整数で指定してください")


if __name__ == "__main__":
    main()
