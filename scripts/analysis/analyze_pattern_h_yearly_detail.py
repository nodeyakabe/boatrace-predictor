#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンHハイブリッド戦略の年度別詳細分析

作成日: 2026-01-07
"""
import sqlite3
import sys
import io
import os
from typing import Dict, List, Tuple

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 条件定義（use_pattern_hフラグ付き）
CONDITIONS = [
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'use_pattern_h': False},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'use_pattern_h': False},
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'motor_min': 40, 'use_pattern_h': False},
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'use_pattern_h': True},
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
     'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8], 'use_pattern_h': True},
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
     'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17], 'use_pattern_h': False},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
     'venue_filter': [14], 'use_pattern_h': True},
    {'name': 'D×40-50×B1×2連率', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50,
     'c1_second_rate_min': 20, 'c1_second_rate_max': 30, 'use_pattern_h': False},
    {'name': 'D×5コース予測', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'], 'odds_min': 10, 'odds_max': 200,
     'predicted_course': 5, 'use_pattern_h': True},
]


def build_condition_query(cond: Dict, year: int) -> str:
    """条件に基づいたSQLクエリを構築"""
    confidence = cond['confidence']
    c1_ranks = cond['c1_rank']
    odds_min = cond['odds_min']
    odds_max = cond['odds_max']

    c1_rank_filter = "', '".join(c1_ranks)

    # 追加条件
    extra_conditions = []

    if 'venue_filter' in cond:
        venues = ', '.join(str(v) for v in cond['venue_filter'])
        extra_conditions.append(f"AND r.venue_code IN ({venues})")

    if 'motor_min' in cond:
        extra_conditions.append(f"AND e1.motor_second_rate >= {cond['motor_min']}")

    if 'c1_second_rate_min' in cond:
        extra_conditions.append(f"AND e1.second_rate >= {cond['c1_second_rate_min']}")

    if 'c1_second_rate_max' in cond:
        extra_conditions.append(f"AND e1.second_rate < {cond['c1_second_rate_max']}")

    if 'predicted_course' in cond:
        extra_conditions.append(f"AND rp1.pit_number = {cond['predicted_course']}")

    extra_sql = '\n        '.join(extra_conditions)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp.confidence,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            rp4.pit_number as p4,
            rp5.pit_number as p5,
            e1.racer_rank as c1_rank,
            e1.motor_second_rate,
            e1.second_rate as c1_second_rate
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND e1.racer_rank IN ('{c1_rank_filter}')
        AND r.race_date >= '{year}-01-01'
        AND r.race_date < '{year + 1}-01-01'
        {extra_sql}
    ),
    race_with_odds AS (
        SELECT
            rb.*,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    )
    SELECT
        -- 1点買い（123のみ）
        SUM(CASE WHEN odds_123 >= {odds_min} AND odds_123 < {odds_max} THEN 1 ELSE 0 END) as single_bets,
        SUM(CASE WHEN odds_123 >= {odds_min} AND odds_123 < {odds_max}
                 AND actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 THEN 1 ELSE 0 END) as single_hits,
        SUM(CASE WHEN odds_123 >= {odds_min} AND odds_123 < {odds_max}
                 AND actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 THEN odds_123 * 100 ELSE 0 END) as single_payout,
        -- パターンH（3点買い）
        COUNT(*) as pattern_h_races,
        SUM(CASE
            WHEN (odds_123 >= {odds_min} AND odds_123 < {odds_max} AND actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3)
              OR (odds_124 >= {odds_min} AND odds_124 < {odds_max} AND actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4)
              OR (odds_125 >= {odds_min} AND odds_125 < {odds_max} AND actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5)
            THEN 1 ELSE 0 END) as pattern_h_hits,
        SUM(
            CASE WHEN odds_123 >= {odds_min} AND odds_123 < {odds_max} AND actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 THEN odds_123 * 200 ELSE 0 END +
            CASE WHEN odds_124 >= {odds_min} AND odds_124 < {odds_max} AND actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 THEN odds_124 * 100 ELSE 0 END +
            CASE WHEN odds_125 >= {odds_min} AND odds_125 < {odds_max} AND actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 THEN odds_125 * 100 ELSE 0 END
        ) as pattern_h_payout,
        SUM(
            CASE WHEN odds_123 >= {odds_min} AND odds_123 < {odds_max} THEN 200 ELSE 0 END +
            CASE WHEN odds_124 >= {odds_min} AND odds_124 < {odds_max} THEN 100 ELSE 0 END +
            CASE WHEN odds_125 >= {odds_min} AND odds_125 < {odds_max} THEN 100 ELSE 0 END
        ) as pattern_h_investment
    FROM race_with_odds
    WHERE odds_123 >= {odds_min} AND odds_123 < {odds_max}
    '''
    return query


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    years = [2020, 2021, 2022, 2023, 2024, 2025]

    print("=" * 120)
    print("パターンHハイブリッド戦略 年度別詳細分析")
    print("=" * 120)
    print()

    # 条件ごとの年度別分析
    for cond in CONDITIONS:
        print(f"\n{'='*80}")
        print(f"条件: {cond['name']} | 推奨: {'パターンH' if cond['use_pattern_h'] else '1点買い'}")
        print("=" * 80)
        print(f"{'年度':<6} {'件数':>8} {'1点ROI':>10} {'1点収支':>12} {'パターンH ROI':>14} {'パターンH収支':>14} {'ハイブリッド収支':>16}")
        print("-" * 80)

        total_single_invest = 0
        total_single_payout = 0
        total_pattern_h_invest = 0
        total_pattern_h_payout = 0
        total_hybrid_profit = 0

        for year in years:
            try:
                query = build_condition_query(cond, year)
                cursor.execute(query)
                row = cursor.fetchone()

                if row and row[0]:
                    single_bets, single_hits, single_payout, pattern_h_races, pattern_h_hits, pattern_h_payout, pattern_h_invest = row

                    single_bets = single_bets or 0
                    single_hits = single_hits or 0
                    single_payout = single_payout or 0
                    pattern_h_hits = pattern_h_hits or 0
                    pattern_h_payout = pattern_h_payout or 0
                    pattern_h_invest = pattern_h_invest or 0

                    single_invest = single_bets * 100
                    single_roi = 100.0 * single_payout / single_invest if single_invest > 0 else 0
                    single_profit = single_payout - single_invest

                    pattern_h_roi = 100.0 * pattern_h_payout / pattern_h_invest if pattern_h_invest > 0 else 0
                    pattern_h_profit = pattern_h_payout - pattern_h_invest

                    # ハイブリッド（推奨に従う）
                    if cond['use_pattern_h']:
                        hybrid_profit = pattern_h_profit
                    else:
                        hybrid_profit = single_profit

                    total_single_invest += single_invest
                    total_single_payout += single_payout
                    total_pattern_h_invest += pattern_h_invest
                    total_pattern_h_payout += pattern_h_payout
                    total_hybrid_profit += hybrid_profit

                    print(f"{year:<6} {single_bets:>8} {single_roi:>9.1f}% {single_profit:>+12,.0f} {pattern_h_roi:>13.1f}% {pattern_h_profit:>+14,.0f} {hybrid_profit:>+16,.0f}")
                else:
                    print(f"{year:<6} {'0':>8} {'-':>10} {'-':>12} {'-':>14} {'-':>14} {'-':>16}")
            except Exception as e:
                print(f"{year:<6} Error: {str(e)[:50]}")

        # 合計
        total_single_roi = 100.0 * total_single_payout / total_single_invest if total_single_invest > 0 else 0
        total_single_profit = total_single_payout - total_single_invest
        total_pattern_h_roi = 100.0 * total_pattern_h_payout / total_pattern_h_invest if total_pattern_h_invest > 0 else 0
        total_pattern_h_profit = total_pattern_h_payout - total_pattern_h_invest

        print("-" * 80)
        print(f"{'合計':<6} {'-':>8} {total_single_roi:>9.1f}% {total_single_profit:>+12,.0f} {total_pattern_h_roi:>13.1f}% {total_pattern_h_profit:>+14,.0f} {total_hybrid_profit:>+16,.0f}")

    # 全条件のハイブリッド合計
    print("\n" + "=" * 120)
    print("全条件ハイブリッド戦略 年度別サマリー")
    print("=" * 120)
    print(f"{'年度':<6} {'件数':>8} {'投資額':>12} {'払戻額':>14} {'収支':>14} {'ROI':>10}")
    print("-" * 70)

    grand_total_invest = 0
    grand_total_payout = 0

    for year in years:
        year_invest = 0
        year_payout = 0
        year_bets = 0

        for cond in CONDITIONS:
            try:
                query = build_condition_query(cond, year)
                cursor.execute(query)
                row = cursor.fetchone()

                if row and row[0]:
                    single_bets, single_hits, single_payout, pattern_h_races, pattern_h_hits, pattern_h_payout, pattern_h_invest = row

                    single_bets = single_bets or 0
                    single_payout = single_payout or 0
                    pattern_h_payout = pattern_h_payout or 0
                    pattern_h_invest = pattern_h_invest or 0

                    single_invest = single_bets * 100

                    if cond['use_pattern_h']:
                        year_invest += pattern_h_invest
                        year_payout += pattern_h_payout
                        year_bets += single_bets  # レース数は同じ
                    else:
                        year_invest += single_invest
                        year_payout += single_payout
                        year_bets += single_bets
            except:
                pass

        year_profit = year_payout - year_invest
        year_roi = 100.0 * year_payout / year_invest if year_invest > 0 else 0

        grand_total_invest += year_invest
        grand_total_payout += year_payout

        status = "○黒字" if year_profit > 0 else "×赤字"
        print(f"{year:<6} {year_bets:>8} {year_invest:>12,.0f} {year_payout:>14,.0f} {year_profit:>+14,.0f} {year_roi:>9.1f}% {status}")

    grand_total_profit = grand_total_payout - grand_total_invest
    grand_total_roi = 100.0 * grand_total_payout / grand_total_invest if grand_total_invest > 0 else 0

    print("-" * 70)
    print(f"{'合計':<6} {'-':>8} {grand_total_invest:>12,.0f} {grand_total_payout:>14,.0f} {grand_total_profit:>+14,.0f} {grand_total_roi:>9.1f}%")

    # 黒字年数カウント
    print()
    black_years = sum(1 for y in years if True)  # 再計算必要

    conn.close()


if __name__ == '__main__':
    main()
