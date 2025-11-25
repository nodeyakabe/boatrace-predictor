"""
再予測機能のテストスクリプト
サンプルデータを使って動作確認
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH


def create_sample_exhibition_data(race_id: int):
    """サンプル展示データを作成"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("サンプル展示データを作成中...")

    # レースの艇番を取得
    cursor.execute("""
        SELECT pit_number FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))

    pits = [row[0] for row in cursor.fetchall()]

    if len(pits) != 6:
        print(f"エラー: レースID {race_id} に6艇の出走データがありません")
        conn.close()
        return False

    collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # サンプルデータ（1号艇が良好、4号艇が不調）
    sample_data = {
        1: {'time': 6.72, 'start': 4, 'turn': 4, 'weight': 0.0},
        2: {'time': 6.85, 'start': 3, 'turn': 3, 'weight': 0.5},
        3: {'time': 6.91, 'start': 3, 'turn': 3, 'weight': -0.3},
        4: {'time': 7.15, 'start': 2, 'turn': 2, 'weight': 2.1},  # 不調
        5: {'time': 6.88, 'start': 3, 'turn': 3, 'weight': 0.2},
        6: {'time': 6.95, 'start': 3, 'turn': 3, 'weight': -0.5},
    }

    for pit in pits:
        data = sample_data[pit]
        cursor.execute("""
            INSERT OR REPLACE INTO exhibition_data (
                race_id, pit_number, exhibition_time, start_timing,
                turn_quality, weight_change, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (race_id, pit, data['time'], data['start'],
              data['turn'], data['weight'], collected_at))

    conn.commit()
    conn.close()

    print("✓ 展示データ作成完了")
    print(f"  1号艇: 展示タイム優秀 {sample_data[1]['time']}秒")
    print(f"  4号艇: 展示タイム不良 {sample_data[4]['time']}秒、体重変化大 +{sample_data[4]['weight']}kg")
    return True


def create_sample_race_conditions(race_id: int):
    """サンプルレース条件データを作成"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\nサンプルレース条件を作成中...")

    collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # サンプル: 向い風でインコース有利
    cursor.execute("""
        INSERT OR REPLACE INTO race_conditions (
            race_id, weather, wind_direction, wind_speed,
            wave_height, temperature, water_temperature, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (race_id, '晴', '向い風', 4.2, 2, 24.5, 21.0, collected_at))

    conn.commit()
    conn.close()

    print("✓ レース条件作成完了")
    print("  天候: 晴、風向: 向い風 4.2m/s（インコース有利）")
    return True


def create_sample_actual_courses(race_id: int):
    """サンプル実際の進入コースデータを作成"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\nサンプル進入コースを作成中...")

    # レースの艇番を取得（コースは通常pit_numberと同じ）
    cursor.execute("""
        SELECT pit_number FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))

    entries = cursor.fetchall()

    collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # サンプル: 3号艇と4号艇が入れ替わり
    course_mapping = {
        1: 1,
        2: 2,
        3: 4,  # 進入変化
        4: 3,  # 進入変化
        5: 5,
        6: 6,
    }

    for (pit,) in entries:
        expected_course = pit  # 予定コースはpit_numberと同じ
        actual_course = course_mapping.get(pit, expected_course)
        cursor.execute("""
            INSERT OR REPLACE INTO actual_courses (
                race_id, pit_number, actual_course, collected_at
            ) VALUES (?, ?, ?, ?)
        """, (race_id, pit, actual_course, collected_at))

    conn.commit()
    conn.close()

    print("✓ 進入コース作成完了")
    print("  進入変化: 3号艇 3→4コース、4号艇 4→3コース")
    return True


