# -*- coding: utf-8 -*-
"""
B×30-50×B1+会場条件: 赤字会場除外効果の検証
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


def analyze_venue_filter(venue_filter, filter_name):
    """指定会場フィルターでのパフォーマンス分析"""
    venue_filter_str = ','.join(map(str, venue_filter))

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
        year,
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(bet_123 + bet_124 + bet_125) as investment,
        SUM(payout_123 + payout_124 + payout_125) as payout
    FROM race_payouts
    WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
    GROUP BY year
    ORDER BY year
    '''

    df = pd.read_sql_query(query, conn)
    df['profit'] = df['payout'] - df['investment']
    df['roi'] = (df['payout'] / df['investment'] * 100).round(1)

    total_bets = df['bets'].sum()
    total_hits = df['hits'].sum()
    total_investment = df['investment'].sum()
    total_payout = df['payout'].sum()
    total_profit = total_payout - total_investment
    total_roi = total_payout / total_investment * 100

    return {
        'name': filter_name,
        'venues': venue_filter,
        'venue_names': [venue_names[v] for v in venue_filter],
        'yearly': df,
        'total_bets': total_bets,
        'total_hits': total_hits,
        'total_investment': total_investment,
        'total_payout': total_payout,
        'total_profit': total_profit,
        'total_roi': total_roi,
        'black_years': (df['profit'] > 0).sum()
    }


print('=' * 100)
print('B×30-50×B1+会場条件: 会場フィルター最適化検証')
print('=' * 100)

# 現在のフィルター
current_filter = [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]
# 三国、浜名湖、児島、芦屋、津、尼崎、若松、大村、蒲郡、常滑

# 6年間赤字会場: 若松(-310), 尼崎(-2,589), 児島(-4,380), 蒲郡(-7,270)
# 2025年赤字会場: 大村(-500), 三国(-1,240), 浜名湖(-1,329), 若松(-2,690), 児島(-3,400), 尼崎(-5,030), 常滑(-7,400), 蒲郡(-8,400)

# テストするフィルターパターン
test_filters = [
    ('現在（10会場）', current_filter),
    ('6年間赤字4会場除外', [10, 6, 21, 9, 24, 8]),  # 若松、尼崎、児島、蒲郡を除外
    ('2025年赤字5会場除外', [21, 9]),  # 芦屋、津のみ
    ('黒字上位5会場', [9, 10, 21, 6, 8]),  # 津、三国、芦屋、浜名湖、常滑（6年間収支順）
    ('黒字上位4会場', [9, 10, 21, 6]),  # 津、三国、芦屋、浜名湖
]

results = []
for name, venues in test_filters:
    result = analyze_venue_filter(venues, name)
    results.append(result)

# 結果表示
print('\n【フィルターパターン別 6年間パフォーマンス比較】')
print('=' * 120)
print(f"{'パターン':<30} {'会場':^40} {'件数':>6} {'ROI':>8} {'収支':>14} {'黒字年'}")
print('-' * 120)
for r in results:
    venues_str = ','.join(r['venue_names'][:6]) + ('...' if len(r['venue_names']) > 6 else '')
    print(f"{r['name']:<30} {venues_str:^40} {r['total_bets']:>6} {r['total_roi']:>7.1f}% {r['total_profit']:>+14,.0f} {r['black_years']}/6年")

# 各パターンの年度別詳細
print('\n\n【各パターンの年度別詳細】')
for r in results:
    print(f"\n>>> {r['name']} - 対象会場: {r['venue_names']}")
    print(f"{'年度':>6} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12} {'判定'}")
    print('-' * 60)
    for _, row in r['yearly'].iterrows():
        judge = '○' if row['profit'] > 0 else '×'
        print(f"{int(row['year']):>6} {int(row['bets']):>6} {int(row['hits']):>4} {row['roi']:>7.1f}% {int(row['profit']):>+12,} {judge}")
    print('-' * 60)
    print(f"{'合計':>6} {r['total_bets']:>6} {r['total_hits']:>4} {r['total_roi']:>7.1f}% {r['total_profit']:>+12,.0f}")

# 2025年の月別分析
print('\n\n【2025年 月別パフォーマンス（現在フィルター）】')
print('=' * 80)
query_monthly = f'''
WITH race_base AS (
    SELECT
        r.id as race_id,
        CAST(strftime('%m', r.race_date) AS INTEGER) as month,
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
    AND CAST(r.venue_code AS INTEGER) IN ({','.join(map(str, current_filter))})
    AND r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
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
    month,
    COUNT(*) as bets,
    SUM(is_hit) as hits,
    SUM(bet_123 + bet_124 + bet_125) as investment,
    SUM(payout_123 + payout_124 + payout_125) as payout
FROM race_payouts
WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
GROUP BY month
ORDER BY month
'''

df_monthly = pd.read_sql_query(query_monthly, conn)
df_monthly['profit'] = df_monthly['payout'] - df_monthly['investment']
df_monthly['roi'] = (df_monthly['payout'] / df_monthly['investment'] * 100).round(1)

print(f"{'月':>4} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12} {'判定'}")
print('-' * 60)
for _, row in df_monthly.iterrows():
    judge = '○' if row['profit'] > 0 else '×'
    print(f"{int(row['month']):>3}月 {int(row['bets']):>6} {int(row['hits']):>4} {row['roi']:>7.1f}% {int(row['profit']):>+12,} {judge}")

conn.close()
