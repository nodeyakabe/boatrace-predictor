#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
3連対率×会場のクロス分析スクリプト

目的:
    各購入条件について、1コース選手の3連対率帯と会場の組み合わせによる
    ROI差異を調査し、除外/採用条件の候補を特定する

出力:
    1. 会場×3連対率のクロス集計表（ROI、件数、的中率）
    2. 有望パターンリスト（改善効果、p値、年度別安定性）
    3. 最終推奨（実装すべき条件）
"""
import sqlite3
import sys
import io
import os
import json
from collections import defaultdict
import numpy as np
from scipy import stats

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 会場名マッピング
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# イン強会場（参考）
IN_STRONG_VENUES = [10, 21, 24, 18, 19]  # 三国, 芦屋, 大村, 徳山, 下関

# 3連対率帯の定義
THIRD_RATE_BANDS = [
    (0, 40, '0-40%'),
    (40, 50, '40-50%'),
    (50, 60, '50-60%'),
    (60, 100, '60%+')
]

# 現在の購入条件定義
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


def get_third_rate_band(third_rate):
    """3連対率から帯を取得"""
    if third_rate is None:
        return None
    for low, high, label in THIRD_RATE_BANDS:
        if low <= third_rate < high:
            return label
    return '60%+' if third_rate >= 60 else '0-40%'


def analyze_condition_by_venue_third_rate(cursor, cond, year_start=2020, year_end=2025, target='c1'):
    """
    条件別の会場×3連対率クロス分析

    Args:
        cursor: DB cursor
        cond: 条件辞書
        year_start: 開始年
        year_end: 終了年
        target: 'c1'=1コース選手, 'pred2'=2着予測選手

    Returns:
        dict: {(venue_code, third_rate_band): {'bets', 'hits', 'payout', 'roi', 'profit'}}
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

    # ターゲットによって取得するカラムを変更
    if target == 'c1':
        target_third_rate = "e1.third_rate"
    else:  # pred2
        target_third_rate = "e2.third_rate"

    query = f'''
    SELECT
        CAST(r.venue_code AS INTEGER) as venue_code,
        {target_third_rate} as target_third_rate,
        substr(r.race_date, 1, 4) as year,
        COALESCE(
            (SELECT o.odds FROM trifecta_odds o
             WHERE o.race_id = r.id
             AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
            ), 0
        ) as pred_odds,
        CASE
            WHEN (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') = rp1.pit_number
             AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') = rp2.pit_number
             AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') = rp3.pit_number
            THEN 1 ELSE 0
        END as is_hit,
        CASE
            WHEN (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') = rp1.pit_number
             AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') = rp2.pit_number
             AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') = rp3.pit_number
            THEN COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                ), 0
            ) * 100
            ELSE 0
        END as payout
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    JOIN entries e2 ON r.id = e2.race_id AND e2.pit_number = rp2.pit_number
    WHERE rp.rank_prediction = 1
    AND rp.confidence = '{cond["confidence"]}'
    AND e1.racer_rank IN ('{c1_rank_str}')
    AND r.race_date >= '{year_start}-01-01'
    AND r.race_date < '{year_end + 1}-01-01'
    {venue_clause}
    {motor_clause}
    {race_exclude_clause}
    {venue_exclude_clause}
    {predicted_course_clause}
    {c1_second_rate_clause}
    '''

    cursor.execute(query)
    rows = cursor.fetchall()

    # 条件に合致するオッズ範囲でフィルタリング
    results = defaultdict(lambda: {'bets': 0, 'hits': 0, 'payout': 0, 'yearly': defaultdict(lambda: {'bets': 0, 'hits': 0, 'payout': 0})})

    for venue_code, target_third_rate, year, pred_odds, is_hit, payout in rows:
        if pred_odds < cond['odds_min'] or pred_odds >= cond['odds_max']:
            continue

        third_rate_band = get_third_rate_band(target_third_rate)
        if third_rate_band is None:
            continue

        key = (venue_code, third_rate_band)
        results[key]['bets'] += 1
        results[key]['hits'] += is_hit
        results[key]['payout'] += payout
        results[key]['yearly'][year]['bets'] += 1
        results[key]['yearly'][year]['hits'] += is_hit
        results[key]['yearly'][year]['payout'] += payout

    # ROI計算
    for key in results:
        bets = results[key]['bets']
        if bets > 0:
            results[key]['roi'] = 100.0 * results[key]['payout'] / (bets * 100)
            results[key]['profit'] = results[key]['payout'] - (bets * 100)
            results[key]['hit_rate'] = 100.0 * results[key]['hits'] / bets
        else:
            results[key]['roi'] = 0
            results[key]['profit'] = 0
            results[key]['hit_rate'] = 0

        # 年度別ROI計算
        for year in results[key]['yearly']:
            yearly_bets = results[key]['yearly'][year]['bets']
            if yearly_bets > 0:
                results[key]['yearly'][year]['roi'] = 100.0 * results[key]['yearly'][year]['payout'] / (yearly_bets * 100)
                results[key]['yearly'][year]['profit'] = results[key]['yearly'][year]['payout'] - (yearly_bets * 100)
            else:
                results[key]['yearly'][year]['roi'] = 0
                results[key]['yearly'][year]['profit'] = 0

    return dict(results)


