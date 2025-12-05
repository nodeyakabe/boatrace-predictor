"""
競艇場（会場）と選手の特性分析

データベースから統計情報を抽出して、
各会場の特性（1コース勝率、平均オッズなど）と
選手の傾向を分析する
"""

import sys
sys.path.append('.')

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

print("=" * 70)
print("競艇場・選手特性分析")
print("=" * 70)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# データベース接続
conn = sqlite3.connect("data/boatrace.db")

# 分析期間
start_date = "2024-04-01"
end_date = "2024-06-30"
print(f"\n分析期間: {start_date} 〜 {end_date}")

# =============================================================================
# 1. 競艇場（会場）特性分析
# =============================================================================
print("\n" + "=" * 70)
print("【1】競艇場特性分析")
print("=" * 70)

query_venue = """
SELECT
    r.venue_code,
    COUNT(DISTINCT r.id) as total_races,
    COUNT(DISTINCT res.race_id) as completed_races,

    -- 枠番別勝率（コース情報の代わりに）
    SUM(CASE WHEN e.pit_number = 1 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.pit_number = 1 THEN 1 ELSE 0 END), 0) as pit1_win_rate,
    SUM(CASE WHEN e.pit_number = 2 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.pit_number = 2 THEN 1 ELSE 0 END), 0) as pit2_win_rate,
    SUM(CASE WHEN e.pit_number = 3 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.pit_number = 3 THEN 1 ELSE 0 END), 0) as pit3_win_rate,

    -- 平均モーター2連対率
    AVG(e.second_rate) as avg_motor_2rate,

    -- 天候情報
    AVG(r.temperature) as avg_temperature,
    AVG(r.wind_speed) as avg_wind_speed,
    AVG(r.wave_height) as avg_wave_height

FROM races r
LEFT JOIN entries e ON r.id = e.race_id
LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
WHERE r.race_date BETWEEN ? AND ?
GROUP BY r.venue_code
ORDER BY total_races DESC
"""

df_venue = pd.read_sql_query(query_venue, conn, params=(start_date, end_date))

print(f"\n総会場数: {len(df_venue)}会場")
print(f"\n各会場の特性:")
print("-" * 150)
print(f"{'会場':<6} {'レース数':<8} {'1C勝率':<8} {'2C勝率':<8} {'3C勝率':<8} "
      f"{'進入変化率':<10} {'平均展示T':<10} {'平均ST':<10} {'平均気温':<8} {'平均風速':<8}")
print("-" * 150)

for _, row in df_venue.iterrows():
    print(f"{row['venue_code']:<6} "
          f"{int(row['total_races']):<8} "
          f"{row['course1_win_rate']:.1f}%    "
          f"{row['course2_win_rate']:.1f}%    "
          f"{row['course3_win_rate']:.1f}%    "
          f"{row['course_change_rate']:.1f}%      "
          f"{row['avg_exhibition_time']:.2f}s     "
          f"{row['avg_st_time']:.3f}s   "
          f"{row['avg_temperature']:.1f}℃   "
          f"{row['avg_wind_speed']:.1f}m/s")

# =============================================================================
# 2. 選手特性分析（上位選手）
# =============================================================================
print("\n" + "=" * 70)
print("【2】選手特性分析（出走回数トップ50）")
print("=" * 70)

query_racer = """
SELECT
    e.racer_number,
    e.racer_name,
    COUNT(*) as total_races,

    -- 勝率
    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
    SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as place2_rate,
    SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as place3_rate,

    -- 平均着順
    AVG(CAST(res.rank AS REAL)) as avg_rank,

    -- コース別勝率（1コースと2コース）
    SUM(CASE WHEN e.actual_course = 1 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.actual_course = 1 THEN 1 ELSE 0 END), 0) as course1_win_rate,
    SUM(CASE WHEN e.actual_course = 2 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.actual_course = 2 THEN 1 ELSE 0 END), 0) as course2_win_rate,

    -- コース取得率
    SUM(CASE WHEN e.actual_course = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as course1_get_rate,

    -- 平均展示タイム
    AVG(e.exhibition_time) as avg_exhibition_time,

    -- 平均スタートタイミング
    AVG(e.st_time) as avg_st_time,

    -- フライング回数
    SUM(CASE WHEN e.st_time < 0 THEN 1 ELSE 0 END) as flying_count,

    -- 級別（最頻値）
    e.racer_rank as racer_rank

FROM entries e
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
JOIN races r ON e.race_id = r.id
WHERE r.race_date BETWEEN ? AND ?
  AND res.rank IN ('1', '2', '3', '4', '5', '6')
GROUP BY e.racer_number, e.racer_name, e.racer_rank
HAVING COUNT(*) >= 30
ORDER BY total_races DESC
LIMIT 50
"""

