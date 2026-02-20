#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
購入条件別: パターンH vs 1点買い分析

目的:
    現在の購入条件を適用した状態で、
    パターンH（3点買い）と1点買いを比較する

作成日: 2026-01-07
"""
import sqlite3
import sys
import io
import os
from typing import Dict, List

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


# 購入条件定義
CONDITIONS = [
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'venue_filter': None},
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40},
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None},
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
     'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]},
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
     'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
     'venue_filter': [14]},
    {'name': 'D×40-50×B1×2連率', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None,
     'c1_second_rate_min': 20, 'c1_second_rate_max': 30},
    {'name': 'D×5コース予測', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'], 'odds_min': 10, 'odds_max': 200,
     'venue_filter': None, 'predicted_course': 5},
]


def analyze_condition_single(cursor, cond: Dict, year_start: int, year_end: int) -> Dict:
    """条件別の1点買い（100円）分析"""
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
        AND r.race_date < '{year_end + 1}-01-01'
        {venue_clause}
        {motor_clause}
        {predicted_course_clause}
        {c1_second_rate_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    )
    SELECT
        COUNT(*) as bets,
        SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 THEN odds_123 * 100 ELSE 0 END) as payout
    FROM race_bets
    WHERE odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
    '''
    cursor.execute(query)
    row = cursor.fetchone()
    bets, hits, payout = row
    hits = hits or 0
    payout = payout or 0
    investment = bets * 100 if bets else 0
    roi = 100.0 * payout / investment if investment > 0 else 0
    profit = payout - investment

    return {
        'name': cond['name'],
        'bets': bets or 0,
        'hits': hits,
        'investment': investment,
        'payout': payout,
        'roi': roi,
        'profit': profit,
    }


def analyze_condition_pattern_h(cursor, cond: Dict, year_start: int, year_end: int) -> Dict:
    """条件別のパターンH（200/100/100円）分析"""
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
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            rp4.pit_number as p4,
            rp5.pit_number as p5
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end + 1}-01-01'
        {venue_clause}
        {motor_clause}
        {predicted_course_clause}
        {c1_second_rate_clause}
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
    ),
    race_payouts AS (
        SELECT
            rwo.*,
            -- 1点目のオッズがオッズ範囲内ならレースを購入対象とする
            CASE WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN 1 ELSE 0 END as is_target,
            -- 投資額
            200 as bet_123,
            100 as bet_124,
            100 as bet_125,
            -- 払戻額
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 THEN odds_123 * 200 ELSE 0 END as payout_123,
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 THEN odds_124 * 100 ELSE 0 END as payout_124,
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 THEN odds_125 * 100 ELSE 0 END as payout_125,
            -- 的中フラグ
            CASE WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3)
                   OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4)
                   OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5)
                 THEN 1 ELSE 0 END as is_hit
        FROM race_with_odds rwo
    )
    SELECT
        SUM(is_target) as bets,
        SUM(CASE WHEN is_target = 1 THEN is_hit ELSE 0 END) as hits,
        SUM(CASE WHEN is_target = 1 THEN bet_123 + bet_124 + bet_125 ELSE 0 END) as total_investment,
        SUM(CASE WHEN is_target = 1 THEN payout_123 + payout_124 + payout_125 ELSE 0 END) as total_payout
    FROM race_payouts
    '''
    cursor.execute(query)
    row = cursor.fetchone()
    bets, hits, investment, payout = row
    bets = bets or 0
    hits = hits or 0
    payout = payout or 0
    investment = investment or 0
    roi = 100.0 * payout / investment if investment > 0 else 0
    profit = payout - investment

    return {
        'name': cond['name'],
        'bets': bets,
        'hits': hits,
        'investment': investment,
        'payout': payout,
        'roi': roi,
        'profit': profit,
    }


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    years = [2020, 2021, 2022, 2023, 2024, 2025]
    year_start = years[0]
    year_end = years[-1]

    print("=" * 110)
    print("購入条件別: パターンH vs 1点買い分析")
    print(f"対象期間: {year_start}年〜{year_end}年")
    print("=" * 110)
    print()

    print("[条件別: 1点買い vs パターンH比較]")
    print("-" * 110)
    print(f"{'条件':<25} {'1点件数':>8} {'1点ROI':>8} {'1点収支':>12} {'パターンH件数':>12} {'パターンH ROI':>12} {'パターンH収支':>14} {'推奨'}")
    print("-" * 110)

    total_single_invest = 0
    total_single_profit = 0
    total_pattern_h_invest = 0
    total_pattern_h_profit = 0

    results = []
    for cond in CONDITIONS:
        single = analyze_condition_single(cursor, cond, year_start, year_end)
        pattern_h = analyze_condition_pattern_h(cursor, cond, year_start, year_end)

        diff_roi = pattern_h['roi'] - single['roi']

        # 推奨判定（ROI差と収支差を考慮）
        if single['profit'] > 0 and pattern_h['profit'] > 0:
            # 両方黒字なら収支が大きい方
            recommend = "パターンH" if pattern_h['profit'] > single['profit'] else "1点買い"
        elif single['profit'] > 0 and pattern_h['profit'] <= 0:
            recommend = "1点買い"
        elif single['profit'] <= 0 and pattern_h['profit'] > 0:
            recommend = "パターンH"
        else:
            # 両方赤字なら損失が少ない方
            recommend = "パターンH" if pattern_h['profit'] > single['profit'] else "1点買い"

        results.append({
            'cond': cond,
            'single': single,
            'pattern_h': pattern_h,
            'diff_roi': diff_roi,
            'recommend': recommend,
        })

        print(f"{cond['name']:<25} {single['bets']:>8} {single['roi']:>7.1f}% {single['profit']:>+12,.0f} "
              f"{pattern_h['bets']:>12} {pattern_h['roi']:>11.1f}% {pattern_h['profit']:>+14,.0f} {recommend}")

        total_single_invest += single['investment']
        total_single_profit += single['profit']
        total_pattern_h_invest += pattern_h['investment']
        total_pattern_h_profit += pattern_h['profit']

    print("-" * 110)

    total_single_roi = 100.0 * (total_single_profit + total_single_invest) / total_single_invest if total_single_invest else 0
    total_pattern_h_roi = 100.0 * (total_pattern_h_profit + total_pattern_h_invest) / total_pattern_h_invest if total_pattern_h_invest else 0

    print(f"{'合計':<25} {'-':>8} {total_single_roi:>7.1f}% {total_single_profit:>+12,.0f} "
          f"{'-':>12} {total_pattern_h_roi:>11.1f}% {total_pattern_h_profit:>+14,.0f}")
    print()

    # ハイブリッド戦略
    print("[ハイブリッド戦略（条件別に最適な方式を選択）]")
    print("-" * 80)

    hybrid_invest = 0
    hybrid_profit = 0

    for r in results:
        if r['recommend'] == 'パターンH':
            hybrid_invest += r['pattern_h']['investment']
            hybrid_profit += r['pattern_h']['profit']
            print(f"  {r['cond']['name']}: パターンH → ROI {r['pattern_h']['roi']:.1f}%, 収支 {r['pattern_h']['profit']:+,.0f}円")
        else:
            hybrid_invest += r['single']['investment']
            hybrid_profit += r['single']['profit']
            print(f"  {r['cond']['name']}: 1点買い → ROI {r['single']['roi']:.1f}%, 収支 {r['single']['profit']:+,.0f}円")

    hybrid_roi = 100.0 * (hybrid_profit + hybrid_invest) / hybrid_invest if hybrid_invest else 0
    print("-" * 80)
    print(f"  ハイブリッド合計: ROI {hybrid_roi:.1f}%, 収支 {hybrid_profit:+,.0f}円")
    print()

    # 最終サマリー
    print("=" * 80)
    print("[最終サマリー]")
    print("=" * 80)
    print(f"{'戦略':<25} {'ROI':>10} {'収支':>15}")
    print("-" * 80)
    print(f"{'全て1点買い':<25} {total_single_roi:>9.1f}% {total_single_profit:>+15,.0f}")
    print(f"{'全てパターンH':<25} {total_pattern_h_roi:>9.1f}% {total_pattern_h_profit:>+15,.0f}")
    print(f"{'ハイブリッド（最適化）':<25} {hybrid_roi:>9.1f}% {hybrid_profit:>+15,.0f}")
    print()

    # 推奨ルールのまとめ
    print("[推奨ルール]")
    print("-" * 80)
    single_conds = [r['cond']['name'] for r in results if r['recommend'] == '1点買い']
    pattern_h_conds = [r['cond']['name'] for r in results if r['recommend'] == 'パターンH']

    print(f"1点買い推奨: {', '.join(single_conds) if single_conds else 'なし'}")
    print(f"パターンH推奨: {', '.join(pattern_h_conds) if pattern_h_conds else 'なし'}")
    print()

    conn.close()


if __name__ == '__main__':
    main()
