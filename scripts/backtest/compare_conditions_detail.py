#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""前回条件と今回条件の詳細比較"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()

print('=' * 80)
print('前回（12/20時点）の条件でバックテスト（2025年1-11月）')
print('=' * 80)

# 前回の条件
conditions_old = [
    ("A×A1×10-20", "confidence = 'A' AND c1_rank = 'A1' AND pred_odds >= 10 AND pred_odds < 20"),
    ("B×50-100", "confidence = 'B' AND c1_rank IN ('A1', 'A2', 'B1') AND pred_odds >= 50 AND pred_odds < 100"),
    ("C×30-40×B1/A1", "confidence = 'C' AND c1_rank IN ('B1', 'A1') AND pred_odds >= 30 AND pred_odds < 40"),
    ("D×20-50", "confidence = 'D' AND pred_odds >= 20 AND pred_odds < 50"),
]

total_bets_old = 0
total_hits_old = 0
total_payout_old = 0

for name, condition in conditions_old:
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
        AND r.race_date >= '2025-01-01'
        AND r.race_date < '2025-12-01'
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
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM race_base rb
    ),
    race_targets AS (
        SELECT * FROM race_bets
        WHERE {condition}
    )
    SELECT
        COUNT(*) as bets,
        SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
        SUM(payout) as payout
    FROM race_targets
    '''

    cur.execute(query)
    row = cur.fetchone()
    if row and row[0] and row[0] > 0:
        bets, hits, payout = row
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        print(f'{name:20s}: {bets:4d}件, {hits:3d}的中, ROI {roi:6.1f}%, 収支 {profit:+10,.0f}円')
        total_bets_old += bets
        total_hits_old += hits
        total_payout_old += payout
    else:
        print(f'{name:20s}: データなし')

print('-' * 80)
if total_bets_old > 0:
    total_roi_old = 100.0 * total_payout_old / (total_bets_old * 100)
    total_profit_old = total_payout_old - (total_bets_old * 100)
    print(f'{"前回合計":20s}: {total_bets_old:4d}件, {total_hits_old:3d}的中, ROI {total_roi_old:6.1f}%, 収支 {total_profit_old:+10,.0f}円')

print()
print('=' * 80)
print('今回（改善後）の条件でバックテスト（2025年1-11月）')
print('=' * 80)

# 今回の条件（会場フィルター含む）
venue_filter = "venue_code IN (10,6,16,21,9,13,20,24,7,8)"
conditions_new = [
    ("A×A1×10-20", "confidence = 'A' AND c1_rank = 'A1' AND pred_odds >= 10 AND pred_odds < 20"),
    ("B×30-50×B1+会場", f"confidence = 'B' AND c1_rank = 'B1' AND pred_odds >= 30 AND pred_odds < 50 AND {venue_filter}"),
    ("B×50-100", "confidence = 'B' AND c1_rank IN ('A1', 'A2', 'B1') AND pred_odds >= 50 AND pred_odds < 100"),
    ("D×30-60×A1/A2/B1", "confidence = 'D' AND c1_rank IN ('A1', 'A2', 'B1') AND pred_odds >= 30 AND pred_odds < 60"),
]

total_bets_new = 0
total_hits_new = 0
total_payout_new = 0

for name, condition in conditions_new:
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
        AND r.race_date >= '2025-01-01'
        AND r.race_date < '2025-12-01'
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
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM race_base rb
    ),
    race_targets AS (
        SELECT * FROM race_bets
        WHERE {condition}
    )
    SELECT
        COUNT(*) as bets,
        SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
        SUM(payout) as payout
    FROM race_targets
    '''

    cur.execute(query)
    row = cur.fetchone()
    if row and row[0] and row[0] > 0:
        bets, hits, payout = row
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        print(f'{name:20s}: {bets:4d}件, {hits:3d}的中, ROI {roi:6.1f}%, 収支 {profit:+10,.0f}円')
        total_bets_new += bets
        total_hits_new += hits
        total_payout_new += payout
    else:
        print(f'{name:20s}: データなし')

print('-' * 80)
if total_bets_new > 0:
    total_roi_new = 100.0 * total_payout_new / (total_bets_new * 100)
    total_profit_new = total_payout_new - (total_bets_new * 100)
    print(f'{"今回合計":20s}: {total_bets_new:4d}件, {total_hits_new:3d}的中, ROI {total_roi_new:6.1f}%, 収支 {total_profit_new:+10,.0f}円')

print()
print('=' * 80)
print('差分（今回 - 前回）')
print('=' * 80)
diff_bets = total_bets_new - total_bets_old
diff_hits = total_hits_new - total_hits_old
diff_payout = total_payout_new - total_payout_old
diff_roi = total_roi_new - total_roi_old if total_bets_old > 0 else 0
diff_profit = total_profit_new - total_profit_old

print(f'購入件数差: {diff_bets:+d}件')
print(f'的中数差: {diff_hits:+d}件')
print(f'ROI差: {diff_roi:+.1f}pt')
print(f'収支差: {diff_profit:+,.0f}円')

conn.close()
