# -*- coding: utf-8 -*-
"""B×50-100 的中パターン分析"""
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

# 的中したレースの詳細を確認
query = '''
WITH race_base AS (
    SELECT
        r.id as race_id,
        r.venue_code,
        r.race_date,
        strftime('%Y', r.race_date) as year,
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
        END as is_hit
    FROM race_base rb
)
SELECT
    year,
    venue_code,
    c1_rank,
    pred_odds,
    p1, p2, p3
FROM race_bets
WHERE pred_odds >= 50 AND pred_odds < 100
AND is_hit = 1
ORDER BY year, pred_odds DESC
'''

print('='*80)
print('[B x 50-100 A1/B1] 的中レース一覧')
print('='*80)

df = pd.read_sql_query(query, conn)
df['venue_name'] = df['venue_code'].map(VENUE_NAMES)
print(df[['year', 'venue_name', 'c1_rank', 'pred_odds', 'p1', 'p2', 'p3']].to_string(index=False))

# 的中時のオッズ分布
print('\n■ 的中時のオッズ統計:')
print(f'   平均オッズ: {df["pred_odds"].mean():.1f}倍')
print(f'   最高オッズ: {df["pred_odds"].max():.1f}倍')
print(f'   最低オッズ: {df["pred_odds"].min():.1f}倍')

# 的中の会場分布
print('\n■ 的中の会場分布:')
venue_hits = df.groupby('venue_name').size().sort_values(ascending=False)
print(venue_hits.to_string())

# 的中の1コース級別分布
print('\n■ 的中の1コース級別分布:')
rank_hits = df.groupby('c1_rank').size()
print(rank_hits.to_string())

# 的中の1着予測コース分布
print('\n■ 的中の1着予測コース分布:')
course_hits = df.groupby('p1').size().sort_values(ascending=False)
print(course_hits.to_string())

conn.close()
