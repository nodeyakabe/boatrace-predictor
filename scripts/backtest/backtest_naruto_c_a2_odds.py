#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
鳴門×C×A2のオッズ帯別バックテスト

目的:
    最も有望な「鳴門×C×A2」パターンの最適オッズ帯を特定
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


def analyze_odds_range(cursor, odds_min, odds_max, venue=14):
    """オッズ帯別のバックテスト"""
    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.race_date,
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
        AND rp.confidence = 'C'
        AND e1.racer_rank = 'A2'
        AND r.venue_code = '{venue:02d}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
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
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
        SUM(payout) as payout,
        AVG(odds) as avg_odds
    FROM race_with_payout
    WHERE odds >= {odds_min} AND odds < {odds_max}
    '''

    cursor.execute(query)
    result = cursor.fetchone()
    total, hits, payout, avg_odds = result if result else (0, 0, 0, 0)
    total = total or 0
    hits = hits or 0
    payout = payout or 0
    avg_odds = avg_odds or 0

    cost = total * 100
    roi = (payout / cost) * 100 if cost > 0 else 0
    return {
        'odds_min': odds_min,
        'odds_max': odds_max,
        'total': total,
        'hits': hits,
        'roi': roi,
        'profit': payout - cost,
        'avg_odds': avg_odds
    }


def main():
    print("=" * 70)
    print(" 鳴門 × 信頼度C × A2 オッズ帯別バックテスト")
    print("=" * 70)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # オッズ帯を細かく分析
    odds_ranges = [
        (10, 20),
        (20, 30),
        (30, 40),
        (40, 50),
        (50, 60),
        (60, 80),
        (80, 100),
        (100, 200),
    ]

    print(f"{'オッズ帯':<12} {'件数':>6} {'的中':>4} {'平均オッズ':>8} {'ROI':>8} {'収支':>10}")
    print("-" * 60)

    for odds_min, odds_max in odds_ranges:
        result = analyze_odds_range(cursor, odds_min, odds_max)
        status = "★" if result['roi'] >= 150 else ("◎" if result['roi'] >= 100 else " ")
        print(f"{odds_min:>3}-{odds_max:<3}倍     {result['total']:>6} {result['hits']:>4} "
              f"{result['avg_odds']:>7.1f}x {result['roi']:>7.1f}% {result['profit']:>+10,.0f} {status}")

    print()
    print("=" * 70)
    print(" 複合オッズ帯分析")
    print("=" * 70)

    combo_ranges = [
        (20, 50),
        (30, 60),
        (40, 80),
        (50, 100),
        (30, 80),
        (20, 60),
    ]

    print(f"{'オッズ帯':<12} {'件数':>6} {'的中':>4} {'平均オッズ':>8} {'ROI':>8} {'収支':>10}")
    print("-" * 60)

    for odds_min, odds_max in combo_ranges:
        result = analyze_odds_range(cursor, odds_min, odds_max)
        status = "★" if result['roi'] >= 150 else ("◎" if result['roi'] >= 100 else " ")
        print(f"{odds_min:>3}-{odds_max:<3}倍     {result['total']:>6} {result['hits']:>4} "
              f"{result['avg_odds']:>7.1f}x {result['roi']:>7.1f}% {result['profit']:>+10,.0f} {status}")

    # 年度別の安定性も確認
    print()
    print("=" * 70)
    print(" 最有望オッズ帯 (30-60倍) 年度別安定性")
    print("=" * 70)

    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
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
            AND rp.confidence = 'C'
            AND e1.racer_rank = 'A2'
            AND r.venue_code = '14'
            AND r.race_date >= '{year}-01-01'
            AND r.race_date <= '{year}-12-31'
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
        SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout)
        FROM race_with_payout
        WHERE odds >= 30 AND odds < 60
        '''
        cursor.execute(query)
        result = cursor.fetchone()
        total, hits, payout = result if result else (0, 0, 0)
        total = total or 0
        hits = hits or 0
        payout = payout or 0
        cost = total * 100
        roi = (payout / cost) * 100 if cost > 0 else 0
        profit = payout - cost
        status = "✅" if roi >= 100 else "❌"
        print(f"  {year}年: {total:>3}件, {hits}的中, ROI {roi:>6.1f}%, 収支 {profit:>+8,.0f}円 {status}")

    conn.close()


if __name__ == "__main__":
    main()
