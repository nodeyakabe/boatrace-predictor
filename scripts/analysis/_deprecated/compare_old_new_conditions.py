#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
旧条件と新条件の比較スクリプト

旧条件（ベースライン）:
- A×A1×10-12（会場フィルターなし）
- A×A1×14-16（存在）
- A×B1×Motor40%+

新条件（2026-01-07改善後）:
- A×A1×10-12+会場（7会場限定）
- A×A1×14-16（廃止）
- A×B1×Motor40%+（変更なし）
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

# 旧条件（ベースライン）
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


def analyze_condition(cursor, cond, year):
    """条件別のROIを計算"""
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

    query = f"""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN res.result_123 = rp1.pit_number || '-' || rp2.pit_number || '-' || rp3.pit_number THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN res.result_123 = rp1.pit_number || '-' || rp2.pit_number || '-' || rp3.pit_number
            THEN COALESCE(o.odds, 0) * 100 ELSE 0 END) as payout
    FROM races r
    JOIN race_predictions rp1 ON r.race_id = rp1.race_id AND rp1.predicted_rank = 1 AND rp1.prediction_type = 'advance'
    JOIN race_predictions rp2 ON r.race_id = rp2.race_id AND rp2.predicted_rank = 2 AND rp2.prediction_type = 'advance'
    JOIN race_predictions rp3 ON r.race_id = rp3.race_id AND rp3.predicted_rank = 3 AND rp3.prediction_type = 'advance'
    JOIN ml_analysis_features mf ON r.race_id = mf.race_id AND mf.feature_type = 'advance'
    JOIN entries e1 ON r.race_id = e1.race_id AND e1.pit_number = 1
    LEFT JOIN results res ON r.race_id = res.race_id
    LEFT JOIN trifecta_odds o ON r.race_id = o.race_id
        AND o.combination = rp1.pit_number || '-' || rp2.pit_number || '-' || rp3.pit_number
    WHERE strftime('%Y', r.race_date) = '{year}'
      AND mf.confidence = '{cond['confidence']}'
      AND e1.class_name IN ('{c1_rank_str}')
      AND COALESCE(o.odds, 0) >= {cond['odds_min']}
      AND COALESCE(o.odds, 0) < {cond['odds_max']}
      {venue_clause}
      {motor_clause}
      {predicted_course_clause}
      {c1_second_rate_clause}
    """

    cursor.execute(query)
    row = cursor.fetchone()

    if row and row[0] > 0:
        total, hits, payout = row
        investment = total * 100
        profit = payout - investment
        roi = (payout / investment * 100) if investment > 0 else 0
        return {'total': total, 'hits': hits or 0, 'payout': payout or 0, 'investment': investment, 'profit': profit, 'roi': roi}
    return {'total': 0, 'hits': 0, 'payout': 0, 'investment': 0, 'profit': 0, 'roi': 0}


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("旧条件 vs 新条件 比較（2025年）")
    print("=" * 80)

    # 旧条件
    print("\n【旧条件（ベースライン）】")
    print("-" * 80)
    print(f"{'条件':<25} {'件数':>8} {'的中':>6} {'ROI':>10} {'収支':>12}")
    print("-" * 80)

    old_total = 0
    old_investment = 0
    old_payout = 0

    for cond in OLD_CONDITIONS:
        result = analyze_condition(cursor, cond, '2025')
        old_total += result['total']
        old_investment += result['investment']
        old_payout += result['payout']
        profit_str = f"+{int(result['profit']):,}" if result['profit'] >= 0 else f"{int(result['profit']):,}"
        print(f"{cond['name']:<25} {result['total']:>8} {result['hits']:>6} {result['roi']:>9.1f}% {profit_str:>12}")

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
    new_investment = 0
    new_payout = 0

    for cond in NEW_CONDITIONS:
        result = analyze_condition(cursor, cond, '2025')
        new_total += result['total']
        new_investment += result['investment']
        new_payout += result['payout']
        profit_str = f"+{int(result['profit']):,}" if result['profit'] >= 0 else f"{int(result['profit']):,}"
        print(f"{cond['name']:<25} {result['total']:>8} {result['hits']:>6} {result['roi']:>9.1f}% {profit_str:>12}")

    new_roi = (new_payout / new_investment * 100) if new_investment > 0 else 0
    new_profit = new_payout - new_investment
    new_profit_str = f"+{int(new_profit):,}" if new_profit >= 0 else f"{int(new_profit):,}"
    print("-" * 80)
    print(f"{'合計':<25} {new_total:>8} {'-':>6} {new_roi:>9.1f}% {new_profit_str:>12}")

    # 比較サマリー
    print("\n" + "=" * 80)
    print("【改善効果サマリー】")
    print("=" * 80)

    diff_total = new_total - old_total
    diff_roi = new_roi - old_roi
    diff_profit = new_profit - old_profit

    print(f"\n{'指標':<20} {'旧条件':>15} {'新条件':>15} {'差分':>15}")
    print("-" * 65)
    print(f"{'件数':<20} {old_total:>15,} {new_total:>15,} {diff_total:>+15,}")
    print(f"{'ROI':<20} {old_roi:>14.1f}% {new_roi:>14.1f}% {diff_roi:>+14.1f}pt")
    print(f"{'収支':<20} {int(old_profit):>14,}円 {int(new_profit):>14,}円 {int(diff_profit):>+14,}円")

    # 廃止条件の影響
    print("\n【廃止条件の影響（A×A1×14-16）】")
    old_14_16 = analyze_condition(cursor, OLD_CONDITIONS[1], '2025')
    profit_str = f"+{int(old_14_16['profit']):,}" if old_14_16['profit'] >= 0 else f"{int(old_14_16['profit']):,}"
    print(f"  2025年: {old_14_16['total']}件, ROI {old_14_16['roi']:.1f}%, 収支 {profit_str}円")
    print(f"  → 廃止により収支 {-int(old_14_16['profit']):+,}円 の影響")

    # 会場フィルターの影響
    print("\n【会場フィルターの影響（A×A1×10-12）】")
    old_10_12 = analyze_condition(cursor, OLD_CONDITIONS[0], '2025')
    new_10_12 = analyze_condition(cursor, NEW_CONDITIONS[0], '2025')

    old_profit_str = f"+{int(old_10_12['profit']):,}" if old_10_12['profit'] >= 0 else f"{int(old_10_12['profit']):,}"
    new_profit_str = f"+{int(new_10_12['profit']):,}" if new_10_12['profit'] >= 0 else f"{int(new_10_12['profit']):,}"

    print(f"  旧（全会場）: {old_10_12['total']}件, ROI {old_10_12['roi']:.1f}%, 収支 {old_profit_str}円")
    print(f"  新（7会場）:  {new_10_12['total']}件, ROI {new_10_12['roi']:.1f}%, 収支 {new_profit_str}円")
    print(f"  → 件数 {new_10_12['total'] - old_10_12['total']:+,}件, 収支 {int(new_10_12['profit'] - old_10_12['profit']):+,}円")

    conn.close()


if __name__ == '__main__':
    main()
