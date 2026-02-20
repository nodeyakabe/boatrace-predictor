# -*- coding: utf-8 -*-
"""A×B1×Motor40%+ 深掘り分析"""
import sqlite3
import pandas as pd
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

print('='*80)
print('[A x B1 x Motor40%+] 深掘り分析')
print('='*80)

# 1. 黒字会場 + 30-50倍の組み合わせ
positive_venues = [22, 7, 19, 5, 11, 9, 1, 6, 2, 13, 10]

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
    AND rp.confidence = 'A'
    AND e1.racer_rank = 'B1'
    AND e1.motor_second_rate >= 40
    AND r.venue_code IN ({','.join(map(str, positive_venues))})
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
WHERE pred_odds >= 30 AND pred_odds < 50
GROUP BY year
ORDER BY year
'''

print('\n■ 案1: 黒字会場 + 30-50倍限定')
print(f'   黒字会場: {positive_venues}')
df = pd.read_sql_query(query, conn)
if len(df) > 0:
    print(df.to_string(index=False))
    total_bets = df['bets'].sum()
    total_profit = df['profit'].sum()
    if total_bets > 0:
        total_roi = (total_profit + total_bets * 100) / (total_bets * 100) * 100
        print(f'\n   6年間: 件数{total_bets}, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円')
        print(f'   黒字年数: {len(df[df["profit"] > 0])}/6年')
else:
    print('   該当データなし')

# 2. モーター50%以上に引き上げ
print('\n' + '='*80)
print('■ 案2: モーター50%+に引き上げ')
query2 = '''
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
    AND rp.confidence = 'A'
    AND e1.racer_rank = 'B1'
    AND e1.motor_second_rate >= 50
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
WHERE pred_odds >= 10 AND pred_odds < 100
GROUP BY year
ORDER BY year
'''
df2 = pd.read_sql_query(query2, conn)
if len(df2) > 0:
    print(df2.to_string(index=False))
    total_bets = df2['bets'].sum()
    total_profit = df2['profit'].sum()
    if total_bets > 0:
        total_roi = (total_profit + total_bets * 100) / (total_bets * 100) * 100
        print(f'\n   6年間: 件数{total_bets}, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円')
        print(f'   黒字年数: {len(df2[df2["profit"] > 0])}/6年')
else:
    print('   該当データなし')

# 3. 1コース2連率30%以上に追加条件
print('\n' + '='*80)
print('■ 案3: 1コース選手の2連率30%以上を追加')
query3 = '''
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.venue_code,
        strftime('%Y', r.race_date) as year,
        e1.second_rate,
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
    AND rp.confidence = 'A'
    AND e1.racer_rank = 'B1'
    AND e1.motor_second_rate >= 40
    AND e1.second_rate >= 30
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
WHERE pred_odds >= 10 AND pred_odds < 100
GROUP BY year
ORDER BY year
'''
df3 = pd.read_sql_query(query3, conn)
if len(df3) > 0:
    print(df3.to_string(index=False))
    total_bets = df3['bets'].sum()
    total_profit = df3['profit'].sum()
    if total_bets > 0:
        total_roi = (total_profit + total_bets * 100) / (total_bets * 100) * 100
        print(f'\n   6年間: 件数{total_bets}, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円')
        print(f'   黒字年数: {len(df3[df3["profit"] > 0])}/6年')
else:
    print('   該当データなし')

# 4. 廃止した場合の全体への影響
print('\n' + '='*80)
print('■ 廃止した場合の影響')
print('   現状: ROI 92.0%, 収支 -3,680円')
print('   廃止すると: 全体ROIに+0.5pt程度の改善効果')

conn.close()
