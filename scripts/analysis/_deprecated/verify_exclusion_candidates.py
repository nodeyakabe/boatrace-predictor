# -*- coding: utf-8 -*-
"""
除外候補の効果検証
==================

不的中パターン分析で発見した除外候補の効果を検証する。

使用例:
    python scripts/analysis/verify_exclusion_candidates.py
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


def analyze_with_exclusion(cursor, cond, year_start=2020, year_end=2025):
    """除外条件を適用した場合のROIを計算"""
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

    predicted_course_exclude_clause = ""
    if cond.get('predicted_course_exclude'):
        predicted_course_exclude_clause = f"AND rp1.pit_number NOT IN ({','.join(map(str, cond['predicted_course_exclude']))})"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            substr(r.race_date, 1, 4) as year,
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
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {motor_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
        {predicted_course_exclude_clause}
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
        year,
        COUNT(*) as bets,
        SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
        SUM(payout) as total_payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    GROUP BY year
    ORDER BY year
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    results = {y: {'bets': 0, 'hits': 0, 'payout': 0} for y in years}

    for row in rows:
        year, bets, hits, payout = row
        if year in results:
            results[year] = {'bets': bets, 'hits': hits or 0, 'payout': payout or 0}

    total_bets = sum(r['bets'] for r in results.values())
    total_hits = sum(r['hits'] for r in results.values())
    total_payout = sum(r['payout'] for r in results.values())
    total_invest = total_bets * 100
    total_roi = total_payout / total_invest * 100 if total_invest > 0 else 0
    total_profit = total_payout - total_invest

    positive_years = sum(1 for y, r in results.items() if r['payout'] - r['bets'] * 100 > 0)

    return {
        'bets': total_bets,
        'hits': total_hits,
        'roi': total_roi,
        'profit': total_profit,
        'positive_years': positive_years,
        'yearly': results
    }


def main():
    print("=" * 80)
    print("除外候補の効果検証")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # ============================================================
    # D×35-60 条件の除外効果検証
    # ============================================================
    print("\n" + "=" * 60)
    print("D×35-60 除外効果検証")
    print("=" * 60)

    # 現行条件
    base_cond = {
        'name': 'D×35-60（現行）',
        'confidence': 'D',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 35,
        'odds_max': 60,
        'race_exclude': [9],
        'venue_exclude': [10]
    }
    base_result = analyze_with_exclusion(cursor, base_cond)
    print(f"\n現行: {base_result['bets']}件, ROI {base_result['roi']:.1f}%, {base_result['profit']:+,.0f}円, {base_result['positive_years']}/6年黒字")

    # 11R除外追加
    test_cond = base_cond.copy()
    test_cond['race_exclude'] = [9, 11]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +11R除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # 3R除外追加
    test_cond = base_cond.copy()
    test_cond['race_exclude'] = [9, 3]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +3R除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # 1R除外追加
    test_cond = base_cond.copy()
    test_cond['race_exclude'] = [9, 1]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +1R除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # 11R+3R除外
    test_cond = base_cond.copy()
    test_cond['race_exclude'] = [9, 11, 3]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +11R+3R除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # 1コース予測除外
    test_cond = base_cond.copy()
    test_cond['predicted_course_exclude'] = [1]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +1コース予測除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # ============================================================
    # D×40-50×B1 条件の除外効果検証
    # ============================================================
    print("\n" + "=" * 60)
    print("D×40-50×B1 除外効果検証")
    print("=" * 60)

    base_cond = {
        'name': 'D×40-50×B1（現行）',
        'confidence': 'D',
        'c1_rank': ['B1'],
        'odds_min': 40,
        'odds_max': 50,
    }
    base_result = analyze_with_exclusion(cursor, base_cond)
    print(f"\n現行: {base_result['bets']}件, ROI {base_result['roi']:.1f}%, {base_result['profit']:+,.0f}円, {base_result['positive_years']}/6年黒字")

    # 7R+8R+10R除外
    test_cond = base_cond.copy()
    test_cond['race_exclude'] = [7, 8, 10]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +7R+8R+10R除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # 1コース予測除外
    test_cond = base_cond.copy()
    test_cond['predicted_course_exclude'] = [1]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +1コース予測除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # 三国除外
    test_cond = base_cond.copy()
    test_cond['venue_exclude'] = [10]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +三国除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # ============================================================
    # C×20-30×B1+会場 条件の除外効果検証
    # ============================================================
    print("\n" + "=" * 60)
    print("C×20-30×B1+会場 除外効果検証")
    print("=" * 60)

    base_cond = {
        'name': 'C×20-30×B1+会場（現行）',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]
    }
    base_result = analyze_with_exclusion(cursor, base_cond)
    print(f"\n現行: {base_result['bets']}件, ROI {base_result['roi']:.1f}%, {base_result['profit']:+,.0f}円, {base_result['positive_years']}/6年黒字")

    # 5R除外
    test_cond = base_cond.copy()
    test_cond['race_exclude'] = [5]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +5R除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # 2R+3R除外
    test_cond = base_cond.copy()
    test_cond['race_exclude'] = [2, 3]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +2R+3R除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    # 2R+3R+5R除外
    test_cond = base_cond.copy()
    test_cond['race_exclude'] = [2, 3, 5]
    test_result = analyze_with_exclusion(cursor, test_cond)
    diff = test_result['profit'] - base_result['profit']
    print(f"  +2R+3R+5R除外: {test_result['bets']}件, ROI {test_result['roi']:.1f}%, {test_result['profit']:+,.0f}円 (差分 {diff:+,.0f}円)")

    conn.close()

    print("\n" + "=" * 80)
    print("検証完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
