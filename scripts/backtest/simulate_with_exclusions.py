#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
除外ルール適用後のシミュレーション

採用候補の除外ルールを適用した場合の収支をシミュレート
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
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# 現在の購入条件 + 除外ルール
CONDITIONS = [
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None, 'motor_min': None,
     'exclusions': []},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'venue_filter': None, 'motor_min': None,
     'exclusions': []},
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40,
     'exclusions': []},
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None, 'motor_min': None,
     'exclusions': []},  # A2級を除外（条件から外す）
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
     'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8], 'motor_min': None,
     'exclusions': []},
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
     'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17], 'motor_min': None,
     'exclusions': []},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
     'venue_filter': [14], 'motor_min': None,
     'exclusions': []},
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None, 'motor_min': None,
     'exclusions': []},
    # D×30-60: 30-35倍帯を除外、9R除外、三国除外
    {'name': 'D×35-60', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 35, 'odds_max': 60, 'venue_filter': None, 'motor_min': None,
     'exclusions': [{'type': 'race', 'value': 9}, {'type': 'venue', 'value': 10}]},  # 30-35倍は条件自体で除外
]


def analyze_condition(cond, year_start, year_end):
    """条件別のROIを計算（除外ルール適用）"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"
    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    # 除外条件を構築
    exclusion_clauses = []
    for exc in cond.get('exclusions', []):
        if exc['type'] == 'race':
            exclusion_clauses.append(f"r.race_number != {exc['value']}")
        elif exc['type'] == 'venue':
            exclusion_clauses.append(f"r.venue_code != {exc['value']}")
        elif exc['type'] == 'rank':
            exclusion_clauses.append(f"e1.racer_rank != '{exc['value']}'")

    exclusion_clause = ""
    if exclusion_clauses:
        exclusion_clause = "AND " + " AND ".join(exclusion_clauses)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
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
        AND rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {motor_clause}
        {exclusion_clause}
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
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) as payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    '''
    cursor.execute(query)
    row = cursor.fetchone()
    bets, hits, payout = row
    if bets and bets > 0:
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        return {'name': cond['name'], 'bets': bets, 'hits': hits, 'roi': roi, 'profit': profit}
    return {'name': cond['name'], 'bets': 0, 'hits': 0, 'roi': 0, 'profit': 0}


def run_simulation(year):
    """シミュレーションを実行"""
    results = []
    total_bets = 0
    total_profit = 0

    for cond in CONDITIONS:
        result = analyze_condition(cond, year, year)
        results.append(result)
        total_bets += result['bets']
        total_profit += result['profit']

    total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100) if total_bets > 0 else 0

    return {
        'year': year,
        'conditions': results,
        'total': {
            'bets': total_bets,
            'roi': total_roi,
            'profit': total_profit
        }
    }


def main():
    print("=" * 100)
    print("除外ルール適用後のシミュレーション")
    print("=" * 100)
    print()

    print("【適用する除外ルール】")
    print("  1. D×30-60 → D×35-60 に変更（30-35倍帯を除外）")
    print("  2. D×35-60: 9R を除外")
    print("  3. D×35-60: 三国 を除外")
    print("  4. B×50-100: A2級を除外（A1/B1のみ）")
    print()

    # 年別結果
    print("=" * 100)
    print("【年別結果】")
    print("=" * 100)

    all_results = []
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        data = run_simulation(year)
        all_results.append(data)
        print(f"\n{year}年: {data['total']['bets']}件, ROI {data['total']['roi']:.1f}%, 収支 {data['total']['profit']:+,.0f}円")

    # 6年合計
    total_bets = sum(d['total']['bets'] for d in all_results)
    total_profit = sum(d['total']['profit'] for d in all_results)
    total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100) if total_bets > 0 else 0

    print(f"\n{'='*50}")
    print(f"6年合計: {total_bets}件, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円")

    # 2025年の詳細
    print("\n" + "=" * 100)
    print("【2025年 条件別詳細】")
    print("=" * 100)

    data_2025 = all_results[-1]
    print(f"\n{'条件':<25} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12}")
    print("-" * 60)
    for r in data_2025['conditions']:
        print(f"{r['name']:<25} {r['bets']:>6} {r['hits']:>4} {r['roi']:>7.1f}% {r['profit']:>+12,.0f}")
    print("-" * 60)
    print(f"{'合計':<25} {data_2025['total']['bets']:>6} {'-':>4} {data_2025['total']['roi']:>7.1f}% {data_2025['total']['profit']:>+12,.0f}")

    conn.close()


if __name__ == '__main__':
    main()
