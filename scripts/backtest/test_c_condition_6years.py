#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C条件（ペーパートレード）の6年間テスト"""
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

# C×20-30×B1 + 会場フィルター
venue_filter_c = [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]
venue_names = {
    23: '唐津', 18: '徳山', 5: '多摩川', 4: '平和島', 9: '津',
    15: '丸亀', 8: '常滑', 24: '大村', 20: '若松', 17: '宮島'
}

venue_clause = f"AND r.venue_code IN ({','.join(map(str, venue_filter_c))})"

query = f'''
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.venue_code,
        CAST(substr(r.race_date, 1, 4) AS INTEGER) as year,
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
    AND rp.confidence = 'C'
    AND e1.racer_rank = 'B1'
    AND substr(r.race_date, 1, 4) >= '2020'
    AND substr(r.race_date, 1, 4) <= '2025'
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
    year,
    COUNT(*) as bets,
    SUM(is_hit) as hits,
    SUM(payout) as payout
FROM race_bets
WHERE pred_odds >= 20 AND pred_odds < 30
GROUP BY year
ORDER BY year
'''

print("=" * 80)
print("C×20-30×B1 + 会場フィルター 6年間テスト結果")
print("=" * 80)
print()
print(f"会場フィルター: {', '.join([venue_names[v] for v in venue_filter_c])}")
print()

cursor.execute(query)
rows = cursor.fetchall()

print(f"{'年':>6} {'件数':>8} {'的中':>6} {'払戻':>12} {'的中率':>8} {'ROI':>8} {'収支':>12}")
print("-" * 80)

total_bets = 0
total_hits = 0
total_payout = 0
yearly_results = []

for row in rows:
    year, bets, hits, payout = row
    if bets and bets > 0:
        hit_rate = 100.0 * hits / bets
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        total_bets += bets
        total_hits += hits
        total_payout += payout
        yearly_results.append({'year': year, 'roi': roi, 'profit': profit})
        print(f"{year:>6} {bets:>8} {hits:>6} {payout:>12,.0f} {hit_rate:>7.1f}% {roi:>7.1f}% {profit:>+12,.0f}")

print("-" * 80)
if total_bets > 0:
    total_hit_rate = 100.0 * total_hits / total_bets
    total_roi = 100.0 * total_payout / (total_bets * 100)
    total_profit = total_payout - (total_bets * 100)
    print(f"{'合計':>6} {total_bets:>8} {total_hits:>6} {total_payout:>12,.0f} {total_hit_rate:>7.1f}% {total_roi:>7.1f}% {total_profit:>+12,.0f}")

print()
print("=" * 80)
print("年度別評価")
print("=" * 80)
print()

# 黒字年数カウント
profitable_years = sum(1 for r in yearly_results if r['roi'] >= 100)
print(f"黒字年数: {profitable_years}/6年")
print()

# 各年の状況
for r in yearly_results:
    status = "✅ 黒字" if r['roi'] >= 100 else "❌ 赤字"
    print(f"  {r['year']}年: ROI {r['roi']:.1f}%, 収支 {r['profit']:+,.0f}円 {status}")

print()

# フィルターなしとの比較
print("=" * 80)
print("会場フィルターなしとの比較")
print("=" * 80)
print()

query_no_filter = '''
WITH race_base AS (
    SELECT
        r.id as race_id,
        CAST(substr(r.race_date, 1, 4) AS INTEGER) as year,
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
    AND rp.confidence = 'C'
    AND e1.racer_rank = 'B1'
    AND substr(r.race_date, 1, 4) >= '2020'
    AND substr(r.race_date, 1, 4) <= '2025'
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
WHERE pred_odds >= 20 AND pred_odds < 30
'''

cursor.execute(query_no_filter)
row = cursor.fetchone()
bets_nf, hits_nf, payout_nf = row
roi_nf = 100.0 * payout_nf / (bets_nf * 100) if bets_nf > 0 else 0
profit_nf = payout_nf - (bets_nf * 100) if bets_nf > 0 else 0

print(f"フィルターなし: {bets_nf}件, ROI {roi_nf:.1f}%, 収支 {profit_nf:+,.0f}円")
print(f"フィルターあり: {total_bets}件, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円")
print(f"改善効果: ROI {total_roi - roi_nf:+.1f}pt")
print()

conn.close()
