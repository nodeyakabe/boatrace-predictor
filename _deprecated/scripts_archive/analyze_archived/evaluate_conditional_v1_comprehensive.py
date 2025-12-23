"""
条件付きモデルv1の包括的性能評価

2024-2025年データで以下を評価:
1. 1位・2位・3位の個別的中率
2. 三連単的中率
3. 予想1位的中時・外れ時の2位・3位精度
4. ROI（平均オッズとの比較）
"""
import os
import sys
import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.prediction.hierarchical_predictor import HierarchicalPredictor


def evaluate_conditional_v1(db_path, model_dir, max_races=500):
    """条件付きモデルv1を評価"""

    print("="*80)
    print("条件付きモデルv1の包括的評価")
    print("="*80)

    # レースを取得
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

    print(f"\n評価対象: {len(races):,}レース")

    predictor = HierarchicalPredictor(str(db_path), str(model_dir), use_v2=False)

    results = {
        'total': 0,
        'rank1_correct': 0,
        'rank2_correct': 0,
        'rank3_correct': 0,
        'trifecta_correct': 0,
        'case1': {'total': 0, 'rank2_correct': 0, 'rank3_correct': 0},  # 予想1位的中時
        'case2': {'total': 0, 'rank2_correct': 0, 'rank3_correct': 0},  # 予想1位外れ時
        'total_odds': 0,
        'hit_odds': 0,
        'predictions': []
    }

    for i, (race_id, race_date, venue_code, race_number) in enumerate(races):
        if (i + 1) % 100 == 0:
            print(f"処理中: {i+1}/{len(races)} レース...")

        try:
            # 予測実行
            prediction = predictor.predict_race(race_id, use_conditional_model=True)

            if 'error' in prediction or not prediction.get('top_combinations'):
                continue

            # 予測結果
            top_trifecta = prediction['top_combinations'][0]
            predicted_combo = top_trifecta[0]
            predicted_pits = [int(p) for p in predicted_combo.split('-')]

            # 実際の結果
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

                # オッズ取得
                cursor.execute("""
                    SELECT odds FROM trifecta_odds
                    WHERE race_id = ? AND combination = ?
                """, (race_id, predicted_combo))
                odds_row = cursor.fetchone()
                predicted_odds = odds_row[0] if odds_row else None

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

            # ケース別集計
            if rank1_correct:
                results['case1']['total'] += 1
                if rank2_correct:
                    results['case1']['rank2_correct'] += 1
                if rank3_correct:
                    results['case1']['rank3_correct'] += 1
            else:
                results['case2']['total'] += 1
                if rank2_correct:
                    results['case2']['rank2_correct'] += 1
                if rank3_correct:
                    results['case2']['rank3_correct'] += 1

            # オッズ集計
            if predicted_odds:
                results['total_odds'] += predicted_odds
                if trifecta_correct:
                    results['hit_odds'] += predicted_odds

            # 詳細記録
            results['predictions'].append({
                'race_id': race_id,
                'race_date': race_date,
                'predicted': predicted_combo,
                'actual': actual_combo,
                'rank1_correct': rank1_correct,
                'rank2_correct': rank2_correct,
                'rank3_correct': rank3_correct,
                'trifecta_correct': trifecta_correct,
                'odds': predicted_odds
            })

        except Exception as e:
            print(f"エラー (race_id={race_id}): {e}")
            continue

    return results


