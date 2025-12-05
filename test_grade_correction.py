"""
級別補正機能テスト

entriesテーブル修正後、級別補正が正しく機能しているかテスト
Phase 3（ST/展示なし）vs Phase 5修正版（級別補正あり）
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag
import sqlite3


def test_grade_correction(db_path="data/boatrace.db", num_races=100):
    """級別補正機能のテスト"""

    print("=" * 80)
    print(f"級別補正機能テスト: {num_races}レース")
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
        INNER JOIN entries e ON r.id = e.race_id
        WHERE rd.st_time IS NOT NULL
          AND rd.st_time > 0
          AND rd.exhibition_time IS NOT NULL
          AND rd.exhibition_time > 0
          AND res.rank IS NOT NULL
          AND res.rank != ''
          AND e.racer_rank IS NOT NULL
        ORDER BY r.id DESC
        LIMIT ?
    """

    cursor.execute(query, (num_races,))
    race_ids = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    print(f"      -> {len(race_ids)}レースを取得（級別データあり）")

    # Phase 3（ベースライン: ST/展示なし）
    print("\n[2/3] Phase 3（ベースライン: ST/展示なし）テスト中...")
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

    # Phase 5修正版（級別補正あり: ST/展示+級別補正）
    print("\n[3/3] Phase 5修正版（級別補正あり）テスト中...")
    set_feature_flag('before_safe_st_exhibition', True)
    predictor_phase5 = RacePredictor(db_path=db_path)

    correct_phase5 = 0
    total_phase5 = 0
    grade_used_count = 0

    for race_id in race_ids:
        try:
            predictions = predictor_phase5.predict_race(race_id)
            if not predictions:
                continue

            top_prediction = predictions[0]
            predicted_pit = top_prediction['pit_number']

            # 級別データ使用確認
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM entries WHERE race_id = ? AND racer_rank IS NOT NULL", (race_id,))
            grade_count = cursor.fetchone()[0]
            if grade_count > 0:
                grade_used_count += 1

            # 実際の結果を取得
            cursor.execute("SELECT pit_number FROM results WHERE race_id = ? AND rank = '1'", (race_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if not row:
                continue

            actual_winner = row[0]
            total_phase5 += 1

            if predicted_pit == actual_winner:
                correct_phase5 += 1
        except Exception as e:
            print(f"Warning: レース{race_id}でエラー: {e}")
            continue

    accuracy_phase5 = (correct_phase5 / total_phase5 * 100) if total_phase5 > 0 else 0
    print(f"      -> 的中数: {correct_phase5}/{total_phase5} ({accuracy_phase5:.1f}%)")
    print(f"      -> 級別データ使用: {grade_used_count}/{len(race_ids)}レース")

    # 結果サマリー
    print("\n" + "=" * 80)
    print("結果サマリー")
    print("=" * 80)

    print(f"\nPhase 3（ベースライン）: {correct_phase3}/{total_phase3} ({accuracy_phase3:.1f}%)")
    print(f"Phase 5修正版（級別補正）: {correct_phase5}/{total_phase5} ({accuracy_phase5:.1f}%)")

    diff = accuracy_phase5 - accuracy_phase3
    print(f"\n差分: {diff:+.1f}ポイント")

    if diff > 2.0:
        print("\n[OK] 級別補正が有意に改善しています！")
        print("   - Opus推奨の+2-3pt改善を達成")
        print("   - entriesテーブル修正が成功")
        print("   - ST/展示タイムの級別補正が機能")
    elif diff > 0.0:
        print("\n[!] 級別補正は改善傾向ですが、効果は限定的")
        print("   - より大規模なテスト（200-300レース）を推奨")
    else:
        print("\n[X] 級別補正は改善効果が見られません")
        print("   - ST/展示の相関が弱すぎる可能性")
        print("   - 級別補正の重み調整が必要")

    # 技術的考察
    print("\n" + "-" * 80)
    print("技術的考察:")

    if grade_used_count == len(race_ids):
        print("  [OK] 全レースで級別データを使用")
        print("      -> entriesテーブル修正が成功")
    else:
        print(f"  [!] 級別データ使用率: {grade_used_count/len(race_ids)*100:.1f}%")
        print("      -> 一部レースで級別データが不足")

    if diff > 0:
        print("  [+] ST/展示タイムの級別補正が効果あり")
        print("      -> A1選手とB2選手のSTタイム差を正しく評価")
    else:
        print("  [-] 級別補正の効果が不明瞭")
        print("      -> 相関が弱すぎる、または補正ロジックに問題")

    print("\nテスト完了!")

    return {
        'phase3': {'accuracy': accuracy_phase3, 'correct': correct_phase3, 'total': total_phase3},
        'phase5': {'accuracy': accuracy_phase5, 'correct': correct_phase5, 'total': total_phase5},
        'diff': diff,
        'grade_used': grade_used_count
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='級別補正機能テスト')
    parser.add_argument('--num-races', type=int, default=100, help='テストレース数')

    args = parser.parse_args()

    test_grade_correction(num_races=args.num_races)
