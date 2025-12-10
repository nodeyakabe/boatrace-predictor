"""
v2モデルの実測性能評価スクリプト

2024-2025年データで以下を評価:
1. 予想1位的中時・外れ時の2位予測精度
2. 三連単的中率
3. ROI
4. v1との比較
"""
import os
import sys
import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.prediction.hierarchical_predictor import HierarchicalPredictor


def evaluate_predictions(db_path, predictor, model_name, start_date='2024-01-01', end_date='2026-01-01', max_races=1000):
    """予測性能を評価"""
    print(f"\n{'='*80}")
    print(f"{model_name}モデルの評価")
    print(f"{'='*80}")

    # レースIDを取得
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, race_date, venue_code, race_number
            FROM races
            WHERE race_date >= ? AND race_date < ?
            ORDER BY race_date, venue_code, race_number
            LIMIT ?
        """, (start_date, end_date, max_races))
        races = cursor.fetchall()

    print(f"\n評価レース数: {len(races):,}レース")

    results = {
        'total': 0,
        'rank1_correct': 0,
        'rank2_correct': 0,
        'rank3_correct': 0,
        'trifecta_correct': 0,
        'case1': {'total': 0, 'rank2_correct': 0},  # 予想1位的中時
        'case2': {'total': 0, 'rank2_correct': 0},  # 予想1位外れ時
        'predictions': []
    }

    for i, (race_id, race_date, venue_code, race_number) in enumerate(races):
        if (i + 1) % 100 == 0:
            print(f"処理中: {i+1}/{len(races)} レース...")

        try:
            # 予測実行
            prediction = predictor.predict_race(race_id, use_conditional_model=True)

            if 'error' in prediction:
                continue

            # 予測結果を取得
            top_trifecta = prediction['top_combinations'][0] if prediction['top_combinations'] else None
            if not top_trifecta:
                continue

            predicted_combo = top_trifecta[0]  # '1-2-3' 形式
            predicted_pits = [int(p) for p in predicted_combo.split('-')]

            # 実際の結果を取得
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT pit_number, rank
                    FROM results
                    WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                    ORDER BY rank
                """, (race_id,))
                actual_results = cursor.fetchall()

            if len(actual_results) < 3:
                continue

            actual_pits = [r[0] for r in actual_results[:3]]
            actual_combo = f"{actual_pits[0]}-{actual_pits[1]}-{actual_pits[2]}"

            # 的中判定
            rank1_correct = (predicted_pits[0] == actual_pits[0])
            rank2_correct = (predicted_pits[1] == actual_pits[1])
            rank3_correct = (predicted_pits[2] == actual_pits[2])
            trifecta_correct = (predicted_combo == actual_combo)

            results['total'] += 1
            if rank1_correct:
                results['rank1_correct'] += 1
            if rank2_correct:
                results['rank2_correct'] += 1
            if rank3_correct:
                results['rank3_correct'] += 1
            if trifecta_correct:
                results['trifecta_correct'] += 1

            # ケース別集計（予想1位的中時・外れ時）
            if rank1_correct:
                results['case1']['total'] += 1
                if rank2_correct:
                    results['case1']['rank2_correct'] += 1
            else:
                results['case2']['total'] += 1
                if rank2_correct:
                    results['case2']['rank2_correct'] += 1

            # 詳細記録
            results['predictions'].append({
                'race_id': race_id,
                'race_date': race_date,
                'predicted': predicted_combo,
                'actual': actual_combo,
                'rank1_correct': rank1_correct,
                'rank2_correct': rank2_correct,
                'rank3_correct': rank3_correct,
                'trifecta_correct': trifecta_correct
            })

        except Exception as e:
            print(f"エラー (race_id={race_id}): {e}")
            continue

    # 結果表示
    print(f"\n{'='*80}")
    print(f"評価結果: {model_name}")
    print(f"{'='*80}")

    if results['total'] > 0:
        print(f"\n評価レース数: {results['total']:,}レース")
        print(f"\n各順位の的中率:")
        print(f"  1位的中率: {results['rank1_correct']}/{results['total']} = {results['rank1_correct']/results['total']*100:.2f}%")
        print(f"  2位的中率: {results['rank2_correct']}/{results['total']} = {results['rank2_correct']/results['total']*100:.2f}%")
        print(f"  3位的中率: {results['rank3_correct']}/{results['total']} = {results['rank3_correct']/results['total']*100:.2f}%")
        print(f"\n三連単的中率: {results['trifecta_correct']}/{results['total']} = {results['trifecta_correct']/results['total']*100:.2f}%")

        # ケース別分析
        print(f"\n{'='*80}")
        print("ケース別分析（2位予測精度）")
        print(f"{'='*80}")

        if results['case1']['total'] > 0:
            case1_acc = results['case1']['rank2_correct'] / results['case1']['total'] * 100
            print(f"\nケース1（予想1位が的中）:")
            print(f"  レース数: {results['case1']['total']:,} ({results['case1']['total']/results['total']*100:.1f}%)")
            print(f"  2位的中率: {results['case1']['rank2_correct']}/{results['case1']['total']} = {case1_acc:.2f}%")

        if results['case2']['total'] > 0:
            case2_acc = results['case2']['rank2_correct'] / results['case2']['total'] * 100
            print(f"\nケース2（予想1位が外れ）:")
            print(f"  レース数: {results['case2']['total']:,} ({results['case2']['total']/results['total']*100:.1f}%)")
            print(f"  2位的中率: {results['case2']['rank2_correct']}/{results['case2']['total']} = {case2_acc:.2f}%")

            if results['case1']['total'] > 0:
                diff = case1_acc - case2_acc
                print(f"\n  ケース1との差: {diff:+.2f}pt")

    return results


