"""
直前情報の気象データ活用テスト

Phase 1-3の実装効果を確認:
- Phase 1: race_conditions優先参照
- Phase 2: 気温・水温活用
- Phase 3: 天候コード活用

最近のデータ（2025年12月）で動作確認
"""
import os
import sys
import sqlite3

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.beforeinfo_scorer import BeforeInfoScorer
from src.analysis.weather_adjuster import WeatherAdjuster


def test_beforeinfo_scorer():
    """BeforeInfoScorerのテスト（Phase 2: 気温・水温活用）"""
    print("=" * 80)
    print("Phase 2テスト: BeforeInfoScorer（気温・水温活用）")
    print("=" * 80)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 2025年12月10日のレース（天候データが100%揃っている）
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number,
               rc.temperature, rc.water_temperature, rc.weather
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date = '2025-12-10'
          AND rc.weather IS NOT NULL
        LIMIT 1
    """)

    row = cursor.fetchone()
    if not row:
        print("テストデータが見つかりません")
        conn.close()
        return

    race_id = row[0]
    venue_code = row[1]
    race_number = row[2]
    temperature = row[3]
    water_temp = row[4]
    weather_condition = row[5]

    print(f"\n【テスト対象レース】")
    print(f"  レースID: {race_id}")
    print(f"  会場: {venue_code}, R{race_number}")
    print(f"  気温: {temperature}℃, 水温: {water_temp}℃")
    print(f"  天候: {weather_condition}")
    print()

    # BeforeInfoScorerでスコア計算
    scorer = BeforeInfoScorer()

    for pit in range(1, 7):
        result = scorer.calculate_beforeinfo_score(race_id, pit)

        print(f"【{pit}号艇】")
        print(f"  総合スコア: {result['total_score']:.2f}点")
        print(f"    - 展示タイム: {result['exhibition_time_score']:.2f}点")
        print(f"    - ST: {result['st_score']:.2f}点")
        print(f"    - 進入: {result['entry_score']:.2f}点")
        print(f"    - 前走: {result['prev_race_score']:.2f}点")
        print(f"    - チルト・風: {result['tilt_wind_score']:.2f}点")
        print(f"    - 部品・重量: {result['parts_weight_score']:.2f}点")
        print(f"    - 気象条件: {result['weather_score']:.2f}点 ← NEW!")
        print(f"  信頼度: {result['confidence']:.3f}")
        print()

    conn.close()


def test_weather_adjuster():
    """WeatherAdjusterのテスト（Phase 3: 天候コード活用）"""
    print("=" * 80)
    print("Phase 3テスト: WeatherAdjuster（天候コード活用）")
    print("=" * 80)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 雨天のレースを探す
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number,
               rc.temperature, rc.water_temperature, rc.wind_speed,
               rc.wave_height, rc.weather, rc.wind_direction
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date >= '2025-12-01'
          AND rc.weather = '雨'
        LIMIT 1
    """)

    row = cursor.fetchone()

    if not row:
        # 雨天がなければ晴天のレースでテスト
        print("※ 雨天レースが見つからないため、晴天レースでテスト\n")
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number,
                   rc.temperature, rc.water_temperature, rc.wind_speed,
                   rc.wave_height, rc.weather, rc.wind_direction
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            WHERE r.race_date = '2025-12-10'
            LIMIT 1
        """)
        row = cursor.fetchone()

    if not row:
        print("テストデータが見つかりません")
        conn.close()
        return

    venue_code = row[1]
    race_number = row[2]
    temperature = row[3]
    water_temp = row[4]
    wind_speed = row[5]
    wave_height = row[6]
    weather_condition = row[7]
    wind_direction = row[8]

    print(f"【テスト対象レース】")
    print(f"  会場: {venue_code}, R{race_number}")
    print(f"  気温: {temperature}℃, 水温: {water_temp}℃")
    print(f"  風速: {wind_speed}m, 波高: {wave_height}cm")
    print(f"  天候: {weather_condition}")
    print(f"  風向: {wind_direction}")
    print()

    # WeatherAdjusterで補正計算
    adjuster = WeatherAdjuster()

    for course in range(1, 7):
        result = adjuster.calculate_adjustment(
            venue_code,
            course,
            wind_speed,
            wave_height,
            wind_direction,
            weather_condition  # NEW: 天候条件
        )

        print(f"【{course}コース】")
        print(f"  補正値: {result['adjustment']:+.3f} ({result['adjustment']*100:+.1f}%)")
        print(f"  理由: {result['reason']}")
        print(f"  天候条件: {result['weather_condition']} ← NEW!")
        print()

    conn.close()


def test_data_source():
    """データソーステスト（Phase 1: race_conditions優先参照）"""
    print("=" * 80)
    print("Phase 1テスト: データソース確認（race_conditions優先）")
    print("=" * 80)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 2025年12月10日のデータ
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN rc.weather IS NOT NULL AND rc.weather != '' THEN 1 END) as has_weather
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date = '2025-12-10'
    """)

    row = cursor.fetchone()
    total = row[0]
    has_weather = row[1]

    print(f"\n【2025年12月10日のデータ】")
    print(f"  総レース数: {total}件")
    print(f"  天候データあり: {has_weather}件 ({has_weather/total*100:.1f}%)")

    if has_weather == total:
        print("  OK: race_conditionsテーブルに完全な天候データがあります")
    else:
        print(f"  WARNING: {total - has_weather}件のレースに天候データがありません")

    print()

    # サンプルデータを表示
    cursor.execute("""
        SELECT r.venue_code, r.race_number,
               rc.temperature, rc.water_temperature, rc.wind_speed,
               rc.wave_height, rc.weather, rc.wind_direction
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date = '2025-12-10'
        LIMIT 3
    """)

    print("【サンプルデータ】")
    for row in cursor.fetchall():
        print(f"  会場{row[0]} R{row[1]}: 気温{row[2]}℃, 水温{row[3]}℃, "
              f"風速{row[4]}m, 波高{row[5]}cm, 天候={row[6]}, 風向={row[7]}")

    conn.close()


def main():
    """全テストを実行"""
    print("\n")
    print("*" * 80)
    print(" 直前情報の気象データ活用テスト（Phase 1-3）")
    print("*" * 80)
    print("\n")

    # Phase 1: データソース確認
    test_data_source()
    print("\n")

    # Phase 2: 気温・水温活用
    test_beforeinfo_scorer()
    print("\n")

    # Phase 3: 天候コード活用
    test_weather_adjuster()
    print("\n")

    print("*" * 80)
    print(" 全テスト完了")
    print("*" * 80)


if __name__ == "__main__":
    main()
