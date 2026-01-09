#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
除外条件候補の年度別安定性検証スクリプト

目的:
    有望な除外条件候補が年度を跨いで安定しているかを検証する

検証対象:
    1. A×A1×14-16: p2_third_rate < 35% を残す（35%以上を除外）
    2. C×20-30×B1+会場: c1_second_rate >= 35% を残す（35%未満を除外）
    3. A×A1×10-12: p3_second_rate >= 55% を残す（55%未満を除外）
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

# 検証対象の条件と除外ルール
VALIDATION_TARGETS = [
    {
        'cond_name': 'A×A1×14-16',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 14,
        'odds_max': 16,
        'venue_filter': None,
        'exclusion_column': 'p2_third_rate',
        'exclusion_operator': '<',  # この条件を残す
        'exclusion_threshold': 35,
        'description': '2着予測選手の3連対率が35%以上を除外'
    },
    {
        'cond_name': 'A×A1×14-16',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 14,
        'odds_max': 16,
        'venue_filter': None,
        'exclusion_column': 'p2_second_rate',
        'exclusion_operator': '<',
        'exclusion_threshold': 25,
        'description': '2着予測選手の2連対率が25%以上を除外'
    },
    {
        'cond_name': 'C×20-30×B1+会場',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17],
        'exclusion_column': 'c1_second_rate',
        'exclusion_operator': '>=',  # この条件を残す
        'exclusion_threshold': 35,
        'description': '1コース選手の2連対率が35%未満を除外'
    },
    {
        'cond_name': 'C×20-30×B1+会場',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17],
        'exclusion_column': 'p1_second_rate',
        'exclusion_operator': '>=',
        'exclusion_threshold': 35,
        'description': '1着予測選手の2連対率が35%未満を除外'
    },
    {
        'cond_name': 'A×A1×10-12',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 10,
        'odds_max': 12,
        'venue_filter': None,
        'exclusion_column': 'p3_second_rate',
        'exclusion_operator': '>=',
        'exclusion_threshold': 55,
        'description': '3着予測選手の2連対率が55%未満を除外'
    },
]


