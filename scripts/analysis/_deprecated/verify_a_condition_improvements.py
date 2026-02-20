#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A条件改善の効果検証

改善内容:
1. A×A1×14-16: 廃止（6年間-19,990円）
2. A×A1×10-12: 会場フィルター追加（7会場限定）
3. A×B1×Motor40%+: 15-30倍限定

作成日: 2026-01-07
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


def analyze_condition(cursor, name: str, query: str, years: list):
    """条件の年度別分析"""
    print(f"\n{'='*70}")
    print(f"条件: {name}")
    print("=" * 70)
    print(f"{'年度':<6} {'件数':>8} {'的中':>6} {'ROI':>10} {'収支':>14}")
    print("-" * 70)

    total_bets = 0
    total_hits = 0
    total_payout = 0

    for year in years:
        year_query = query.format(year_start=year, year_end=year)
        cursor.execute(year_query)
        row = cursor.fetchone()

        if row:
            bets, hits, payout = row
            bets = bets or 0
            hits = hits or 0
            payout = payout or 0

            investment = bets * 100
            roi = 100.0 * payout / investment if investment > 0 else 0
            profit = payout - investment

            total_bets += bets
            total_hits += hits
            total_payout += payout

            status = "○" if profit > 0 else "×"
            print(f"{year:<6} {bets:>8} {hits:>6} {roi:>9.1f}% {profit:>+14,.0f} {status}")

    total_investment = total_bets * 100
    total_roi = 100.0 * total_payout / total_investment if total_investment > 0 else 0
    total_profit = total_payout - total_investment

    print("-" * 70)
    print(f"{'合計':<6} {total_bets:>8} {total_hits:>6} {total_roi:>9.1f}% {total_profit:>+14,.0f}")

    return {
        'bets': total_bets,
        'hits': total_hits,
        'roi': total_roi,
        'profit': total_profit
    }


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    years = [2020, 2021, 2022, 2023, 2024, 2025]

    print("=" * 80)
    print("A条件改善の効果検証")
    print("=" * 80)

    # =====================================================
    # 1. A×A1×10-12 改善前（全会場）
    # =====================================================
    query_10_12_all = '''
    SELECT
        COUNT(*) as bets,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN o.odds * 100 ELSE 0 END) as payout
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    JOIN trifecta_odds o ON r.id = o.race_id
        AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
    LEFT JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
    LEFT JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
    LEFT JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
    WHERE rp.confidence = 'A'
    AND e1.racer_rank = 'A1'
    AND o.odds >= 10 AND o.odds < 12
    AND r.race_date >= '{year_start}-01-01' AND r.race_date < '{year_end}-12-31'
    '''

    result_10_12_before = analyze_condition(cursor, "A×A1×10-12【改善前・全会場】", query_10_12_all, years)

    # =====================================================
    # 2. A×A1×10-12 改善後（7会場限定）
    # =====================================================
    query_10_12_filtered = '''
    SELECT
        COUNT(*) as bets,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN o.odds * 100 ELSE 0 END) as payout
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    JOIN trifecta_odds o ON r.id = o.race_id
        AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
    LEFT JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
    LEFT JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
    LEFT JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
    WHERE rp.confidence = 'A'
    AND e1.racer_rank = 'A1'
    AND o.odds >= 10 AND o.odds < 12
    AND r.venue_code IN (10, 14, 21, 18, 8, 19, 12)
    AND r.race_date >= '{year_start}-01-01' AND r.race_date < '{year_end}-12-31'
    '''

    result_10_12_after = analyze_condition(cursor, "A×A1×10-12【改善後・7会場】", query_10_12_filtered, years)

    # =====================================================
    # 3. A×A1×14-16（廃止対象）
    # =====================================================
    query_14_16 = '''
    SELECT
        COUNT(*) as bets,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN o.odds * 100 ELSE 0 END) as payout
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    JOIN trifecta_odds o ON r.id = o.race_id
        AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
    LEFT JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
    LEFT JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
    LEFT JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
    WHERE rp.confidence = 'A'
    AND e1.racer_rank = 'A1'
    AND o.odds >= 14 AND o.odds < 16
    AND r.race_date >= '{year_start}-01-01' AND r.race_date < '{year_end}-12-31'
    '''

    result_14_16 = analyze_condition(cursor, "A×A1×14-16【廃止対象】", query_14_16, years)

    # =====================================================
    # 4. A×B1×Motor40%+ 改善前（全オッズ）
    # =====================================================
    query_motor_all = '''
    SELECT
        COUNT(*) as bets,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN o.odds * 100 ELSE 0 END) as payout
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    JOIN trifecta_odds o ON r.id = o.race_id
        AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
    LEFT JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
    LEFT JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
    LEFT JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
    WHERE rp.confidence = 'A'
    AND e1.racer_rank = 'B1'
    AND e1.motor_second_rate >= 40
    AND r.race_date >= '{year_start}-01-01' AND r.race_date < '{year_end}-12-31'
    '''

    result_motor_before = analyze_condition(cursor, "A×B1×Motor40%+【改善前・全オッズ】", query_motor_all, years)

    # =====================================================
    # 5. A×B1×Motor40%+ 改善後（15-30倍）
    # =====================================================
    query_motor_filtered = '''
    SELECT
        COUNT(*) as bets,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN res1.pit_number = rp1.pit_number
                  AND res2.pit_number = rp2.pit_number
                  AND res3.pit_number = rp3.pit_number THEN o.odds * 100 ELSE 0 END) as payout
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    JOIN trifecta_odds o ON r.id = o.race_id
        AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
    LEFT JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
    LEFT JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
    LEFT JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
    WHERE rp.confidence = 'A'
    AND e1.racer_rank = 'B1'
    AND e1.motor_second_rate >= 40
    AND o.odds >= 15 AND o.odds < 30
    AND r.race_date >= '{year_start}-01-01' AND r.race_date < '{year_end}-12-31'
    '''

    result_motor_after = analyze_condition(cursor, "A×B1×Motor40%+【改善後・15-30倍】", query_motor_filtered, years)

    # =====================================================
    # サマリー
    # =====================================================
    print("\n" + "=" * 80)
    print("改善効果サマリー")
    print("=" * 80)

    print("\n[A×A1×10-12]")
    print(f"  改善前: {result_10_12_before['bets']}件, ROI {result_10_12_before['roi']:.1f}%, 収支 {result_10_12_before['profit']:+,.0f}円")
    print(f"  改善後: {result_10_12_after['bets']}件, ROI {result_10_12_after['roi']:.1f}%, 収支 {result_10_12_after['profit']:+,.0f}円")
    print(f"  効果: {result_10_12_after['profit'] - result_10_12_before['profit']:+,.0f}円")

    print("\n[A×A1×14-16 廃止]")
    print(f"  廃止対象: {result_14_16['bets']}件, ROI {result_14_16['roi']:.1f}%, 収支 {result_14_16['profit']:+,.0f}円")
    print(f"  効果: {-result_14_16['profit']:+,.0f}円（赤字回避）")

    print("\n[A×B1×Motor40%+]")
    print(f"  改善前: {result_motor_before['bets']}件, ROI {result_motor_before['roi']:.1f}%, 収支 {result_motor_before['profit']:+,.0f}円")
    print(f"  改善後: {result_motor_after['bets']}件, ROI {result_motor_after['roi']:.1f}%, 収支 {result_motor_after['profit']:+,.0f}円")
    print(f"  効果: {result_motor_after['profit'] - result_motor_before['profit']:+,.0f}円")

    total_improvement = (
        (result_10_12_after['profit'] - result_10_12_before['profit']) +
        (-result_14_16['profit']) +
        (result_motor_after['profit'] - result_motor_before['profit'])
    )

    print("\n" + "-" * 80)
    print(f"総合改善効果: {total_improvement:+,.0f}円/6年間")

    conn.close()


if __name__ == '__main__':
    main()
