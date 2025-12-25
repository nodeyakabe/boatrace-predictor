#!/usr/bin/env python3
"""購入条件最適化分析"""
import sqlite3
import pandas as pd
from pathlib import Path

# DB接続
db_path = r"c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"
conn = sqlite3.connect(db_path)

print("=" * 80)
print("購入条件最適化分析")
print("=" * 80)

# ========================================
# 1. D×30-60条件: 会場別×年度別パフォーマンス
# ========================================
print("\n【1】D×30-60条件: 会場別×年度別パフォーマンス")
print("-" * 80)

sql_d30_60 = """
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
    AND rp.confidence = 'D'
    AND e1.racer_rank IN ('A1', 'A2', 'B1')
    AND r.race_date >= '2020-01-01'
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
)
SELECT
    venue_code,
    year,
    COUNT(*) as bets,
    SUM(is_hit) as hits,
    SUM(payout) - COUNT(*) * 100 as profit,
    ROUND(100.0 * (SUM(payout) - COUNT(*) * 100) / (COUNT(*) * 100), 1) as roi_pct
FROM race_bets
WHERE pred_odds >= 30 AND pred_odds < 60
GROUP BY venue_code, year
ORDER BY venue_code, year;
"""

df_d30_60 = pd.read_sql_query(sql_d30_60, conn)
print(df_d30_60.to_string(index=False))

# 会場別集計
print("\n【1-1】D×30-60: 会場別集計（6年間合計）")
df_d30_60_venue = df_d30_60.groupby('venue_code').agg({
    'bets': 'sum',
    'hits': 'sum',
    'profit': 'sum'
}).reset_index()
df_d30_60_venue['roi_pct'] = 100.0 * df_d30_60_venue['profit'] / (df_d30_60_venue['bets'] * 100)
df_d30_60_venue = df_d30_60_venue.sort_values('profit')
print(df_d30_60_venue.to_string(index=False))

# 赤字会場の特定（ROI < 80%または利益 < -5000円）
bad_venues = df_d30_60_venue[
    (df_d30_60_venue['roi_pct'] < 80) | (df_d30_60_venue['profit'] < -5000)
]['venue_code'].tolist()

print(f"\n【1-2】除外候補会場（ROI<80%または利益<-5000円）: {bad_venues}")

# 除外前の全体集計
total_before = df_d30_60_venue.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_before = 100.0 * total_before['profit'] / (total_before['bets'] * 100)
print(f"\n除外前: {int(total_before['bets'])}件, 利益{int(total_before['profit']):+,}円, ROI {roi_before:.1f}%")

# 除外後の全体集計
df_filtered = df_d30_60_venue[~df_d30_60_venue['venue_code'].isin(bad_venues)]
total_after = df_filtered.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_after = 100.0 * total_after['profit'] / (total_after['bets'] * 100)
print(f"除外後: {int(total_after['bets'])}件, 利益{int(total_after['profit']):+,}円, ROI {roi_after:.1f}%")
print(f"改善額: {int(total_after['profit'] - total_before['profit']):+,}円, ROI改善 {roi_after - roi_before:+.1f}%pt")

# ========================================
# 2. A×A1×14-16条件: 会場別×年度別パフォーマンス
# ========================================
print("\n" + "=" * 80)
print("【2】A×A1×14-16条件: 会場別×年度別パフォーマンス")
print("-" * 80)

sql_a_a1_14_16 = """
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
    AND e1.racer_rank = 'A1'
    AND r.race_date >= '2020-01-01'
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
)
SELECT
    venue_code,
    year,
    COUNT(*) as bets,
    SUM(is_hit) as hits,
    SUM(payout) - COUNT(*) * 100 as profit,
    ROUND(100.0 * (SUM(payout) - COUNT(*) * 100) / (COUNT(*) * 100), 1) as roi_pct
FROM race_bets
WHERE pred_odds >= 14 AND pred_odds < 16
GROUP BY venue_code, year
ORDER BY venue_code, year;
"""

df_a_a1 = pd.read_sql_query(sql_a_a1_14_16, conn)
print(df_a_a1.to_string(index=False))

