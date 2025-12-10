# -*- coding: utf-8 -*-
"""不採用6条件の活用方法検討

戦略Aに含まれない6件の超高ROI条件について、
実運用での活用可能性を検証
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


# 不採用の6条件
UNUSED_6_CONDITIONS = [
    {'id': 8, 'name': 'C x A1 x 150-200倍', 'confidence': 'C', 'c1_rank': 'A1', 'odds_min': 150, 'odds_max': 200, 'expected_roi': 245.6},
    {'id': 9, 'name': 'D x A1 x 25-30倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 25, 'odds_max': 30, 'expected_roi': 215.8},
    {'id': 10, 'name': 'B x A2 x 20-25倍', 'confidence': 'B', 'c1_rank': 'A2', 'odds_min': 20, 'odds_max': 25, 'expected_roi': 215.0},
    {'id': 11, 'name': 'D x A2 x 100-150倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 100, 'odds_max': 150, 'expected_roi': 193.4},
    {'id': 12, 'name': 'C x A2 x 70-100倍', 'confidence': 'C', 'c1_rank': 'A2', 'odds_min': 70, 'odds_max': 100, 'expected_roi': 176.7},
    {'id': 13, 'name': 'C x A2 x 50-70倍', 'confidence': 'C', 'c1_rank': 'A2', 'odds_min': 50, 'odds_max': 70, 'expected_roi': 160.5},
]


def evaluate_condition(cursor, races, condition):
    """単一条件の詳細評価"""
    stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    monthly_stats = defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})

    # 連敗追跡
    max_consecutive_losses = 0
    current_streak = 0

    for race in races:
        race_id = race['race_id']
        race_date = race['race_date']
        month = race_date[:7]  # YYYY-MM

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
        monthly_stats[month]['target'] += 1
        monthly_stats[month]['bet'] += 300

        # 実際の結果
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        hit = False
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
                    monthly_stats[month]['hit'] += 1
                    monthly_stats[month]['payout'] += actual_payout
                    hit = True
                    current_streak = 0

        if not hit:
            current_streak += 1
            max_consecutive_losses = max(max_consecutive_losses, current_streak)

    # 結果計算
    if stats['target'] > 0:
        roi = stats['payout'] / stats['bet'] * 100
        hit_rate = stats['hit'] / stats['target'] * 100
        profit = stats['payout'] - stats['bet']
        avg_purchase_per_month = stats['target'] / 12

        # 月別黒字率
        black_months = sum(1 for m_stats in monthly_stats.values() if m_stats['payout'] > m_stats['bet'])
        red_months = sum(1 for m_stats in monthly_stats.values() if m_stats['payout'] < m_stats['bet'])
        total_months = len([m for m, m_stats in monthly_stats.items() if m_stats['target'] > 0])

        return {
            'target': stats['target'],
            'hit': stats['hit'],
            'hit_rate': hit_rate,
            'roi': roi,
            'profit': profit,
            'avg_purchase_per_month': avg_purchase_per_month,
            'max_consecutive_losses': max_consecutive_losses,
            'black_months': black_months,
            'red_months': red_months,
            'total_months': total_months,
            'black_month_rate': black_months / total_months * 100 if total_months > 0 else 0,
        }
    else:
        return None


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("不採用6条件の活用方法検討")
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

    results = []

    for condition in UNUSED_6_CONDITIONS:
        print(f"{'=' * 80}")
        print(f"条件 #{condition['id']}: {condition['name']}")
        print(f"{'=' * 80}")
        print()

        result = evaluate_condition(cursor, races, condition)

        if result:
            results.append({
                'condition': condition,
                'result': result,
            })

            print(f"期待ROI: {condition['expected_roi']:.1f}%")
            print(f"実測ROI: {result['roi']:.1f}%")
            print(f"達成率: {result['roi'] / condition['expected_roi'] * 100:.1f}%")
            print()
            print(f"年間購入: {result['target']}レース（月平均{result['avg_purchase_per_month']:.1f}）")
            print(f"年間的中: {result['hit']}回")
            print(f"的中率: {result['hit_rate']:.1f}%")
            print(f"年間収支: {result['profit']:+,.0f}円")
            print(f"最大連敗: {result['max_consecutive_losses']}回")
            print()
            print(f"黒字月: {result['black_months']}ヶ月（{result['black_month_rate']:.1f}%）")
            print(f"赤字月: {result['red_months']}ヶ月")
            print()

            # 評価
            print("評価:")
            issues = []
            strengths = []

            # ROI評価
            if result['roi'] >= condition['expected_roi'] * 0.9:
                strengths.append(f"  [OK] ROI達成（{result['roi']:.1f}% >= {condition['expected_roi'] * 0.9:.1f}%）")
            else:
                issues.append(f"  [WARN] ROI未達（{result['roi']:.1f}% < {condition['expected_roi'] * 0.9:.1f}%）")

            # 購入頻度評価
            if result['avg_purchase_per_month'] >= 5:
                strengths.append(f"  [OK] 十分な購入頻度（月{result['avg_purchase_per_month']:.1f}レース）")
            elif result['avg_purchase_per_month'] >= 2:
                issues.append(f"  [WARN] やや低頻度（月{result['avg_purchase_per_month']:.1f}レース）")
            else:
                issues.append(f"  [NG] 低頻度すぎる（月{result['avg_purchase_per_month']:.1f}レース）")

            # 連敗評価
            if result['max_consecutive_losses'] <= 10:
                strengths.append(f"  [OK] 連敗リスク低（最大{result['max_consecutive_losses']}回）")
            elif result['max_consecutive_losses'] <= 20:
                issues.append(f"  [WARN] 連敗リスク中（最大{result['max_consecutive_losses']}回）")
            else:
                issues.append(f"  [NG] 連敗リスク高（最大{result['max_consecutive_losses']}回）")

            # 黒字月率評価
            if result['black_month_rate'] >= 60:
                strengths.append(f"  [OK] 安定した黒字率（{result['black_month_rate']:.1f}%）")
            elif result['black_month_rate'] >= 40:
                issues.append(f"  [WARN] やや不安定（黒字率{result['black_month_rate']:.1f}%）")
            else:
                issues.append(f"  [NG] 不安定（黒字率{result['black_month_rate']:.1f}%）")

            for s in strengths:
                print(s)
            for i in issues:
                print(i)

            print()

            # 推奨度
            if len(issues) == 0:
                recommendation = "即追加推奨"
            elif len(issues) <= 1:
                recommendation = "条件付き追加推奨"
            elif len(issues) <= 2:
                recommendation = "慎重に検討"
            else:
                recommendation = "追加非推奨"

            print(f"推奨度: {recommendation}")
            print()

        else:
            print("  購入対象レースなし")
            print()

    conn.close()

    # 総合サマリー
    print("=" * 80)
    print("総合サマリー（全6条件）")
    print("=" * 80)
    print()

    if results:
        total_target = sum(r['result']['target'] for r in results)
        total_hit = sum(r['result']['hit'] for r in results)
        total_bet = total_target * 300
        total_payout = sum(r['result']['profit'] for r in results) + total_bet

        if total_bet > 0:
            total_roi = total_payout / total_bet * 100
            total_profit = total_payout - total_bet

            print(f"合計購入: {total_target}レース（月{total_target/12:.1f}）")
            print(f"合計的中: {total_hit}回（月{total_hit/12:.1f}）")
            print(f"合計投資: {total_bet:,}円（月{total_bet/12:,.0f}円）")
            print(f"合計払戻: {total_payout:,.0f}円（月{total_payout/12:,.0f}円）")
            print(f"合計収支: {total_profit:+,.0f}円（月{total_profit/12:+,.0f}円）")
            print(f"合計ROI: {total_roi:.1f}%")
            print()

            # 戦略A+6条件のシミュレーション
            print("=" * 80)
            print("戦略A + 6条件のシミュレーション")
            print("=" * 80)
            print()

            strategy_a_target = 637
            strategy_a_hit = 52
            strategy_a_bet = 191100
            strategy_a_payout = 571170
            strategy_a_profit = 380070
            strategy_a_roi = 298.9

            combined_target = strategy_a_target + total_target
            combined_hit = strategy_a_hit + total_hit
            combined_bet = strategy_a_bet + total_bet
            combined_payout = strategy_a_payout + total_payout
            combined_profit = strategy_a_profit + total_profit
            combined_roi = combined_payout / combined_bet * 100

            print("項目           | 戦略A      | +6条件     | 合計")
            print("-" * 70)
            print(f"購入レース     | {strategy_a_target:6d}     | {total_target:6d}     | {combined_target:6d}")
            print(f"的中回数       | {strategy_a_hit:6d}     | {total_hit:6d}     | {combined_hit:6d}")
            print(f"年間投資       | {strategy_a_bet:9,}円 | {total_bet:9,}円 | {combined_bet:9,}円")
            print(f"年間収支       | {strategy_a_profit:+9,}円 | {total_profit:+9,}円 | {combined_profit:+9,}円")
            print(f"ROI            | {strategy_a_roi:6.1f}%   | {total_roi:6.1f}%   | {combined_roi:6.1f}%")
            print()

    print("=" * 80)


if __name__ == '__main__':
    main()
