# -*- coding: utf-8 -*-
"""戦略Aと現在実装の比較

BetTargetEvaluatorの実装内容と戦略Aの理想を比較
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


# 戦略A（理想の8条件）
STRATEGY_A = [
    {'tier': 1, 'name': 'D x B1 x 200-300倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 200, 'odds_max': 300},
    {'tier': 1, 'name': 'D x A1 x 100-150倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 100, 'odds_max': 150},
    {'tier': 1, 'name': 'D x A1 x 200-300倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 200, 'odds_max': 300},
    {'tier': 1, 'name': 'C x B1 x 150-200倍', 'confidence': 'C', 'c1_rank': 'B1', 'odds_min': 150, 'odds_max': 200},
    {'tier': 2, 'name': 'D x A2 x 30-40倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 30, 'odds_max': 40},
    {'tier': 2, 'name': 'D x A1 x 40-50倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 40, 'odds_max': 50},
    {'tier': 2, 'name': 'D x A1 x 20-25倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 20, 'odds_max': 25},
    {'tier': 3, 'name': 'D x B1 x 5-10倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 5, 'odds_max': 10},
]

# BetTargetEvaluatorの実装（現在）
CURRENT_IMPLEMENTATION = [
    {'tier': 1, 'name': 'C x B1 x 150-200倍', 'confidence': 'C', 'c1_rank': 'B1', 'odds_min': 150, 'odds_max': 200},
    {'tier': 1, 'name': 'D x B1 x 200-300倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 200, 'odds_max': 300},
    {'tier': 1, 'name': 'D x A1 x 100-150倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 100, 'odds_max': 150},
    {'tier': 1, 'name': 'D x A1 x 200-300倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 200, 'odds_max': 300},
    {'tier': 2, 'name': 'D x A2 x 30-40倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 30, 'odds_max': 40},
    {'tier': 2, 'name': 'D x A1 x 40-50倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 40, 'odds_max': 50},
    {'tier': 2, 'name': 'D x A1 x 20-25倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 20, 'odds_max': 25},
    {'tier': 3, 'name': 'D x B1 x 5-10倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 5, 'odds_max': 10},
]


def evaluate_conditions(cursor, races, conditions):
    """条件リストを評価"""
    total_stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    condition_results = []

    for condition in conditions:
        stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

        for race in races:
            race_id = race['race_id']

            # 1コース級別
            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank_actual = c1['racer_rank'] if c1 else 'B1'

            if c1_rank_actual != condition['c1_rank']:
                continue

            # 予測情報
            cursor.execute('''
                SELECT pit_number, confidence
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'advance'
                ORDER BY rank_prediction
            ''', (race_id,))
            preds = cursor.fetchall()

            if len(preds) < 6:
                continue

            conf_actual = preds[0]['confidence']
            if conf_actual != condition['confidence']:
                continue

            pred = [p['pit_number'] for p in preds[:3]]
            combo = f"{pred[0]}-{pred[1]}-{pred[2]}"

            # オッズ取得
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?', (race_id, combo))
            odds_row = cursor.fetchone()
            odds = odds_row['odds'] if odds_row else 0

            if odds < condition['odds_min'] or odds >= condition['odds_max']:
                continue

            stats['target'] += 1
            stats['bet'] += 300

            # 実際の結果
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            if len(results) >= 3:
                actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

                if combo == actual_combo:
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        stats['hit'] += 1
                        actual_payout = (300 / 100) * payout_row['amount']
                        stats['payout'] += actual_payout

        if stats['target'] > 0:
            roi = stats['payout'] / stats['bet'] * 100
            hit_rate = stats['hit'] / stats['target'] * 100
            profit = stats['payout'] - stats['bet']

            condition_results.append({
                'name': condition['name'],
                'tier': condition['tier'],
                'target': stats['target'],
                'hit': stats['hit'],
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': profit,
            })

            total_stats['target'] += stats['target']
            total_stats['hit'] += stats['hit']
            total_stats['bet'] += stats['bet']
            total_stats['payout'] += stats['payout']

    return condition_results, total_stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("戦略A vs 現在実装の比較")
    print("=" * 80)
    print()

    # 2025年全期間のレース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    print(f"検証期間: 2025年全期間（{len(races):,}レース）")
    print()

    # 戦略A評価
    print("=" * 80)
    print("【戦略A】理想の8条件")
    print("=" * 80)
    print()

    strategy_a_results, strategy_a_total = evaluate_conditions(cursor, races, STRATEGY_A)

    for result in strategy_a_results:
        print(f"Tier {result['tier']}: {result['name']}")
        print(f"  購入{result['target']:4d}, 的中{result['hit']:3d}, ROI {result['roi']:6.1f}%, 収支{result['profit']:+9,.0f}円")

    print()
    print("戦略A 合計:")
    if strategy_a_total['target'] > 0:
        strategy_a_roi = strategy_a_total['payout'] / strategy_a_total['bet'] * 100
        strategy_a_profit = strategy_a_total['payout'] - strategy_a_total['bet']
        print(f"  購入: {strategy_a_total['target']}レース")
        print(f"  的中: {strategy_a_total['hit']}回")
        print(f"  投資: {strategy_a_total['bet']:,}円")
        print(f"  払戻: {strategy_a_total['payout']:,.0f}円")
        print(f"  収支: {strategy_a_profit:+,.0f}円")
        print(f"  ROI: {strategy_a_roi:.1f}%")
    print()

    # 現在実装評価
    print("=" * 80)
    print("【現在実装】BetTargetEvaluatorの条件")
    print("=" * 80)
    print()

    current_results, current_total = evaluate_conditions(cursor, races, CURRENT_IMPLEMENTATION)

    for result in current_results:
        print(f"Tier {result['tier']}: {result['name']}")
        print(f"  購入{result['target']:4d}, 的中{result['hit']:3d}, ROI {result['roi']:6.1f}%, 収支{result['profit']:+9,.0f}円")

    print()
    print("現在実装 合計:")
    if current_total['target'] > 0:
        current_roi = current_total['payout'] / current_total['bet'] * 100
        current_profit = current_total['payout'] - current_total['bet']
        print(f"  購入: {current_total['target']}レース")
        print(f"  的中: {current_total['hit']}回")
        print(f"  投資: {current_total['bet']:,}円")
        print(f"  払戻: {current_total['payout']:,.0f}円")
        print(f"  収支: {current_profit:+,.0f}円")
        print(f"  ROI: {current_roi:.1f}%")
    print()

    # 差分分析
    print("=" * 80)
    print("差分分析")
    print("=" * 80)
    print()

    if strategy_a_total['target'] > 0 and current_total['target'] > 0:
        strategy_a_roi = strategy_a_total['payout'] / strategy_a_total['bet'] * 100
        strategy_a_profit = strategy_a_total['payout'] - strategy_a_total['bet']
        current_roi = current_total['payout'] / current_total['bet'] * 100
        current_profit = current_total['payout'] - current_total['bet']

        print("項目           | 戦略A      | 現在実装   | 差分")
        print("-" * 60)
        print(f"購入レース     | {strategy_a_total['target']:6d}     | {current_total['target']:6d}     | {current_total['target'] - strategy_a_total['target']:+6d}")
        print(f"的中回数       | {strategy_a_total['hit']:6d}     | {current_total['hit']:6d}     | {current_total['hit'] - strategy_a_total['hit']:+6d}")
        print(f"ROI            | {strategy_a_roi:6.1f}%   | {current_roi:6.1f}%   | {current_roi - strategy_a_roi:+6.1f}%")
        print(f"収支           | {strategy_a_profit:+9,.0f}円 | {current_profit:+9,.0f}円 | {current_profit - strategy_a_profit:+9,.0f}円")

    print()

    # 一致度チェック
    print("=" * 80)
    print("条件一致度チェック")
    print("=" * 80)
    print()

    strategy_a_set = set((c['confidence'], c['c1_rank'], c['odds_min'], c['odds_max']) for c in STRATEGY_A)
    current_set = set((c['confidence'], c['c1_rank'], c['odds_min'], c['odds_max']) for c in CURRENT_IMPLEMENTATION)

    matching = strategy_a_set & current_set
    only_strategy_a = strategy_a_set - current_set
    only_current = current_set - strategy_a_set

    print(f"一致する条件: {len(matching)}/8")
    for cond in matching:
        print(f"  {cond[0]} x {cond[1]} x {cond[2]}-{cond[3]}倍")

    if only_strategy_a:
        print()
        print("戦略Aにあるが現在実装にない条件:")
        for cond in only_strategy_a:
            print(f"  {cond[0]} x {cond[1]} x {cond[2]}-{cond[3]}倍")

    if only_current:
        print()
        print("現在実装にあるが戦略Aにない条件:")
        for cond in only_current:
            print(f"  {cond[0]} x {cond[1]} x {cond[2]}-{cond[3]}倍")

    conn.close()

    print()
    print("=" * 80)
    print("結論: ", end='')
    if len(matching) == 8:
        print("完全一致 [OK]")
    elif len(matching) >= 7:
        print("ほぼ一致 [WARN]")
    else:
        print("不一致あり [NG]")
    print("=" * 80)


if __name__ == '__main__':
    main()