def analyze_venue_group_third_rate(cursor, cond, year_start=2020, year_end=2025):
    """
    イン強会場 vs その他 × 3連対率のクロス分析
    """
    results = analyze_condition_by_venue_third_rate(cursor, cond, year_start, year_end, 'c1')

    # イン強会場とその他で集約
    aggregated = {
        'in_strong': defaultdict(lambda: {'bets': 0, 'hits': 0, 'payout': 0, 'yearly': defaultdict(lambda: {'bets': 0, 'hits': 0, 'payout': 0})}),
        'other': defaultdict(lambda: {'bets': 0, 'hits': 0, 'payout': 0, 'yearly': defaultdict(lambda: {'bets': 0, 'hits': 0, 'payout': 0})})
    }

    for (venue_code, third_rate_band), data in results.items():
        group = 'in_strong' if venue_code in IN_STRONG_VENUES else 'other'
        aggregated[group][third_rate_band]['bets'] += data['bets']
        aggregated[group][third_rate_band]['hits'] += data['hits']
        aggregated[group][third_rate_band]['payout'] += data['payout']

        for year, yearly_data in data['yearly'].items():
            aggregated[group][third_rate_band]['yearly'][year]['bets'] += yearly_data['bets']
            aggregated[group][third_rate_band]['yearly'][year]['hits'] += yearly_data['hits']
            aggregated[group][third_rate_band]['yearly'][year]['payout'] += yearly_data['payout']

    # ROI計算
    for group in aggregated:
        for band in aggregated[group]:
            bets = aggregated[group][band]['bets']
            if bets > 0:
                aggregated[group][band]['roi'] = 100.0 * aggregated[group][band]['payout'] / (bets * 100)
                aggregated[group][band]['profit'] = aggregated[group][band]['payout'] - (bets * 100)
                aggregated[group][band]['hit_rate'] = 100.0 * aggregated[group][band]['hits'] / bets

    return aggregated


def chi_square_test(results_a, results_b):
    """
    2つの結果間でカイ二乗検定を実行

    Args:
        results_a: {'bets': N, 'hits': M, ...}
        results_b: {'bets': N, 'hits': M, ...}

    Returns:
        (chi2, p_value)
    """
    # 2x2の分割表を作成 [[hits_a, misses_a], [hits_b, misses_b]]
    hits_a, bets_a = results_a['hits'], results_a['bets']
    hits_b, bets_b = results_b['hits'], results_b['bets']

    misses_a = bets_a - hits_a
    misses_b = bets_b - hits_b

    if bets_a < 5 or bets_b < 5:
        return None, None

    table = [[hits_a, misses_a], [hits_b, misses_b]]

    try:
        chi2, p_value, dof, expected = stats.chi2_contingency(table)
        return chi2, p_value
    except:
        return None, None


