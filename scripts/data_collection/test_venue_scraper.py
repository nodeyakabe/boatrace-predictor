"""
競艇場スクレイパーの動作テスト

丸亀競艇場のスクレイパーが正しく動作するかテストします。
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.scraper.venue_specific_scraper import MarugameScraper
from datetime import datetime


def test_marugame_scraper():
    """丸亀競艇場スクレイパーのテスト"""

    print("=" * 70)
    print("丸亀競艇場スクレイパー 動作テスト")
    print("=" * 70)

    scraper = MarugameScraper()

    # テスト日付
    test_date = "2026-01-17"

    # 1. 潮汐表のテスト
    print(f"\n【1. 潮汐表取得テスト】")
    print(f"対象日: {test_date}")
    print("-" * 70)

    try:
        tide_data = scraper.get_tide_table(test_date)

        if tide_data:
            print(f"[OK] 取得成功 ({len(tide_data)}件)")
            for tide in tide_data:
                print(f"  {tide['time']} {tide['type']} (潮周り: {tide['tide_name']})")
        else:
            print("[NG] データ取得失敗 or データなし")

    except Exception as e:
        print(f"[ERROR] エラー: {e}")

    # 2. 気象データのテスト
    print(f"\n【2. 気象データ取得テスト】")
    print("-" * 70)

    try:
        weather_data = scraper.get_weather_data(test_date)

        if weather_data:
            print("[OK] 取得成功")
            print(f"  風向: {weather_data.get('wind_direction', 'N/A')}")
            print(f"  風速: {weather_data.get('wind_speed', 'N/A')} m/s")
            print(f"  気温: {weather_data.get('temperature', 'N/A')} ℃")
            print(f"  気圧: {weather_data.get('pressure', 'N/A')} hPa")
            print(f"  湿度: {weather_data.get('humidity', 'N/A')} %")
            print(f"  雨量: {weather_data.get('rainfall', 'N/A')} mm")
            print(f"  観測時刻: {weather_data.get('observed_at', 'N/A')}")
        else:
            print("[NG] データ取得失敗 or データなし")

    except Exception as e:
        print(f"[ERROR] エラー: {e}")

    # 3. 進入コース別成績のテスト
    print(f"\n【3. 進入コース別成績取得テスト】")
    print("-" * 70)

    try:
        course_stats = scraper.get_course_stats()

        if course_stats:
            print(f"[OK] 取得成功 ({len(course_stats)}コース)")
            print("\nコース | 1着率 | 2連対率 | 3連対率")
            print("-" * 40)
            for stat in course_stats:
                print(f"  {stat['course']}C   | {stat['win_rate']:5.1f}% | "
                      f"{stat['place_rate_2']:6.1f}% | {stat['place_rate_3']:6.1f}%")
        else:
            print("[NG] データ取得失敗 or データなし")

    except Exception as e:
        print(f"[ERROR] エラー: {e}")

    # 4. 前検タイムのテスト（開催中のみ有効）
    print(f"\n【4. 前検タイムランキング取得テスト】")
    print("※ 開催中でない場合はデータ取得できない可能性があります")
    print("-" * 70)

    try:
        zenken_data = scraper.get_zenken_time_ranking(test_date)

        if zenken_data:
            print(f"[OK] 取得成功 ({len(zenken_data)}件)")
            for racer in zenken_data[:5]:  # 上位5件のみ表示
                print(f"  選手{racer['racer_id']} {racer['pit']}号艇: "
                      f"{racer['time']}秒 (モーター{racer['motor_no']})")
        else:
            print("[NG] データ取得失敗 or データなし（開催中でない可能性）")

    except Exception as e:
        print(f"[ERROR] エラー: {e}")

    scraper.close()

    print("\n" + "=" * 70)
    print("テスト完了")
    print("=" * 70)


if __name__ == "__main__":
    test_marugame_scraper()
