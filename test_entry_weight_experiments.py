"""
進入スコア重み配分実験

Phase 0診断結果を踏まえて以下3パターンをテスト:
1. Phase 3（ベースライン）: ST/展示なし
2. 進入重み50%版: 進入の影響を強調
3. 進入単独100%版: 進入スコアのみで評価

目的: 進入変更の-8.63pt影響を正しく活かす最適重み配分を発見
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.analysis.race_predictor import RacePredictor
from src.analysis.before_safe_scorer import BeforeSafeScorer
from config.feature_flags import set_feature_flag
import sqlite3


def test_weight_experiments(db_path="data/boatrace.db", num_races=100):
    """進入スコア重み配分実験"""

    print("=" * 80)
    print(f"進入スコア重み配分実験: {num_races}レース")
    print("=" * 80)

    # テスト用レース取得
    print("\n[1/5] テスト用レース取得中...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT DISTINCT r.id
        FROM races r
        INNER JOIN race_details rd ON r.id = rd.race_id
        INNER JOIN results res ON r.id = res.race_id
        WHERE rd.st_time IS NOT NULL
          AND rd.st_time > 0
          AND rd.exhibition_time IS NOT NULL
          AND rd.exhibition_time > 0
          AND res.rank IS NOT NULL
          AND res.rank != ''
        ORDER BY r.id DESC
        LIMIT ?
    """

    cursor.execute(query, (num_races,))
    race_ids = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    print(f"      -> {len(race_ids)}レースを取得")

    # ========================================
    # パターン1: Phase 3（ベースライン）
    # ========================================
    print("\n[2/5] Phase 3（ベースライン: ST/展示なし）テスト中...")
    set_feature_flag('before_safe_st_exhibition', False)
    predictor_phase3 = RacePredictor(db_path=db_path)

    correct_phase3 = 0
    total_phase3 = 0

    for race_id in race_ids:
        try:
            predictions = predictor_phase3.predict_race(race_id)
            if not predictions:
                continue

            top_prediction = predictions[0]
            predicted_pit = top_prediction['pit_number']

            # 実際の結果を取得
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT pit_number FROM results WHERE race_id = ? AND rank = '1'", (race_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if not row:
                continue

            actual_winner = row[0]
            total_phase3 += 1

            if predicted_pit == actual_winner:
                correct_phase3 += 1
        except Exception as e:
            print(f"Warning: レース{race_id}でエラー: {e}")
            continue

    accuracy_phase3 = (correct_phase3 / total_phase3 * 100) if total_phase3 > 0 else 0
    print(f"      -> 的中数: {correct_phase3}/{total_phase3} ({accuracy_phase3:.1f}%)")

    # ========================================
    # パターン2: 進入重み50%版
    # ========================================
    print("\n[3/5] 進入重み50%版テスト中...")
    print("      設定: 進入50%, 部品30%, ST10%, 展示10%")

    # 一時的に重みを変更
    set_feature_flag('before_safe_st_exhibition', True)
    scorer_50 = BeforeSafeScorer(db_path=db_path, use_st_exhibition=True)

    # 重みを上書き
    scorer_50.ENTRY_WEIGHT = 0.50
    scorer_50.PARTS_WEIGHT = 0.30
    scorer_50.ST_WEIGHT = 0.10
    scorer_50.EXHIBITION_WEIGHT = 0.10

    # RacePredictorにスコアラーを差し替え
    predictor_50 = RacePredictor(db_path=db_path)
    predictor_50.before_safe_scorer = scorer_50

    correct_50 = 0
    total_50 = 0

    for race_id in race_ids:
        try:
            predictions = predictor_50.predict_race(race_id)
            if not predictions:
                continue

            top_prediction = predictions[0]
            predicted_pit = top_prediction['pit_number']

            # 実際の結果を取得
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT pit_number FROM results WHERE race_id = ? AND rank = '1'", (race_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if not row:
                continue

            actual_winner = row[0]
            total_50 += 1

            if predicted_pit == actual_winner:
                correct_50 += 1
        except Exception as e:
            continue

    accuracy_50 = (correct_50 / total_50 * 100) if total_50 > 0 else 0
    print(f"      -> 的中数: {correct_50}/{total_50} ({accuracy_50:.1f}%)")

    # ========================================
    # パターン3: 進入単独100%版
    # ========================================
    print("\n[4/5] 進入単独100%版テスト中...")
    print("      設定: 進入100%, 部品0%, ST0%, 展示0%")

    scorer_100 = BeforeSafeScorer(db_path=db_path, use_st_exhibition=True)

    # 進入のみに集中
    scorer_100.ENTRY_WEIGHT = 1.0
    scorer_100.PARTS_WEIGHT = 0.0
    scorer_100.ST_WEIGHT = 0.0
    scorer_100.EXHIBITION_WEIGHT = 0.0

    predictor_100 = RacePredictor(db_path=db_path)
    predictor_100.before_safe_scorer = scorer_100

    correct_100 = 0
    total_100 = 0

    for race_id in race_ids:
        try:
            predictions = predictor_100.predict_race(race_id)
            if not predictions:
                continue

            top_prediction = predictions[0]
            predicted_pit = top_prediction['pit_number']

            # 実際の結果を取得
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT pit_number FROM results WHERE race_id = ? AND rank = '1'", (race_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if not row:
                continue

            actual_winner = row[0]
            total_100 += 1

            if predicted_pit == actual_winner:
                correct_100 += 1
        except Exception as e:
            continue

    accuracy_100 = (correct_100 / total_100 * 100) if total_100 > 0 else 0
    print(f"      -> 的中数: {correct_100}/{total_100} ({accuracy_100:.1f}%)")

    # ========================================
    # 結果サマリー
    # ========================================
    print("\n" + "=" * 80)
    print("結果サマリー")
    print("=" * 80)

    results = [
        ("Phase 3（ベースライン）", accuracy_phase3, correct_phase3, total_phase3),
        ("進入重み50%版", accuracy_50, correct_50, total_50),
        ("進入単独100%版", accuracy_100, correct_100, total_100)
    ]

    for name, acc, correct, total in results:
        print(f"\n{name}:")
        print(f"  的中数: {correct}/{total} ({acc:.1f}%)")
        if name != "Phase 3（ベースライン）":
            diff = acc - accuracy_phase3
            print(f"  差分: {diff:+.1f}ポイント")

    # 最高精度を判定
    print("\n" + "-" * 80)
    best_idx = max(range(len(results)), key=lambda i: results[i][1])
    best_name, best_acc, _, _ = results[best_idx]

    if best_idx == 0:
        print("[結論] Phase 3（ベースライン）が最も優れています")
        print("  - ST/展示なし、進入60%+部品40%の組み合わせが最適")
        print("  - 推奨: Phase 3設定を維持")
    elif best_idx == 1:
        print(f"[結論] 進入重み50%版が最も優れています（{best_acc:.1f}%）")
        print("  - 進入変更の影響を強調することで改善")
        print("  - 推奨: 進入50%, 部品30%, ST10%, 展示10%に変更")
    else:
        print(f"[結論] 進入単独100%版が最も優れています（{best_acc:.1f}%）")
        print("  - 進入スコアのみで十分な予測力")
        print("  - 推奨: 進入100%に単純化（ただし過剰適合に注意）")

    # 詳細な考察
    print("\n" + "-" * 80)
    print("考察:")

    if accuracy_50 > accuracy_phase3 + 1.0:
        print("  [+] 進入重み50%版の改善が有意")
        print("      -> Phase 0診断の-8.63pt影響が活かされている")
        print("      -> 進入スコアの重要性が高い")
    elif accuracy_50 > accuracy_phase3:
        print("  [~] 進入重み50%版は改善傾向だが効果は限定的")
        print("      -> さらなる重み調整が必要")
    else:
        print("  [-] 進入重み50%版は改善なし")
        print("      -> ST/展示の弱い相関が足を引っ張っている")

    if accuracy_100 > accuracy_phase3 + 1.0:
        print("  [+] 進入単独100%版の改善が有意")
        print("      -> 進入スコアが最も重要な要素")
        print("      -> 他の要素は不要（単純化可能）")
    elif accuracy_100 > accuracy_phase3:
        print("  [~] 進入単独100%版は改善傾向だが効果は限定的")
        print("      -> 部品交換スコアとの組み合わせが望ましい")
    else:
        print("  [-] 進入単独100%版は改善なし")
        print("      -> 進入スコア単体では不十分")
        print("      -> 部品交換・ST・展示との組み合わせが必要")

    print("\nテスト完了!")

    return {
        'phase3': {'accuracy': accuracy_phase3, 'correct': correct_phase3, 'total': total_phase3},
        'entry_50': {'accuracy': accuracy_50, 'correct': correct_50, 'total': total_50},
        'entry_100': {'accuracy': accuracy_100, 'correct': correct_100, 'total': total_100}
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='進入スコア重み配分実験')
    parser.add_argument('--num-races', type=int, default=100, help='テストレース数')

    args = parser.parse_args()

    test_weight_experiments(num_races=args.num_races)
