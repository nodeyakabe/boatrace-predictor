"""
会場×風向×風速補正の統合テスト

BeforeInfoScorerに統合された会場×風向補正の動作確認
"""
import os
import sys
import sqlite3

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.beforeinfo_scorer import BeforeInfoScorer


def find_storm_race_examples(db_path: str) -> list:
    """
    暴風レース（8m以上）の例を検索

    Returns:
        [(race_id, venue_code, wind_speed, wind_direction), ...]
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number,
               rc.wind_speed, rc.wind_direction, rc.weather
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rc.wind_speed >= 8.0
          AND rc.wind_direction IS NOT NULL
          AND r.venue_code IN ('02', '03', '10', '13', '14', '19', '23')
        ORDER BY r.race_date DESC
        LIMIT 20
    """)

    results = cursor.fetchall()
    conn.close()

    races = []
    for row in results:
        races.append({
            'race_id': row['id'],
            'venue_code': row['venue_code'],
            'race_date': row['race_date'],
            'race_number': row['race_number'],
            'wind_speed': row['wind_speed'],
            'wind_direction': row['wind_direction'],
            'weather': row['weather']
        })

    return races


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 80)
    print("会場×風向×風速補正の統合テスト")
    print("=" * 80)

    # 暴風レースの例を検索
    print("\n暴風レース（8m以上）の例を検索中...")
    storm_races = find_storm_race_examples(db_path)

    print(f"\n検索結果: {len(storm_races)}件")

    if not storm_races:
        print("暴風レースが見つかりませんでした。")
        return

    # BeforeInfoScorerのインスタンス作成
    scorer = BeforeInfoScorer(db_path)

    # 各レースについて気象スコアを計算
    print("\n" + "=" * 80)
    print("気象スコア計算テスト（会場×風向補正を含む）")
    print("=" * 80)

    for race in storm_races[:10]:  # 上位10件のみ
        race_id = race['race_id']
        venue_code = race['venue_code']
        venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
        wind_speed = race['wind_speed']
        wind_direction = race['wind_direction']

        print(f"\n【{race['race_date']} 会場{venue_num:02d} {race['race_number']:2d}R】")
        print(f"  風速: {wind_speed}m, 風向: {wind_direction}, 天候: {race['weather']}")

        # 気象データを準備（DBから完全なデータを取得）
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT temperature, water_temperature, weather, wind_speed, wind_direction
            FROM race_conditions
            WHERE race_id = ?
        """, (race_id,))

        row = cursor.fetchone()
        conn.close()

        weather_data = {
            'temperature': row['temperature'] if row else None,
            'water_temp': row['water_temperature'] if row else None,
            'weather_condition': row['weather'] if row else None,
            'wind_speed': row['wind_speed'] if row else None,
            'wind_direction': row['wind_direction'] if row else None
        }

        # 1コースの気象スコアを計算（exhibition_coursesは{1: 1}と仮定）
        beforeinfo_data = {
            'is_published': True,
            'weather': weather_data,
            'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
            'exhibition_times': {},
            'start_timings': {},
            'previous_race': {},
            'tilt_angles': {},
            'parts_replacements': {},
            'adjusted_weights': {}
        }

        # 1コースのスコアを計算
        score_result = scorer.calculate_beforeinfo_score(race_id, 1, beforeinfo_data)
        weather_score = score_result['weather_score']

        print(f"  → 1コース気象スコア: {weather_score:+6.1f}点")

        # 期待される補正を表示
        venue_str = f"{int(venue_code):02d}"
        from src.analysis.weather_venue_adjuster import VENUE_WIND_DIRECTION_ADJUSTMENT

        if venue_str in VENUE_WIND_DIRECTION_ADJUSTMENT:
            if wind_direction in VENUE_WIND_DIRECTION_ADJUSTMENT[venue_str]:
                expected_diff = VENUE_WIND_DIRECTION_ADJUSTMENT[venue_str][wind_direction]
                expected_score = expected_diff * 0.5 * 0.5  # 0.5は会場補正、0.5は5点満点正規化
                print(f"  期待される補正: {expected_diff:+6.1f}pt → スコア{expected_score:+6.1f}点")
                print(f"  評価: {'超有利' if expected_diff > 20 else '有利' if expected_diff > 0 else '不利' if expected_diff > -20 else '壊滅的'}")
            else:
                print(f"  風向データなし（補正なし）")
        else:
            print(f"  会場データなし（補正なし）")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
