# -*- coding: utf-8 -*-
"""
全年度バックテスト（新規D条件追加後）
=====================================

新規追加条件を含めた6年間の完全バックテストを実行する。

使用例:
    python scripts/backtest/full_backtest_with_new_conditions.py
"""

import sqlite3
import sys
import io
import os
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


# 条件定義（bet_target_evaluator.py と同期）
CONDITIONS = [
    # A条件
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16},
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'motor_min': 40},

    # B条件
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100},
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
     'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]},

    # C条件
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
     'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
     'venue_filter': [14]},

    # D条件（既存）
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50},
    {'name': 'D×35-60（9R/三国除外）', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 35, 'odds_max': 60,
     'race_exclude': [9], 'venue_exclude': [10]},

    # D条件（2026-01-05追加）
    {'name': 'D×5コース予測', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'], 'odds_min': 10, 'odds_max': 200,
     'predicted_course': 5},
    {'name': '浜名湖×D×50-100×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 50, 'odds_max': 100,
     'venue_filter': [6]},
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

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year}-01-01'
        AND r.race_date < '{year}-12-01'
        {venue_clause}
        {motor_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
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
        payout = payout or 0
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        return {'bets': bets, 'hits': hits or 0, 'roi': roi, 'profit': profit}
    return {'bets': 0, 'hits': 0, 'roi': 0, 'profit': 0}


def main():
    print("=" * 80)
    print("全年度バックテスト（新規D条件追加後）")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    years = [2020, 2021, 2022, 2023, 2024, 2025]

    # 条件別の年度別結果を保持
    results = {cond['name']: {} for cond in CONDITIONS}
    year_totals = {year: {'bets': 0, 'profit': 0} for year in years}

    for cond in CONDITIONS:
        for year in years:
            r = analyze_condition(cursor, cond, year)
            results[cond['name']][year] = r
            year_totals[year]['bets'] += r['bets']
            year_totals[year]['profit'] += r['profit']

    conn.close()

    # 条件別サマリー
    print("\n[条件別 6年間サマリー]")
    print("-" * 100)
    header = f"{'条件':<25} {'合計件数':>8} {'合計収支':>12} {'ROI':>8} {'黒字年数':>8}"
    print(header)
    print("-" * 100)

    total_bets = 0
    total_profit = 0

    for cond in CONDITIONS:
        name = cond['name']
        cond_bets = sum(results[name][y]['bets'] for y in years)
        cond_profit = sum(results[name][y]['profit'] for y in years)
        cond_invest = cond_bets * 100
        cond_roi = (cond_profit + cond_invest) / cond_invest * 100 if cond_invest > 0 else 0
        positive_years = sum(1 for y in years if results[name][y]['profit'] > 0)

        print(f"{name:<25} {cond_bets:>8} {cond_profit:>+12,.0f} {cond_roi:>7.1f}% {positive_years:>6}/6年")

        total_bets += cond_bets
        total_profit += cond_profit

    total_invest = total_bets * 100
    total_roi = (total_profit + total_invest) / total_invest * 100 if total_invest > 0 else 0

    print("-" * 100)
    print(f"{'合計':<25} {total_bets:>8} {total_profit:>+12,.0f} {total_roi:>7.1f}%")

    # 年度別サマリー
    print("\n[年度別サマリー]")
    print("-" * 60)
    print(f"{'年度':>6} {'件数':>8} {'収支':>12} {'ROI':>8}")
    print("-" * 60)

    for year in years:
        bets = year_totals[year]['bets']
        profit = year_totals[year]['profit']
        invest = bets * 100
        roi = (profit + invest) / invest * 100 if invest > 0 else 0
        status = "+" if profit > 0 else "-"
        print(f"{year:>6} {bets:>8} {profit:>+12,.0f} {roi:>7.1f}% [{status}]")

    print("-" * 60)
    print(f"{'6年合計':>6} {total_bets:>8} {total_profit:>+12,.0f} {total_roi:>7.1f}%")

    # 新規追加条件の詳細
    print("\n" + "=" * 80)
    print("【新規追加条件の詳細】")
    print("=" * 80)

    for cond_name in ['D×5コース予測', '浜名湖×D×50-100×B1']:
        print(f"\n{cond_name}:")
        print("-" * 50)
        for year in years:
            r = results[cond_name][year]
            status = "+" if r['profit'] > 0 else "-"
            print(f"  {year}: {r['bets']:>4}件, {r['hits']}的中, ROI {r['roi']:>6.1f}%, {r['profit']:>+8,.0f}円 [{status}]")

        cond_bets = sum(results[cond_name][y]['bets'] for y in years)
        cond_profit = sum(results[cond_name][y]['profit'] for y in years)
        cond_invest = cond_bets * 100
        cond_roi = (cond_profit + cond_invest) / cond_invest * 100 if cond_invest > 0 else 0
        positive_years = sum(1 for y in years if results[cond_name][y]['profit'] > 0)
        print("-" * 50)
        print(f"  合計: {cond_bets}件, ROI {cond_roi:.1f}%, {cond_profit:+,.0f}円 ({positive_years}/6年黒字)")


if __name__ == "__main__":
    main()
