#!/usr/bin/env python3
"""購入条件最適化分析レポート"""
import sqlite3
import pandas as pd
from pathlib import Path

# DB接続
db_path = r"c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"
conn = sqlite3.connect(db_path)

print("=" * 100)
print("購入条件最適化分析レポート")
print("=" * 100)

# ========================================
# 1. D×30-60条件: 除外基準の再検討
# ========================================
print("\n【1】D×30-60条件: 会場フィルター最適化")
print("-" * 100)

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

# 会場別集計
df_d30_60_venue = df_d30_60.groupby('venue_code').agg({
    'bets': 'sum',
    'hits': 'sum',
    'profit': 'sum'
}).reset_index()
df_d30_60_venue['roi_pct'] = 100.0 * df_d30_60_venue['profit'] / (df_d30_60_venue['bets'] * 100)
df_d30_60_venue = df_d30_60_venue.sort_values('profit')

print("【1-1】会場別パフォーマンス（ROI < 50% の会場）")
poor_venues = df_d30_60_venue[df_d30_60_venue['roi_pct'] < 50.0]
print(poor_venues.to_string(index=False))

# 除外基準の段階的評価
print("\n【1-2】除外基準の段階的評価")

# 基準1: ROI < 0% (完全赤字)
exclude_1 = df_d30_60_venue[df_d30_60_venue['roi_pct'] < 0]['venue_code'].tolist()
df_after_1 = df_d30_60_venue[~df_d30_60_venue['venue_code'].isin(exclude_1)]
total_1 = df_after_1.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_1 = 100.0 * total_1['profit'] / (total_1['bets'] * 100)
print(f"基準1: ROI < 0% 除外 ({len(exclude_1)}会場)")
print(f"  除外会場: {exclude_1}")
print(f"  結果: {int(total_1['bets'])}件, 利益{int(total_1['profit']):+,}円, ROI {roi_1:.1f}%")

# 基準2: ROI < 20% (大幅赤字)
exclude_2 = df_d30_60_venue[df_d30_60_venue['roi_pct'] < 20]['venue_code'].tolist()
df_after_2 = df_d30_60_venue[~df_d30_60_venue['venue_code'].isin(exclude_2)]
total_2 = df_after_2.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_2 = 100.0 * total_2['profit'] / (total_2['bets'] * 100)
print(f"\n基準2: ROI < 20% 除外 ({len(exclude_2)}会場)")
print(f"  除外会場: {exclude_2}")
print(f"  結果: {int(total_2['bets'])}件, 利益{int(total_2['profit']):+,}円, ROI {roi_2:.1f}%")

# 基準3: ROI < 50% (安定性重視)
exclude_3 = df_d30_60_venue[df_d30_60_venue['roi_pct'] < 50]['venue_code'].tolist()
df_after_3 = df_d30_60_venue[~df_d30_60_venue['venue_code'].isin(exclude_3)]
total_3 = df_after_3.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_3 = 100.0 * total_3['profit'] / (total_3['bets'] * 100)
print(f"\n基準3: ROI < 50% 除外 ({len(exclude_3)}会場)")
print(f"  除外会場: {exclude_3}")
print(f"  結果: {int(total_3['bets'])}件, 利益{int(total_3['profit']):+,}円, ROI {roi_3:.1f}%")

# 現状（除外なし）
total_0 = df_d30_60_venue.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_0 = 100.0 * total_0['profit'] / (total_0['bets'] * 100)
print(f"\n現状（除外なし）: {int(total_0['bets'])}件, 利益{int(total_0['profit']):+,}円, ROI {roi_0:.1f}%")

# ========================================
# 2. A×A1×14-16条件: 除外基準の再検討
# ========================================
print("\n" + "=" * 100)
print("【2】A×A1×14-16条件: 会場フィルター最適化")
print("-" * 100)

