# -*- coding: utf-8 -*-
"""B×50-100 詳細分析"""
import sqlite3
import pandas as pd
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川', '06': '浜名湖',
    '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国', '11': '琵琶湖', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島', '17': '宮島', '18': '徳山',
    '19': '下関', '20': '若松', '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}

# 会場別分析
query = '''
WITH race_base AS (
    SELECT
        r.id as race_id,
        printf('%02d', r.venue_code) as venue_code,
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
    venue_code,
    COUNT(*) as bets,
    SUM(is_hit) as hits,
    ROUND(SUM(is_hit) * 100.0 / COUNT(*), 1) as hit_rate,
    ROUND(SUM(payout) * 100.0 / (COUNT(*) * 100), 1) as roi,
    SUM(payout) - COUNT(*) * 100 as profit
FROM race_bets
WHERE pred_odds >= 50 AND pred_odds < 100
GROUP BY venue_code
HAVING COUNT(*) >= 5
ORDER BY profit DESC
'''
df = pd.read_sql_query(query, conn)
df['venue_name'] = df['venue_code'].map(VENUE_NAMES)
print('='*80)
print('[B x 50-100 A1/B1] 会場別成績（6年間、5件以上）')
print('='*80)
print(df[['venue_name', 'venue_code', 'bets', 'hits', 'hit_rate', 'roi', 'profit']].to_string(index=False))

# 黒字会場と赤字会場
positive_venues = df[df['profit'] > 0]
negative_venues = df[df['profit'] < 0]
print(f'\n黒字会場（{len(positive_venues)}会場）: 合計 {positive_venues["profit"].sum():+,.0f}円')
print(f'赤字会場（{len(negative_venues)}会場）: 合計 {negative_venues["profit"].sum():+,.0f}円')

# 赤字会場を除外した場合の効果
positive_only_profit = positive_venues['profit'].sum()
positive_only_bets = positive_venues['bets'].sum()
positive_only_roi = (positive_only_profit + positive_only_bets * 100) / (positive_only_bets * 100) * 100
print(f'\n黒字会場のみの場合:')
print(f'   件数: {positive_only_bets}, ROI: {positive_only_roi:.1f}%, 収支: {positive_only_profit:+,.0f}円')

# 黒字会場リスト
print(f'\n黒字会場コード: {sorted(positive_venues["venue_code"].astype(int).tolist())}')

conn.close()