def print_results(results):
    """結果を表示"""
    if results['total'] == 0:
        print("評価データなし")
        return

    print(f"\n{'='*80}")
    print("評価結果サマリー")
    print(f"{'='*80}")

    print(f"\n評価レース数: {results['total']:,}レース")

    # 各順位の的中率
    print(f"\n【各順位の的中率】")
    rank1_rate = results['rank1_correct'] / results['total'] * 100
    rank2_rate = results['rank2_correct'] / results['total'] * 100
    rank3_rate = results['rank3_correct'] / results['total'] * 100

    print(f"  1位的中率: {results['rank1_correct']:4d}/{results['total']} = {rank1_rate:6.2f}% (ランダム: 16.67%)")
    print(f"  2位的中率: {results['rank2_correct']:4d}/{results['total']} = {rank2_rate:6.2f}% (ランダム: 20.00%)")
    print(f"  3位的中率: {results['rank3_correct']:4d}/{results['total']} = {rank3_rate:6.2f}% (ランダム: 25.00%)")

    # 三連単的中率
    trifecta_rate = results['trifecta_correct'] / results['total'] * 100
    print(f"\n【三連単的中率】")
    print(f"  的中数: {results['trifecta_correct']:4d}/{results['total']}")
    print(f"  的中率: {trifecta_rate:.2f}% (ランダム: 0.83%)")
    print(f"  改善倍率: {trifecta_rate / 0.83:.1f}倍")

    # ケース別分析
    print(f"\n{'='*80}")
    print("ケース別分析")
    print(f"{'='*80}")

    if results['case1']['total'] > 0:
        case1_rank2 = results['case1']['rank2_correct'] / results['case1']['total'] * 100
        case1_rank3 = results['case1']['rank3_correct'] / results['case1']['total'] * 100
        print(f"\n【ケース1: 予想1位が的中】")
        print(f"  発生率: {results['case1']['total']:4d}/{results['total']} = {results['case1']['total']/results['total']*100:.1f}%")
        print(f"  2位的中率: {results['case1']['rank2_correct']:4d}/{results['case1']['total']} = {case1_rank2:.2f}% (ランダム: 20.00%)")
        print(f"  3位的中率: {results['case1']['rank3_correct']:4d}/{results['case1']['total']} = {case1_rank3:.2f}% (ランダム: 25.00%)")

    if results['case2']['total'] > 0:
        case2_rank2 = results['case2']['rank2_correct'] / results['case2']['total'] * 100
        case2_rank3 = results['case2']['rank3_correct'] / results['case2']['total'] * 100
        print(f"\n【ケース2: 予想1位が外れ】")
        print(f"  発生率: {results['case2']['total']:4d}/{results['total']} = {results['case2']['total']/results['total']*100:.1f}%")
        print(f"  2位的中率: {results['case2']['rank2_correct']:4d}/{results['case2']['total']} = {case2_rank2:.2f}% (ランダム: 20.00%)")
        print(f"  3位的中率: {results['case2']['rank3_correct']:4d}/{results['case2']['total']} = {case2_rank3:.2f}% (ランダム: 25.00%)")

        if results['case1']['total'] > 0:
            print(f"\n  ケース1との差（2位）: {case1_rank2 - case2_rank2:+.2f}pt")
            print(f"  ケース1との差（3位）: {case1_rank3 - case2_rank3:+.2f}pt")

    # ROI分析
    if results['trifecta_correct'] > 0:
        avg_odds = results['total_odds'] / results['total']
        avg_hit_odds = results['hit_odds'] / results['trifecta_correct']
        roi = (results['hit_odds'] / results['total']) * 100

        print(f"\n{'='*80}")
        print("ROI分析")
        print(f"{'='*80}")
        print(f"\n  平均オッズ（全予想）: {avg_odds:.2f}倍")
        print(f"  平均オッズ（的中時）: {avg_hit_odds:.2f}倍")
        print(f"  ROI: {roi:.2f}%")
        print(f"  期待収支: 100円 → {roi:.0f}円")


