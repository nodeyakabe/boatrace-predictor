# -*- coding: utf-8 -*-
"""
B×30-50×B1+会場条件の会場別パフォーマンス分析
"""
import sqlite3
import pandas as pd
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

pd.set_option('display.width', 200)
pd.set_option('display.max_columns', 20)

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

venue_names = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# 現在の会場フィルター
venue_filter = [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]
venue_filter_str = ','.join(map(str, venue_filter))

print('=' * 100)
print('B×30-50×B1+会場条件の詳細分析（パターンH: 3点買い400円）')
print('=' * 100)
print(f'現在の会場フィルター: {[venue_names[v] for v in venue_filter]}')

# SQLクエリ: 会場別・年度別パフォーマンス（パターンH）
query = f'''
WITH race_base AS (
    SELECT
        r.id as race_id,
        CAST(strftime('%Y', r.race_date) AS INTEGER) as year,
        CAST(r.venue_code AS INTEGER) as venue_code,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp3.pit_number as p3,
        rp4.pit_number as p4,
        rp5.pit_number as p5
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.rank_prediction = 1
    AND rp.confidence = 'B'
    AND e1.racer_rank = 'B1'
    AND CAST(r.venue_code AS INTEGER) IN ({venue_filter_str})
),
race_with_results AS (
    SELECT
        rb.*,
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                  AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                  AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                  AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125,
        (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
        (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
    FROM race_base rb
),
race_payouts AS (
    SELECT
        rwr.*,
        CASE WHEN odds_123 >= 30 AND odds_123 < 50 THEN 200 ELSE 0 END as bet_123,
        CASE WHEN odds_124 >= 30 AND odds_124 < 50 THEN 100 ELSE 0 END as bet_124,
        CASE WHEN odds_125 >= 30 AND odds_125 < 50 THEN 100 ELSE 0 END as bet_125,
        CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 30 AND odds_123 < 50
             THEN odds_123 * 200 ELSE 0 END as payout_123,
        CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= 30 AND odds_124 < 50
             THEN odds_124 * 100 ELSE 0 END as payout_124,
        CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= 30 AND odds_125 < 50
             THEN odds_125 * 100 ELSE 0 END as payout_125,
        CASE WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 30 AND odds_123 < 50)
              OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= 30 AND odds_124 < 50)
              OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= 30 AND odds_125 < 50)
             THEN 1 ELSE 0 END as is_hit
    FROM race_with_results rwr
)
SELECT
    venue_code,
    year,
    COUNT(*) as bets,
    SUM(is_hit) as hits,
    SUM(bet_123 + bet_124 + bet_125) as investment,
    SUM(payout_123 + payout_124 + payout_125) as payout
FROM race_payouts
WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
GROUP BY venue_code, year
ORDER BY venue_code, year
'''

df = pd.read_sql_query(query, conn)
df['venue_name'] = df['venue_code'].map(venue_names)
df['profit'] = df['payout'] - df['investment']
df['roi'] = (df['payout'] / df['investment'] * 100).round(1)

print('\n【会場別×年度別 収支一覧（パターンH）】')
print('=' * 100)

# ピボットテーブル
pivot_profit = df.pivot_table(index='venue_name', columns='year', values='profit', aggfunc='sum', fill_value=0)
pivot_count = df.pivot_table(index='venue_name', columns='year', values='bets', aggfunc='sum', fill_value=0)

# 会場別6年間合計
venue_total = df.groupby('venue_name').agg({'bets': 'sum', 'hits': 'sum', 'investment': 'sum', 'payout': 'sum'}).reset_index()
venue_total['profit'] = venue_total['payout'] - venue_total['investment']
venue_total['roi'] = (venue_total['payout'] / venue_total['investment'] * 100).round(1)

print('\n【件数】')
print(pivot_count.to_string())

print('\n【収支（円）】')
print(pivot_profit.to_string())

# 2025年の収支
print('\n\n【2025年パフォーマンス詳細】')
print('=' * 80)
df_2025 = df[df['year'] == 2025].copy()
print(f"{'会場':<6} {'件数':>6} {'的中':>4} {'投資額':>8} {'払戻':>10} {'ROI':>8} {'収支':>12}")
print('-' * 80)
for _, row in df_2025.sort_values('profit', ascending=False).iterrows():
    print(f"{row['venue_name']:<6} {int(row['bets']):>6} {int(row['hits']):>4} {int(row['investment']):>8,} {int(row['payout']):>10,} {row['roi']:>7.1f}% {int(row['profit']):>+12,}")
total_2025 = df_2025.agg({'bets': 'sum', 'hits': 'sum', 'investment': 'sum', 'payout': 'sum'})
total_profit_2025 = total_2025['payout'] - total_2025['investment']
total_roi_2025 = total_2025['payout'] / total_2025['investment'] * 100
print('-' * 80)
print(f"{'合計':<6} {int(total_2025['bets']):>6} {int(total_2025['hits']):>4} {int(total_2025['investment']):>8,} {int(total_2025['payout']):>10,} {total_roi_2025:>7.1f}% {int(total_profit_2025):>+12,}")

# 6年間合計
print('\n\n【会場別6年間サマリー】')
print('=' * 80)
print(f"{'会場':<6} {'件数':>6} {'的中':>4} {'投資額':>10} {'払戻':>12} {'ROI':>8} {'収支':>12}")
print('-' * 80)
for _, row in venue_total.sort_values('profit', ascending=False).iterrows():
    print(f"{row['venue_name']:<6} {int(row['bets']):>6} {int(row['hits']):>4} {int(row['investment']):>10,} {int(row['payout']):>12,} {row['roi']:>7.1f}% {int(row['profit']):>+12,}")
total_6y = venue_total.agg({'bets': 'sum', 'hits': 'sum', 'investment': 'sum', 'payout': 'sum'})
total_profit_6y = total_6y['payout'] - total_6y['investment']
total_roi_6y = total_6y['payout'] / total_6y['investment'] * 100
print('-' * 80)
print(f"{'合計':<6} {int(total_6y['bets']):>6} {int(total_6y['hits']):>4} {int(total_6y['investment']):>10,} {int(total_6y['payout']):>12,} {total_roi_6y:>7.1f}% {int(total_profit_6y):>+12,}")

# 年度別サマリー
print('\n\n【年度別サマリー】')
print('=' * 80)
yearly = df.groupby('year').agg({'bets': 'sum', 'hits': 'sum', 'investment': 'sum', 'payout': 'sum'}).reset_index()
yearly['profit'] = yearly['payout'] - yearly['investment']
yearly['roi'] = (yearly['payout'] / yearly['investment'] * 100).round(1)
print(f"{'年度':>6} {'件数':>6} {'的中':>4} {'投資額':>10} {'払戻':>12} {'ROI':>8} {'収支':>12} {'判定'}")
print('-' * 80)
for _, row in yearly.iterrows():
    judge = '○黒字' if row['profit'] > 0 else '×赤字'
    print(f"{int(row['year']):>6} {int(row['bets']):>6} {int(row['hits']):>4} {int(row['investment']):>10,} {int(row['payout']):>12,} {row['roi']:>7.1f}% {int(row['profit']):>+12,} {judge}")

conn.close()
