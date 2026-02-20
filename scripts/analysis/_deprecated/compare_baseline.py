#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
旧条件（ベースライン）と新条件の比較

HANDOVER.mdのベースライン（2025年）と新条件の比較
"""
import sqlite3
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 旧条件（HANDOVER.mdのベースライン）
OLD_CONDITIONS = [
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'venue_filter': None},
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40},
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None},
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50, 'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]},
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30, 'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80, 'venue_filter': [14]},
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None, 'c1_second_rate_min': 20, 'c1_second_rate_max': 30},
    {'name': 'D×5コース予測', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'], 'odds_min': 10, 'odds_max': 200, 'venue_filter': None, 'predicted_course': 5},
]

# 新条件（2026-01-07改善後）
NEW_CONDITIONS = [
    {'name': 'A×A1×10-12+会場', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': [10, 14, 21, 18, 8, 19, 12]},
    # A×A1×14-16 廃止
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40},
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None},
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50, 'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]},
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30, 'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80, 'venue_filter': [14]},
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None, 'c1_second_rate_min': 20, 'c1_second_rate_max': 30},
    {'name': 'D×5コース予測', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'], 'odds_min': 10, 'odds_max': 200, 'venue_filter': None, 'predicted_course': 5},
]


def analyze_condition(cursor, cond, year_start, year_end):
    """条件別のROIを計算（standard_backtest.pyと同じクエリ）"""
    c1_rank_str = "','".join(cond['c1_rank'])

    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            rp.confidence,
            e1.racer_rank as c1_rank,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {motor_clause}
        {predicted_course_clause}
        {c1_second_rate_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = rb.race_id
                 AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                ), 0
            ) as pred_odds,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN 1 ELSE 0
            END as is_hit,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM race_base rb
    )
    SELECT
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) as payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    '''
    cursor.execute(query)
    row = cursor.fetchone()
    bets, hits, payout = row
    if bets and bets > 0:
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        return {'bets': bets, 'hits': hits or 0, 'roi': roi, 'profit': profit}
    return {'bets': 0, 'hits': 0, 'roi': 0, 'profit': 0}


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("旧条件（ベースライン）vs 新条件 比較【2025年】")
    print("=" * 80)

    # 旧条件
    print("\n【旧条件（HANDOVER.mdのベースライン）】")
    print("-" * 80)
    print(f"{'条件':<25} {'件数':>8} {'的中':>6} {'ROI':>10} {'収支':>12}")
    print("-" * 80)

    old_total = 0
    old_payout = 0

    for cond in OLD_CONDITIONS:
        result = analyze_condition(cursor, cond, 2025, 2025)
        old_total += result['bets']
        old_payout += result['bets'] * 100 + result['profit']
        profit_str = f"+{int(result['profit']):,}" if result['profit'] >= 0 else f"{int(result['profit']):,}"
        print(f"{cond['name']:<25} {result['bets']:>8} {result['hits']:>6} {result['roi']:>9.1f}% {profit_str:>12}")

    old_investment = old_total * 100
    old_roi = (old_payout / old_investment * 100) if old_investment > 0 else 0
    old_profit = old_payout - old_investment
    old_profit_str = f"+{int(old_profit):,}" if old_profit >= 0 else f"{int(old_profit):,}"
    print("-" * 80)
    print(f"{'合計':<25} {old_total:>8} {'-':>6} {old_roi:>9.1f}% {old_profit_str:>12}")

    # 新条件
    print("\n【新条件（2026-01-07改善後）】")
    print("-" * 80)
    print(f"{'条件':<25} {'件数':>8} {'的中':>6} {'ROI':>10} {'収支':>12}")
    print("-" * 80)

    new_total = 0
    new_payout = 0

    for cond in NEW_CONDITIONS:
        result = analyze_condition(cursor, cond, 2025, 2025)
        new_total += result['bets']
        new_payout += result['bets'] * 100 + result['profit']
        profit_str = f"+{int(result['profit']):,}" if result['profit'] >= 0 else f"{int(result['profit']):,}"
        print(f"{cond['name']:<25} {result['bets']:>8} {result['hits']:>6} {result['roi']:>9.1f}% {profit_str:>12}")

    new_investment = new_total * 100
    new_roi = (new_payout / new_investment * 100) if new_investment > 0 else 0
    new_profit = new_payout - new_investment
    new_profit_str = f"+{int(new_profit):,}" if new_profit >= 0 else f"{int(new_profit):,}"
    print("-" * 80)
    print(f"{'合計':<25} {new_total:>8} {'-':>6} {new_roi:>9.1f}% {new_profit_str:>12}")

    # 比較サマリー
    print("\n" + "=" * 80)
    print("【改善効果サマリー（2025年）】")
    print("=" * 80)

    print(f"\n{'指標':<20} {'旧条件':>15} {'新条件':>15} {'差分':>15}")
    print("-" * 65)
    print(f"{'件数':<20} {old_total:>15,} {new_total:>15,} {new_total - old_total:>+15,}")
    print(f"{'ROI':<20} {old_roi:>14.1f}% {new_roi:>14.1f}% {new_roi - old_roi:>+14.1f}pt")
    print(f"{'収支':<20} {int(old_profit):>14,}円 {int(new_profit):>14,}円 {int(new_profit - old_profit):>+14,}円")

    # 廃止条件の影響
    print("\n【廃止条件の影響】")
    old_14_16 = analyze_condition(cursor, OLD_CONDITIONS[1], 2025, 2025)
    profit_str = f"+{int(old_14_16['profit']):,}" if old_14_16['profit'] >= 0 else f"{int(old_14_16['profit']):,}"
    print(f"A×A1×14-16: {old_14_16['bets']}件, ROI {old_14_16['roi']:.1f}%, 収支 {profit_str}円")
    print(f"→ 廃止により収支 {-int(old_14_16['profit']):+,}円 の影響")

    # 会場フィルターの影響
    print("\n【会場フィルターの影響】")
    old_10_12 = analyze_condition(cursor, OLD_CONDITIONS[0], 2025, 2025)
    new_10_12 = analyze_condition(cursor, NEW_CONDITIONS[0], 2025, 2025)

    old_profit_str = f"+{int(old_10_12['profit']):,}" if old_10_12['profit'] >= 0 else f"{int(old_10_12['profit']):,}"
    new_profit_str = f"+{int(new_10_12['profit']):,}" if new_10_12['profit'] >= 0 else f"{int(new_10_12['profit']):,}"

    print(f"A×A1×10-12（旧・全会場）: {old_10_12['bets']}件, ROI {old_10_12['roi']:.1f}%, 収支 {old_profit_str}円")
    print(f"A×A1×10-12（新・7会場）:  {new_10_12['bets']}件, ROI {new_10_12['roi']:.1f}%, 収支 {new_profit_str}円")
    print(f"→ 件数 {new_10_12['bets'] - old_10_12['bets']:+,}件, 収支 {int(new_10_12['profit'] - old_10_12['profit']):+,}円")

    conn.close()


if __name__ == '__main__':
    main()
