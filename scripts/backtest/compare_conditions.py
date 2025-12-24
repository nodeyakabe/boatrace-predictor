#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""前回条件と今回条件の比較分析"""
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

def analyze_condition(name, confidence, c1_ranks, odds_min, odds_max, venue_filter=None):
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
        return {'name': name, 'bets': bets, 'hits': hits, 'roi': roi, 'profit': profit}
    return {'name': name, 'bets': 0, 'hits': 0, 'roi': 0, 'profit': 0}


print("=" * 80)
print("前回条件（12/20）と今回条件の比較分析")
print("対象期間: 2025年1-11月")
print("=" * 80)
print()

# 前回条件（12/20時点）を再現
print("[前回条件 12/20時点]")
print("-" * 80)

# A条件（前回）: ほぼなし（3件）- 条件不明
# B条件（前回）: 482件 - オッズ50-100倍 または 1コースB1級らしい
# C条件（前回）: 506件 - オッズ30-40倍、1コースB1級 or A1級
# D条件（前回）: 114件 - オッズ20-50倍、1コースB1級/A1級/A2級

# C条件の前回推測
c_old = analyze_condition("C×30-40×B1/A1", 'C', ['B1', 'A1'], 30, 40)
print(f"  C×30-40×B1/A1: {c_old['bets']}件, 的中{c_old['hits']}, ROI {c_old['roi']:.1f}%, 収支{c_old['profit']:+,.0f}円")

# B条件の前回（50-100）
b_old_high = analyze_condition("B×50-100", 'B', ['A1', 'A2', 'B1'], 50, 100)
print(f"  B×50-100: {b_old_high['bets']}件, 的中{b_old_high['hits']}, ROI {b_old_high['roi']:.1f}%, 収支{b_old_high['profit']:+,.0f}円")

# B条件の前回（B1全体）- 会場フィルターなし
b_old_b1 = analyze_condition("B×30-50×B1（フィルターなし）", 'B', ['B1'], 30, 50)
print(f"  B×30-50×B1（全会場）: {b_old_b1['bets']}件, 的中{b_old_b1['hits']}, ROI {b_old_b1['roi']:.1f}%, 収支{b_old_b1['profit']:+,.0f}円")

# D条件の前回
d_old = analyze_condition("D×20-50×A1/A2/B1", 'D', ['A1', 'A2', 'B1'], 20, 50)
print(f"  D×20-50×A1/A2/B1: {d_old['bets']}件, 的中{d_old['hits']}, ROI {d_old['roi']:.1f}%, 収支{d_old['profit']:+,.0f}円")

print()
print("[今回条件]")
print("-" * 80)

# A条件（今回）: A×A1×10-20
a_now = analyze_condition("A×A1×10-20", 'A', ['A1'], 10, 20)
print(f"  A×A1×10-20: {a_now['bets']}件, 的中{a_now['hits']}, ROI {a_now['roi']:.1f}%, 収支{a_now['profit']:+,.0f}円")

# B条件（今回）: B×50-100
b_now_high = analyze_condition("B×50-100", 'B', ['A1', 'A2', 'B1'], 50, 100)
print(f"  B×50-100: {b_now_high['bets']}件, 的中{b_now_high['hits']}, ROI {b_now_high['roi']:.1f}%, 収支{b_now_high['profit']:+,.0f}円")

# B条件（今回）: B×30-50×B1 + 会場フィルター
venue_filter_b = [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]
b_now_filtered = analyze_condition("B×30-50×B1+会場フィルター", 'B', ['B1'], 30, 50, venue_filter_b)
print(f"  B×30-50×B1+会場: {b_now_filtered['bets']}件, 的中{b_now_filtered['hits']}, ROI {b_now_filtered['roi']:.1f}%, 収支{b_now_filtered['profit']:+,.0f}円")

# D条件（今回）: D×40-50×B1
d_now_1 = analyze_condition("D×40-50×B1", 'D', ['B1'], 40, 50)
print(f"  D×40-50×B1: {d_now_1['bets']}件, 的中{d_now_1['hits']}, ROI {d_now_1['roi']:.1f}%, 収支{d_now_1['profit']:+,.0f}円")

# D条件（今回）: D×30-60×A1/A2/B1
d_now_2 = analyze_condition("D×30-60×A1/A2/B1", 'D', ['A1', 'A2', 'B1'], 30, 60)
print(f"  D×30-60×A1/A2/B1: {d_now_2['bets']}件, 的中{d_now_2['hits']}, ROI {d_now_2['roi']:.1f}%, 収支{d_now_2['profit']:+,.0f}円")

print()
print("=" * 80)
print("差異分析")
print("=" * 80)
print()

# 消えた条件
print("[消えた条件（前回あり→今回なし）]")
print(f"  C×30-40×B1/A1: {c_old['profit']:+,.0f}円 → 今回なし")
print()

# 追加された条件
print("[追加された条件（前回なし→今回あり）]")
print(f"  A×A1×10-20: 今回 {a_now['profit']:+,.0f}円")
print()

# 変更された条件
print("[変更された条件]")
print(f"  B×30-50×B1: 全会場 {b_old_b1['profit']:+,.0f}円 → 会場フィルター {b_now_filtered['profit']:+,.0f}円 (差: {b_now_filtered['profit'] - b_old_b1['profit']:+,.0f}円)")
print()

# 収支影響の計算
print("=" * 80)
print("収支影響サマリー")
print("=" * 80)
print()

# 前回の推定収支
old_total = c_old['profit'] + b_old_high['profit'] + b_old_b1['profit'] + d_old['profit']
print(f"前回条件の推定収支:")
print(f"  C×30-40: {c_old['profit']:+,.0f}円")
print(f"  B×50-100: {b_old_high['profit']:+,.0f}円")
print(f"  B×30-50×B1(全会場): {b_old_b1['profit']:+,.0f}円")
print(f"  D×20-50: {d_old['profit']:+,.0f}円")
print(f"  → 合計: {old_total:+,.0f}円")
print()

# 今回の収支
now_total = a_now['profit'] + b_now_high['profit'] + b_now_filtered['profit'] + d_now_2['profit']
print(f"今回条件の収支:")
print(f"  A×10-20: {a_now['profit']:+,.0f}円")
print(f"  B×50-100: {b_now_high['profit']:+,.0f}円")
print(f"  B×30-50+会場: {b_now_filtered['profit']:+,.0f}円")
print(f"  D×30-60: {d_now_2['profit']:+,.0f}円")
print(f"  → 合計: {now_total:+,.0f}円")
print()

print(f"差異: {now_total - old_total:+,.0f}円")
print()

# 主な原因
print("=" * 80)
print("主な原因")
print("=" * 80)
print()
print(f"1. C条件の削除: -{c_old['profit']:,.0f}円 の損失")
print(f"2. A条件の追加: {a_now['profit']:+,.0f}円（赤字追加）")
print(f"3. B×30-50の会場フィルター: 件数減少で収支減")
print()

conn.close()
