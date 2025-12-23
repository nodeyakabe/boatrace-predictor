"""
BeforeInfoScorerの気象補正（全コース対応）のテスト

Priority 3実装完了テスト
"""
import os
import sys

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.beforeinfo_scorer import BeforeInfoScorer


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 100)
    print("BeforeInfoScorer 気象補正（全コース対応）のテスト")
    print("=" * 100)

    scorer = BeforeInfoScorer(db_path)

    # テストケース: 仮想的な直前情報データ
    test_cases = [
        {
            'description': "1コース、戸田、東風4m（不利パターン -26.6pt → -7.0点）",
            'pit_number': 1,
            'race_id': 999999,  # ダミー
            'venue_code': '02',
            'weather': {
                'wind_speed': 4.0,
                'wind_direction': '東',
                'wave_height': 5,
                'temperature': 20,
                'water_temp': 18
            },
            'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        },
        {
            'description': "2コース、宮島、西南西4m（有利パターン +31.0pt → +10.0点）",
            'pit_number': 2,
            'race_id': 999999,
            'venue_code': '17',
            'weather': {
                'wind_speed': 4.0,
                'wind_direction': '西南西',
                'wave_height': 5,
                'temperature': 20,
                'water_temp': 18
            },
            'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        },
        {
            'description': "3コース、戸田、北風4m（有利パターン +12.9pt → +3.0点）",
            'pit_number': 3,
            'race_id': 999999,
            'venue_code': '02',
            'weather': {
                'wind_speed': 4.0,
                'wind_direction': '北',
                'wave_height': 5,
                'temperature': 20,
                'water_temp': 18
            },
            'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        },
        {
            'description': "4コース、びわこ、西南西4m（有利パターン +23.1pt → +7.0点）",
            'pit_number': 4,
            'race_id': 999999,
            'venue_code': '11',
            'weather': {
                'wind_speed': 4.0,
                'wind_direction': '西南西',
                'wave_height': 5,
                'temperature': 20,
                'water_temp': 18
            },
            'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        },
        {
            'description': "1コース、風速2m（補正なし）",
            'pit_number': 1,
            'race_id': 999999,
            'venue_code': '02',
            'weather': {
                'wind_speed': 2.0,
                'wind_direction': '東',
                'wave_height': 5,
                'temperature': 20,
                'water_temp': 18
            },
            'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        },
    ]

    print("\nテストケース:")
    print(f"{'説明':<50} {'気象スコア':<15}")
    print("-" * 100)

    for test_case in test_cases:
        description = test_case['description']
        pit_number = test_case['pit_number']
        weather = test_case['weather']
        exhibition_courses = test_case['exhibition_courses']

        # _calc_weather_scoreメソッドを直接テスト
        # race_idは会場コード取得用なので、ダミー処理が必要
        # ここでは_get_venue_codeをモックする代わりに、直接風向補正をテスト

        from src.analysis.wind_venue_adjuster_all_courses import calculate_wind_venue_adjustment

        course = exhibition_courses.get(pit_number, pit_number)
        venue_code = test_case['venue_code']
        wind_speed = weather.get('wind_speed')
        wind_direction = weather.get('wind_direction')

        wind_adj = calculate_wind_venue_adjustment(
            course=course,
            venue_code=venue_code,
            wind_speed=wind_speed,
            wind_direction=wind_direction
        )

        print(f"{description:<50} {wind_adj:+6.1f}点")

    print("\n" + "=" * 100)
    print("テスト完了")
    print("=" * 100)


if __name__ == "__main__":
    main()