def analyze_all_conditions():
    """全条件を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    all_results = {}
    promising_patterns = []

    print("=" * 100)
    print("3連対率×会場 クロス分析レポート")
    print("=" * 100)
    print()

    for cond in CONDITIONS:
        print(f"\n{'=' * 80}")
        print(f"条件: {cond['name']}")
        print(f"{'=' * 80}")

        # 1コース選手の3連対率×会場分析
        results_c1 = analyze_condition_by_venue_third_rate(cursor, cond, 2020, 2025, 'c1')

        if not results_c1:
            print("  データなし")
            continue

        # 全体のベースライン計算
        total_bets = sum(r['bets'] for r in results_c1.values())
        total_hits = sum(r['hits'] for r in results_c1.values())
        total_payout = sum(r['payout'] for r in results_c1.values())

        if total_bets == 0:
            print("  データなし")
            continue

        baseline_roi = 100.0 * total_payout / (total_bets * 100)
        baseline_hit_rate = 100.0 * total_hits / total_bets

        print(f"\n【ベースライン】 件数: {total_bets:,}, 的中率: {baseline_hit_rate:.2f}%, ROI: {baseline_roi:.1f}%")

        # 3連対率帯別の集計
        print(f"\n【1コース3連対率帯別】")
        print(f"{'3連対率帯':<12} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
        print("-" * 60)

        band_results = defaultdict(lambda: {'bets': 0, 'hits': 0, 'payout': 0})
        for (venue, band), data in results_c1.items():
            band_results[band]['bets'] += data['bets']
            band_results[band]['hits'] += data['hits']
            band_results[band]['payout'] += data['payout']

        for band in ['0-40%', '40-50%', '50-60%', '60%+']:
            if band in band_results:
                bets = band_results[band]['bets']
                hits = band_results[band]['hits']
                payout = band_results[band]['payout']
                if bets > 0:
                    roi = 100.0 * payout / (bets * 100)
                    hit_rate = 100.0 * hits / bets
                    profit = payout - (bets * 100)
                    roi_diff = roi - baseline_roi
                    print(f"{band:<12} {bets:>8,} {hits:>6} {hit_rate:>7.2f}% {roi:>7.1f}% {profit:>+12,.0f}  ({roi_diff:>+.1f}pt)")

        # 会場グループ×3連対率
        print(f"\n【イン強会場 vs その他 × 3連対率】")
        group_results = analyze_venue_group_third_rate(cursor, cond)

        for group in ['in_strong', 'other']:
            group_name = 'イン強会場' if group == 'in_strong' else 'その他会場'
            print(f"\n  [{group_name}]")
            print(f"  {'3連対率帯':<12} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
            print("  " + "-" * 58)

            for band in ['0-40%', '40-50%', '50-60%', '60%+']:
                if band in group_results[group]:
                    data = group_results[group][band]
                    bets = data['bets']
                    hits = data['hits']
                    payout = data['payout']
                    if bets > 0:
                        roi = 100.0 * payout / (bets * 100)
                        hit_rate = 100.0 * hits / bets
                        profit = payout - (bets * 100)
                        print(f"  {band:<12} {bets:>8,} {hits:>6} {hit_rate:>7.2f}% {roi:>7.1f}% {profit:>+12,.0f}")

        # 有望パターン（除外/追加候補）の特定
        print(f"\n【会場×3連対率 詳細】")
        print(f"{'会場':<8} {'3連対率帯':<10} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>7} {'収支':>10} {'差分':>8} {'黒字年':>6}")
        print("-" * 85)

        # サンプル50件以上でROI差が30pt以上のパターンを抽出
        for (venue_code, band), data in sorted(results_c1.items(), key=lambda x: x[1].get('roi', 0) - baseline_roi, reverse=True):
            bets = data['bets']
            if bets < 10:
                continue

            hits = data['hits']
            payout = data['payout']
            roi = 100.0 * payout / (bets * 100) if bets > 0 else 0
            hit_rate = 100.0 * hits / bets if bets > 0 else 0
            profit = payout - (bets * 100)
            roi_diff = roi - baseline_roi

            # 年度別黒字年数
            black_years = sum(1 for year, yd in data['yearly'].items() if yd['bets'] > 0 and yd['payout'] > yd['bets'] * 100)
            total_years = sum(1 for year, yd in data['yearly'].items() if yd['bets'] > 0)

            venue_name = VENUE_NAMES.get(venue_code, str(venue_code))
            print(f"{venue_name:<8} {band:<10} {bets:>6} {hits:>4} {hit_rate:>6.2f}% {roi:>6.1f}% {profit:>+10,.0f} {roi_diff:>+7.1f}pt {black_years}/{total_years}年")

            # 有望パターンの条件（サンプル50件以上、ROI差30pt以上）
            if bets >= 50 and abs(roi_diff) >= 30:
                # カイ二乗検定
                other_bets = total_bets - bets
                other_hits = total_hits - hits
                other_payout = total_payout - payout

                chi2, p_value = chi_square_test(
                    {'bets': bets, 'hits': hits},
                    {'bets': other_bets, 'hits': other_hits}
                )

                pattern = {
                    'condition': cond['name'],
                    'venue_code': venue_code,
                    'venue_name': venue_name,
                    'third_rate_band': band,
                    'bets': bets,
                    'hits': hits,
                    'roi': roi,
                    'roi_diff': roi_diff,
                    'profit': profit,
                    'black_years': black_years,
                    'total_years': total_years,
                    'chi2': chi2,
                    'p_value': p_value,
                    'type': 'exclude' if roi_diff < 0 else 'include',
                    'yearly': {str(y): dict(d) for y, d in data['yearly'].items()}
                }
                promising_patterns.append(pattern)

        all_results[cond['name']] = {
            'baseline': {'bets': total_bets, 'hits': total_hits, 'roi': baseline_roi},
            'by_venue_third_rate': {f"{v}_{b}": dict(d) for (v, b), d in results_c1.items()}
        }

    # 有望パターンのサマリー
    print("\n" + "=" * 100)
    print("有望パターンサマリー（サンプル50件以上、ROI差30pt以上）")
    print("=" * 100)

    # 除外候補
    exclude_patterns = [p for p in promising_patterns if p['type'] == 'exclude']
    include_patterns = [p for p in promising_patterns if p['type'] == 'include']

    print("\n【除外候補（ROIが平均より低い）】")
    if exclude_patterns:
        print(f"{'条件':<25} {'会場':<8} {'3連対率':<10} {'件数':>6} {'ROI':>7} {'差分':>8} {'黒字年':>6} {'p値':>10}")
        print("-" * 95)
        for p in sorted(exclude_patterns, key=lambda x: x['roi_diff']):
            p_str = f"{p['p_value']:.4f}" if p['p_value'] else "-"
            print(f"{p['condition']:<25} {p['venue_name']:<8} {p['third_rate_band']:<10} {p['bets']:>6} {p['roi']:>6.1f}% {p['roi_diff']:>+7.1f}pt {p['black_years']}/{p['total_years']}年 {p_str:>10}")
    else:
        print("  なし")

    print("\n【追加候補（ROIが平均より高い）】")
    if include_patterns:
        print(f"{'条件':<25} {'会場':<8} {'3連対率':<10} {'件数':>6} {'ROI':>7} {'差分':>8} {'黒字年':>6} {'p値':>10}")
        print("-" * 95)
        for p in sorted(include_patterns, key=lambda x: -x['roi_diff']):
            p_str = f"{p['p_value']:.4f}" if p['p_value'] else "-"
            print(f"{p['condition']:<25} {p['venue_name']:<8} {p['third_rate_band']:<10} {p['bets']:>6} {p['roi']:>6.1f}% {p['roi_diff']:>+7.1f}pt {p['black_years']}/{p['total_years']}年 {p_str:>10}")
    else:
        print("  なし")

    # 年度別安定性の詳細（有望パターン）
    print("\n" + "=" * 100)
    print("有望パターンの年度別詳細")
    print("=" * 100)

    for p in sorted(promising_patterns, key=lambda x: -abs(x['roi_diff'])):
        print(f"\n【{p['condition']} / {p['venue_name']} / {p['third_rate_band']}】")
        print(f"  全体: 件数={p['bets']}, ROI={p['roi']:.1f}%, 差分={p['roi_diff']:+.1f}pt, p値={'%.4f' % p['p_value'] if p['p_value'] else '-'}")
        print(f"  {'年':>6} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>10}")
        for year in sorted(p['yearly'].keys()):
            yd = p['yearly'][year]
            if yd['bets'] > 0:
                y_roi = 100.0 * yd['payout'] / (yd['bets'] * 100)
                y_profit = yd['payout'] - yd['bets'] * 100
                print(f"  {year:>6} {yd['bets']:>6} {yd['hits']:>4} {y_roi:>7.1f}% {y_profit:>+10,.0f}")

    conn.close()

    return all_results, promising_patterns


def analyze_pred2_third_rate():
    """2着予測選手の3連対率分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 100)
    print("2着予測選手の3連対率×会場 クロス分析")
    print("=" * 100)

    for cond in CONDITIONS[:4]:  # 主要条件のみ
        print(f"\n{'=' * 80}")
        print(f"条件: {cond['name']} - 2着予測選手の3連対率")
        print(f"{'=' * 80}")

        results = analyze_condition_by_venue_third_rate(cursor, cond, 2020, 2025, 'pred2')

        if not results:
            print("  データなし")
            continue

        # 3連対率帯別集計
        band_results = defaultdict(lambda: {'bets': 0, 'hits': 0, 'payout': 0})
        for (venue, band), data in results.items():
            band_results[band]['bets'] += data['bets']
            band_results[band]['hits'] += data['hits']
            band_results[band]['payout'] += data['payout']

        total_bets = sum(r['bets'] for r in band_results.values())
        total_payout = sum(r['payout'] for r in band_results.values())
        baseline_roi = 100.0 * total_payout / (total_bets * 100) if total_bets > 0 else 0

        print(f"\n【2着予測選手 3連対率帯別】ベースラインROI: {baseline_roi:.1f}%")
        print(f"{'3連対率帯':<12} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
        print("-" * 60)

        for band in ['0-40%', '40-50%', '50-60%', '60%+']:
            if band in band_results:
                bets = band_results[band]['bets']
                hits = band_results[band]['hits']
                payout = band_results[band]['payout']
                if bets > 0:
                    roi = 100.0 * payout / (bets * 100)
                    hit_rate = 100.0 * hits / bets
                    profit = payout - (bets * 100)
                    roi_diff = roi - baseline_roi
                    print(f"{band:<12} {bets:>8,} {hits:>6} {hit_rate:>7.2f}% {roi:>7.1f}% {profit:>+12,.0f}  ({roi_diff:>+.1f}pt)")

    conn.close()


if __name__ == '__main__':
    all_results, promising = analyze_all_conditions()
    analyze_pred2_third_rate()

    # 最終推奨
    print("\n" + "=" * 100)
    print("最終推奨")
    print("=" * 100)

    # 安定性の高い除外候補（4年以上連続赤字または黒字率50%以下）
    stable_exclude = [p for p in promising if p['type'] == 'exclude' and p['black_years'] <= p['total_years'] * 0.5 and p['bets'] >= 50]
    # 安定性の高い追加候補（4年以上連続黒字）
    stable_include = [p for p in promising if p['type'] == 'include' and p['black_years'] >= 4 and p['bets'] >= 50]

    print("\n【推奨: 除外条件】")
    if stable_exclude:
        for p in sorted(stable_exclude, key=lambda x: x['roi_diff']):
            significance = "有意" if p['p_value'] and p['p_value'] < 0.05 else "参考"
            p_val_str = f"{p['p_value']:.4f}" if p['p_value'] else '-'
            print(f"  - {p['condition']} で {p['venue_name']}×{p['third_rate_band']} を除外")
            print(f"    効果: ROI {p['roi_diff']:+.1f}pt改善見込み、件数 -{p['bets']}件")
            print(f"    根拠: 黒字{p['black_years']}/{p['total_years']}年、p値={p_val_str}({significance})")
    else:
        print("  なし（安定した除外候補が見つかりませんでした）")

    print("\n【推奨: 採用強化条件】")
    if stable_include:
        for p in sorted(stable_include, key=lambda x: -x['roi_diff']):
            significance = "有意" if p['p_value'] and p['p_value'] < 0.05 else "参考"
            p_val_str = f"{p['p_value']:.4f}" if p['p_value'] else '-'
            print(f"  - {p['condition']} で {p['venue_name']}×{p['third_rate_band']} を優先")
            print(f"    効果: ROI {p['roi_diff']:+.1f}pt、収益 {p['profit']:+,.0f}円")
            print(f"    根拠: 黒字{p['black_years']}/{p['total_years']}年、p値={p_val_str}({significance})")
    else:
        print("  なし（安定した追加候補が見つかりませんでした）")