def get_yearly_results(cursor, target, year):
    """
    特定年度のデータを取得し、除外条件適用前後の結果を比較
    """
    c1_rank_str = "','".join(target['c1_rank'])
    venue_clause = ""
    if target.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, target['venue_filter']))})"

    # exclusion_columnに応じたJOIN
    col = target['exclusion_column']
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

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
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
        AND rp.confidence = '{target["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year}-01-01'
        AND r.race_date < '{year}-12-01'
        {venue_clause}
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
        filter_rate,
        pred_odds,
        is_hit,
        payout
    FROM race_bets
    WHERE pred_odds >= {target['odds_min']} AND pred_odds < {target['odds_max']}
    AND filter_rate IS NOT NULL
    '''

    cursor.execute(query)
    rows = cursor.fetchall()

    # 元の結果（全体）
    original_n = len(rows)
    original_hits = sum(1 for r in rows if r[2] == 1)
    original_payout = sum(r[3] for r in rows)
    original_roi = 100.0 * original_payout / (original_n * 100) if original_n > 0 else 0
    original_profit = original_payout - (original_n * 100)

    # フィルター適用後
    threshold = target['exclusion_threshold']
    op = target['exclusion_operator']

    if op == '<':
        filtered_rows = [r for r in rows if r[0] < threshold]
        excluded_rows = [r for r in rows if r[0] >= threshold]
    else:  # '>='
        filtered_rows = [r for r in rows if r[0] >= threshold]
        excluded_rows = [r for r in rows if r[0] < threshold]

    filtered_n = len(filtered_rows)
    filtered_hits = sum(1 for r in filtered_rows if r[2] == 1)
    filtered_payout = sum(r[3] for r in filtered_rows)
    filtered_roi = 100.0 * filtered_payout / (filtered_n * 100) if filtered_n > 0 else 0
    filtered_profit = filtered_payout - (filtered_n * 100)

    excluded_n = len(excluded_rows)
    excluded_hits = sum(1 for r in excluded_rows if r[2] == 1)
    excluded_payout = sum(r[3] for r in excluded_rows)
    excluded_roi = 100.0 * excluded_payout / (excluded_n * 100) if excluded_n > 0 else 0
    excluded_profit = excluded_payout - (excluded_n * 100)

    return {
        'year': year,
        'original_n': original_n,
        'original_hits': original_hits,
        'original_roi': original_roi,
        'original_profit': original_profit,
        'filtered_n': filtered_n,
        'filtered_hits': filtered_hits,
        'filtered_roi': filtered_roi,
        'filtered_profit': filtered_profit,
        'excluded_n': excluded_n,
        'excluded_hits': excluded_hits,
        'excluded_roi': excluded_roi,
        'excluded_profit': excluded_profit,
        'roi_improvement': filtered_roi - original_roi
    }


def main():
    print("=" * 120)
    print("除外条件候補の年度別安定性検証")
    print("=" * 120)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    years = [2020, 2021, 2022, 2023, 2024, 2025]

    # 最終的な推奨候補
    recommendations = []

    for target in VALIDATION_TARGETS:
        print(f"\n{'='*100}")
        print(f"条件: {target['cond_name']}")
        print(f"除外ルール: {target['description']}")
        print(f"フィルター: {target['exclusion_column']} {target['exclusion_operator']} {target['exclusion_threshold']}%")
        print(f"{'='*100}")

        yearly_results = []
        for year in years:
            result = get_yearly_results(cursor, target, year)
            yearly_results.append(result)

        # 年度別結果を表示
        print(f"\n{'年度':<6} {'元件数':>6} {'元ROI':>8} {'元収支':>12} {'新件数':>6} {'新ROI':>8} {'新収支':>12} {'除外件数':>6} {'除外ROI':>8} {'ROI改善':>10}")
        print("-" * 110)

        total_original_profit = 0
        total_filtered_profit = 0
        yearly_improvements = []
        years_positive_improvement = 0
        years_filtered_profitable = 0

        for r in yearly_results:
            print(f"{r['year']:<6} {r['original_n']:>6} {r['original_roi']:>7.1f}% {r['original_profit']:>+12,.0f} "
                  f"{r['filtered_n']:>6} {r['filtered_roi']:>7.1f}% {r['filtered_profit']:>+12,.0f} "
                  f"{r['excluded_n']:>6} {r['excluded_roi']:>7.1f}% {r['roi_improvement']:>+9.1f}%")

            total_original_profit += r['original_profit']
            total_filtered_profit += r['filtered_profit']
            yearly_improvements.append(r['roi_improvement'])

            if r['roi_improvement'] > 0:
                years_positive_improvement += 1
            if r['filtered_roi'] > 100:
                years_filtered_profitable += 1

        # 6年間合計
        total_original_n = sum(r['original_n'] for r in yearly_results)
        total_original_payout = sum(r['original_profit'] + r['original_n'] * 100 for r in yearly_results)
        total_original_roi = 100.0 * total_original_payout / (total_original_n * 100) if total_original_n > 0 else 0

        total_filtered_n = sum(r['filtered_n'] for r in yearly_results)
        total_filtered_payout = sum(r['filtered_profit'] + r['filtered_n'] * 100 for r in yearly_results)
        total_filtered_roi = 100.0 * total_filtered_payout / (total_filtered_n * 100) if total_filtered_n > 0 else 0

        total_excluded_n = sum(r['excluded_n'] for r in yearly_results)
        total_excluded_payout = sum(r['excluded_profit'] + r['excluded_n'] * 100 for r in yearly_results)
        total_excluded_roi = 100.0 * total_excluded_payout / (total_excluded_n * 100) if total_excluded_n > 0 else 0

        print("-" * 110)
        print(f"{'合計':<6} {total_original_n:>6} {total_original_roi:>7.1f}% {total_original_profit:>+12,.0f} "
              f"{total_filtered_n:>6} {total_filtered_roi:>7.1f}% {total_filtered_profit:>+12,.0f} "
              f"{total_excluded_n:>6} {total_excluded_roi:>7.1f}% {total_filtered_roi - total_original_roi:>+9.1f}%")

        # 安定性評価
        print(f"\n[安定性評価]")
        print(f"  - ROI改善年数: {years_positive_improvement}/6年")
        print(f"  - フィルター後黒字年数: {years_filtered_profitable}/6年")
        print(f"  - 6年間ROI改善: {total_filtered_roi - total_original_roi:+.1f}pt")
        print(f"  - 6年間収支改善: {total_filtered_profit - total_original_profit:+,.0f}円")

        # 統計的有意性検定（6年間データ）
        print(f"\n[統計的有意性]")
        all_original = []
        all_filtered = []
        for r in yearly_results:
            all_original.extend([1] * r['original_hits'] + [0] * (r['original_n'] - r['original_hits']))
            all_filtered.extend([1] * r['filtered_hits'] + [0] * (r['filtered_n'] - r['filtered_hits']))

        if len(all_filtered) > 10 and len(all_original) > 10:
            # フィルター前後のROI差の検定
            # 除外対象vs残す対象のカイ二乗検定
            all_excluded = []
            for r in yearly_results:
                all_excluded.extend([1] * r['excluded_hits'] + [0] * (r['excluded_n'] - r['excluded_hits']))

            if len(all_excluded) > 5:
                filtered_hits_total = sum(r['filtered_hits'] for r in yearly_results)
                filtered_miss_total = total_filtered_n - filtered_hits_total
                excluded_hits_total = sum(r['excluded_hits'] for r in yearly_results)
                excluded_miss_total = total_excluded_n - excluded_hits_total

                observed = np.array([[filtered_hits_total, filtered_miss_total],
                                    [excluded_hits_total, excluded_miss_total]])

                if observed.min() >= 1:  # 期待度数の条件
                    chi2, p_value, dof, expected = stats.chi2_contingency(observed)
                    print(f"  - カイ二乗統計量: {chi2:.3f}")
                    print(f"  - p値: {p_value:.4f}")
                    significance = "有意 (p<0.05)" if p_value < 0.05 else ("やや有意 (p<0.1)" if p_value < 0.1 else "有意でない")
                    print(f"  - 判定: {significance}")
                else:
                    p_value = None
                    print(f"  - サンプル不足で検定不可")
            else:
                p_value = None
                print(f"  - 除外対象が少なすぎて検定不可")
        else:
            p_value = None
            print(f"  - サンプル不足で検定不可")

        # 推奨判定
        is_recommended = (
            years_positive_improvement >= 4 and  # 4年以上でROI改善
            years_filtered_profitable >= 4 and   # 4年以上で黒字
            total_filtered_roi > total_original_roi and  # 全体でROI改善
            (p_value is None or p_value < 0.1)   # 統計的に有意（or サンプル不足）
        )

        print(f"\n[推奨判定]: {'採用推奨' if is_recommended else '採用見送り'}")

        if is_recommended:
            recommendations.append({
                'cond_name': target['cond_name'],
                'description': target['description'],
                'filter_rule': f"{target['exclusion_column']} {target['exclusion_operator']} {target['exclusion_threshold']}%",
                'original_roi': total_original_roi,
                'filtered_roi': total_filtered_roi,
                'roi_improvement': total_filtered_roi - total_original_roi,
                'profit_improvement': total_filtered_profit - total_original_profit,
                'years_positive': years_positive_improvement,
                'p_value': p_value
            })

    conn.close()

    # 最終サマリー
    print("\n" + "=" * 120)
    print("最終推奨候補サマリー")
    print("=" * 120)

    if recommendations:
        print(f"\n{'条件名':<25} {'除外ルール':<40} {'元ROI':>8} {'新ROI':>8} {'改善':>8} {'収支改善':>12} {'p値':>10}")
        print("-" * 120)
        for rec in recommendations:
            p_str = f"{rec['p_value']:.4f}" if rec['p_value'] else "N/A"
            print(f"{rec['cond_name']:<25} {rec['filter_rule']:<40} {rec['original_roi']:>7.1f}% {rec['filtered_roi']:>7.1f}% "
                  f"{rec['roi_improvement']:>+7.1f}% {rec['profit_improvement']:>+12,.0f} {p_str:>10}")

        print(f"\n推奨候補数: {len(recommendations)}件")
    else:
        print("\n年度別安定性の基準を満たす推奨候補はありませんでした。")

    print("\n検証完了")


if __name__ == '__main__':
    main()
