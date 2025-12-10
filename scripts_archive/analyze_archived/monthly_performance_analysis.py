# -*- coding: utf-8 -*-
"""月別パフォーマンス分析

戦略Aの月別成績を詳細に分析
"""

import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


# 戦略A の条件定義
STRATEGY_A_CONDITIONS = [
    # Tier 1: 超高配当狙い
    {'tier': 1, 'name': 'D x B1 x 200-300倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 200, 'odds_max': 300},
    {'tier': 1, 'name': 'D x A1 x 100-150倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 100, 'odds_max': 150},
    {'tier': 1, 'name': 'D x A1 x 200-300倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 200, 'odds_max': 300},
    {'tier': 1, 'name': 'C x B1 x 150-200倍', 'confidence': 'C', 'c1_rank': 'B1', 'odds_min': 150, 'odds_max': 200},

    # Tier 2: 中高配当狙い
    {'tier': 2, 'name': 'D x A2 x 30-40倍', 'confidence': 'D', 'c1_rank': 'A2', 'odds_min': 30, 'odds_max': 40},
    {'tier': 2, 'name': 'D x A1 x 40-50倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 40, 'odds_max': 50},
    {'tier': 2, 'name': 'D x A1 x 20-25倍', 'confidence': 'D', 'c1_rank': 'A1', 'odds_min': 20, 'odds_max': 25},

    # Tier 3: 堅実狙い
    {'tier': 3, 'name': 'D x B1 x 5-10倍', 'confidence': 'D', 'c1_rank': 'B1', 'odds_min': 5, 'odds_max': 10},
]


def evaluate_month(cursor, races, conditions):
    """月間成績を評価"""
    tier_stats = defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})
    total_stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

    for condition in conditions:
        for race in races:
            race_id = race['race_id']

            # 1コース級別チェック
            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank_actual = c1['racer_rank'] if c1 else 'B1'

            if c1_rank_actual != condition['c1_rank']:
                continue

            # 予測情報取得
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

            tier_stats[condition['tier']]['target'] += 1
            tier_stats[condition['tier']]['bet'] += 300
            total_stats['target'] += 1
            total_stats['bet'] += 300

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
                    # 実際の払戻金取得
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        actual_payout = (300 / 100) * payout_row['amount']
                        tier_stats[condition['tier']]['hit'] += 1
                        tier_stats[condition['tier']]['payout'] += actual_payout
                        total_stats['hit'] += 1
                        total_stats['payout'] += actual_payout

    return tier_stats, total_stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("戦略A 月別パフォーマンス分析")
    print("=" * 80)
    print()

    # 2025年の各月のレース取得
    months = [
        ('2025-01', '2025-01-01', '2025-01-31'),
        ('2025-02', '2025-02-01', '2025-02-28'),
        ('2025-03', '2025-03-01', '2025-03-31'),
        ('2025-04', '2025-04-01', '2025-04-30'),
        ('2025-05', '2025-05-01', '2025-05-31'),
        ('2025-06', '2025-06-01', '2025-06-30'),
        ('2025-07', '2025-07-01', '2025-07-31'),
        ('2025-08', '2025-08-01', '2025-08-31'),
        ('2025-09', '2025-09-01', '2025-09-30'),
        ('2025-10', '2025-10-01', '2025-10-31'),
        ('2025-11', '2025-11-01', '2025-11-30'),
        ('2025-12', '2025-12-01', '2025-12-31'),
    ]

    monthly_results = []
    yearly_total = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

    for month_name, start_date, end_date in months:
        cursor.execute('''
            SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
            FROM races r
            WHERE r.race_date >= ? AND r.race_date <= ?
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''', (start_date, end_date))
        races = cursor.fetchall()

        if len(races) == 0:
            continue

        tier_stats, total_stats = evaluate_month(cursor, races, STRATEGY_A_CONDITIONS)

        if total_stats['target'] > 0:
            roi = total_stats['payout'] / total_stats['bet'] * 100
            hit_rate = total_stats['hit'] / total_stats['target'] * 100
            profit = total_stats['payout'] - total_stats['bet']

            monthly_results.append({
                'month': month_name,
                'total_races': len(races),
                'target': total_stats['target'],
                'hit': total_stats['hit'],
                'hit_rate': hit_rate,
                'bet': total_stats['bet'],
                'payout': total_stats['payout'],
                'profit': profit,
                'roi': roi,
                'tier_stats': tier_stats,
            })

            yearly_total['target'] += total_stats['target']
            yearly_total['hit'] += total_stats['hit']
            yearly_total['bet'] += total_stats['bet']
            yearly_total['payout'] += total_stats['payout']

    conn.close()

    # 月別サマリー表示
    print("=" * 80)
    print("月別成績サマリー")
    print("=" * 80)
    print()

    for result in monthly_results:
        print(f"{result['month']}月:")
        print(f"  総レース数: {result['total_races']:,}")
        print(f"  購入: {result['target']:3d}レース, 的中: {result['hit']:2d}回 ({result['hit_rate']:5.1f}%)")
        print(f"  投資: {result['bet']:,}円, 払戻: {result['payout']:,.0f}円")
        print(f"  収支: {result['profit']:+,.0f}円, ROI: {result['roi']:6.1f}%")

        # Tier別表示
        for tier in [1, 2, 3]:
            if result['tier_stats'][tier]['target'] > 0:
                t_stats = result['tier_stats'][tier]
                t_roi = t_stats['payout'] / t_stats['bet'] * 100 if t_stats['bet'] > 0 else 0
                print(f"    Tier {tier}: 購入{t_stats['target']:2d}, 的中{t_stats['hit']:2d}, ROI {t_roi:6.1f}%")
        print()

    # 年間総合
    if yearly_total['target'] > 0:
        yearly_roi = yearly_total['payout'] / yearly_total['bet'] * 100
        yearly_hit_rate = yearly_total['hit'] / yearly_total['target'] * 100
        yearly_profit = yearly_total['payout'] - yearly_total['bet']

        print("=" * 80)
        print("年間総合成績（2025年）")
        print("=" * 80)
        print(f"購入: {yearly_total['target']}レース（月平均{yearly_total['target']/len(monthly_results):.1f}）")
        print(f"的中: {yearly_total['hit']}回（月平均{yearly_total['hit']/len(monthly_results):.1f}）")
        print(f"的中率: {yearly_hit_rate:.1f}%")
        print(f"投資: {yearly_total['bet']:,}円（月平均{yearly_total['bet']/len(monthly_results):,.0f}円）")
        print(f"払戻: {yearly_total['payout']:,.0f}円（月平均{yearly_total['payout']/len(monthly_results):,.0f}円）")
        print(f"収支: {yearly_profit:+,.0f}円（月平均{yearly_profit/len(monthly_results):+,.0f}円）")
        print(f"ROI: {yearly_roi:.1f}%")
        print()

    # 月別成績の統計
    print("=" * 80)
    print("月別統計分析")
    print("=" * 80)
    print()

    profits = [r['profit'] for r in monthly_results]
    rois = [r['roi'] for r in monthly_results]
    black_months = sum(1 for p in profits if p > 0)
    red_months = sum(1 for p in profits if p < 0)

    print(f"黒字月: {black_months}ヶ月 ({black_months/len(monthly_results)*100:.1f}%)")
    print(f"赤字月: {red_months}ヶ月 ({red_months/len(monthly_results)*100:.1f}%)")
    print(f"最大黒字月: {max(profits):+,.0f}円")
    print(f"最大赤字月: {min(profits):+,.0f}円")
    print(f"平均ROI: {sum(rois)/len(rois):.1f}%")
    print(f"最高ROI: {max(rois):.1f}%")
    print(f"最低ROI: {min(rois):.1f}%")
    print()

    # ROI分布
    print("=" * 80)
    print("ROI分布")
    print("=" * 80)
    print()

    roi_ranges = [
        (300, float('inf'), 'ROI 300%以上'),
        (200, 300, 'ROI 200-300%'),
        (150, 200, 'ROI 150-200%'),
        (100, 150, 'ROI 100-150%'),
        (0, 100, 'ROI 0-100%'),
    ]

    for min_roi, max_roi, label in roi_ranges:
        count = sum(1 for r in rois if min_roi <= r < max_roi)
        if count > 0:
            print(f"{label}: {count}ヶ月")

    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
