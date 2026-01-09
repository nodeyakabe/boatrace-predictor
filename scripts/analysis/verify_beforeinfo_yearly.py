# -*- coding: utf-8 -*-
"""
直前情報除外条件の年度別安定性検証
==================================

有力な除外条件の年度別効果を検証する。

使用例:
    python scripts/analysis/verify_beforeinfo_yearly.py
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


def analyze_yearly(cursor, cond):
    """年度別のROIを計算"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"
    if cond.get('motor_max'):
        motor_clause += f" AND e1.motor_second_rate < {cond['motor_max']}"

    wind_clause = ""
    if cond.get('wind_max'):
        wind_clause = f"AND (w.wind_speed IS NULL OR w.wind_speed < {cond['wind_max']})"
    if cond.get('wind_not_null'):
        wind_clause = "AND w.wind_speed IS NOT NULL"

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
        LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
        WHERE rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '2020-01-01'
        AND r.race_date < '2025-12-01'
        {venue_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
        {motor_clause}
        {wind_clause}
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

    results = {}
    for row in rows:
        year, bets, hits, payout = row
        hits = hits or 0
        payout = payout or 0
        invest = bets * 100
        roi = payout / invest * 100 if invest > 0 else 0
        profit = payout - invest
        results[year] = {'bets': bets, 'hits': hits, 'roi': roi, 'profit': profit}

    return results


def print_yearly_comparison(name, base_results, test_results):
    """年度別比較を表示"""
    print(f"\n{name}")
    print("-" * 80)
    print(f"{'年度':>6} | {'現行件数':>8} {'現行ROI':>8} {'現行収支':>12} | {'改善件数':>8} {'改善ROI':>8} {'改善収支':>12} | {'差分':>10}")
    print("-" * 80)

    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    total_base_profit = 0
    total_test_profit = 0
    base_positive = 0
    test_positive = 0

    for year in years:
        base = base_results.get(year, {'bets': 0, 'roi': 0, 'profit': 0})
        test = test_results.get(year, {'bets': 0, 'roi': 0, 'profit': 0})
        diff = test['profit'] - base['profit']

        total_base_profit += base['profit']
        total_test_profit += test['profit']

        if base['profit'] > 0:
            base_positive += 1
        if test['profit'] > 0:
            test_positive += 1

        base_status = "+" if base['profit'] > 0 else "-"
        test_status = "+" if test['profit'] > 0 else "-"

        print(f"{year:>6} | {base['bets']:>8} {base['roi']:>7.1f}% {base['profit']:>+11,.0f}円 | {test['bets']:>8} {test['roi']:>7.1f}% {test['profit']:>+11,.0f}円 | {diff:>+10,.0f}円")

    print("-" * 80)
    total_diff = total_test_profit - total_base_profit
    print(f"{'合計':>6} |          {total_base_profit:>+11,.0f}円 ({base_positive}/6年黒字) |          {total_test_profit:>+11,.0f}円 ({test_positive}/6年黒字) | {total_diff:>+10,.0f}円")


def main():
    print("=" * 80)
    print("直前情報除外条件の年度別安定性検証")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # ============================================================
    # D×35-60: モーター25%以上に限定
    # ============================================================
    print("\n" + "=" * 80)
    print("【D×35-60】モーター2連率25%以上に限定")
    print("=" * 80)

    base_cond = {
        'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 35, 'odds_max': 60,
        'race_exclude': [9], 'venue_exclude': [10]
    }
    base_results = analyze_yearly(cursor, base_cond)

    test_cond = base_cond.copy()
    test_cond['motor_min'] = 25
    test_results = analyze_yearly(cursor, test_cond)

    print_yearly_comparison("モーター25%以上に限定", base_results, test_results)

    # モーター40%以上
    test_cond = base_cond.copy()
    test_cond['motor_min'] = 40
    test_results = analyze_yearly(cursor, test_cond)

    print_yearly_comparison("モーター40%以上に限定", base_results, test_results)

    # ============================================================
    # D×40-50×B1: 風速4m未満 + NULLなしに限定
    # ============================================================
    print("\n" + "=" * 80)
    print("【D×40-50×B1】風速条件")
    print("=" * 80)

    base_cond = {
        'confidence': 'D', 'c1_rank': ['B1'],
        'odds_min': 40, 'odds_max': 50
    }
    base_results = analyze_yearly(cursor, base_cond)

    # 風速4m未満に限定
    test_cond = base_cond.copy()
    test_cond['wind_max'] = 4
    test_results = analyze_yearly(cursor, test_cond)

    print_yearly_comparison("風速4m未満に限定", base_results, test_results)

    # 風速データありのみ
    test_cond = base_cond.copy()
    test_cond['wind_not_null'] = True
    test_results = analyze_yearly(cursor, test_cond)

    print_yearly_comparison("風速データありのみ", base_results, test_results)

    # ============================================================
    # D×5コース予測: モーター25%以上に限定
    # ============================================================
    print("\n" + "=" * 80)
    print("【D×5コース予測】モーター条件")
    print("=" * 80)

    base_cond = {
        'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'],
        'odds_min': 10, 'odds_max': 200,
        'predicted_course': 5
    }
    base_results = analyze_yearly(cursor, base_cond)

    # モーター25%以上
    test_cond = base_cond.copy()
    test_cond['motor_min'] = 25
    test_results = analyze_yearly(cursor, test_cond)

    print_yearly_comparison("モーター25%以上に限定", base_results, test_results)

    # ============================================================
    # C×20-30×B1+会場: 風速6m未満に限定
    # ============================================================
    print("\n" + "=" * 80)
    print("【C×20-30×B1+会場】風速条件")
    print("=" * 80)

    base_cond = {
        'confidence': 'C', 'c1_rank': ['B1'],
        'odds_min': 20, 'odds_max': 30,
        'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]
    }
    base_results = analyze_yearly(cursor, base_cond)

    # 風速6m未満
    test_cond = base_cond.copy()
    test_cond['wind_max'] = 6
    test_results = analyze_yearly(cursor, test_cond)

    print_yearly_comparison("風速6m未満に限定", base_results, test_results)

    conn.close()

    print("\n" + "=" * 80)
    print("検証完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