def analyze_issues(results):
    """問題点を分析"""
    print(f"\n{'='*80}")
    print("問題点の分析")
    print(f"{'='*80}")

    if results['total'] == 0:
        return

    rank1_rate = results['rank1_correct'] / results['total'] * 100
    rank2_rate = results['rank2_correct'] / results['total'] * 100
    rank3_rate = results['rank3_correct'] / results['total'] * 100

    issues = []

    # 1位精度チェック
    if rank1_rate < 50:
        issues.append(f"1位的中率が{rank1_rate:.1f}%と低い（目標: 60%以上）")

    # 2位精度チェック
    if rank2_rate < 30:
        issues.append(f"2位的中率が{rank2_rate:.1f}%と低い（目標: 35%以上）")

    # 3位精度チェック
    if rank3_rate < 30:
        issues.append(f"3位的中率が{rank3_rate:.1f}%と低い（目標: 35%以上）")

    # ケース2の精度チェック
    if results['case2']['total'] > 0:
        case2_rank2 = results['case2']['rank2_correct'] / results['case2']['total'] * 100
        if case2_rank2 < 20:
            issues.append(f"予想1位外れ時の2位的中率が{case2_rank2:.1f}%とランダム以下")

    if issues:
        print("\n主要な問題点:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("\n主要な問題は検出されませんでした")


def suggest_improvements(results):
    """改善策を提案"""
    print(f"\n{'='*80}")
    print("改善策の提案")
    print(f"{'='*80}")

    if results['total'] == 0:
        return

    rank1_rate = results['rank1_correct'] / results['total'] * 100
    rank2_rate = results['rank2_correct'] / results['total'] * 100

    suggestions = []

    # 1位精度に基づく提案
    if rank1_rate < 60:
        suggestions.append({
            'priority': 'HIGH',
            'target': 'Stage1モデル（1位予測）',
            'issue': f'1位的中率 {rank1_rate:.1f}% （目標60%未満）',
            'solution': [
                'より多くの特徴量を追加（前走成績、コース別勝率など）',
                'モデルアーキテクチャの改善（LGBM→XGBoost等）',
                '学習データの期間を調整（直近データ重視）'
            ]
        })

    # 2位精度に基づく提案
    if rank2_rate < 35:
        suggestions.append({
            'priority': 'HIGH',
            'target': 'Stage2モデル（2位予測）',
            'issue': f'2位的中率 {rank2_rate:.1f}% （目標35%未満）',
            'solution': [
                '予想1位との相対的特徴量を強化',
                '展示タイムの差分特徴量を追加',
                'ST差の活用を改善'
            ]
        })

    # ケース2の精度に基づく提案
    if results['case2']['total'] > 0:
        case2_rank2 = results['case2']['rank2_correct'] / results['case2']['total'] * 100
        if case2_rank2 < 20:
            suggestions.append({
                'priority': 'CRITICAL',
                'target': 'Stage2モデル（予想1位外れ時）',
                'issue': f'予想1位外れ時の2位的中率 {case2_rank2:.1f}% （ランダム以下）',
                'solution': [
                    'v2アプローチ: 予想1位を条件とした学習データで再学習',
                    'アンサンブル: 複数の予想1位候補で予測して統合',
                    '信頼度フィルタ: 予想1位の確信度が低い場合は別ロジック'
                ]
            })

    if suggestions:
        print("\n推奨される改善策:\n")
        for i, sug in enumerate(suggestions, 1):
            print(f"【改善策{i}】優先度: {sug['priority']}")
            print(f"  対象: {sug['target']}")
            print(f"  問題: {sug['issue']}")
            print(f"  解決策:")
            for j, sol in enumerate(sug['solution'], 1):
                print(f"    {j}. {sol}")
            print()
    else:
        print("\n現時点で明確な改善策は不要です（十分な精度）")


def main():
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    model_dir = PROJECT_ROOT / "models"

    # 500レースで評価
    results = evaluate_conditional_v1(db_path, model_dir, max_races=500)

    # 結果表示
    print_results(results)

    # 問題点分析
    analyze_issues(results)

    # 改善策提案
    suggest_improvements(results)

    # CSVに保存
    if results['predictions']:
        output_dir = PROJECT_ROOT / "results"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        df = pd.DataFrame(results['predictions'])
        csv_path = output_dir / f"conditional_v1_evaluation_{timestamp}.csv"
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"\n詳細結果保存: {csv_path.relative_to(PROJECT_ROOT)}")

    print(f"\n{'='*80}")
    print("評価完了")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