df_racer = pd.read_sql_query(query_racer, conn, params=(start_date, end_date))

print(f"\n分析対象選手数: {len(df_racer)}名（30レース以上出走）")
print(f"\nトップ20選手:")
print("-" * 140)
print(f"{'選手番号':<8} {'選手名':<12} {'級別':<4} {'出走数':<6} "
      f"{'勝率':<7} {'2連率':<7} {'3連率':<7} {'平均着順':<8} "
      f"{'1C勝率':<8} {'1C取得率':<9} {'平均ST':<10}")
print("-" * 140)

for _, row in df_racer.head(20).iterrows():
    print(f"{row['racer_number']:<8} "
          f"{row['racer_name']:<12} "
          f"{row['racer_rank']:<4} "
          f"{int(row['total_races']):<6} "
          f"{row['win_rate']:.1f}%   "
          f"{row['place2_rate']:.1f}%   "
          f"{row['place3_rate']:.1f}%   "
          f"{row['avg_rank']:.2f}     "
          f"{row['course1_win_rate']:.1f}%    "
          f"{row['course1_get_rate']:.1f}%      "
          f"{row['avg_st_time']:.3f}s")

# =============================================================================
# 3. 級別分析
# =============================================================================
print("\n" + "=" * 70)
print("【3】級別別パフォーマンス")
print("=" * 70)

query_rank = """
SELECT
    e.racer_rank,
    COUNT(*) as total_races,

    -- 勝率
    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,

    -- 平均着順
    AVG(CAST(res.rank AS REAL)) as avg_rank,

    -- 1コース取得時の勝率
    SUM(CASE WHEN e.actual_course = 1 AND res.rank = '1' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN e.actual_course = 1 THEN 1 ELSE 0 END), 0) as course1_win_rate,

    -- 平均スタートタイミング
    AVG(e.st_time) as avg_st_time

FROM entries e
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
JOIN races r ON e.race_id = r.id
WHERE r.race_date BETWEEN ? AND ?
  AND res.rank IN ('1', '2', '3', '4', '5', '6')
  AND e.racer_rank IS NOT NULL
GROUP BY e.racer_rank
ORDER BY e.racer_rank
"""

df_rank = pd.read_sql_query(query_rank, conn, params=(start_date, end_date))

print(f"\n級別別統計:")
print("-" * 80)
print(f"{'級別':<6} {'出走数':<10} {'勝率':<10} {'平均着順':<10} {'1C勝率':<10} {'平均ST':<10}")
print("-" * 80)

for _, row in df_rank.iterrows():
    print(f"{row['racer_rank']:<6} "
          f"{int(row['total_races']):<10} "
          f"{row['win_rate']:.2f}%    "
          f"{row['avg_rank']:.2f}      "
          f"{row['course1_win_rate']:.1f}%     "
          f"{row['avg_st_time']:.3f}s")

# =============================================================================
# 4. 重要な特徴量の相関分析
# =============================================================================
print("\n" + "=" * 70)
print("【4】特徴量と勝利の相関分析")
print("=" * 70)

query_correlation = """
SELECT
    e.actual_course,
    e.exhibition_time,
    e.st_time,
    e.second_rate as motor_2rate,
    e.third_rate as motor_3rate,
    e.win_rate as racer_win_rate,
    CASE WHEN res.rank = '1' THEN 1 ELSE 0 END as is_win

FROM entries e
JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
JOIN races r ON e.race_id = r.id
WHERE r.race_date BETWEEN ? AND ?
  AND res.rank IN ('1', '2', '3', '4', '5', '6')
  AND e.exhibition_time IS NOT NULL
  AND e.st_time IS NOT NULL
"""

df_corr = pd.read_sql_query(query_correlation, conn, params=(start_date, end_date))

print(f"\n特徴量と勝利(is_win)の相関係数:")
correlations = df_corr.corr()['is_win'].sort_values(ascending=False)
print("-" * 60)
for feature, corr in correlations.items():
    if feature != 'is_win':
        stars = "★" * int(abs(corr) * 10)
        print(f"{feature:<25} {corr:+.4f}  {stars}")

conn.close()

print(f"\n完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
