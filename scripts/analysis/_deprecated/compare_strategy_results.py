"""
戦略Aの前回実績と今回シミュレーション結果の差異分析

前回: 年間+380,070円、ROI 298.9%
今回: 年間-549,180円、ROI 65.0%

この大幅な差の原因を調査
"""

import sys
from pathlib import Path
import sqlite3
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / 'data' / 'boatrace.db'

# 前回の戦略A実績（残タスク一覧.mdより）
PREVIOUS_RESULTS = {
    'total': {
        'races': 637,
        'hits': 52,
        'investment': 191100,
        'payout': 571170,
        'profit': 380070,
        'roi': 298.9,
        'hit_rate': 8.2
    },
    'tier1': {
        'D×B1×200-300倍': {'races': None, 'roi': 746.7, 'profit': 124170, 'bet': 300},
        'D×A1×100-150倍': {'races': None, 'roi': 383.6, 'profit': 51900, 'bet': 300},
        'D×A1×200-300倍': {'races': None, 'roi': 384.7, 'profit': 51240, 'bet': 300},
        'C×B1×150-200倍': {'races': None, 'roi': 337.4, 'profit': 41310, 'bet': 300},
    },
    'tier2': {
        'D×A2×30-40倍': {'races': None, 'roi': 251.4, 'profit': 33150, 'bet': 300},
        'D×A1×40-50倍': {'races': None, 'roi': 488.9, 'profit': 51330, 'bet': 300},
        'D×A1×20-25倍': {'races': None, 'roi': 258.1, 'profit': 19920, 'bet': 300},
    },
    'tier3': {
        'D×B1×5-10倍': {'races': None, 'roi': 110.0, 'profit': 7050, 'bet': 300},
    }
}

# 今回のシミュレーション結果
CURRENT_RESULTS = {
    'total': {
        'races': 785,
        'hits': 312,
        'investment': 1570000,
        'payout': 1020820,
        'profit': -549180,
        'roi': 65.0,
        'hit_rate': 39.75
    },
    'strategies': {
        'D×B1×200-300倍 [Tier1]': {'races': 156, 'hits': 55, 'investment': 312000, 'payout': 152930, 'profit': -159070, 'roi': 49.0, 'hit_rate': 35.26},
        'C×B1×150-200倍': {'races': 554, 'hits': 209, 'investment': 1108000, 'payout': 741610, 'profit': -366390, 'roi': 66.9, 'hit_rate': 37.73},
        'D×A2×30-40倍 [Tier2]': {'races': 26, 'hits': 18, 'investment': 52000, 'payout': 42160, 'profit': -9840, 'roi': 81.1, 'hit_rate': 69.23},
        'D×A1×100-150倍 [Tier2]': {'races': 16, 'hits': 8, 'investment': 32000, 'payout': 41220, 'profit': 9220, 'roi': 128.8, 'hit_rate': 50.00},
        'D×A1×40-50倍 [Tier3]': {'races': 28, 'hits': 20, 'investment': 56000, 'payout': 38380, 'profit': -17620, 'roi': 68.5, 'hit_rate': 71.43},
        'D×A1×200-300倍 [Tier2]': {'races': 5, 'hits': 2, 'investment': 10000, 'payout': 4520, 'profit': -5480, 'roi': 45.2, 'hit_rate': 40.00},
    }
}


def analyze_bet_amount_difference():
    """賭け金の違いを分析"""
    print("=" * 100)
    print("賭け金設定の違い")
    print("=" * 100)

    print("\n【前回の設定】")
    print("  賭け金: 300円（全通り買い想定）")
    print("  計算方法: 単勝式（1点買い）")

    print("\n【今回の設定】")
    print("  賭け金: 100円 × 20通り = 2,000円")
    print("  計算方法: 3連単全通り買い")

    print("\n【差異の原因】")
    print("  [NG] 前回: 単勝買いまたは3連単1点買いを想定（賭け金300円）")
    print("  [NG] 今回: 3連単20通り買いを想定（賭け金2,000円）")
    print("  -> 賭け金が約6.7倍に増加している")


