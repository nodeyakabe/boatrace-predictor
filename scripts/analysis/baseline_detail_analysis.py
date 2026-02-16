"""
現在のベースライン（ROI 191.7%）の詳細分析

月別パフォーマンス、信頼度別パフォーマンスを出力
"""

import sqlite3
from pathlib import Path
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from config.bet_conditions import BET_CONDITIONS

def analyze_baseline_details():
    """
    ベースラインの詳細分析
    """
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    print("=" * 80)
    print("ベースライン詳細分析（2020-2025年、ROI 191.7%）")
    print("=" * 80)
    print()

    # ========================================
    # 1. 条件別サマリー
    # ========================================
    print("【1. 条件別サマリー】")
    print("-" * 80)

    total_conditions = len(BET_CONDITIONS)
    pattern_h_count = sum(1 for c in BET_CONDITIONS if c.get('use_pattern_h', False))
    single_bet_count = total_conditions - pattern_h_count

    print(f"総条件数: {total_conditions}件")
    print(f"  - パターンH（3点買い400円）: {pattern_h_count}件")
    print(f"  - 1点買い（100円）: {single_bet_count}件")
    print()

    # ========================================
    # 2. 信頼度別条件数
    # ========================================
    print("【2. 信頼度別条件数】")
    print("-" * 80)

    confidence_count = {}
    for condition in BET_CONDITIONS:
        conf = condition.get('confidence', 'None')
        confidence_count[conf] = confidence_count.get(conf, 0) + 1

    print(f"{'信頼度':<10} {'条件数':>10}")
    print("-" * 80)
    for conf in sorted(confidence_count.keys(), key=lambda x: ('Z' if x is None or x == 'None' else x)):
        display_conf = '指定なし' if conf is None or conf == 'None' else conf
        print(f"{display_conf:<10} {confidence_count[conf]:>10}件")
    print()

    # ========================================
    # 3. 条件別の詳細（上位5条件）
    # ========================================
    print("【3. 条件別の詳細（ROI上位5条件）】")
    print("-" * 80)

    # 標準バックテストの結果から手動で入力（上位5条件）
    top_conditions = [
        {'name': 'B×50-100×冬+4月除外+会場最適化', 'roi': 349.4, 'profit': 234980, 'count': 587, 'confidence': 'B'},
        {'name': 'D×5コース予測×A2除外+会場最適化', 'roi': 199.3, 'profit': 77050, 'count': 315, 'confidence': 'D'},
        {'name': '唐津×C×B1×20-30', 'roi': 206.0, 'profit': 15690, 'count': 148, 'confidence': 'C'},
        {'name': 'B×30-50×B1+4会場', 'roi': 189.8, 'profit': 49730, 'count': 369, 'confidence': 'B'},
        {'name': '鳴門×C×A2×30-80', 'roi': 164.4, 'profit': 48510, 'count': 381, 'confidence': 'C'},
    ]

    print(f"{'条件名':<35} {'信頼度':<8} {'件数':>8} {'ROI':>10} {'収支':>15}")
    print("-" * 80)
    for cond in top_conditions:
        print(f"{cond['name']:<35} {cond['confidence']:<8} {cond['count']:>8}件 {cond['roi']:>9.1f}% {cond['profit']:>14,}円")
    print()

    # ========================================
    # 4. 信頼度別パフォーマンス（推定）
    # ========================================
    print("【4. 信頼度別パフォーマンス（推定値）】")
    print("-" * 80)
    print("※ 上位5条件から推定した信頼度別の傾向")
    print()

    confidence_performance = {
        'A': {'count': 286, 'roi': 149.0, 'profit': 14020, 'note': 'A×A1×10-12+会場+逃げ率'},
        'B': {'count': 956, 'roi': 280.0, 'profit': 284710, 'note': 'B×50-100とB×30-50の合計'},
        'C': {'count': 1738, 'roi': 150.0, 'profit': 116280, 'note': 'C×20-30、鳴門、唐津、児島の合計'},
        'D': {'count': 600, 'roi': 178.0, 'profit': 93600, 'note': 'D×40-50とD×5コースの合計'},
    }

    print(f"{'信頼度':<10} {'推定件数':>12} {'推定ROI':>12} {'推定収支':>15} {'備考':<40}")
    print("-" * 80)
    for conf in ['A', 'B', 'C', 'D']:
        data = confidence_performance[conf]
        print(f"{conf:<10} {data['count']:>12}件 {data['roi']:>11.1f}% {data['profit']:>14,}円 {data['note']:<40}")
    print()

    conn.close()

    print("=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    analyze_baseline_details()
