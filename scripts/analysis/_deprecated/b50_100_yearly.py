# -*- coding: utf-8 -*-
"""B×50-100 年度×会場別分析"""
import sqlite3
import pandas as pd
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)

# 黒字会場: [2, 3, 4, 7, 8, 9, 11, 16, 17, 19, 22]
POSITIVE_VENUES = [2, 3, 4, 7, 8, 9, 11, 16, 17, 19, 22]

# 黒字会場のみでの年度別分析
query = f'''
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.venue_code,
        strftime('%Y', r.race_date) as year,
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
    AND rp.confidence = 'B'
    AND e1.racer_rank IN ('A1', 'B1')
    AND r.venue_code IN ({','.join(map(str, POSITIVE_VENUES))})
    AND r.race_date >= '2020-01-01'
    AND r.race_date < '2026-01-01'
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
    ROUND(SUM(is_hit) * 100.0 / COUNT(*), 1) as hit_rate,
    ROUND(SUM(payout) * 100.0 / (COUNT(*) * 100), 1) as roi,
    SUM(payout) - COUNT(*) * 100 as profit
FROM race_bets
WHERE pred_odds >= 50 AND pred_odds < 100
GROUP BY year
ORDER BY year
'''

print('='*80)
print('[B x 50-100 A1/B1 + 黒字11会場フィルター] 年度別成績')
print('='*80)
print(f'黒字会場: {POSITIVE_VENUES}')
print('(戸田,江戸川,平和島,蒲郡,常滑,津,琵琶湖,児島,宮島,下関,福岡)')
print()

df = pd.read_sql_query(query, conn)
print(df.to_string(index=False))

total_bets = df['bets'].sum()
total_hits = df['hits'].sum()
total_profit = df['profit'].sum()
total_roi = (total_profit + total_bets * 100) / (total_bets * 100) * 100
print(f'\n6年間合計: 件数: {total_bets}, 的中: {total_hits}, ROI: {total_roi:.1f}%, 収支: {total_profit:+,.0f}円')

# 黒字年数カウント
positive_years = len(df[df['profit'] > 0])
print(f'黒字年数: {positive_years}/6年')

conn.close()