def test_reprediction(race_id: int):
    """再予測機能をテスト"""

    print("=" * 80)
    print("再予測機能テスト")
    print("=" * 80)

    # レース情報を確認
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.race_date, r.venue_code, r.race_number, COUNT(e.pit_number)
        FROM races r
        LEFT JOIN entries e ON r.id = e.race_id
        WHERE r.id = ?
        GROUP BY r.id
    """, (race_id,))

    race_info = cursor.fetchone()
    if not race_info or race_info[3] != 6:
        print(f"\nエラー: レースID {race_id} が見つからないか、出走数が6艇ではありません")
        conn.close()
        return

    race_date, venue_code, race_number, entry_count = race_info

    print(f"\nテスト対象: {race_date} 会場{int(venue_code):02d} {int(race_number):2d}R")

    # 初期予測があるか確認
    cursor.execute("""
        SELECT COUNT(*) FROM race_predictions WHERE race_id = ?
    """, (race_id,))

    pred_count = cursor.fetchone()[0]
    if pred_count == 0:
        print("\nエラー: 初期予測がありません")
        print("先に予測を生成してください（generate_one_date.py など）")
        conn.close()
        return

    print(f"初期予測: {pred_count}艇分あり")

    # 初期予測を表示
    cursor.execute("""
        SELECT
            rp.rank_prediction,
            rp.pit_number,
            e.racer_name,
            rp.total_score,
            rp.confidence
        FROM race_predictions rp
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        WHERE rp.race_id = ?
        ORDER BY rp.rank_prediction
    """, (race_id,))

    predictions = cursor.fetchall()

    print("\n【初期予測】")
    print("-" * 80)
    print("順位 | 艇番 | 選手名           | スコア | 信頼度")
    print("-" * 80)
    for rank, pit, name, score, conf in predictions:
        print(f" {rank}位  |  {pit}  | {name:16s} | {score:5.1f}  |   {conf}")
    print("-" * 80)

    conn.close()

    # サンプルデータを作成
    print("\n" + "=" * 80)
    if not create_sample_exhibition_data(race_id):
        return
    if not create_sample_race_conditions(race_id):
        return
    if not create_sample_actual_courses(race_id):
        return

    # 再予測を実行
    print("\n" + "=" * 80)
    print("再予測を実行中...")
    print("=" * 80)

    from src.analysis.prediction_updater import PredictionUpdater

    updater = PredictionUpdater()
    result = updater.update_prediction_with_exhibition_data(race_id)

    if not result['success']:
        print(f"\nエラー: {result.get('error', '不明なエラー')}")
        return

    changes = result['changes']

    print(f"\n変更があった艇: {len(changes)}艇")

    if changes:
        print("\n【変更詳細】")
        print("-" * 80)
        for pit in sorted(changes.keys()):
            change = changes[pit]
            initial = change['initial']
            updated = change['updated']
            score_diff = updated['total_score'] - initial['total_score']

            print(f"\n{pit}号艇:")
            print(f"  スコア: {initial['total_score']:.1f} → {updated['total_score']:.1f} ({score_diff:+.1f})")
            print(f"  信頼度: {initial['confidence']} → {updated['confidence']}")
            print(f"  理由: {', '.join([r for r in change['reasons'] if r])}")

    # 更新後の予測を表示
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            rp.rank_prediction,
            rp.pit_number,
            e.racer_name,
            rp.total_score,
            rp.confidence
        FROM race_predictions rp
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        WHERE rp.race_id = ?
        ORDER BY rp.rank_prediction
    """, (race_id,))

    updated_predictions = cursor.fetchall()

    print("\n【更新後の予測】")
    print("-" * 80)
    print("順位 | 艇番 | 選手名           | スコア | 信頼度 | 変更")
    print("-" * 80)
    for rank, pit, name, score, conf in updated_predictions:
        changed_mark = "⚠" if pit in changes else " "
        print(f" {rank}位  |  {pit}  | {name:16s} | {score:5.1f}  |   {conf}   |  {changed_mark}")
    print("-" * 80)

    conn.close()

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)


def main():
    if len(sys.argv) < 2:
        print("使用方法: python test_reprediction_sample.py <race_id>")
        print("例: python test_reprediction_sample.py 12345")
        print()
        print("注意: 指定するrace_idには初期予測が生成されている必要があります")
        return

    try:
        race_id = int(sys.argv[1])
        test_reprediction(race_id)
    except ValueError:
        print("エラー: race_id は整数で指定してください")
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
