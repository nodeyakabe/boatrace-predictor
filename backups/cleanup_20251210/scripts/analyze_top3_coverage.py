"""
予想上位3艇が実際の上位3艇をどれだけカバーしているか分析

予想1位が外れた場合でも、予想した3艇が実際の上位3艇に
どれだけ含まれているかを評価する
"""
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.prediction.hierarchical_predictor import HierarchicalPredictor


def analyze_top3_coverage(db_path, model_dir, max_races=500):
    """予想上位3艇のカバレッジを分析"""

    print("="*80)
    print("予想上位3艇のカバレッジ分析")
    print("="*80)

    # レース取得
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, race_date, venue_code, race_number
            FROM races
            WHERE race_date >= '2024-01-01' AND race_date < '2026-01-01'
            ORDER BY race_date, venue_code, race_number
            LIMIT ?
        """, (max_races,))
        races = cursor.fetchall()

    print(f"\n評価レース数: {len(races):,}\n")

    predictor = HierarchicalPredictor(str(db_path), str(model_dir), use_v2=False)

    # 統計
    stats = {
        'case1': {  # 予想1位的中
            'total': 0,
            'coverage_3': 0,  # 3艇全て的中
            'coverage_2': 0,  # 2艇的中
            'coverage_1': 0,  # 1艇的中
            'coverage_0': 0   # 0艇的中
        },
        'case2': {  # 予想1位外れ
            'total': 0,
            'coverage_3': 0,
            'coverage_2': 0,
            'coverage_1': 0,
            'coverage_0': 0
        }
    }

    for i, (race_id, race_date, venue_code, race_number) in enumerate(races):
        if (i + 1) % 100 == 0:
            print(f"処理中: {i+1}/{len(races)} レース...")

        try:
            # 予測
            prediction = predictor.predict_race(race_id, use_conditional_model=True)
            if 'error' in prediction or not prediction.get('top_combinations'):
                continue

            predicted_combo = prediction['top_combinations'][0][0]
            predicted_pits = [int(p) for p in predicted_combo.split('-')]

            # 実際の結果
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT pit_number
                    FROM results
                    WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                    ORDER BY rank
                """, (race_id,))
                actual_results = cursor.fetchall()

                if len(actual_results) < 3:
                    continue

                actual_pits = [r[0] for r in actual_results]

            # ケース判定
            rank1_correct = (predicted_pits[0] == actual_pits[0])
            case = 'case1' if rank1_correct else 'case2'

            # カバレッジ計算（予想3艇が実際の上位3艇に何艇含まれるか）
            coverage = len(set(predicted_pits) & set(actual_pits))

            stats[case]['total'] += 1
            if coverage == 3:
                stats[case]['coverage_3'] += 1
            elif coverage == 2:
                stats[case]['coverage_2'] += 1
            elif coverage == 1:
                stats[case]['coverage_1'] += 1
            else:
                stats[case]['coverage_0'] += 1

        except Exception as e:
            continue

    # 結果表示
    print("\n" + "="*80)
    print("分析結果")
    print("="*80)

    for case_name, case_data in [('case1', '予想1位的中'), ('case2', '予想1位外れ')]:
        case_stats = stats[case_name]

        if case_stats['total'] == 0:
            continue

        print(f"\n【{case_data}】")
        print(f"  レース数: {case_stats['total']:,}")

        total = case_stats['total']
        cov3_rate = case_stats['coverage_3'] / total * 100
        cov2_rate = case_stats['coverage_2'] / total * 100
        cov1_rate = case_stats['coverage_1'] / total * 100
        cov0_rate = case_stats['coverage_0'] / total * 100

        print(f"\n  3艇全て的中: {case_stats['coverage_3']:4d}/{total} = {cov3_rate:6.2f}%")
        print(f"  2艇的中:     {case_stats['coverage_2']:4d}/{total} = {cov2_rate:6.2f}%")
        print(f"  1艇的中:     {case_stats['coverage_1']:4d}/{total} = {cov1_rate:6.2f}%")
        print(f"  0艇的中:     {case_stats['coverage_0']:4d}/{total} = {cov0_rate:6.2f}%")

        # 平均カバレッジ
        avg_coverage = (
            case_stats['coverage_3'] * 3 +
            case_stats['coverage_2'] * 2 +
            case_stats['coverage_1'] * 1
        ) / total

        print(f"\n  平均カバレッジ: {avg_coverage:.2f}艇/3艇 ({avg_coverage/3*100:.1f}%)")

    # 比較
    if stats['case1']['total'] > 0 and stats['case2']['total'] > 0:
        print(f"\n{'='*80}")
        print("ケース間の比較")
        print(f"{'='*80}")

        avg_cov1 = (
            stats['case1']['coverage_3'] * 3 +
            stats['case1']['coverage_2'] * 2 +
            stats['case1']['coverage_1'] * 1
        ) / stats['case1']['total']

        avg_cov2 = (
            stats['case2']['coverage_3'] * 3 +
            stats['case2']['coverage_2'] * 2 +
            stats['case2']['coverage_1'] * 1
        ) / stats['case2']['total']

        print(f"\n予想1位的中時の平均カバレッジ: {avg_cov1:.2f}艇 ({avg_cov1/3*100:.1f}%)")
        print(f"予想1位外れ時の平均カバレッジ: {avg_cov2:.2f}艇 ({avg_cov2/3*100:.1f}%)")
        print(f"差: {avg_cov1 - avg_cov2:+.2f}艇")

        # 理論値との比較
        print(f"\n【理論値との比較】")
        print(f"ランダム予想の期待カバレッジ: 1.5艇 (50%)")
        print(f"予想1位的中時: {avg_cov1:.2f}艇 (ランダムの{avg_cov1/1.5:.2f}倍)")
        print(f"予想1位外れ時: {avg_cov2:.2f}艇 (ランダムの{avg_cov2/1.5:.2f}倍)")


def main():
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    model_dir = PROJECT_ROOT / "models"

    analyze_top3_coverage(db_path, model_dir, max_races=500)

    print(f"\n{'='*80}")
    print("分析完了")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