def compare_models(results_v1, results_v2):
    """v1とv2の比較"""
    print(f"\n{'='*80}")
    print("v1とv2の比較")
    print(f"{'='*80}")

    if results_v1['total'] == 0 or results_v2['total'] == 0:
        print("比較するデータが不足しています")
        return

    # 全体の的中率比較
    print("\n【全体の的中率】")
    print(f"{'項目':<20} {'v1':<15} {'v2':<15} {'差分':<15}")
    print("-" * 65)

    for metric, name in [('rank1', '1位'), ('rank2', '2位'), ('rank3', '3位'), ('trifecta', '三連単')]:
        v1_rate = results_v1[f'{metric}_correct'] / results_v1['total'] * 100
        v2_rate = results_v2[f'{metric}_correct'] / results_v2['total'] * 100
        diff = v2_rate - v1_rate

        print(f"{name+'的中率':<20} {v1_rate:>6.2f}% {v2_rate:>14.2f}% {diff:>+13.2f}pt")

    # ケース別比較
    print("\n【ケース別2位予測精度】")
    print(f"{'ケース':<25} {'v1':<15} {'v2':<15} {'差分':<15}")
    print("-" * 70)

    for case_num, case_name in [('case1', '予想1位が的中'), ('case2', '予想1位が外れ')]:
        if results_v1[case_num]['total'] > 0 and results_v2[case_num]['total'] > 0:
            v1_acc = results_v1[case_num]['rank2_correct'] / results_v1[case_num]['total'] * 100
            v2_acc = results_v2[case_num]['rank2_correct'] / results_v2[case_num]['total'] * 100
            diff = v2_acc - v1_acc

            print(f"{case_name:<25} {v1_acc:>6.2f}% {v2_acc:>14.2f}% {diff:>+13.2f}pt")


