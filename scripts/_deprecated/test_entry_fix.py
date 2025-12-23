"""
進入スコア修正版のテスト（簡易版）

Phase 0修正: 進入スコアの符号を修正
- 枠なり（進入変更なし）→ プラス評価
- 進入変更 → マイナス評価
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag
import sqlite3


def test_entry_fix(db_path="data/boatrace.db", num_races=30):
    """進入スコア修正版のテスト"""

    print("=" * 80)
    print(f"進入スコア修正版テスト: {num_races}レース")
    print("=" * 80)

    # テスト用レース取得
    print("\n[1/3] テスト用レース取得中...")
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

    print(f"      → {len(race_ids)}レースを取得")

    # Phase 3版（ST/展示なし）でテスト
    print("\n[2/3] Phase 3版（ST/展示なし）でテスト実行中...")
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
    print(f"      → 的中数: {correct_phase3}/{total_phase3} ({accuracy_phase3:.1f}%)")

    # 進入スコア修正版でテスト
    print("\n[3/3] 進入スコア修正版（符号修正+ST/展示あり）でテスト実行中...")
    set_feature_flag('before_safe_st_exhibition', True)
    predictor_fixed = RacePredictor(db_path=db_path)

    correct_fixed = 0
    total_fixed = 0

    for race_id in race_ids:
        try:
            predictions = predictor_fixed.predict_race(race_id)
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
            total_fixed += 1

            if predicted_pit == actual_winner:
                correct_fixed += 1
        except Exception as e:
            print(f"Warning: レース{race_id}でエラー: {e}")
            continue

    accuracy_fixed = (correct_fixed / total_fixed * 100) if total_fixed > 0 else 0
    print(f"      → 的中数: {correct_fixed}/{total_fixed} ({accuracy_fixed:.1f}%)")

    # 結果サマリー
    print("\n" + "=" * 80)
    print("結果サマリー")
    print("=" * 80)

    print(f"\nPhase 3（ST/展示なし）: {correct_phase3}/{total_phase3} ({accuracy_phase3:.1f}%)")
    print(f"進入スコア修正版: {correct_fixed}/{total_fixed} ({accuracy_fixed:.1f}%)")

    diff = accuracy_fixed - accuracy_phase3
    print(f"\n差分: {diff:+.1f}ポイント")

    if diff > 2.0:
        print("\n[OK] 進入スコア修正版が有意に改善しています！")
        print("   - 進入スコアの符号修正が効果的")
        print("   - ST/展示データとの組み合わせが機能")
    elif diff > 0.0:
        print("\n[!] 進入スコア修正版は改善傾向ですが、効果は限定的")
        print("   - より大規模なテスト（100-200レース）を推奨")
    else:
        print("\n[X] 進入スコア修正版は改善効果が見られません")
        print("   - さらなる調整が必要")

    print("\nテスト完了！")

    return {
        'phase3_accuracy': accuracy_phase3,
        'fixed_accuracy': accuracy_fixed,
        'diff': diff
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='進入スコア修正版のテスト')
    parser.add_argument('--num-races', type=int, default=30, help='テストレース数')

    args = parser.parse_args()

    test_entry_fix(num_races=args.num_races)
