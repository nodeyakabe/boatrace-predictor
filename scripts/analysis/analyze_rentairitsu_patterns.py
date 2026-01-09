#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2連対率・3連対率を活用した不的中パターン分析スクリプト

目的:
    各購入条件における不的中レースの特徴を分析し、除外条件を探索する

分析観点:
    - 1コース選手の2連対率・3連対率と的中率の関係
    - 2着予測選手の2連対率・3連対率と的中率の関係
    - 3着予測選手の2連対率・3連対率と的中率の関係
    - 複数選手の連対率組み合わせパターン

使用方法:
    python scripts/analysis/analyze_rentairitsu_patterns.py
"""

import sqlite3
import sys
import io
import os
import numpy as np
from scipy import stats
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 購入条件定義（standard_backtest.pyと同一）
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
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None,
     'c1_second_rate_min': 20, 'c1_second_rate_max': 30},
    {'name': 'D×35-60', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 35, 'odds_max': 60, 'venue_filter': None,
     'race_exclude': [9], 'venue_exclude': [10]},
    {'name': 'D×5コース予測', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'], 'odds_min': 10, 'odds_max': 200,
     'venue_filter': None, 'predicted_course': 5},
]


def get_race_data_for_condition(cursor, cond, year_start, year_end):
    """
    条件に合致するレースの詳細データを取得
    各レースについて、予測艇と結果、選手の連対率を取得
    """
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

    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_number,
            rp.confidence,
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
        {venue_clause}
        {motor_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
        {c1_second_rate_clause}
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
        race_id,
        venue_code,
        race_number,
        confidence,
        c1_rank,
        c1_second_rate,
        c1_third_rate,
        p1,
        p2,
        p3,
        p1_second_rate,
        p1_third_rate,
        p2_second_rate,
        p2_third_rate,
        p3_second_rate,
        p3_third_rate,
        pred_odds,
        is_hit,
        payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    '''
    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def analyze_second_rate_distribution(races, rate_column, position_name):
    """
    連対率の分布と的中率の関係を分析
    """
    # 連対率を10%刻みでビン分け
    bins = [(0, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 100)]
    results = []

    for bin_min, bin_max in bins:
        bin_races = [r for r in races if r[rate_column] is not None
                     and bin_min <= r[rate_column] < bin_max]
        if len(bin_races) == 0:
            continue

        hits = sum(1 for r in bin_races if r['is_hit'] == 1)
        total = len(bin_races)
        hit_rate = 100.0 * hits / total if total > 0 else 0
        total_payout = sum(r['payout'] for r in bin_races)
        roi = 100.0 * total_payout / (total * 100) if total > 0 else 0
        profit = total_payout - (total * 100)

        results.append({
            'bin': f"{bin_min}-{bin_max}%",
            'count': total,
            'hits': hits,
            'hit_rate': hit_rate,
            'roi': roi,
            'profit': profit
        })

    return results


def chi_square_test(races, rate_column, threshold):
    """
    カイ二乗検定: 連対率の閾値による的中率の差を検定
    """
    # 閾値以上と未満でグループ分け
    above = [r for r in races if r[rate_column] is not None and r[rate_column] >= threshold]
    below = [r for r in races if r[rate_column] is not None and r[rate_column] < threshold]

    if len(above) < 5 or len(below) < 5:
        return None  # サンプル不足

    # 観測度数
    above_hit = sum(1 for r in above if r['is_hit'] == 1)
    above_miss = len(above) - above_hit
    below_hit = sum(1 for r in below if r['is_hit'] == 1)
    below_miss = len(below) - below_hit

    # 2x2のカイ二乗検定
    observed = np.array([[above_hit, above_miss], [below_hit, below_miss]])

    try:
        chi2, p_value, dof, expected = stats.chi2_contingency(observed)
        return {
            'chi2': chi2,
            'p_value': p_value,
            'above_n': len(above),
            'above_hit_rate': 100.0 * above_hit / len(above),
            'below_n': len(below),
            'below_hit_rate': 100.0 * below_hit / len(below)
        }
    except:
        return None


def find_exclusion_candidates(races, rate_columns):
    """
    除外条件候補を探索
    ROIが大きく改善する閾値を探す
    """
    candidates = []

    for col in rate_columns:
        # 各閾値でテスト
        for threshold in [20, 25, 30, 35, 40, 45, 50, 55, 60]:
            # 閾値未満を除外した場合のROI
            filtered = [r for r in races if r[col] is not None and r[col] >= threshold]
            excluded = [r for r in races if r[col] is not None and r[col] < threshold]

            if len(filtered) < 10 or len(excluded) < 5:
                continue

            # 元のROI
            original_payout = sum(r['payout'] for r in races if r[col] is not None)
            original_n = len([r for r in races if r[col] is not None])
            original_roi = 100.0 * original_payout / (original_n * 100) if original_n > 0 else 0

            # フィルター後のROI
            filtered_payout = sum(r['payout'] for r in filtered)
            filtered_roi = 100.0 * filtered_payout / (len(filtered) * 100) if len(filtered) > 0 else 0

            # 除外対象のROI
            excluded_payout = sum(r['payout'] for r in excluded)
            excluded_roi = 100.0 * excluded_payout / (len(excluded) * 100) if len(excluded) > 0 else 0

            roi_improvement = filtered_roi - original_roi

            # 有意性検定
            chi_result = chi_square_test(races, col, threshold)

            candidates.append({
                'column': col,
                'threshold': threshold,
                'operator': '>=',  # 閾値以上を残す（未満を除外）
                'original_n': original_n,
                'original_roi': original_roi,
                'filtered_n': len(filtered),
                'filtered_roi': filtered_roi,
                'excluded_n': len(excluded),
                'excluded_roi': excluded_roi,
                'roi_improvement': roi_improvement,
                'chi_result': chi_result
            })

            # 閾値以上を除外した場合も検討
            filtered_inv = excluded
            excluded_inv = filtered

            if len(filtered_inv) < 10:
                continue

            filtered_inv_payout = sum(r['payout'] for r in filtered_inv)
            filtered_inv_roi = 100.0 * filtered_inv_payout / (len(filtered_inv) * 100) if len(filtered_inv) > 0 else 0

            excluded_inv_payout = sum(r['payout'] for r in excluded_inv)
            excluded_inv_roi = 100.0 * excluded_inv_payout / (len(excluded_inv) * 100) if len(excluded_inv) > 0 else 0

            roi_improvement_inv = filtered_inv_roi - original_roi

            candidates.append({
                'column': col,
                'threshold': threshold,
                'operator': '<',  # 閾値未満を残す（以上を除外）
                'original_n': original_n,
                'original_roi': original_roi,
                'filtered_n': len(filtered_inv),
                'filtered_roi': filtered_inv_roi,
                'excluded_n': len(excluded_inv),
                'excluded_roi': excluded_inv_roi,
                'roi_improvement': roi_improvement_inv,
                'chi_result': chi_result
            })

    # ROI改善が大きい順にソート
    candidates.sort(key=lambda x: x['roi_improvement'], reverse=True)
    return candidates


def analyze_combined_patterns(races):
    """
    複数の連対率の組み合わせパターンを分析
    """
    patterns = []

    # 1着予測選手と2着予測選手の連対率組み合わせ
    rate_bins = [(0, 30, 'low'), (30, 50, 'mid'), (50, 100, 'high')]

    for p1_min, p1_max, p1_label in rate_bins:
        for p2_min, p2_max, p2_label in rate_bins:
            filtered = [r for r in races
                       if r['p1_second_rate'] is not None and r['p2_second_rate'] is not None
                       and p1_min <= r['p1_second_rate'] < p1_max
                       and p2_min <= r['p2_second_rate'] < p2_max]

            if len(filtered) < 10:
                continue

            hits = sum(1 for r in filtered if r['is_hit'] == 1)
            total_payout = sum(r['payout'] for r in filtered)
            roi = 100.0 * total_payout / (len(filtered) * 100)
            hit_rate = 100.0 * hits / len(filtered)
            profit = total_payout - (len(filtered) * 100)

            patterns.append({
                'pattern': f"P1:{p1_label} x P2:{p2_label}",
                'p1_range': f"{p1_min}-{p1_max}%",
                'p2_range': f"{p2_min}-{p2_max}%",
                'count': len(filtered),
                'hits': hits,
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': profit
            })

    return patterns


def main():
    print("=" * 100)
    print("2連対率・3連対率を活用した不的中パターン分析")
    print("=" * 100)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 分析期間: 2020-2025年
    year_start = 2020
    year_end = 2025

    all_candidates = []

    for cond in CONDITIONS:
        print(f"\n{'='*80}")
        print(f"条件: {cond['name']}")
        print(f"{'='*80}")

        races = get_race_data_for_condition(cursor, cond, year_start, year_end)

        if len(races) == 0:
            print("該当レースなし")
            continue

        # 基本統計
        total_bets = len(races)
        total_hits = sum(1 for r in races if r['is_hit'] == 1)
        total_payout = sum(r['payout'] for r in races)
        hit_rate = 100.0 * total_hits / total_bets if total_bets > 0 else 0
        roi = 100.0 * total_payout / (total_bets * 100) if total_bets > 0 else 0
        profit = total_payout - (total_bets * 100)

        print(f"\n[基本統計]")
        print(f"購入数: {total_bets}件, 的中: {total_hits}件 ({hit_rate:.1f}%)")
        print(f"ROI: {roi:.1f}%, 収支: {profit:+,.0f}円")

        # 1. 1コース選手の連対率分析
        print(f"\n[1コース選手の2連対率と的中率の関係]")
        c1_dist = analyze_second_rate_distribution(races, 'c1_second_rate', '1コース選手')
        print(f"{'2連対率帯':>12} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
        print("-" * 60)
        for d in c1_dist:
            print(f"{d['bin']:>12} {d['count']:>8} {d['hits']:>6} {d['hit_rate']:>7.1f}% {d['roi']:>7.1f}% {d['profit']:>+12,.0f}")

        # 2. 1着予測選手の連対率分析
        print(f"\n[1着予測選手の2連対率と的中率の関係]")
        p1_dist = analyze_second_rate_distribution(races, 'p1_second_rate', '1着予測選手')
        print(f"{'2連対率帯':>12} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
        print("-" * 60)
        for d in p1_dist:
            print(f"{d['bin']:>12} {d['count']:>8} {d['hits']:>6} {d['hit_rate']:>7.1f}% {d['roi']:>7.1f}% {d['profit']:>+12,.0f}")

        # 3. 2着予測選手の連対率分析
        print(f"\n[2着予測選手の2連対率と的中率の関係]")
        p2_dist = analyze_second_rate_distribution(races, 'p2_second_rate', '2着予測選手')
        print(f"{'2連対率帯':>12} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
        print("-" * 60)
        for d in p2_dist:
            print(f"{d['bin']:>12} {d['count']:>8} {d['hits']:>6} {d['hit_rate']:>7.1f}% {d['roi']:>7.1f}% {d['profit']:>+12,.0f}")

        # 4. 3着予測選手の連対率分析
        print(f"\n[3着予測選手の2連対率と的中率の関係]")
        p3_dist = analyze_second_rate_distribution(races, 'p3_second_rate', '3着予測選手')
        print(f"{'2連対率帯':>12} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
        print("-" * 60)
        for d in p3_dist:
            print(f"{d['bin']:>12} {d['count']:>8} {d['hits']:>6} {d['hit_rate']:>7.1f}% {d['roi']:>7.1f}% {d['profit']:>+12,.0f}")

        # 5. 3連対率分析（1着予測選手）
        print(f"\n[1着予測選手の3連対率と的中率の関係]")
        p1_third_dist = analyze_second_rate_distribution(races, 'p1_third_rate', '1着予測選手(3連対)')
        print(f"{'3連対率帯':>12} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
        print("-" * 60)
        for d in p1_third_dist:
            print(f"{d['bin']:>12} {d['count']:>8} {d['hits']:>6} {d['hit_rate']:>7.1f}% {d['roi']:>7.1f}% {d['profit']:>+12,.0f}")

        # 6. 除外条件候補の探索
        print(f"\n[有望な除外条件候補（ROI改善順・上位10件）]")
        rate_columns = ['c1_second_rate', 'p1_second_rate', 'p2_second_rate', 'p3_second_rate',
                       'c1_third_rate', 'p1_third_rate', 'p2_third_rate', 'p3_third_rate']
        candidates = find_exclusion_candidates(races, rate_columns)

        # 有望な候補（ROI改善+5pt以上、統計的に有意 or サンプル多い）
        promising = [c for c in candidates
                    if c['roi_improvement'] > 5
                    and c['filtered_n'] >= 20
                    and (c['chi_result'] is None or c['chi_result']['p_value'] < 0.1)]

        if promising:
            print(f"{'カラム':<20} {'条件':<10} {'元ROI':>8} {'新ROI':>8} {'改善':>8} {'除外件数':>8} {'除外ROI':>8} {'p値':>10}")
            print("-" * 100)
            for c in promising[:10]:
                p_val_str = f"{c['chi_result']['p_value']:.4f}" if c['chi_result'] else "N/A"
                cond_str = f"{c['operator']}{c['threshold']}%"
                print(f"{c['column']:<20} {cond_str:<10} {c['original_roi']:>7.1f}% {c['filtered_roi']:>7.1f}% {c['roi_improvement']:>+7.1f}% {c['excluded_n']:>8} {c['excluded_roi']:>7.1f}% {p_val_str:>10}")

                # 全体の候補にも追加
                all_candidates.append({
                    'condition': cond['name'],
                    **c
                })
        else:
            print("有望な除外条件候補なし")

        # 7. 組み合わせパターン分析
        print(f"\n[連対率組み合わせパターン分析]")
        patterns = analyze_combined_patterns(races)

        # ROIでソート
        patterns.sort(key=lambda x: x['roi'], reverse=True)

        print(f"{'パターン':<20} {'P1範囲':<12} {'P2範囲':<12} {'件数':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
        print("-" * 90)
        for p in patterns[:10]:
            print(f"{p['pattern']:<20} {p['p1_range']:<12} {p['p2_range']:<12} {p['count']:>6} {p['hit_rate']:>7.1f}% {p['roi']:>7.1f}% {p['profit']:>+12,.0f}")

    conn.close()

    # 全条件を通じた有望な除外条件のサマリー
    print("\n" + "=" * 100)
    print("全条件を通じた有望な除外条件候補サマリー")
    print("=" * 100)

    if all_candidates:
        # ROI改善が大きい順にソート
        all_candidates.sort(key=lambda x: x['roi_improvement'], reverse=True)

        print(f"\n{'条件名':<25} {'カラム':<18} {'閾値条件':<10} {'元ROI':>8} {'新ROI':>8} {'改善':>8} {'除外ROI':>8}")
        print("-" * 110)
        for c in all_candidates[:20]:
            cond_str = f"{c['operator']}{c['threshold']}%"
            print(f"{c['condition']:<25} {c['column']:<18} {cond_str:<10} {c['original_roi']:>7.1f}% {c['filtered_roi']:>7.1f}% {c['roi_improvement']:>+7.1f}% {c['excluded_roi']:>7.1f}%")
    else:
        print("有望な除外条件候補は見つかりませんでした")

    print("\n分析完了")


if __name__ == '__main__':
    main()