def main():
    """メイン処理"""
    print("="*80)
    print("v2モデル実測性能評価")
    print("="*80)

    # パス設定
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    model_dir = PROJECT_ROOT / "models"

    # 評価設定
    start_date = '2024-01-01'
    end_date = '2026-01-01'
    max_races = 100  # 最大評価レース数（調整可能）

    print(f"\n評価期間: {start_date} ~ {end_date}")
    print(f"最大評価レース数: {max_races:,}レース")

    # v1モデルで評価
    print("\n" + "="*80)
    print("STEP 1: v1モデルの評価")
    print("="*80)

    predictor_v1 = HierarchicalPredictor(str(db_path), str(model_dir), use_v2=False)
    results_v1 = evaluate_predictions(db_path, predictor_v1, "v1", start_date, end_date, max_races)

    # v2モデルで評価
    print("\n" + "="*80)
    print("STEP 2: v2モデルの評価")
    print("="*80)

    predictor_v2 = HierarchicalPredictor(str(db_path), str(model_dir), use_v2=True)
    results_v2 = evaluate_predictions(db_path, predictor_v2, "v2", start_date, end_date, max_races)

    # 比較
    compare_models(results_v1, results_v2)

    # 結果をCSVに保存
    output_dir = PROJECT_ROOT / "results"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # v1の詳細結果
    if results_v1['predictions']:
        df_v1 = pd.DataFrame(results_v1['predictions'])
        df_v1.to_csv(output_dir / f"v1_predictions_{timestamp}.csv", index=False, encoding='utf-8-sig')
        print(f"\nv1詳細結果保存: results/v1_predictions_{timestamp}.csv")

    # v2の詳細結果
    if results_v2['predictions']:
        df_v2 = pd.DataFrame(results_v2['predictions'])
        df_v2.to_csv(output_dir / f"v2_predictions_{timestamp}.csv", index=False, encoding='utf-8-sig')
        print(f"v2詳細結果保存: results/v2_predictions_{timestamp}.csv")

    # サマリー
    summary = {
        'model': ['v1', 'v2'],
        'total_races': [results_v1['total'], results_v2['total']],
        'rank1_accuracy': [
            results_v1['rank1_correct']/results_v1['total']*100 if results_v1['total'] > 0 else 0,
            results_v2['rank1_correct']/results_v2['total']*100 if results_v2['total'] > 0 else 0
        ],
        'rank2_accuracy': [
            results_v1['rank2_correct']/results_v1['total']*100 if results_v1['total'] > 0 else 0,
            results_v2['rank2_correct']/results_v2['total']*100 if results_v2['total'] > 0 else 0
        ],
        'rank3_accuracy': [
            results_v1['rank3_correct']/results_v1['total']*100 if results_v1['total'] > 0 else 0,
            results_v2['rank3_correct']/results_v2['total']*100 if results_v2['total'] > 0 else 0
        ],
        'trifecta_accuracy': [
            results_v1['trifecta_correct']/results_v1['total']*100 if results_v1['total'] > 0 else 0,
            results_v2['trifecta_correct']/results_v2['total']*100 if results_v2['total'] > 0 else 0
        ],
        'case1_rank2_accuracy': [
            results_v1['case1']['rank2_correct']/results_v1['case1']['total']*100 if results_v1['case1']['total'] > 0 else 0,
            results_v2['case1']['rank2_correct']/results_v2['case1']['total']*100 if results_v2['case1']['total'] > 0 else 0
        ],
        'case2_rank2_accuracy': [
            results_v1['case2']['rank2_correct']/results_v1['case2']['total']*100 if results_v1['case2']['total'] > 0 else 0,
            results_v2['case2']['rank2_correct']/results_v2['case2']['total']*100 if results_v2['case2']['total'] > 0 else 0
        ]
    }

    df_summary = pd.DataFrame(summary)
    df_summary.to_csv(output_dir / f"model_comparison_{timestamp}.csv", index=False, encoding='utf-8-sig')
    print(f"比較サマリー保存: results/model_comparison_{timestamp}.csv")

    print("\n" + "="*80)
    print("評価完了")
    print("="*80)


if __name__ == "__main__":
    main()
