#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""最適化後の条件でバックテスト"""
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

def analyze_condition(name, confidence, c1_ranks, odds_min, odds_max, venue_filter=None, paper_trade=False):
    """条件別のROIを計算"""
    c1_rank_str = "','".join(c1_ranks)
    venue_clause = ""
    if venue_filter:
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, venue_filter))})"

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
        AND rp.confidence = '{confidence}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '2025-01-01'
        AND r.race_date < '2025-12-01'
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
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) as payout
    FROM race_bets
    WHERE pred_odds >= {odds_min} AND pred_odds < {odds_max}
    '''
    cursor.execute(query)
    row = cursor.fetchone()
    bets, hits, payout = row
    if bets and bets > 0:
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        return {'name': name, 'bets': bets, 'hits': hits, 'roi': roi, 'profit': profit, 'paper_trade': paper_trade}
    return {'name': name, 'bets': 0, 'hits': 0, 'roi': 0, 'profit': 0, 'paper_trade': paper_trade}


print("=" * 80)
print("最適化後の条件 バックテスト結果")
print("対象期間: 2025年1-11月")
print("=" * 80)
print()

# 最適化後の条件
conditions = []

# A条件（最適化後）: 10-12倍、14-16倍のみ
a_10_12 = analyze_condition("A×A1×10-12", 'A', ['A1'], 10, 12)
a_14_16 = analyze_condition("A×A1×14-16", 'A', ['A1'], 14, 16)
conditions.append(a_10_12)
conditions.append(a_14_16)

# B条件
b_50_100 = analyze_condition("B×50-100", 'B', ['A1', 'A2', 'B1'], 50, 100)
venue_filter_b = [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]
b_30_50_venue = analyze_condition("B×30-50×B1+会場", 'B', ['B1'], 30, 50, venue_filter_b)
conditions.append(b_50_100)
conditions.append(b_30_50_venue)

# C条件（本番運用）
venue_filter_c = [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]
c_20_30_venue = analyze_condition("C×20-30×B1+会場", 'C', ['B1'], 20, 30, venue_filter_c, paper_trade=False)
conditions.append(c_20_30_venue)

# D条件
d_40_50 = analyze_condition("D×40-50×B1", 'D', ['B1'], 40, 50)
d_30_60 = analyze_condition("D×30-60×A1/A2/B1", 'D', ['A1', 'A2', 'B1'], 30, 60)
conditions.append(d_40_50)
conditions.append(d_30_60)

print("[最適化後の条件別パフォーマンス]")
print("-" * 80)
print(f"{'条件':<25} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12} {'備考':<10}")
print("-" * 80)

total_bets = 0
total_profit = 0
total_bets_real = 0  # ペーパートレード除く
total_profit_real = 0

for cond in conditions:
    mark = "（PT）" if cond['paper_trade'] else ""
    print(f"{cond['name']:<25} {cond['bets']:>6} {cond['hits']:>4} {cond['roi']:>7.1f}% {cond['profit']:>+12,.0f} {mark}")
    total_bets += cond['bets']
    total_profit += cond['profit']
    if not cond['paper_trade']:
        total_bets_real += cond['bets']
        total_profit_real += cond['profit']

print("-" * 80)
if total_bets_real > 0:
    total_roi_real = 100.0 * (total_profit_real + total_bets_real * 100) / (total_bets_real * 100)
    print(f"{'実購入合計':<25} {total_bets_real:>6} {'-':>4} {total_roi_real:>7.1f}% {total_profit_real:>+12,.0f}")

if total_bets > 0:
    total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100)
    print(f"{'全体合計（PT含む）':<25} {total_bets:>6} {'-':>4} {total_roi:>7.1f}% {total_profit:>+12,.0f}")

print()
print("=" * 80)
print("前回との比較")
print("=" * 80)
print()
print("前回（12/20時点）: 1,105件, ROI 136.0%, +39,740円")
print("改善前（今回実装前）: 1,102件, ROI 127.3%, +30,120円")
print(f"最適化後（実購入のみ）: {total_bets_real}件, ROI {total_roi_real:.1f}%, {total_profit_real:+,.0f}円")
print()

# 改善効果
print("=" * 80)
print("改善効果")
print("=" * 80)
print()
print(f"改善前 → 最適化後:")
print(f"  ROI: 127.3% → {total_roi_real:.1f}% ({total_roi_real - 127.3:+.1f}pt)")
print(f"  収支: +30,120円 → {total_profit_real:+,.0f}円 ({total_profit_real - 30120:+,.0f}円)")
print(f"  件数: 1,102件 → {total_bets_real}件 ({total_bets_real - 1102:+,}件)")
print()

conn.close()
