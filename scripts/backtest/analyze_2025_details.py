#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""2025年1-11月の詳細分析"""
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

print()
print('[2] 月別パフォーマンス（2025年1-11月・購入対象条件のみ）')
print('-' * 80)

# pred_oddsをサブクエリとして重複して計算する
monthly_query = '''
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        substr(r.race_date, 6, 2) as month,
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
),
race_targets AS (
    SELECT
        *,
        CASE
            WHEN (confidence = 'D' AND c1_rank = 'B1' AND pred_odds >= 40 AND pred_odds < 50)
              OR (confidence = 'D' AND c1_rank IN ('A1','A2','B1') AND pred_odds >= 30 AND pred_odds < 60)
              OR (confidence = 'B' AND c1_rank IN ('A1','A2','B1') AND pred_odds >= 50 AND pred_odds < 100)
              OR (confidence = 'B' AND c1_rank = 'B1' AND pred_odds >= 30 AND pred_odds < 50 AND venue_code IN (10,6,16,21,9,13,20,24,7,8))
              OR (confidence = 'A' AND c1_rank = 'A1' AND pred_odds >= 10 AND pred_odds < 20)
            THEN 1 ELSE 0
        END as is_target
    FROM race_bets
)
SELECT
    month,
    SUM(is_target) as bets,
    SUM(CASE WHEN is_target = 1 THEN is_hit ELSE 0 END) as hits,
    SUM(CASE WHEN is_target = 1 THEN payout ELSE 0 END) as payout
FROM race_targets
GROUP BY month
ORDER BY month
'''

cursor.execute(monthly_query)
rows = cursor.fetchall()

print(f'  月     件数     的中       払戻     的中率      ROI       収支')
print('-' * 80)

total_bets = 0
total_hits = 0
total_payout = 0

for row in rows:
    month, bets, hits, payout = row
    if bets and bets > 0:
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
print()

# 信頼度別
print('[3] 信頼度別パフォーマンス（2025年1-11月）')
print('-' * 80)

conf_query = '''
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
),
race_targets AS (
    SELECT
        *,
        CASE
            WHEN (confidence = 'D' AND c1_rank = 'B1' AND pred_odds >= 40 AND pred_odds < 50)
              OR (confidence = 'D' AND c1_rank IN ('A1','A2','B1') AND pred_odds >= 30 AND pred_odds < 60)
            THEN 'D'
            WHEN (confidence = 'B' AND c1_rank IN ('A1','A2','B1') AND pred_odds >= 50 AND pred_odds < 100)
              OR (confidence = 'B' AND c1_rank = 'B1' AND pred_odds >= 30 AND pred_odds < 50 AND venue_code IN (10,6,16,21,9,13,20,24,7,8))
            THEN 'B'
            WHEN (confidence = 'A' AND c1_rank = 'A1' AND pred_odds >= 10 AND pred_odds < 20)
            THEN 'A'
            ELSE NULL
        END as target_conf
    FROM race_bets
)
SELECT
    target_conf as conf,
    COUNT(*) as bets,
    SUM(is_hit) as hits,
    SUM(payout) as payout
FROM race_targets
WHERE target_conf IS NOT NULL
GROUP BY target_conf
ORDER BY target_conf
'''

cursor.execute(conf_query)
rows = cursor.fetchall()

print(f'信頼度   件数     的中       払戻     的中率      ROI       収支')
print('-' * 80)

for row in rows:
    conf, bets, hits, payout = row
    if bets and bets > 0:
        hit_rate = 100.0 * hits / bets
        roi = 100.0 * payout / (bets * 100)
        profit = payout - (bets * 100)
        print(f'  {conf}   {bets:>8} {hits:>6} {payout:>12,.0f} {hit_rate:>7.1f}% {roi:>7.1f}% {profit:>+12,.0f}')

print()
conn.close()
