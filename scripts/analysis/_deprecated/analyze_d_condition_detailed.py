#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
D条件の詳細分析スクリプト

目的:
    D×35-60とD×5コース予測条件について、連対率による除外条件を探索
"""

import sqlite3
import sys
import io
import os
import numpy as np
from scipy import stats

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

D_CONDITIONS = [
    {
        'name': 'D×35-60',
        'confidence': 'D',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 35,
        'odds_max': 60,
        'venue_filter': None,
        'race_exclude': [9],
        'venue_exclude': [10],
    },
    {
        'name': 'D×5コース予測',
        'confidence': 'D',
        'c1_rank': ['A1', 'A2', 'B1', 'B2'],
        'odds_min': 10,
        'odds_max': 200,
        'venue_filter': None,
        'predicted_course': 5,
    },
]


def get_race_data_for_d_condition(cursor, cond, year_start, year_end):
    """D条件のレースデータを取得"""
    c1_rank_str = "','".join(cond['c1_rank'])

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
            r.venue_code,
            r.race_number,
            e1.racer_rank as c1_rank,
            e1.second_rate as c1_second_rate,
            e1.third_rate as c1_third_rate,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            e_p1.second_rate as p1_second_rate,
            e_p1.third_rate as p1_third_rate,
            e_p2.second_rate as p2_second_rate,
            e_p2.third_rate as p2_third_rate,
            e_p3.second_rate as p3_second_rate,
            e_p3.third_rate as p3_third_rate
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        JOIN entries e_p1 ON r.id = e_p1.race_id AND e_p1.pit_number = rp1.pit_number
        JOIN entries e_p2 ON r.id = e_p2.race_id AND e_p2.pit_number = rp2.pit_number
        JOIN entries e_p3 ON r.id = e_p3.race_id AND e_p3.pit_number = rp3.pit_number
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
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
        race_id, venue_code, race_number, c1_rank,
        c1_second_rate, c1_third_rate,
        p1, p2, p3,
        p1_second_rate, p1_third_rate,
        p2_second_rate, p2_third_rate,
        p3_second_rate, p3_third_rate,
        pred_odds, is_hit, payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    '''
    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def analyze_rentairitsu_cross(races, col1, col2, bins):
    """2つの連対率のクロス集計"""
    results = []
    for b1_min, b1_max, b1_label in bins:
        for b2_min, b2_max, b2_label in bins:
            filtered = [r for r in races
                       if r[col1] is not None and r[col2] is not None
                       and b1_min <= r[col1] < b1_max
                       and b2_min <= r[col2] < b2_max]

            if len(filtered) < 5:
                continue

            hits = sum(1 for r in filtered if r['is_hit'] == 1)
            total_payout = sum(r['payout'] for r in filtered)
            roi = 100.0 * total_payout / (len(filtered) * 100) if len(filtered) > 0 else 0
            hit_rate = 100.0 * hits / len(filtered)
            profit = total_payout - (len(filtered) * 100)

            results.append({
                'label': f"{b1_label}x{b2_label}",
                'col1_range': f"{b1_min}-{b1_max}%",
                'col2_range': f"{b2_min}-{b2_max}%",
                'count': len(filtered),
                'hits': hits,
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': profit
            })

    return results


def find_best_exclusion(races, rate_columns):
    """最適な除外条件を探索"""
    candidates = []

    for col in rate_columns:
        for threshold in [15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]:
            for op in ['<', '>=']:
                if op == '<':
                    filtered = [r for r in races if r[col] is not None and r[col] < threshold]
                    excluded = [r for r in races if r[col] is not None and r[col] >= threshold]
                else:
                    filtered = [r for r in races if r[col] is not None and r[col] >= threshold]
                    excluded = [r for r in races if r[col] is not None and r[col] < threshold]

                if len(filtered) < 20 or len(excluded) < 10:
                    continue

                original_n = len([r for r in races if r[col] is not None])
                original_payout = sum(r['payout'] for r in races if r[col] is not None)
                original_roi = 100.0 * original_payout / (original_n * 100) if original_n > 0 else 0

                filtered_payout = sum(r['payout'] for r in filtered)
                filtered_roi = 100.0 * filtered_payout / (len(filtered) * 100) if len(filtered) > 0 else 0

                excluded_payout = sum(r['payout'] for r in excluded)
                excluded_roi = 100.0 * excluded_payout / (len(excluded) * 100) if len(excluded) > 0 else 0

                roi_improvement = filtered_roi - original_roi
                profit_improvement = (filtered_payout - len(filtered) * 100) - (original_payout - original_n * 100) * len(filtered) / original_n if original_n > 0 else 0

                # カイ二乗検定
                filtered_hits = sum(1 for r in filtered if r['is_hit'] == 1)
                filtered_miss = len(filtered) - filtered_hits
                excluded_hits = sum(1 for r in excluded if r['is_hit'] == 1)
                excluded_miss = len(excluded) - excluded_hits

                try:
                    observed = np.array([[filtered_hits, filtered_miss], [excluded_hits, excluded_miss]])
                    if observed.min() >= 1:
                        chi2, p_value, dof, expected = stats.chi2_contingency(observed)
                    else:
                        p_value = None
                except:
                    p_value = None

                candidates.append({
                    'column': col,
                    'operator': op,
                    'threshold': threshold,
                    'original_n': original_n,
                    'original_roi': original_roi,
                    'filtered_n': len(filtered),
                    'filtered_roi': filtered_roi,
                    'excluded_n': len(excluded),
                    'excluded_roi': excluded_roi,
                    'roi_improvement': roi_improvement,
                    'p_value': p_value
                })

    candidates.sort(key=lambda x: x['roi_improvement'], reverse=True)
    return candidates


def yearly_validation(cursor, cond, col, op, threshold, years):
    """年度別検証"""
    results = []

    c1_rank_str = "','".join(cond['c1_rank'])

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    # カラム名からJOIN先を特定
    if col.startswith('c1_'):
        rate_join = "e1"
        rate_col = col.replace('c1_', '')
    elif col.startswith('p1_'):
        rate_join = "e_p1"
        rate_col = col.replace('p1_', '')
    elif col.startswith('p2_'):
        rate_join = "e_p2"
        rate_col = col.replace('p2_', '')
    elif col.startswith('p3_'):
        rate_join = "e_p3"
        rate_col = col.replace('p3_', '')

    for year in years:
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                {rate_join}.{rate_col} as filter_rate
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            JOIN entries e_p1 ON r.id = e_p1.race_id AND e_p1.pit_number = rp1.pit_number
            JOIN entries e_p2 ON r.id = e_p2.race_id AND e_p2.pit_number = rp2.pit_number
            JOIN entries e_p3 ON r.id = e_p3.race_id AND e_p3.pit_number = rp3.pit_number
            WHERE rp.rank_prediction = 1
            AND rp.confidence = '{cond["confidence"]}'
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{year}-01-01'
            AND r.race_date < '{year}-12-01'
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
            filter_rate, pred_odds, is_hit, payout
        FROM race_bets
        WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
        AND filter_rate IS NOT NULL
        '''

        cursor.execute(query)
        rows = cursor.fetchall()

        original_n = len(rows)
        original_payout = sum(r[3] for r in rows)
        original_roi = 100.0 * original_payout / (original_n * 100) if original_n > 0 else 0
        original_profit = original_payout - (original_n * 100)

        if op == '<':
            filtered_rows = [r for r in rows if r[0] < threshold]
        else:
            filtered_rows = [r for r in rows if r[0] >= threshold]

        filtered_n = len(filtered_rows)
        filtered_payout = sum(r[3] for r in filtered_rows)
        filtered_roi = 100.0 * filtered_payout / (filtered_n * 100) if filtered_n > 0 else 0
        filtered_profit = filtered_payout - (filtered_n * 100)

        results.append({
            'year': year,
            'original_n': original_n,
            'original_roi': original_roi,
            'original_profit': original_profit,
            'filtered_n': filtered_n,
            'filtered_roi': filtered_roi,
            'filtered_profit': filtered_profit,
            'roi_improvement': filtered_roi - original_roi
        })

    return results


def main():
    print("=" * 100)
    print("D条件の詳細分析（連対率による除外条件探索）")
    print("=" * 100)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    years = [2020, 2021, 2022, 2023, 2024, 2025]

    for cond in D_CONDITIONS:
        print(f"\n{'='*80}")
        print(f"条件: {cond['name']}")
        print(f"{'='*80}")

        races = get_race_data_for_d_condition(cursor, cond, 2020, 2025)

        if len(races) == 0:
            print("該当レースなし")
            continue

        # 基本統計
        total_bets = len(races)
        total_hits = sum(1 for r in races if r['is_hit'] == 1)
        total_payout = sum(r['payout'] for r in races)
        hit_rate = 100.0 * total_hits / total_bets
        roi = 100.0 * total_payout / (total_bets * 100)
        profit = total_payout - (total_bets * 100)

        print(f"\n[基本統計]")
        print(f"購入数: {total_bets}件, 的中: {total_hits}件 ({hit_rate:.1f}%)")
        print(f"ROI: {roi:.1f}%, 収支: {profit:+,.0f}円")

        # 除外条件探索
        rate_columns = ['c1_second_rate', 'p1_second_rate', 'p2_second_rate', 'p3_second_rate',
                       'c1_third_rate', 'p1_third_rate', 'p2_third_rate', 'p3_third_rate']

        print(f"\n[有望な除外条件候補（ROI改善順）]")
        candidates = find_best_exclusion(races, rate_columns)

        # 上位候補を表示
        promising = [c for c in candidates if c['roi_improvement'] > 10 and c['filtered_n'] >= 30]

        if promising:
            print(f"\n{'カラム':<18} {'条件':<10} {'元ROI':>8} {'新ROI':>8} {'改善':>8} {'件数変化':>10} {'除外ROI':>8} {'p値':>10}")
            print("-" * 100)
            for c in promising[:15]:
                p_str = f"{c['p_value']:.4f}" if c['p_value'] else "N/A"
                cond_str = f"{c['operator']}{c['threshold']}%"
                n_change = f"{c['original_n']}->{c['filtered_n']}"
                print(f"{c['column']:<18} {cond_str:<10} {c['original_roi']:>7.1f}% {c['filtered_roi']:>7.1f}% {c['roi_improvement']:>+7.1f}% {n_change:>10} {c['excluded_roi']:>7.1f}% {p_str:>10}")

            # 上位3候補について年度別検証
            print(f"\n[上位候補の年度別検証]")
            for c in promising[:3]:
                print(f"\n--- {c['column']} {c['operator']} {c['threshold']}% ---")
                yearly_results = yearly_validation(cursor, cond, c['column'], c['operator'], c['threshold'], years)

                print(f"{'年度':<6} {'元件数':>6} {'元ROI':>8} {'新件数':>6} {'新ROI':>8} {'改善':>10}")
                print("-" * 60)

                years_improved = 0
                years_profitable = 0

                for r in yearly_results:
                    status = "+" if r['roi_improvement'] > 0 else ""
                    print(f"{r['year']:<6} {r['original_n']:>6} {r['original_roi']:>7.1f}% {r['filtered_n']:>6} {r['filtered_roi']:>7.1f}% {r['roi_improvement']:>+9.1f}%")

                    if r['roi_improvement'] > 0:
                        years_improved += 1
                    if r['filtered_roi'] > 100:
                        years_profitable += 1

                print(f"\n改善年数: {years_improved}/6年, 黒字年数: {years_profitable}/6年")

                # 採用推奨判定
                if years_improved >= 4 and years_profitable >= 4:
                    print("推奨: 採用検討")
                else:
                    print("推奨: 見送り（安定性不足）")
        else:
            print("有望な除外条件候補なし（ROI+10pt以上の条件がない）")

        # クロス集計（1着予測選手と2着予測選手の連対率）
        print(f"\n[連対率クロス集計: P1 x P2（2連対率）]")
        bins = [(0, 25, 'low'), (25, 40, 'mid'), (40, 100, 'high')]
        cross_results = analyze_rentairitsu_cross(races, 'p1_second_rate', 'p2_second_rate', bins)

        if cross_results:
            cross_results.sort(key=lambda x: x['roi'], reverse=True)
            print(f"{'パターン':<15} {'P1範囲':<12} {'P2範囲':<12} {'件数':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
            print("-" * 85)
            for c in cross_results:
                print(f"{c['label']:<15} {c['col1_range']:<12} {c['col2_range']:<12} {c['count']:>6} {c['hit_rate']:>7.1f}% {c['roi']:>7.1f}% {c['profit']:>+12,.0f}")

    conn.close()
    print("\n分析完了")


if __name__ == '__main__':
    main()
