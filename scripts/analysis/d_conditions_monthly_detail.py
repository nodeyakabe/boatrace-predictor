#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
D条件2件の月別詳細分析

目的:
    標準バックテストのD条件2件（D×40-50×B1、D×5コース予測）の
    月別ROI・収支を個別に算出

使用方法:
    python scripts/analysis/d_conditions_monthly_detail.py

出力:
    1. D×40-50×B1の月別詳細
    2. D×5コース予測の月別詳細
    3. 2月・4月の合計収支分析
"""

import sqlite3
import sys
import io
from pathlib import Path
from typing import Dict, List

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_PATH = PROJECT_ROOT / 'data' / 'boatrace.db'


def analyze_d_40_50_monthly(cursor) -> List[Dict]:
    """
    D×40-50×B1×2連率20-30%の月別分析
    """

    query = """
    WITH prediction_base AS (
        SELECT
            rp.race_id,
            CAST(strftime('%m', r.race_date) AS INTEGER) as month,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp
        JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp.race_id = r.id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
          AND rp.confidence = 'D'
          AND e1.racer_rank = 'B1'
          AND e1.second_rate >= 20 AND e1.second_rate < 30
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_results AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    bet_races AS (
        SELECT
            pb.month,
            pb.year,
            pb.race_id,
            pb.pred_combo,
            ar.actual_combo,
            t.odds,
            CASE WHEN pb.pred_combo = ar.actual_combo THEN 1 ELSE 0 END as is_hit
        FROM prediction_base pb
        JOIN actual_results ar ON pb.race_id = ar.race_id
        LEFT JOIN trifecta_odds t ON pb.race_id = t.race_id
            AND t.combination = pb.pred_combo
        WHERE t.odds IS NOT NULL
          AND t.odds >= 40 AND t.odds < 50
    )
    SELECT
        month,
        COUNT(*) as races,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(odds), 1) as avg_odds,
        SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) as payout,
        COUNT(*) * 100 as investment,
        ROUND(100.0 * SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 1) as roi,
        SUM(CASE WHEN is_hit = 1 THEN odds * 100 ELSE 0 END) - (COUNT(*) * 100) as profit
    FROM bet_races
    GROUP BY month
    ORDER BY month
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            'month': row[0],
            'races': row[1],
            'hits': row[2],
            'hit_rate': row[3],
            'avg_odds': row[4],
            'payout': row[5],
            'investment': row[6],
            'roi': row[7],
            'profit': row[8],
        })

    return results


