#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH適用範囲の最適化分析

目的:
    オッズ帯別にパターンH（3点買い）と1点買いを比較し、
    最適な適用範囲を特定する

分析内容:
    1. オッズ帯別に1点買いと3点買いのROI比較
    2. 損益分岐点の特定
    3. 最適な適用ルールの提案

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


def analyze_single_bet_by_odds(cursor, odds_min: int, odds_max: int, year_start: int, year_end: int) -> Dict:
    """1点買い（100円）のオッズ帯別分析"""
    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp.confidence,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        WHERE rp.rank_prediction = 1
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end + 1}-01-01'
    ),
    race_bets AS (
        SELECT
            rb.*,
            COALESCE((SELECT o.odds FROM trifecta_odds o
                      WHERE o.race_id = rb.race_id
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
    WHERE odds_123 >= {odds_min} AND odds_123 < {odds_max}
    '''
    cursor.execute(query)
    row = cursor.fetchone()
    bets, hits, payout = row
    hits = hits or 0
    payout = payout or 0
    investment = bets * 100 if bets else 0
    roi = 100.0 * payout / investment if investment > 0 else 0
    profit = payout - investment
    hit_rate = 100.0 * hits / bets if bets else 0

    return {
        'odds_range': f'{odds_min}-{odds_max}',
        'bets': bets or 0,
        'hits': hits,
        'hit_rate': hit_rate,
        'investment': investment,
        'payout': payout,
        'roi': roi,
        'profit': profit,
    }


def analyze_pattern_h_by_odds(cursor, odds_min: int, odds_max: int, year_start: int, year_end: int) -> Dict:
    """パターンH（3点買い：200/100/100円）のオッズ帯別分析"""
    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp.confidence,
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
        WHERE rp.rank_prediction = 1
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end + 1}-01-01'
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
            -- 投資額（オッズ範囲内の買い目のみカウント）
            CASE WHEN odds_123 >= {odds_min} AND odds_123 < {odds_max} THEN 200 ELSE 0 END as bet_123,
            CASE WHEN odds_124 >= {odds_min} AND odds_124 < {odds_max} THEN 100 ELSE 0 END as bet_124,
            CASE WHEN odds_125 >= {odds_min} AND odds_125 < {odds_max} THEN 100 ELSE 0 END as bet_125,
            -- 払戻額
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                      AND odds_123 >= {odds_min} AND odds_123 < {odds_max}
                 THEN odds_123 * 200 ELSE 0 END as payout_123,
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                      AND odds_124 >= {odds_min} AND odds_124 < {odds_max}
                 THEN odds_124 * 100 ELSE 0 END as payout_124,
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5
                      AND odds_125 >= {odds_min} AND odds_125 < {odds_max}
                 THEN odds_125 * 100 ELSE 0 END as payout_125,
            -- 的中フラグ
            CASE WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= {odds_min} AND odds_123 < {odds_max})
                   OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= {odds_min} AND odds_124 < {odds_max})
                   OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= {odds_min} AND odds_125 < {odds_max})
                 THEN 1 ELSE 0 END as is_hit
        FROM race_with_odds rwo
    )
    SELECT
        COUNT(*) as races,
        SUM(CASE WHEN bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0 THEN 1 ELSE 0 END) as bets,
        SUM(is_hit) as hits,
        SUM(bet_123 + bet_124 + bet_125) as total_investment,
        SUM(payout_123 + payout_124 + payout_125) as total_payout
    FROM race_payouts
    WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
    '''
    cursor.execute(query)
    row = cursor.fetchone()
    races, bets, hits, investment, payout = row
    hits = hits or 0
    payout = payout or 0
    investment = investment or 0
    roi = 100.0 * payout / investment if investment > 0 else 0
    profit = payout - investment
    hit_rate = 100.0 * hits / bets if bets else 0

    return {
        'odds_range': f'{odds_min}-{odds_max}',
        'bets': bets or 0,
        'hits': hits,
        'hit_rate': hit_rate,
        'investment': investment,
        'payout': payout,
        'roi': roi,
        'profit': profit,
    }


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # オッズ帯の定義
    odds_ranges = [
        (10, 15),
        (15, 20),
        (20, 25),
        (25, 30),
        (30, 40),
        (40, 50),
        (50, 70),
        (70, 100),
        (100, 200),
    ]

    years = [2020, 2021, 2022, 2023, 2024, 2025]
    year_start = years[0]
    year_end = years[-1]

    print("=" * 100)
    print("パターンH適用範囲の最適化分析")
    print(f"対象期間: {year_start}年〜{year_end}年")
    print("=" * 100)
    print()

    # オッズ帯別の比較
    print("[オッズ帯別: 1点買い vs パターンH（3点買い）比較]")
    print("-" * 100)
    print(f"{'オッズ帯':<12} {'1点買いROI':>10} {'1点収支':>12} {'パターンH ROI':>12} {'パターンH収支':>14} {'差分ROI':>10} {'推奨'}")
    print("-" * 100)

    results = []
    for odds_min, odds_max in odds_ranges:
        single = analyze_single_bet_by_odds(cursor, odds_min, odds_max, year_start, year_end)
        pattern_h = analyze_pattern_h_by_odds(cursor, odds_min, odds_max, year_start, year_end)

        diff_roi = pattern_h['roi'] - single['roi']

        # 推奨判定
        if diff_roi > 5:
            recommend = "パターンH"
        elif diff_roi < -5:
            recommend = "1点買い"
        else:
            recommend = "どちらでも"

        results.append({
            'odds_range': f'{odds_min}-{odds_max}',
            'single': single,
            'pattern_h': pattern_h,
            'diff_roi': diff_roi,
            'recommend': recommend,
        })

        print(f"{single['odds_range']:<12} {single['roi']:>9.1f}% {single['profit']:>+12,.0f} "
              f"{pattern_h['roi']:>11.1f}% {pattern_h['profit']:>+14,.0f} {diff_roi:>+9.1f}pt {recommend}")

    print("-" * 100)
    print()

    # 詳細分析
    print("[詳細分析]")
    print()

    for r in results:
        odds_range = r['odds_range']
        single = r['single']
        pattern_h = r['pattern_h']

        print(f">>> オッズ帯: {odds_range}倍")
        print(f"    1点買い: {single['bets']}件, 的中{single['hits']}件 ({single['hit_rate']:.1f}%), ROI {single['roi']:.1f}%, 収支 {single['profit']:+,.0f}円")
        print(f"    パターンH: {pattern_h['bets']}件, 的中{pattern_h['hits']}件 ({pattern_h['hit_rate']:.1f}%), ROI {pattern_h['roi']:.1f}%, 収支 {pattern_h['profit']:+,.0f}円")
        print(f"    推奨: {r['recommend']} (ROI差: {r['diff_roi']:+.1f}pt)")
        print()

    # 推奨ルールのまとめ
    print("=" * 100)
    print("[推奨ルール]")
    print("=" * 100)

    pattern_h_ranges = [r['odds_range'] for r in results if r['recommend'] == 'パターンH']
    single_ranges = [r['odds_range'] for r in results if r['recommend'] == '1点買い']

    print()
    print(f"パターンH（3点買い）推奨オッズ帯: {', '.join(pattern_h_ranges)}倍")
    print(f"1点買い推奨オッズ帯: {', '.join(single_ranges)}倍")
    print()

    # 最適化シミュレーション
    print("[最適化シミュレーション]")
    print("-" * 80)

    # 全て1点買い
    total_single_profit = sum(r['single']['profit'] for r in results)
    total_single_invest = sum(r['single']['investment'] for r in results)
    total_single_roi = 100.0 * (total_single_profit + total_single_invest) / total_single_invest if total_single_invest else 0

    # 全てパターンH
    total_pattern_h_profit = sum(r['pattern_h']['profit'] for r in results)
    total_pattern_h_invest = sum(r['pattern_h']['investment'] for r in results)
    total_pattern_h_roi = 100.0 * (total_pattern_h_profit + total_pattern_h_invest) / total_pattern_h_invest if total_pattern_h_invest else 0

    # ハイブリッド（推奨に従う）
    total_hybrid_profit = 0
    total_hybrid_invest = 0
    for r in results:
        if r['recommend'] == 'パターンH':
            total_hybrid_profit += r['pattern_h']['profit']
            total_hybrid_invest += r['pattern_h']['investment']
        else:
            total_hybrid_profit += r['single']['profit']
            total_hybrid_invest += r['single']['investment']

    total_hybrid_roi = 100.0 * (total_hybrid_profit + total_hybrid_invest) / total_hybrid_invest if total_hybrid_invest else 0

    print(f"{'戦略':<20} {'総投資':>15} {'収支':>15} {'ROI':>10}")
    print("-" * 80)
    print(f"{'全て1点買い':<20} {total_single_invest:>15,.0f} {total_single_profit:>+15,.0f} {total_single_roi:>9.1f}%")
    print(f"{'全てパターンH':<20} {total_pattern_h_invest:>15,.0f} {total_pattern_h_profit:>+15,.0f} {total_pattern_h_roi:>9.1f}%")
    print(f"{'ハイブリッド（最適化）':<20} {total_hybrid_invest:>15,.0f} {total_hybrid_profit:>+15,.0f} {total_hybrid_roi:>9.1f}%")
    print()

    conn.close()


if __name__ == '__main__':
    main()
