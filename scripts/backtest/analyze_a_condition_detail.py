#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A×A1×10-20条件の詳細分析"""
import sqlite3
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('data/boatrace.db')

print('=' * 80)
print('A×A1×10-20条件の詳細分析')
print('=' * 80)

# 月別分析（2025年）
query_monthly = '''
WITH race_base AS (
    SELECT
        r.id as race_id,
        substr(r.race_date, 6, 2) as month,
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
    WHERE confidence = 'A' AND c1_rank = 'A1' AND pred_odds >= 10 AND pred_odds < 20
)
SELECT
    month,
    COUNT(*) as bets,
    SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
    SUM(payout) as payout
FROM race_targets
GROUP BY month
ORDER BY month
'''

cur = conn.cursor()
cur.execute(query_monthly)
rows = cur.fetchall()

print('\n【月別パフォーマンス（2025年1-11月）】')
print('-' * 80)
print('  月     件数     的中       払戻     的中率      ROI       収支')
print('-' * 80)

total_bets = 0
total_hits = 0
total_payout = 0

for row in rows:
    month, bets, hits, payout = row
    if bets > 0:
        hit_rate = 100.0 * hits / bets
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        total_bets += bets
        total_hits += hits
        total_payout += payout
        print(f'{int(month):>3}月 {bets:>8} {hits:>6} {payout:>12,.0f} {hit_rate:>7.1f}% {roi:>7.1f}% {profit:>+12,.0f}')

print('-' * 80)
if total_bets > 0:
    total_hit_rate = 100.0 * total_hits / total_bets
    total_roi = 100.0 * total_payout / (total_bets * 100)
    total_profit = total_payout - (total_bets * 100)
    print(f' 合計 {total_bets:>8} {total_hits:>6} {total_payout:>12,.0f} {total_hit_rate:>7.1f}% {total_roi:>7.1f}% {total_profit:>+12,.0f}')

# オッズ帯別分析（2025年）
query_odds = '''
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
    SELECT
        *,
        CASE
            WHEN pred_odds >= 10 AND pred_odds < 12 THEN '10-12'
            WHEN pred_odds >= 12 AND pred_odds < 14 THEN '12-14'
            WHEN pred_odds >= 14 AND pred_odds < 16 THEN '14-16'
            WHEN pred_odds >= 16 AND pred_odds < 18 THEN '16-18'
            WHEN pred_odds >= 18 AND pred_odds < 20 THEN '18-20'
            ELSE 'その他'
        END as odds_range
    FROM race_bets
    WHERE confidence = 'A' AND c1_rank = 'A1' AND pred_odds >= 10 AND pred_odds < 20
)
SELECT
    odds_range,
    COUNT(*) as bets,
    SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
    SUM(payout) as payout
FROM race_targets
GROUP BY odds_range
ORDER BY odds_range
'''

cur.execute(query_odds)
rows = cur.fetchall()

print('\n【オッズ帯別パフォーマンス（2025年1-11月）】')
print('-' * 80)
print('オッズ帯  件数     的中       払戻     的中率      ROI       収支')
print('-' * 80)

for row in rows:
    odds_range, bets, hits, payout = row
    if bets > 0:
        hit_rate = 100.0 * hits / bets
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        print(f'{odds_range:>8s} {bets:>6} {hits:>6} {payout:>12,.0f} {hit_rate:>7.1f}% {roi:>7.1f}% {profit:>+12,.0f}')

# 会場別分析（上位10会場）
query_venue = '''
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.venue_code,
        v.venue_name,
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
    LEFT JOIN venues v ON r.venue_code = v.venue_code
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
    WHERE confidence = 'A' AND c1_rank = 'A1' AND pred_odds >= 10 AND pred_odds < 20
)
SELECT
    venue_name,
    COUNT(*) as bets,
    SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
    SUM(payout) as payout
FROM race_targets
GROUP BY venue_name
HAVING COUNT(*) >= 10
ORDER BY (100.0 * SUM(payout) / (COUNT(*) * 100)) DESC
LIMIT 10
'''

cur.execute(query_venue)
rows = cur.fetchall()

print('\n【会場別パフォーマンス（2025年1-11月、10件以上、ROI上位10会場）】')
print('-' * 80)
print('  会場      件数     的中       払戻     的中率      ROI       収支')
print('-' * 80)

for row in rows:
    venue_name, bets, hits, payout = row
    if bets > 0:
        hit_rate = 100.0 * hits / bets
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        print(f'{venue_name:>6s} {bets:>8} {hits:>6} {payout:>12,.0f} {hit_rate:>7.1f}% {roi:>7.1f}% {profit:>+12,.0f}')

conn.close()