# 会場別集計
print("\n【2-1】A×A1×14-16: 会場別集計（6年間合計）")
df_a_a1_venue = df_a_a1.groupby('venue_code').agg({
    'bets': 'sum',
    'hits': 'sum',
    'profit': 'sum'
}).reset_index()
df_a_a1_venue['roi_pct'] = 100.0 * df_a_a1_venue['profit'] / (df_a_a1_venue['bets'] * 100)
df_a_a1_venue = df_a_a1_venue.sort_values('profit')
print(df_a_a1_venue.to_string(index=False))

# 赤字会場の特定（利益 < -1000円）
bad_venues_a_a1 = df_a_a1_venue[df_a_a1_venue['profit'] < -1000]['venue_code'].tolist()
print(f"\n【2-2】除外候補会場（利益<-1000円）: {bad_venues_a_a1}")

# 除外前後の比較
total_before_a = df_a_a1_venue.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_before_a = 100.0 * total_before_a['profit'] / (total_before_a['bets'] * 100)
print(f"\n除外前: {int(total_before_a['bets'])}件, 利益{int(total_before_a['profit']):+,}円, ROI {roi_before_a:.1f}%")

df_filtered_a = df_a_a1_venue[~df_a_a1_venue['venue_code'].isin(bad_venues_a_a1)]
total_after_a = df_filtered_a.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_after_a = 100.0 * total_after_a['profit'] / (total_after_a['bets'] * 100)
print(f"除外後: {int(total_after_a['bets'])}件, 利益{int(total_after_a['profit']):+,}円, ROI {roi_after_a:.1f}%")
print(f"改善額: {int(total_after_a['profit'] - total_before_a['profit']):+,}円, ROI改善 {roi_after_a - roi_before_a:+.1f}%pt")

# ========================================
# 3. A×B1×Motor40%+条件: 年度別パフォーマンス
# ========================================
print("\n" + "=" * 80)
print("【3】A×B1×Motor40%+条件: 年度別パフォーマンス")
print("-" * 80)

sql_a_b1_motor = """
WITH race_base AS (
    SELECT
        r.id as race_id,
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
    AND CAST(e1.motor_second_rate AS REAL) >= 40.0
    AND r.race_date >= '2020-01-01'
    AND r.race_date < '2025-12-01'
),
race_bets AS (
    SELECT
        rb.*,
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
    SUM(payout) - COUNT(*) * 100 as profit,
    ROUND(100.0 * (SUM(payout) - COUNT(*) * 100) / (COUNT(*) * 100), 1) as roi_pct
FROM race_bets
GROUP BY year
ORDER BY year;
"""

df_a_b1 = pd.read_sql_query(sql_a_b1_motor, conn)
print(df_a_b1.to_string(index=False))

# 6年間合計
total_a_b1 = df_a_b1.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_a_b1 = 100.0 * total_a_b1['profit'] / (total_a_b1['bets'] * 100)
print(f"\n【3-1】6年間合計: {int(total_a_b1['bets'])}件, 利益{int(total_a_b1['profit']):+,}円, ROI {roi_a_b1:.1f}%")

# 赤字年数カウント
deficit_years = len(df_a_b1[df_a_b1['profit'] < 0])
surplus_years = len(df_a_b1[df_a_b1['profit'] > 0])
print(f"赤字年: {deficit_years}年, 黒字年: {surplus_years}年")

# 2020-2024と2025の比較
df_2020_2024 = df_a_b1[df_a_b1['year'] < '2025']
total_2020_2024 = df_2020_2024.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_2020_2024 = 100.0 * total_2020_2024['profit'] / (total_2020_2024['bets'] * 100)

df_2025 = df_a_b1[df_a_b1['year'] == '2025']
if len(df_2025) > 0:
    total_2025 = df_2025.iloc[0]
    print(f"\n2020-2024年: {int(total_2020_2024['bets'])}件, 利益{int(total_2020_2024['profit']):+,}円, ROI {roi_2020_2024:.1f}%")
    print(f"2025年: {int(total_2025['bets'])}件, 利益{int(total_2025['profit']):+,}円, ROI {total_2025['roi_pct']:.1f}%")

conn.close()

print("\n" + "=" * 80)
print("分析完了")
print("=" * 80)