def analyze_strategy_comparison():
    """戦略別の比較"""
    print("\n" + "=" * 100)
    print("戦略別ROI比較")
    print("=" * 100)

    print(f"\n{'戦略':<35} {'前回ROI':>12} {'今回ROI':>12} {'差':>12}")
    print("-" * 100)

    # Tier1比較
    print(f"{'D×B1×200-300倍':<35} {746.7:>11.1f}% {49.0:>11.1f}% {-697.7:>11.1f}pt")
    print(f"{'D×A1×100-150倍':<35} {383.6:>11.1f}% {128.8:>11.1f}% {-254.8:>11.1f}pt")
    print(f"{'D×A1×200-300倍':<35} {384.7:>11.1f}% {45.2:>11.1f}% {-339.5:>11.1f}pt")
    print(f"{'C×B1×150-200倍':<35} {337.4:>11.1f}% {66.9:>11.1f}% {-270.5:>11.1f}pt")

    # Tier2比較
    print(f"{'D×A2×30-40倍':<35} {251.4:>11.1f}% {81.1:>11.1f}% {-170.3:>11.1f}pt")
    print(f"{'D×A1×40-50倍':<35} {488.9:>11.1f}% {68.5:>11.1f}% {-420.4:>11.1f}pt")
    print(f"{'D×A1×20-25倍':<35} {258.1:>11.1f}% {'N/A':>11} {'N/A':>11}")

    # Tier3比較
    print(f"{'D×B1×5-10倍':<35} {110.0:>11.1f}% {'N/A':>11} {'N/A':>11}")

    print("\n【主要な差異】")
    print("  1. 全ての戦略でROIが大幅に低下")
    print("  2. D×A1×20-25倍とD×B1×5-10倍は今回のシミュレーションに含まれていない")
    print("  3. 賭け金の設定が異なる（前回300円 vs 今回2,000円）")


def investigate_missing_strategies():
    """欠落している戦略を調査"""
    print("\n" + "=" * 100)
    print("欠落戦略の調査")
    print("=" * 100)

    conn = sqlite3.connect(str(DB_PATH))

    # D×A1×20-25倍の候補レースを検索
    query1 = """
    SELECT COUNT(*) as count
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
    WHERE r.race_date LIKE '2025%'
      AND p.prediction_type = 'before'
      AND p.confidence = 'D'
      AND p.rank_prediction = 1
      AND e.racer_rank = 'A1'
    """

    cursor = conn.cursor()
    cursor.execute(query1)
    d_a1_count = cursor.fetchone()[0]

    # D×B1×5-10倍の候補レースを検索
    query2 = """
    SELECT COUNT(*) as count
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
    WHERE r.race_date LIKE '2025%'
      AND p.prediction_type = 'before'
      AND p.confidence = 'D'
      AND p.rank_prediction = 1
      AND e.racer_rank = 'B1'
    """

    cursor.execute(query2)
    d_b1_count = cursor.fetchone()[0]

    conn.close()

    print(f"\n【欠落戦略の候補レース数】")
    print(f"  D×A1（全オッズ範囲）: {d_a1_count}レース")
    print(f"  D×B1（全オッズ範囲）: {d_b1_count}レース")
    print(f"\n  → 今回のシミュレーションでは低オッズ範囲（5-25倍）を実装していない")
    print(f"  → これらの戦略はTier2,3で収益貢献していた可能性")


