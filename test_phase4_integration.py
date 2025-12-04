"""
Phase 4統合テスト
ST・展示タイム再設計版の効果を検証

比較パターン:
1. Phase 3版（ST/展示なし）: before_safe_st_exhibition = False
2. Phase 4版（ST/展示あり）: before_safe_st_exhibition = True
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.analysis.race_predictor import RacePredictor
from config import feature_flags
import sqlite3


def get_test_races(db_path: str, limit: int = 30):
    """テスト用レースを取得（ST/展示データあり）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT DISTINCT r.id, r.venue_code, r.race_number, r.grade
        FROM races r
        INNER JOIN race_details rd ON r.id = rd.race_id
        INNER JOIN results res ON r.id = res.race_id
        WHERE rd.st_time IS NOT NULL
          AND rd.exhibition_time IS NOT NULL
          AND res.rank = 1
          AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT ?
    """
    cursor.execute(query, (limit,))
    races = cursor.fetchall()
    conn.close()

    return races


def get_actual_winner(db_path: str, race_id: int):
    """実際の1着を取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pit_number
        FROM results
        WHERE race_id = ? AND rank = 1 AND is_invalid = 0
    """, (race_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def test_phase4_integration():
    """Phase 4統合テスト"""
    db_path = "data/boatrace.db"

    print("=" * 80)
    print("Phase 4統合テスト: ST・展示タイム再設計版の効果検証")
    print("=" * 80)

    # テストレースを取得
    test_races = get_test_races(db_path, limit=30)
    if not test_races:
        print("[ERROR] テストレース取得失敗（2025年のST/展示データあり条件）")
        return

    print(f"\nテストレース数: {len(test_races)}件")
    print(f"条件: 2025年、ST・展示データあり\n")

    # Phase 3版テスト（ST/展示なし）
    print("-" * 80)
    print("【Phase 3版】ST/展示なし（before_safe_st_exhibition = False）")
    print("-" * 80)

    feature_flags.set_feature_flag('before_safe_st_exhibition', False)
    predictor_phase3 = RacePredictor(db_path=db_path)

    correct_count_phase3 = 0
    predictions_changed_count = 0

    phase3_predictions = {}

    for race_id, venue_code, race_number, grade in test_races:
        try:
            predictions = predictor_phase3.predict_race(race_id)

            # 1位予測
            top_pred = max(predictions, key=lambda x: x['total_score'])
            predicted_pit = top_pred['pit_number']
            phase3_predictions[race_id] = predicted_pit

            # 実際の1着を取得
            actual_1st = get_actual_winner(db_path, race_id)

            if actual_1st:
                if predicted_pit == actual_1st:
                    correct_count_phase3 += 1

        except Exception as e:
            print(f"[ERROR] race_id={race_id}: {e}")

    accuracy_phase3 = correct_count_phase3 / len(test_races) * 100 if test_races else 0
    print(f"\nPhase 3版 的中率: {correct_count_phase3}/{len(test_races)} ({accuracy_phase3:.1f}%)")

    # Phase 4版テスト（ST/展示あり）
    print("\n" + "-" * 80)
    print("【Phase 4版】ST/展示あり（before_safe_st_exhibition = True）")
    print("-" * 80)

    feature_flags.set_feature_flag('before_safe_st_exhibition', True)
    predictor_phase4 = RacePredictor(db_path=db_path)

    correct_count_phase4 = 0
    phase4_predictions = {}

    for race_id, venue_code, race_number, grade in test_races:
        try:
            predictions = predictor_phase4.predict_race(race_id)

            # 1位予測
            top_pred = max(predictions, key=lambda x: x['total_score'])
            predicted_pit = top_pred['pit_number']
            phase4_predictions[race_id] = predicted_pit

            # 予測変化をカウント
            if phase3_predictions.get(race_id) != predicted_pit:
                predictions_changed_count += 1

            # 実際の1着を取得
            actual_1st = get_actual_winner(db_path, race_id)

            if actual_1st:
                if predicted_pit == actual_1st:
                    correct_count_phase4 += 1

        except Exception as e:
            print(f"[ERROR] race_id={race_id}: {e}")

    accuracy_phase4 = correct_count_phase4 / len(test_races) * 100 if test_races else 0
    print(f"\nPhase 4版 的中率: {correct_count_phase4}/{len(test_races)} ({accuracy_phase4:.1f}%)")

    # 比較結果
    print("\n" + "=" * 80)
    print("【比較結果】")
    print("=" * 80)
    print(f"Phase 3版（ST/展示なし）: {accuracy_phase3:.1f}%")
    print(f"Phase 4版（ST/展示あり）: {accuracy_phase4:.1f}%")
    diff = accuracy_phase4 - accuracy_phase3
    if diff > 0:
        print(f"改善: +{diff:.1f}ポイント")
    elif diff < 0:
        print(f"悪化: {diff:.1f}ポイント")
    else:
        print("変化なし")

    print(f"\n予測が変わったレース: {predictions_changed_count}/{len(test_races)} ({predictions_changed_count/len(test_races)*100:.1f}%)")

    # 詳細分析（予測が変わったレースの的中率）
    if predictions_changed_count > 0:
        changed_correct = 0
        for race_id, venue_code, race_number, grade in test_races:
            if phase3_predictions.get(race_id) != phase4_predictions.get(race_id):
                actual_1st = get_actual_winner(db_path, race_id)
                if actual_1st and phase4_predictions.get(race_id) == actual_1st:
                    changed_correct += 1

        changed_accuracy = changed_correct / predictions_changed_count * 100
        print(f"予測変更レースの的中率: {changed_correct}/{predictions_changed_count} ({changed_accuracy:.1f}%)")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)


if __name__ == '__main__':
    test_phase4_integration()
