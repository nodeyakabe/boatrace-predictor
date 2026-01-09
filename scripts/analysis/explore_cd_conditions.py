#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
信頼度C,D向け新規購入条件探索スクリプト

目的:
    信頼度C,D向けの新規購入条件候補を発見する

探索軸:
    - 信頼度: C, D
    - オッズ帯: 20-30, 30-50, 50-100, 100+
    - 1コース級別: A1, A2, B1, B2
    - 会場: 全24会場
    - 追加条件: モーター2連率、2連対率、予測コース（1-6）

採用基準:
    1. 6年間（2020-2025）でROI 120%以上
    2. 直近4年で3年以上黒字
    3. サンプル数50件以上

使用方法:
    python scripts/analysis/explore_cd_conditions.py

作成日: 2026-01-08
"""
import sqlite3
import sys
import io
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from itertools import product
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# ============================================================
# 探索パラメータ
# ============================================================
CONFIDENCES = ['C', 'D']
ODDS_RANGES = [
    (10, 20),
    (20, 30),
    (30, 50),
    (50, 100),
    (100, 200),
]
C1_RANKS = ['A1', 'A2', 'B1', 'B2']
PREDICTED_COURSES = [1, 2, 3, 4, 5, 6]
# モーター2連率の閾値
MOTOR_THRESHOLDS = [None, 30, 35, 40]
# 1コース選手の2連対率範囲
SECOND_RATE_RANGES = [
    (None, None),  # 制限なし
    (20, 30),
    (30, 40),
    (40, 50),
]

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: 'びわこ', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


def build_exploration_query(
    confidence: str,
    c1_ranks: List[str],
    odds_min: float,
    odds_max: float,
    date_start: str,
    date_end: str,
    venue_code: Optional[int] = None,
    predicted_course: Optional[int] = None,
    motor_min: Optional[float] = None,
    c1_second_rate_min: Optional[float] = None,
    c1_second_rate_max: Optional[float] = None,
) -> str:
    """探索クエリを構築"""
    c1_rank_str = "','".join(c1_ranks)

    venue_clause = ""
    if venue_code is not None:
        venue_clause = f"AND r.venue_code = {venue_code}"

    predicted_course_clause = ""
    if predicted_course is not None:
        predicted_course_clause = f"AND rp1.pit_number = {predicted_course}"

    motor_clause = ""
    if motor_min is not None:
        motor_clause = f"AND e1.motor_second_rate >= {motor_min}"

    second_rate_clause = ""
    if c1_second_rate_min is not None:
        second_rate_clause += f"AND e1.second_rate >= {c1_second_rate_min} "
    if c1_second_rate_max is not None:
        second_rate_clause += f"AND e1.second_rate < {c1_second_rate_max} "

    # 1点買いクエリ（100円）
    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            rp.confidence,
            e1.racer_rank as c1_rank,
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
        AND rp.confidence = '{confidence}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{date_start}'
        AND r.race_date < '{date_end}'
        {venue_clause}
        {predicted_course_clause}
        {motor_clause}
        {second_rate_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            strftime('%Y', rb.race_date) as year,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    ),
    race_payouts AS (
        SELECT
            rb.*,
            CASE WHEN odds_123 >= {odds_min} AND odds_123 < {odds_max} THEN 100 ELSE 0 END as bet_amount,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                     AND odds_123 >= {odds_min} AND odds_123 < {odds_max}
                THEN odds_123 * 100 ELSE 0
            END as payout,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                     AND odds_123 >= {odds_min} AND odds_123 < {odds_max}
                THEN 1 ELSE 0
            END as is_hit
        FROM race_bets rb
    )
    SELECT
        year,
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(bet_amount) as investment,
        SUM(payout) as payout
    FROM race_payouts
    WHERE bet_amount > 0
    GROUP BY year
    ORDER BY year
    '''
    return query


def analyze_condition(
    cursor,
    confidence: str,
    c1_ranks: List[str],
    odds_min: float,
    odds_max: float,
    venue_code: Optional[int] = None,
    predicted_course: Optional[int] = None,
    motor_min: Optional[float] = None,
    c1_second_rate_min: Optional[float] = None,
    c1_second_rate_max: Optional[float] = None,
) -> Dict:
    """条件をバックテスト"""
    results = {
        'yearly': {},
        'total_bets': 0,
        'total_hits': 0,
        'total_investment': 0,
        'total_payout': 0,
    }

    query = build_exploration_query(
        confidence=confidence,
        c1_ranks=c1_ranks,
        odds_min=odds_min,
        odds_max=odds_max,
        date_start='2020-01-01',
        date_end='2026-01-01',
        venue_code=venue_code,
        predicted_course=predicted_course,
        motor_min=motor_min,
        c1_second_rate_min=c1_second_rate_min,
        c1_second_rate_max=c1_second_rate_max,
    )

    cursor.execute(query)
    rows = cursor.fetchall()

    for row in rows:
        year, bets, hits, investment, payout = row
        year = int(year)
        hits = hits or 0
        payout = payout or 0
        investment = investment or 0

        roi = 100.0 * payout / investment if investment > 0 else 0
        profit = payout - investment

        results['yearly'][year] = {
            'bets': bets,
            'hits': hits,
            'investment': investment,
            'payout': payout,
            'roi': roi,
            'profit': profit,
        }

        results['total_bets'] += bets
        results['total_hits'] += hits
        results['total_investment'] += investment
        results['total_payout'] += payout

    if results['total_investment'] > 0:
        results['total_roi'] = 100.0 * results['total_payout'] / results['total_investment']
        results['total_profit'] = results['total_payout'] - results['total_investment']
    else:
        results['total_roi'] = 0
        results['total_profit'] = 0

    return results


def check_adoption_criteria(result: Dict) -> Tuple[bool, str]:
    """採用基準をチェック"""
    # 基準1: 6年間でROI 120%以上
    if result['total_roi'] < 120:
        return False, f"ROI {result['total_roi']:.1f}% < 120%"

    # 基準2: サンプル数50件以上
    if result['total_bets'] < 50:
        return False, f"サンプル {result['total_bets']}件 < 50件"

    # 基準3: 直近4年で3年以上黒字（2022-2025）
    recent_years = [2022, 2023, 2024, 2025]
    black_count = 0
    for year in recent_years:
        if year in result['yearly']:
            if result['yearly'][year]['profit'] > 0:
                black_count += 1

    if black_count < 3:
        return False, f"直近4年黒字 {black_count}/4年 < 3年"

    return True, "採用基準を満たす"


def format_condition_name(
    confidence: str,
    c1_ranks: List[str],
    odds_min: float,
    odds_max: float,
    venue_code: Optional[int] = None,
    predicted_course: Optional[int] = None,
    motor_min: Optional[float] = None,
    c1_second_rate_min: Optional[float] = None,
    c1_second_rate_max: Optional[float] = None,
) -> str:
    """条件名を生成"""
    parts = [f'{confidence}']

    if len(c1_ranks) == 1:
        parts.append(c1_ranks[0])
    elif len(c1_ranks) < 4:
        parts.append('+'.join(c1_ranks))

    parts.append(f'{int(odds_min)}-{int(odds_max)}倍')

    if venue_code is not None:
        parts.insert(0, VENUE_NAMES.get(venue_code, f'会場{venue_code}'))

    if predicted_course is not None:
        parts.append(f'{predicted_course}コース予測')

    if motor_min is not None:
        parts.append(f'Motor{int(motor_min)}%+')

    if c1_second_rate_min is not None or c1_second_rate_max is not None:
        rate_str = '2連率'
        if c1_second_rate_min is not None:
            rate_str += f'{int(c1_second_rate_min)}'
        rate_str += '-'
        if c1_second_rate_max is not None:
            rate_str += f'{int(c1_second_rate_max)}'
        rate_str += '%'
        parts.append(rate_str)

    return '×'.join(parts)


def explore_conditions():
    """条件を網羅的に探索"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    adopted_conditions = []
    all_conditions = []

    print("=" * 100)
    print("信頼度C,D向け新規購入条件探索")
    print("=" * 100)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ============================================================
    # Phase 1: 基本条件の探索（信頼度×級別×オッズ帯）
    # ============================================================
    print("Phase 1: 基本条件探索（信頼度×級別×オッズ帯）")
    print("-" * 80)

    for confidence in CONFIDENCES:
        for c1_rank in C1_RANKS:
            for odds_min, odds_max in ODDS_RANGES:
                result = analyze_condition(
                    cursor,
                    confidence=confidence,
                    c1_ranks=[c1_rank],
                    odds_min=odds_min,
                    odds_max=odds_max,
                )

                if result['total_bets'] == 0:
                    continue

                condition_name = format_condition_name(
                    confidence, [c1_rank], odds_min, odds_max
                )

                passed, reason = check_adoption_criteria(result)

                condition_data = {
                    'name': condition_name,
                    'confidence': confidence,
                    'c1_ranks': [c1_rank],
                    'odds_min': odds_min,
                    'odds_max': odds_max,
                    'result': result,
                    'passed': passed,
                    'reason': reason,
                }

                all_conditions.append(condition_data)

                if passed:
                    adopted_conditions.append(condition_data)
                    print(f"[PASS] {condition_name}")
                    print(f"       件数: {result['total_bets']}, ROI: {result['total_roi']:.1f}%, 収支: {result['total_profit']:+,.0f}円")

    # ============================================================
    # Phase 2: 予測コース条件の探索
    # ============================================================
    print()
    print("Phase 2: 予測コース条件探索")
    print("-" * 80)

    for confidence in CONFIDENCES:
        for predicted_course in PREDICTED_COURSES:
            for odds_min, odds_max in ODDS_RANGES:
                result = analyze_condition(
                    cursor,
                    confidence=confidence,
                    c1_ranks=C1_RANKS,  # 全級別
                    odds_min=odds_min,
                    odds_max=odds_max,
                    predicted_course=predicted_course,
                )

                if result['total_bets'] == 0:
                    continue

                condition_name = format_condition_name(
                    confidence, C1_RANKS, odds_min, odds_max,
                    predicted_course=predicted_course
                )

                passed, reason = check_adoption_criteria(result)

                condition_data = {
                    'name': condition_name,
                    'confidence': confidence,
                    'c1_ranks': C1_RANKS,
                    'odds_min': odds_min,
                    'odds_max': odds_max,
                    'predicted_course': predicted_course,
                    'result': result,
                    'passed': passed,
                    'reason': reason,
                }

                all_conditions.append(condition_data)

                if passed:
                    adopted_conditions.append(condition_data)
                    print(f"[PASS] {condition_name}")
                    print(f"       件数: {result['total_bets']}, ROI: {result['total_roi']:.1f}%, 収支: {result['total_profit']:+,.0f}円")

    # ============================================================
    # Phase 3: モーター条件の探索
    # ============================================================
    print()
    print("Phase 3: モーター条件探索")
    print("-" * 80)

    for confidence in CONFIDENCES:
        for c1_rank in C1_RANKS:
            for motor_min in [30, 35, 40]:
                for odds_min, odds_max in ODDS_RANGES:
                    result = analyze_condition(
                        cursor,
                        confidence=confidence,
                        c1_ranks=[c1_rank],
                        odds_min=odds_min,
                        odds_max=odds_max,
                        motor_min=motor_min,
                    )

                    if result['total_bets'] == 0:
                        continue

                    condition_name = format_condition_name(
                        confidence, [c1_rank], odds_min, odds_max,
                        motor_min=motor_min
                    )

                    passed, reason = check_adoption_criteria(result)

                    condition_data = {
                        'name': condition_name,
                        'confidence': confidence,
                        'c1_ranks': [c1_rank],
                        'odds_min': odds_min,
                        'odds_max': odds_max,
                        'motor_min': motor_min,
                        'result': result,
                        'passed': passed,
                        'reason': reason,
                    }

                    all_conditions.append(condition_data)

                    if passed:
                        adopted_conditions.append(condition_data)
                        print(f"[PASS] {condition_name}")
                        print(f"       件数: {result['total_bets']}, ROI: {result['total_roi']:.1f}%, 収支: {result['total_profit']:+,.0f}円")

    # ============================================================
    # Phase 4: 2連対率条件の探索
    # ============================================================
    print()
    print("Phase 4: 2連対率条件探索")
    print("-" * 80)

    for confidence in CONFIDENCES:
        for c1_rank in C1_RANKS:
            for rate_min, rate_max in [(20, 30), (30, 40), (40, 50), (50, 60)]:
                for odds_min, odds_max in ODDS_RANGES:
                    result = analyze_condition(
                        cursor,
                        confidence=confidence,
                        c1_ranks=[c1_rank],
                        odds_min=odds_min,
                        odds_max=odds_max,
                        c1_second_rate_min=rate_min,
                        c1_second_rate_max=rate_max,
                    )

                    if result['total_bets'] == 0:
                        continue

                    condition_name = format_condition_name(
                        confidence, [c1_rank], odds_min, odds_max,
                        c1_second_rate_min=rate_min,
                        c1_second_rate_max=rate_max
                    )

                    passed, reason = check_adoption_criteria(result)

                    condition_data = {
                        'name': condition_name,
                        'confidence': confidence,
                        'c1_ranks': [c1_rank],
                        'odds_min': odds_min,
                        'odds_max': odds_max,
                        'c1_second_rate_min': rate_min,
                        'c1_second_rate_max': rate_max,
                        'result': result,
                        'passed': passed,
                        'reason': reason,
                    }

                    all_conditions.append(condition_data)

                    if passed:
                        adopted_conditions.append(condition_data)
                        print(f"[PASS] {condition_name}")
                        print(f"       件数: {result['total_bets']}, ROI: {result['total_roi']:.1f}%, 収支: {result['total_profit']:+,.0f}円")

    # ============================================================
    # Phase 5: 会場別条件の探索（上位条件のみ）
    # ============================================================
    print()
    print("Phase 5: 会場別条件探索")
    print("-" * 80)

    for confidence in CONFIDENCES:
        for c1_rank in C1_RANKS:
            for odds_min, odds_max in ODDS_RANGES:
                for venue_code in range(1, 25):
                    result = analyze_condition(
                        cursor,
                        confidence=confidence,
                        c1_ranks=[c1_rank],
                        odds_min=odds_min,
                        odds_max=odds_max,
                        venue_code=venue_code,
                    )

                    if result['total_bets'] == 0:
                        continue

                    condition_name = format_condition_name(
                        confidence, [c1_rank], odds_min, odds_max,
                        venue_code=venue_code
                    )

                    passed, reason = check_adoption_criteria(result)

                    condition_data = {
                        'name': condition_name,
                        'confidence': confidence,
                        'c1_ranks': [c1_rank],
                        'odds_min': odds_min,
                        'odds_max': odds_max,
                        'venue_code': venue_code,
                        'result': result,
                        'passed': passed,
                        'reason': reason,
                    }

                    all_conditions.append(condition_data)

                    if passed:
                        adopted_conditions.append(condition_data)
                        print(f"[PASS] {condition_name}")
                        print(f"       件数: {result['total_bets']}, ROI: {result['total_roi']:.1f}%, 収支: {result['total_profit']:+,.0f}円")

    conn.close()

    # ============================================================
    # 結果サマリー
    # ============================================================
    print()
    print("=" * 100)
    print("採用候補一覧")
    print("=" * 100)

    # ROI順にソート
    adopted_conditions.sort(key=lambda x: x['result']['total_roi'], reverse=True)

    print(f"{'No':<4} {'条件名':<40} {'件数':>8} {'ROI':>8} {'収支':>14} {'直近4年黒字'}")
    print("-" * 100)

    for i, cond in enumerate(adopted_conditions, 1):
        result = cond['result']

        # 直近4年の黒字年数
        recent_years = [2022, 2023, 2024, 2025]
        black_years = []
        for year in recent_years:
            if year in result['yearly'] and result['yearly'][year]['profit'] > 0:
                black_years.append(str(year)[-2:])

        black_str = ','.join(black_years) if black_years else '-'

        print(f"{i:<4} {cond['name']:<40} {result['total_bets']:>8} {result['total_roi']:>7.1f}% {result['total_profit']:>+14,.0f} {len(black_years)}/4年({black_str})")

    print("-" * 100)
    print(f"合計: {len(adopted_conditions)}件の候補")

    # ============================================================
    # 上位候補の詳細
    # ============================================================
    print()
    print("=" * 100)
    print("上位候補の年度別詳細（ROI上位20件）")
    print("=" * 100)

    for i, cond in enumerate(adopted_conditions[:20], 1):
        result = cond['result']
        print(f"\n{i}. {cond['name']}")
        print(f"   6年間: {result['total_bets']}件, ROI {result['total_roi']:.1f}%, 収支 {result['total_profit']:+,.0f}円")

        yearly_str = []
        for year in YEARS:
            if year in result['yearly']:
                y = result['yearly'][year]
                mark = "+" if y['profit'] > 0 else "-"
                yearly_str.append(f"{year}: {mark}{abs(y['profit']):,.0f}円")
        print(f"   年度別: {', '.join(yearly_str)}")

    return adopted_conditions


if __name__ == '__main__':
    explore_conditions()
