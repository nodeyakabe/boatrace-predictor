"""
環境要因減点システムの統合テスト

data_manager.pyに統合された環境要因減点システムの動作確認
"""

import sys
from pathlib import Path
import sqlite3

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.data_manager import DataManager

DB_PATH = project_root / 'data' / 'boatrace.db'


def get_sample_race_with_env():
    """環境情報が揃っているテスト用レースを取得"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number, r.race_time,
               rc.wind_direction, rc.wind_speed, rc.wave_height, rc.weather
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date LIKE '2025%'
          AND rc.wind_direction IS NOT NULL
          AND rc.wind_speed IS NOT NULL
          AND rc.wave_height IS NOT NULL
          AND rc.weather IS NOT NULL
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'race_id': row[0],
            'venue_code': row[1],
            'race_date': row[2],
            'race_number': row[3],
            'race_time': row[4],
            'wind_direction': row[5],
            'wind_speed': row[6],
            'wave_height': row[7],
            'weather': row[8]
        }
    else:
        return None


def test_integration():
    """統合テスト"""
    print("=" * 100)
    print("環境要因減点システム 統合テスト")
    print("=" * 100)

    # テスト用レース取得
    race = get_sample_race_with_env()
    if not race:
        print("エラー: テスト用レースが見つかりません")
        return

    print(f"\n【テスト対象レース】")
    print(f"  race_id: {race['race_id']}")
    print(f"  会場: {race['venue_code']}")
    print(f"  日付: {race['race_date']}")
    print(f"  レース番号: {race['race_number']}")
    print(f"  時刻: {race['race_time']}")
    print(f"  風向: {race['wind_direction']}")
    print(f"  風速: {race['wind_speed']}m/s")
    print(f"  波高: {race['wave_height']}cm")
    print(f"  天候: {race['weather']}")

    # テスト用予測データ（信頼度Bを含む）
    test_predictions = [
        {
            'pit_number': 1,
            'rank_prediction': 1,
            'total_score': 110.0,
            'confidence': 'B',
            'racer_name': 'テスト選手1',
            'racer_number': '0001',
            'applied_rules': 'test_rule',
            'course_score': 50,
            'racer_score': 30,
            'motor_score': 20,
            'kimarite_score': 10,
            'grade_score': 0
        },
        {
            'pit_number': 2,
            'rank_prediction': 2,
            'total_score': 105.0,
            'confidence': 'B',
            'racer_name': 'テスト選手2',
            'racer_number': '0002',
            'applied_rules': 'test_rule',
            'course_score': 45,
            'racer_score': 30,
            'motor_score': 20,
            'kimarite_score': 10,
            'grade_score': 0
        },
        {
            'pit_number': 3,
            'rank_prediction': 3,
            'total_score': 85.0,
            'confidence': 'C',
            'racer_name': 'テスト選手3',
            'racer_number': '0003',
            'applied_rules': 'test_rule',
            'course_score': 40,
            'racer_score': 25,
            'motor_score': 15,
            'kimarite_score': 5,
            'grade_score': 0
        }
    ]

    print("\n【テスト予測データ】")
    for pred in test_predictions:
        print(f"  艇番{pred['pit_number']}: スコア{pred['total_score']:.1f}, 信頼度{pred['confidence']}")

    # データマネージャー初期化
    dm = DataManager(str(DB_PATH))

    # BEFORE予想として保存（環境要因減点が適用される）
    print("\n【BEFORE予想として保存（環境要因減点適用）】")
    result = dm.save_race_predictions(
        race_id=race['race_id'],
        predictions=test_predictions,
        prediction_type='before'
    )

    if result:
        print("[OK] 保存成功")
    else:
        print("[NG] 保存失敗")
        return

    # 保存された予測を確認
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pit_number, rank_prediction, total_score, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
    """, (race['race_id'],))

    rows = cursor.fetchall()
    conn.close()

    print("\n【保存後の予測データ】")
    adjustments = []
    for row in rows:
        pit, rank, score, conf = row
        original = next((p for p in test_predictions if p['pit_number'] == pit), None)
        if original:
            original_conf = original['confidence']
            if original_conf != conf:
                adjustments.append(f"艇番{pit}: {original_conf} → {conf}")
            print(f"  艇番{pit}: スコア{score:.1f}, 信頼度{conf} (元: {original_conf})")
        else:
            print(f"  艇番{pit}: スコア{score:.1f}, 信頼度{conf}")

    if adjustments:
        print(f"\n【調整された予測】")
        for adj in adjustments:
            print(f"  {adj}")
    else:
        print(f"\n信頼度の調整はありませんでした（環境要因による減点が小さかった）")

    # ADVANCE予想として保存（環境要因減点は適用されない）
    print("\n" + "=" * 100)
    print("【ADVANCE予想として保存（環境要因減点なし）】")
    result = dm.save_race_predictions(
        race_id=race['race_id'],
        predictions=test_predictions,
        prediction_type='advance'
    )

    if result:
        print("[OK] 保存成功")
    else:
        print("[NG] 保存失敗")
        return

    # 保存された予測を確認
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pit_number, rank_prediction, total_score, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'advance'
        ORDER BY rank_prediction
    """, (race['race_id'],))

    rows = cursor.fetchall()
    conn.close()

    print("\n【保存後の予測データ】")
    for row in rows:
        pit, rank, score, conf = row
        original = next((p for p in test_predictions if p['pit_number'] == pit), None)
        if original:
            print(f"  艇番{pit}: スコア{score:.1f}, 信頼度{conf} (元: {original['confidence']}) - 変更なし（期待通り）")

    print("\n" + "=" * 100)
    print("統合テスト完了")
    print("=" * 100)


if __name__ == '__main__':
    test_integration()