def calculate_corrected_roi():
    """賭け金を300円に補正した場合のROI計算"""
    print("\n" + "=" * 100)
    print("賭け金補正後のROI計算")
    print("=" * 100)

    print("\n【補正方法】")
    print("  今回のシミュレーション結果を賭け金300円ベースに換算")
    print("  換算式: 補正後投資額 = レース数 × 300円")
    print("          補正後ROI = (払戻額 / 補正後投資額) × 100")

    print(f"\n{'戦略':<35} {'レース数':>10} {'払戻額':>15} {'補正投資額':>15} {'補正ROI':>12}")
    print("-" * 100)

    total_corrected_investment = 0
    total_payout = 0

    for strategy, data in CURRENT_RESULTS['strategies'].items():
        corrected_investment = data['races'] * 300
        corrected_roi = (data['payout'] / corrected_investment * 100) if corrected_investment > 0 else 0
        total_corrected_investment += corrected_investment
        total_payout += data['payout']

        print(f"{strategy:<35} {data['races']:>10} {data['payout']:>14,}円 {corrected_investment:>14,}円 {corrected_roi:>11.1f}%")

    total_corrected_roi = (total_payout / total_corrected_investment * 100) if total_corrected_investment > 0 else 0

    print("-" * 100)
    print(f"{'合計':<35} {CURRENT_RESULTS['total']['races']:>10} {total_payout:>14,}円 {total_corrected_investment:>14,}円 {total_corrected_roi:>11.1f}%")

    print(f"\n【補正後の結果】")
    print(f"  補正前ROI: {CURRENT_RESULTS['total']['roi']:.1f}%（賭け金2,000円ベース）")
    print(f"  補正後ROI: {total_corrected_roi:.1f}%（賭け金300円ベース）")
    print(f"  前回ROI: {PREVIOUS_RESULTS['total']['roi']:.1f}%")
    print(f"  差: {total_corrected_roi - PREVIOUS_RESULTS['total']['roi']:+.1f}pt")


def main():
    print("=" * 100)
    print("戦略A 前回実績 vs 今回シミュレーション 差異分析")
    print("=" * 100)

    print("\n【前回実績（残タスク一覧.mdより）】")
    print(f"  年間購入: {PREVIOUS_RESULTS['total']['races']}レース")
    print(f"  年間収支: +{PREVIOUS_RESULTS['total']['profit']:,}円")
    print(f"  ROI: {PREVIOUS_RESULTS['total']['roi']:.1f}%")
    print(f"  賭け金: 300円/レース")

    print("\n【今回シミュレーション】")
    print(f"  年間購入: {CURRENT_RESULTS['total']['races']}レース")
    print(f"  年間収支: {CURRENT_RESULTS['total']['profit']:,}円")
    print(f"  ROI: {CURRENT_RESULTS['total']['roi']:.1f}%")
    print(f"  賭け金: 2,000円/レース（100円×20通り）")

    # 分析実行
    analyze_bet_amount_difference()
    analyze_strategy_comparison()
    investigate_missing_strategies()
    calculate_corrected_roi()

    print("\n" + "=" * 100)
    print("結論")
    print("=" * 100)
    print("\n【主な差異の原因】")
    print("  1. [NG] 賭け金設定の違い:")
    print("     - 前回: 300円/レース（単勝または3連単1点）")
    print("     - 今回: 2,000円/レース（3連単20通り買い）")
    print("     -> 賭け金が約6.7倍に増加")

    print("\n  2. [NG] 低オッズ戦略の欠落:")
    print("     - D x A1 x 20-25倍（Tier2）が未実装")
    print("     - D x B1 x 5-10倍（Tier3）が未実装")
    print("     -> これらは前回の収益に貢献していた")

    print("\n  3. [NG] 的中率の定義の違い:")
    print("     - 前回: 8.2%（3連単的中を想定）")
    print("     - 今回: 39.75%（1着的中のみカウント）")
    print("     -> 今回は1着的中を的中としているが、3連単的中ではない")

    print("\n  4. [WARN] 払戻金計算方法の違い:")
    print("     - 前回: 不明（おそらく実際の3連単払戻または単勝払戻）")
    print("     - 今回: 実際の3連単払戻（1着的中時のみ）")
    print("     -> 1着的中でも2,3着が外れると払戻0円")

    print("\n【改善案】")
    print("  1. 賭け金を300円に統一して再計算")
    print("  2. 低オッズ戦略（20-25倍、5-10倍）を追加実装")
    print("  3. 3連単的中のみをカウントする方式に修正")
    print("  4. 前回のバックテスト手法を確認・再現")

    print("\n" + "=" * 100)


if __name__ == '__main__':
    main()
