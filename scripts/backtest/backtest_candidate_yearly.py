#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
採用候補パターンの年度別バックテスト

目的:
    有望パターンの年度別安定性を検証
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

# 採用候補パターン
CANDIDATES = [
    {'name': '鳴門×C×A2', 'confidence': 'C', 'c1_rank': ['A2'], 'venue': 14, 'odds_min': 10, 'odds_max': 100},
    {'name': '児島×B×A2', 'confidence': 'B', 'c1_rank': ['A2'], 'venue': 16, 'odds_min': 10, 'odds_max': 100},
    {'name': '児島×B×A1', 'confidence': 'B', 'c1_rank': ['A1'], 'venue': 16, 'odds_min': 10, 'odds_max': 100},
    {'name': '津×B×A1', 'confidence': 'B', 'c1_rank': ['A1'], 'venue': 9, 'odds_min': 10, 'odds_max': 100},
]


def analyze_pattern_yearly(cursor, pattern, year):
    """1年分のバックテスト"""
    c1_rank_str = "','".join(pattern['c1_rank'])
    venue_clause = f"AND r.venue_code = '{pattern['venue']:02d}'" if pattern.get('venue') else ""

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
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
        AND rp.confidence = '{pattern["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year}-01-01'
        AND r.race_date <= '{year}-12-31'
        {venue_clause}
    ),
    race_bets AS (
        SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
    ),
    race_with_odds AS (
        SELECT rb.*, COALESCE(t.odds, 0) as odds
        FROM race_bets rb
        LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
    ),
    race_with_payout AS (
        SELECT ro.*, COALESCE(p.amount, 0) as payout
        FROM race_with_odds ro
        LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
    )
    SELECT COUNT(*) as total, SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits, SUM(payout) as payout
    FROM race_with_payout
    WHERE odds >= {pattern['odds_min']} AND odds <= {pattern['odds_max']}
    '''

    cursor.execute(query)
    result = cursor.fetchone()
    total, hits, payout = result if result else (0, 0, 0)
    total = total or 0
    hits = hits or 0
    payout = payout or 0

    cost = total * 100
    roi = (payout / cost) * 100 if cost > 0 else 0
    return {'year': year, 'total': total, 'hits': hits, 'roi': roi, 'profit': payout - cost}


def main():
    print("=" * 80)
    print(" 採用候補パターン 年度別バックテスト")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    years = [2020, 2021, 2022, 2023, 2024, 2025]

    for pattern in CANDIDATES:
        print(f"\n{'='*60}")
        print(f" {pattern['name']}")
        print(f"{'='*60}")
        print(f"{'年度':>6} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>10} {'判定':<6}")
        print("-" * 50)

        yearly_results = []
        for year in years:
            result = analyze_pattern_yearly(cursor, pattern, year)
            yearly_results.append(result)

            status = "✅黒字" if result['roi'] >= 100 else "❌赤字"
            print(f"{result['year']:>6} {result['total']:>6} {result['hits']:>4} "
                  f"{result['roi']:>7.1f}% {result['profit']:>+10,.0f} {status}")

        # 集計
        total_bets = sum(r['total'] for r in yearly_results)
        total_hits = sum(r['hits'] for r in yearly_results)
        total_payout = sum(r['total'] * 100 + r['profit'] for r in yearly_results)
        total_cost = sum(r['total'] * 100 for r in yearly_results)
        total_roi = (total_payout / total_cost) * 100 if total_cost > 0 else 0
        total_profit = total_payout - total_cost
        positive_years = sum(1 for r in yearly_results if r['roi'] >= 100)

        print("-" * 50)
        print(f"{'合計':>6} {total_bets:>6} {total_hits:>4} {total_roi:>7.1f}% {total_profit:>+10,.0f}")
        print(f"黒字年数: {positive_years}/6年")

        # 採用判定
        print()
        if total_roi >= 150 and total_bets >= 100 and positive_years >= 4:
            print("★★★ 本番採用推奨 ★★★")
        elif total_roi >= 120 and total_bets >= 50 and positive_years >= 3:
            print("★★ 条件付き採用 ★★")
        elif total_roi >= 100:
            print("★ 参考パターン（継続監視）")
        else:
            print("✕ 不採用")

    conn.close()


if __name__ == "__main__":
    main()
