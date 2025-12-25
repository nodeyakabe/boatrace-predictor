#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新規パターンのバックテスト検証スクリプト

目的:
    スコア100点の候補パターンを、before予測データを使った
    バックテスト（1-2-3全的中）で検証する

使用方法:
    python scripts/backtest/backtest_new_patterns.py
    python scripts/backtest/backtest_new_patterns.py --year 2025

重要:
    - 6年間データ分析のROIは「1着予測が1着」での計算
    - バックテストのROIは「1-2-3全的中（3連単）」での計算
    - 両者は大きく異なる可能性がある
"""
import sqlite3
import sys
import io
import os
import json
import argparse
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

VENUE_CODES = {v: k for k, v in VENUE_NAMES.items()}

# ============================================================
# 検証対象の新規パターン（スコア100点から選定）
# ============================================================
NEW_PATTERNS = [
    # 信頼度C × A2 × 会場限定（最有望グループ）
    {'name': '福岡×C×A2', 'confidence': 'C', 'c1_rank': ['A2'], 'venue': 22, 'odds_min': 10, 'odds_max': 100},
    {'name': '鳴門×C×A2', 'confidence': 'C', 'c1_rank': ['A2'], 'venue': 14, 'odds_min': 10, 'odds_max': 100},
    {'name': '桐生×C×A2', 'confidence': 'C', 'c1_rank': ['A2'], 'venue': 1, 'odds_min': 10, 'odds_max': 100},

    # 信頼度A × A1 × 会場限定
    {'name': '児島×A×A1', 'confidence': 'A', 'c1_rank': ['A1'], 'venue': 16, 'odds_min': 10, 'odds_max': 100},

    # 信頼度B × A2 × 会場限定
    {'name': '宮島×B×A2', 'confidence': 'B', 'c1_rank': ['A2'], 'venue': 17, 'odds_min': 10, 'odds_max': 100},
    {'name': '児島×B×A2', 'confidence': 'B', 'c1_rank': ['A2'], 'venue': 16, 'odds_min': 10, 'odds_max': 100},
    {'name': '唐津×B×A2', 'confidence': 'B', 'c1_rank': ['A2'], 'venue': 23, 'odds_min': 10, 'odds_max': 100},

    # 信頼度B × A1 × 会場限定
    {'name': '津×B×A1', 'confidence': 'B', 'c1_rank': ['A1'], 'venue': 9, 'odds_min': 10, 'odds_max': 100},
    {'name': '児島×B×A1', 'confidence': 'B', 'c1_rank': ['A1'], 'venue': 16, 'odds_min': 10, 'odds_max': 100},

    # 信頼度C × A1 × 会場限定
    {'name': '唐津×C×A1', 'confidence': 'C', 'c1_rank': ['A1'], 'venue': 23, 'odds_min': 10, 'odds_max': 100},

    # 全会場 × モーター条件（既存と重複しないもの）
    {'name': '全会場×C×A1×モーター40%+', 'confidence': 'C', 'c1_rank': ['A1'], 'venue': None, 'motor_min': 40, 'odds_min': 10, 'odds_max': 100},
    {'name': '全会場×C×A2×モーター40%+', 'confidence': 'C', 'c1_rank': ['A2'], 'venue': None, 'motor_min': 40, 'odds_min': 10, 'odds_max': 100},
]


def analyze_pattern(cursor, pattern, year_start, year_end):
    """パターンのバックテスト結果を計算"""
    c1_rank_str = "','".join(pattern['c1_rank'])
    venue_clause = ""
    motor_clause = ""

    if pattern.get('venue'):
        venue_clause = f"AND r.venue_code = '{pattern['venue']:02d}'"

    if pattern.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {pattern['motor_min']}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            rp.confidence,
            e1.racer_rank as c1_rank,
            e1.motor_second_rate,
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
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date <= '{year_end}-12-31'
        {venue_clause}
        {motor_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination
        FROM race_base rb
    ),
    race_with_odds AS (
        SELECT
            rb.*,
            COALESCE(t.odds, 0) as odds
        FROM race_bets rb
        LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
    ),
    race_with_payout AS (
        SELECT
            ro.*,
            COALESCE(p.amount, 0) as payout
        FROM race_with_odds ro
        LEFT JOIN payouts p ON ro.race_id = p.race_id
            AND p.bet_type = 'trifecta'
            AND p.combination = ro.combination
    )
    SELECT
        COUNT(*) as total_bets,
        SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
        SUM(payout) as total_payout,
        AVG(odds) as avg_odds
    FROM race_with_payout
    WHERE odds >= {pattern['odds_min']} AND odds <= {pattern['odds_max']}
    '''

    cursor.execute(query)
    result = cursor.fetchone()

    if result:
        total_bets, hits, total_payout, avg_odds = result
        total_bets = total_bets or 0
        hits = hits or 0
        total_payout = total_payout or 0
        avg_odds = avg_odds or 0

        if total_bets > 0:
            cost = total_bets * 100
            roi = (total_payout / cost) * 100 if cost > 0 else 0
            hit_rate = (hits / total_bets) * 100
            profit = total_payout - cost
            return {
                'total_bets': total_bets,
                'hits': hits,
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': profit,
                'avg_odds': avg_odds,
            }

    return {'total_bets': 0, 'hits': 0, 'hit_rate': 0, 'roi': 0, 'profit': 0, 'avg_odds': 0}


def main():
    parser = argparse.ArgumentParser(description='新規パターンのバックテスト検証')
    parser.add_argument('--year', type=int, default=2025, help='検証対象年（デフォルト: 2025）')
    parser.add_argument('--all-years', action='store_true', help='2020-2025年全体で検証')
    args = parser.parse_args()

    print("=" * 70)
    print(" 新規パターン バックテスト検証")
    print("=" * 70)
    print()
    print("【重要】")
    print("- 6年間データ分析: 「1着予測が1着になった」を的中と定義")
    print("- このバックテスト: 「1-2-3全的中（3連単）」を的中と定義")
    print("- 両者のROIは大きく異なる可能性があります")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if args.all_years:
        year_start = 2020
        year_end = 2025
        print(f"検証期間: {year_start}年 〜 {year_end}年")
    else:
        year_start = args.year
        year_end = args.year
        print(f"検証対象年: {args.year}年")

    print()
    print("-" * 70)
    print(f"{'条件':<30} {'件数':>6} {'的中':>4} {'的中率':>7} {'ROI':>8} {'収支':>10}")
    print("-" * 70)

    results = []

    for pattern in NEW_PATTERNS:
        result = analyze_pattern(cursor, pattern, year_start, year_end)
        results.append({
            'name': pattern['name'],
            **result
        })

        print(f"{pattern['name']:<30} {result['total_bets']:>6} {result['hits']:>4} "
              f"{result['hit_rate']:>6.1f}% {result['roi']:>7.1f}% {result['profit']:>+10,.0f}")

    print("-" * 70)

    # ROI 150%以上、サンプル50件以上のパターンを抽出
    print()
    print("=" * 70)
    print(" 採用候補（ROI 150%以上 & サンプル50件以上）")
    print("=" * 70)

    candidates = [r for r in results if r['roi'] >= 150 and r['total_bets'] >= 50]

    if candidates:
        for r in sorted(candidates, key=lambda x: x['roi'], reverse=True):
            print(f"  ★ {r['name']}: ROI {r['roi']:.1f}%, {r['total_bets']}件, 収支 {r['profit']:+,.0f}円")
    else:
        print("  該当なし")

    # 既存条件への追加が有望なパターン
    print()
    print("=" * 70)
    print(" 黒字パターン（ROI 100%以上）")
    print("=" * 70)

    profitable = [r for r in results if r['roi'] >= 100 and r['total_bets'] >= 30]

    if profitable:
        for r in sorted(profitable, key=lambda x: x['roi'], reverse=True):
            print(f"  ◎ {r['name']}: ROI {r['roi']:.1f}%, {r['total_bets']}件, 収支 {r['profit']:+,.0f}円")
    else:
        print("  該当なし")

    # JSON出力
    output_file = os.path.join(PROJECT_ROOT, 'data', 'new_pattern_backtest_results.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'year_start': year_start,
            'year_end': year_end,
            'results': results,
            'candidates': candidates,
            'profitable': profitable,
        }, f, ensure_ascii=False, indent=2)

    print()
    print(f"結果を {output_file} に保存しました")

    conn.close()


if __name__ == "__main__":
    main()