def analyze_d_course5_monthly(cursor) -> List[Dict]:
    """
    D×5コース予測×A2除外+会場最適化の月別分析（パターンH: 3点買い）
    """

    query = """
    WITH prediction_base AS (
        SELECT
            rp.race_id,
            CAST(strftime('%m', r.race_date) AS INTEGER) as month,
            CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            rp4.pit_number as p4,
            rp5.pit_number as p5,
            CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT) as combo_123,
            CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT) as combo_124,
            CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp5.pit_number AS TEXT) as combo_125
        FROM race_predictions rp
        JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN race_predictions rp4 ON rp.race_id = rp4.race_id
            AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON rp.race_id = rp5.race_id
            AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN races r ON rp.race_id = r.id
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.prediction_type = 'before'
          AND rp.rank_prediction = 1
          AND rp.confidence = 'D'
          AND rp1.pit_number = 5
          AND e1.racer_rank IN ('A1', 'B1', 'B2')
          AND r.venue_code IN ('05', '06', '01', '04')
          AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_results AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    bet_races AS (
        SELECT
            pb.month,
            pb.year,
            pb.race_id,
            ar.actual_combo,
            COALESCE((SELECT odds FROM trifecta_odds WHERE race_id = pb.race_id AND combination = pb.combo_123), 0) as odds_123,
            COALESCE((SELECT odds FROM trifecta_odds WHERE race_id = pb.race_id AND combination = pb.combo_124), 0) as odds_124,
            COALESCE((SELECT odds FROM trifecta_odds WHERE race_id = pb.race_id AND combination = pb.combo_125), 0) as odds_125,
            pb.combo_123,
            pb.combo_124,
            pb.combo_125
        FROM prediction_base pb
        JOIN actual_results ar ON pb.race_id = ar.race_id
    ),
    race_payouts AS (
        SELECT
            month,
            year,
            race_id,
            CASE WHEN odds_123 >= 10 AND odds_123 < 200 THEN 200 ELSE 0 END as bet_123,
            CASE WHEN odds_124 >= 10 AND odds_124 < 200 THEN 100 ELSE 0 END as bet_124,
            CASE WHEN odds_125 >= 10 AND odds_125 < 200 THEN 100 ELSE 0 END as bet_125,
            CASE WHEN actual_combo = combo_123 AND odds_123 >= 10 AND odds_123 < 200 THEN odds_123 * 200 ELSE 0 END as payout_123,
            CASE WHEN actual_combo = combo_124 AND odds_124 >= 10 AND odds_124 < 200 THEN odds_124 * 100 ELSE 0 END as payout_124,
            CASE WHEN actual_combo = combo_125 AND odds_125 >= 10 AND odds_125 < 200 THEN odds_125 * 100 ELSE 0 END as payout_125,
            CASE WHEN (actual_combo = combo_123 AND odds_123 >= 10 AND odds_123 < 200)
                   OR (actual_combo = combo_124 AND odds_124 >= 10 AND odds_124 < 200)
                   OR (actual_combo = combo_125 AND odds_125 >= 10 AND odds_125 < 200)
                 THEN 1 ELSE 0 END as is_hit
        FROM bet_races
        WHERE odds_123 > 0 OR odds_124 > 0 OR odds_125 > 0
    )
    SELECT
        month,
        COUNT(*) as races,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        SUM(bet_123 + bet_124 + bet_125) as investment,
        SUM(payout_123 + payout_124 + payout_125) as payout,
        ROUND(100.0 * SUM(payout_123 + payout_124 + payout_125) / NULLIF(SUM(bet_123 + bet_124 + bet_125), 0), 1) as roi,
        SUM(payout_123 + payout_124 + payout_125) - SUM(bet_123 + bet_124 + bet_125) as profit
    FROM race_payouts
    WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
    GROUP BY month
    ORDER BY month
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            'month': row[0],
            'races': row[1],
            'hits': row[2],
            'hit_rate': row[3],
            'investment': row[4],
            'payout': row[5],
            'roi': row[6],
            'profit': row[7],
        })

    return results


def print_results(d40_50_data: List[Dict], d_course5_data: List[Dict]):
    """
    分析結果を表示
    """

    print("=" * 100)
    print("D条件2件の月別詳細分析")
    print("=" * 100)
    print()
    print("分析期間: 2020-2025年（6年間）")
    print()

    # ============================================================
    # 1. D×40-50×B1の月別詳細
    # ============================================================
    print("[1. D×40-50×B1×2連率20-30%の月別詳細]")
    print("-" * 80)
    print(f"{'月':<4} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12} {'評価':<10}")
    print("-" * 80)

    d40_50_total = {'races': 0, 'hits': 0, 'investment': 0, 'payout': 0, 'profit': 0}
    d40_50_feb_apr = {'races': 0, 'profit': 0}

    for data in d40_50_data:
        # 評価
        if data['roi'] >= 150:
            eval_str = '[良好]'
        elif data['roi'] >= 100:
            eval_str = '[普通]'
        else:
            eval_str = '[不調]'

        # 2月・4月をハイライト
        month_str = f"{data['month']:>2}月"
        if data['month'] in [2, 4]:
            month_str += " [注目]"
            d40_50_feb_apr['races'] += data['races']
            d40_50_feb_apr['profit'] += data['profit']
        else:
            month_str += "      "

        print(f"{month_str:<10} {data['races']:>6} {data['hits']:>4} {data['hit_rate']:>6.1f}% {data['roi']:>7.0f}% {data['profit']:>+11,.0f}円 {eval_str:<10}")

        d40_50_total['races'] += data['races']
        d40_50_total['hits'] += data['hits']
        d40_50_total['investment'] += data['investment']
        d40_50_total['payout'] += data['payout']
        d40_50_total['profit'] += data['profit']

    print("-" * 80)
    total_roi = (d40_50_total['payout'] / d40_50_total['investment'] * 100) if d40_50_total['investment'] > 0 else 0
    total_hit_rate = (d40_50_total['hits'] / d40_50_total['races'] * 100) if d40_50_total['races'] > 0 else 0
    print(f"{'合計':<10} {d40_50_total['races']:>6} {d40_50_total['hits']:>4} {total_hit_rate:>6.1f}% {total_roi:>7.0f}% {d40_50_total['profit']:>+11,.0f}円")
    print()
    print(f"2月・4月合計: {d40_50_feb_apr['races']}件, 収支 {d40_50_feb_apr['profit']:+,.0f}円")
    print()

    # ============================================================
    # 2. D×5コース予測の月別詳細
    # ============================================================
    print("[2. D×5コース予測×A2除外+会場最適化の月別詳細]")
    print("-" * 80)
    print(f"{'月':<4} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>12} {'評価':<10}")
    print("-" * 80)

    d_course5_total = {'races': 0, 'hits': 0, 'investment': 0, 'payout': 0, 'profit': 0}
    d_course5_feb_apr = {'races': 0, 'profit': 0}

    for data in d_course5_data:
        # 評価
        if data['roi'] >= 150:
            eval_str = '[良好]'
        elif data['roi'] >= 100:
            eval_str = '[普通]'
        else:
            eval_str = '[不調]'

        # 2月・4月をハイライト
        month_str = f"{data['month']:>2}月"
        if data['month'] in [2, 4]:
            month_str += " [注目]"
            d_course5_feb_apr['races'] += data['races']
            d_course5_feb_apr['profit'] += data['profit']
        else:
            month_str += "      "

        print(f"{month_str:<10} {data['races']:>6} {data['hits']:>4} {data['hit_rate']:>6.1f}% {data['roi']:>7.0f}% {data['profit']:>+11,.0f}円 {eval_str:<10}")

        d_course5_total['races'] += data['races']
        d_course5_total['hits'] += data['hits']
        d_course5_total['investment'] += data['investment']
        d_course5_total['payout'] += data['payout']
        d_course5_total['profit'] += data['profit']

    print("-" * 80)
    total_roi = (d_course5_total['payout'] / d_course5_total['investment'] * 100) if d_course5_total['investment'] > 0 else 0
    total_hit_rate = (d_course5_total['hits'] / d_course5_total['races'] * 100) if d_course5_total['races'] > 0 else 0
    print(f"{'合計':<10} {d_course5_total['races']:>6} {d_course5_total['hits']:>4} {total_hit_rate:>6.1f}% {total_roi:>7.0f}% {d_course5_total['profit']:>+11,.0f}円")
    print()
    print(f"2月・4月合計: {d_course5_feb_apr['races']}件, 収支 {d_course5_feb_apr['profit']:+,.0f}円")
    print()

    # ============================================================
    # 3. 失敗原因の分析
    # ============================================================
    print("[3. 失敗原因の分析]")
    print("-" * 100)

    print(f"D×40-50×B1の2月・4月合計収支: {d40_50_feb_apr['profit']:+,.0f}円")
    if d40_50_feb_apr['profit'] < 0:
        print(f"  -> 赤字条件のため、除外は正しい判断")
    else:
        print(f"  -> 黒字条件を除外したため、慎重な判断が必要")

    print()
    print(f"D×5コース予測の2月・4月合計収支: {d_course5_feb_apr['profit']:+,.0f}円")
    if d_course5_feb_apr['profit'] > 0:
        print(f"  -> 黒字条件を除外したため、ROI悪化の原因")
    else:
        print(f"  -> 赤字条件のため、除外は正しい判断")

    print()
    total_feb_apr_profit = d40_50_feb_apr['profit'] + d_course5_feb_apr['profit']
    print(f"【結論】2月・4月の合計収支: {total_feb_apr_profit:+,.0f}円")

    if total_feb_apr_profit > 0:
        print(f"  -> 全体では黒字のため、除外は不適切")
    elif total_feb_apr_profit < -10000:
        print(f"  -> 大赤字のため、除外を検討すべき")
    else:
        print(f"  -> 微赤字のため、判断は微妙")

    print()
    print("=" * 100)


def main():
    """メイン処理"""

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()

    print("D条件2件の月別詳細分析を実行中...")
    print()

    # 分析実行
    d40_50_data = analyze_d_40_50_monthly(cursor)
    d_course5_data = analyze_d_course5_monthly(cursor)

    # 結果表示
    print_results(d40_50_data, d_course5_data)

    conn.close()


if __name__ == '__main__':
    main()