sql_a_a1 = """
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

df_a_a1 = pd.read_sql_query(sql_a_a1, conn)

# 会場別集計
df_a_a1_venue = df_a_a1.groupby('venue_code').agg({
    'bets': 'sum',
    'hits': 'sum',
    'profit': 'sum'
}).reset_index()
df_a_a1_venue['roi_pct'] = 100.0 * df_a_a1_venue['profit'] / (df_a_a1_venue['bets'] * 100)
df_a_a1_venue = df_a_a1_venue.sort_values('profit')

print("【2-1】会場別パフォーマンス（利益 < 0円 の会場）")
poor_a_a1 = df_a_a1_venue[df_a_a1_venue['profit'] < 0]
print(poor_a_a1.to_string(index=False))

# 除外基準の評価
print("\n【2-2】除外基準の評価")

# 基準1: 利益 < -500円
exclude_a1 = df_a_a1_venue[df_a_a1_venue['profit'] < -500]['venue_code'].tolist()
df_after_a1 = df_a_a1_venue[~df_a_a1_venue['venue_code'].isin(exclude_a1)]
total_a1 = df_after_a1.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_a1 = 100.0 * total_a1['profit'] / (total_a1['bets'] * 100)
print(f"基準1: 利益 < -500円 除外 ({len(exclude_a1)}会場)")
print(f"  除外会場: {exclude_a1}")
print(f"  結果: {int(total_a1['bets'])}件, 利益{int(total_a1['profit']):+,}円, ROI {roi_a1:.1f}%")

# 基準2: ROI < 0%
exclude_a2 = df_a_a1_venue[df_a_a1_venue['roi_pct'] < 0]['venue_code'].tolist()
df_after_a2 = df_a_a1_venue[~df_a_a1_venue['venue_code'].isin(exclude_a2)]
total_a2 = df_after_a2.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_a2 = 100.0 * total_a2['profit'] / (total_a2['bets'] * 100)
print(f"\n基準2: ROI < 0% 除外 ({len(exclude_a2)}会場)")
print(f"  除外会場: {exclude_a2}")
print(f"  結果: {int(total_a2['bets'])}件, 利益{int(total_a2['profit']):+,}円, ROI {roi_a2:.1f}%")

# 現状
total_a0 = df_a_a1_venue.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_a0 = 100.0 * total_a0['profit'] / (total_a0['bets'] * 100)
print(f"\n現状（除外なし）: {int(total_a0['bets'])}件, 利益{int(total_a0['profit']):+,}円, ROI {roi_a0:.1f}%")

# ========================================
# 3. A×B1×Motor40%+条件: 詳細分析
# ========================================
print("\n" + "=" * 100)
print("【3】A×B1×Motor40%+条件: 年度別詳細分析")
print("-" * 100)

sql_a_b1 = """
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
    venue_code,
    COUNT(*) as bets,
    SUM(is_hit) as hits,
    SUM(payout) - COUNT(*) * 100 as profit,
    ROUND(100.0 * (SUM(payout) - COUNT(*) * 100) / (COUNT(*) * 100), 1) as roi_pct
FROM race_bets
GROUP BY year, venue_code
ORDER BY year, venue_code;
"""

df_a_b1 = pd.read_sql_query(sql_a_b1, conn)

# 年度別集計
df_a_b1_year = df_a_b1.groupby('year').agg({
    'bets': 'sum',
    'hits': 'sum',
    'profit': 'sum'
}).reset_index()
df_a_b1_year['roi_pct'] = 100.0 * df_a_b1_year['profit'] / (df_a_b1_year['bets'] * 100)
df_a_b1_year['hit_rate'] = 100.0 * df_a_b1_year['hits'] / df_a_b1_year['bets']

print("【3-1】年度別パフォーマンス")
print(df_a_b1_year.to_string(index=False))

# 2020-2024の会場別集計（赤字会場特定）
df_2020_2024 = df_a_b1[df_a_b1['year'] < '2025']
df_2020_2024_venue = df_2020_2024.groupby('venue_code').agg({
    'bets': 'sum',
    'hits': 'sum',
    'profit': 'sum'
}).reset_index()
df_2020_2024_venue['roi_pct'] = 100.0 * df_2020_2024_venue['profit'] / (df_2020_2024_venue['bets'] * 100)
df_2020_2024_venue = df_2020_2024_venue.sort_values('profit')

print("\n【3-2】2020-2024年 会場別パフォーマンス（利益 < 0円）")
poor_b1 = df_2020_2024_venue[df_2020_2024_venue['profit'] < 0]
print(poor_b1.to_string(index=False))

# 全体統計
total_all = df_a_b1_year.agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_all = 100.0 * total_all['profit'] / (total_all['bets'] * 100)
hit_rate_all = 100.0 * total_all['hits'] / total_all['bets']

total_2020_2024 = df_a_b1_year[df_a_b1_year['year'] < '2025'].agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_2020_2024 = 100.0 * total_2020_2024['profit'] / (total_2020_2024['bets'] * 100)

total_2025 = df_a_b1_year[df_a_b1_year['year'] == '2025'].agg({'bets': 'sum', 'hits': 'sum', 'profit': 'sum'})
roi_2025 = 100.0 * total_2025['profit'] / (total_2025['bets'] * 100)

print(f"\n【3-3】統計サマリー")
print(f"6年間合計: {int(total_all['bets'])}件, 的中{int(total_all['hits'])}回 ({hit_rate_all:.1f}%), 利益{int(total_all['profit']):+,}円, ROI {roi_all:.1f}%")
print(f"2020-2024: {int(total_2020_2024['bets'])}件, 利益{int(total_2020_2024['profit']):+,}円, ROI {roi_2020_2024:.1f}%")
print(f"2025年: {int(total_2025['bets'])}件, 利益{int(total_2025['profit']):+,}円, ROI {roi_2025:.1f}%")

# 赤字年数
deficit_years = len(df_a_b1_year[df_a_b1_year['profit'] < 0])
print(f"\n赤字年数: {deficit_years}/6年")

conn.close()

print("\n" + "=" * 100)
print("分析完了")
print("=" * 100)
