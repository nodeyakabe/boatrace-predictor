# -*- coding: utf-8 -*-
"""
風向き×コース別勝率 詳細分析スクリプト
2024-2025年データ対象

分析1: 風向きとコース別勝率の関係
分析2: 会場別の癖・特性
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import json

# データベースパス
DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

def get_connection():
    return sqlite3.connect(str(DB_PATH))

def analyze_wind_direction_course():
    """
    分析1: 風向き×コース別勝率
    """
    print("=" * 80)
    print("分析1: 風向き×コース別勝率の詳細分析 (2024-2025)")
    print("=" * 80)

    conn = get_connection()

    # 風向きの種類を確認
    query_wind_dirs = """
    SELECT DISTINCT rc.wind_direction
    FROM race_conditions rc
    JOIN races r ON rc.race_id = r.id
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_direction IS NOT NULL
    ORDER BY rc.wind_direction
    """
    df_wind_dirs = pd.read_sql_query(query_wind_dirs, conn)
    print("\n利用可能な風向き:")
    print(df_wind_dirs['wind_direction'].tolist())

    # 風向きと風速とコース別勝率
    query_main = """
    SELECT
        rc.wind_direction,
        rc.wind_speed,
        CASE
            WHEN rc.wind_speed < 2 THEN '0-2m'
            WHEN rc.wind_speed < 4 THEN '2-4m'
            WHEN rc.wind_speed < 6 THEN '4-6m'
            ELSE '6m+'
        END as wind_speed_range,
        rd.pit_number,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_direction IS NOT NULL
    AND rc.wind_speed IS NOT NULL
    AND res.is_invalid = 0
    GROUP BY rc.wind_direction, wind_speed_range, rd.pit_number
    ORDER BY rc.wind_direction, wind_speed_range, rd.pit_number
    """

    df_main = pd.read_sql_query(query_main, conn)
    print(f"\n取得データ件数: {len(df_main)}")

    # 全体のコース別勝率（ベースライン）
    query_baseline = """
    SELECT
        rd.pit_number,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    ORDER BY rd.pit_number
    """

    df_baseline = pd.read_sql_query(query_baseline, conn)
    print("\n=== ベースライン: コース別勝率 (2024-2025全体) ===")
    print(df_baseline.to_string(index=False))

    # 向かい風 vs 追い風の分析
    # 向かい風: 風向き = "向い風", "北", "北北東", "北東", "東北東" など
    # 追い風: "追い風", "南", "南南西", "南西", "西南西" など

    # 風向き分類
    headwind_keywords = ['向い', '北', '北北東', '北東', '東北東']
    tailwind_keywords = ['追い', '南', '南南西', '南西', '西南西']

    print("\n=== 風向き分類別のコース勝率 ===")

    # 向かい風
    headwind_cond = df_main['wind_direction'].str.contains('向い', na=False)
    df_headwind = df_main[headwind_cond].groupby(['wind_speed_range', 'pit_number']).agg({
        'total_races': 'sum',
        'wins': 'sum'
    }).reset_index()
    df_headwind['win_rate'] = (df_headwind['wins'] / df_headwind['total_races'] * 100).round(2)

    print("\n--- 向かい風時のコース別勝率 ---")
    pivot_headwind = df_headwind.pivot(index='wind_speed_range', columns='pit_number', values='win_rate')
    print(pivot_headwind)

    # 追い風
    tailwind_cond = df_main['wind_direction'].str.contains('追い', na=False)
    df_tailwind = df_main[tailwind_cond].groupby(['wind_speed_range', 'pit_number']).agg({
        'total_races': 'sum',
        'wins': 'sum'
    }).reset_index()
    df_tailwind['win_rate'] = (df_tailwind['wins'] / df_tailwind['total_races'] * 100).round(2)

    print("\n--- 追い風時のコース別勝率 ---")
    pivot_tailwind = df_tailwind.pivot(index='wind_speed_range', columns='pit_number', values='win_rate')
    print(pivot_tailwind)

    conn.close()

    return df_main, df_baseline

def analyze_venue_characteristics():
    """
    分析2: 会場別の癖・特性
    """
    print("\n" + "=" * 80)
    print("分析2: 会場別の癖・特性 (2024-2025)")
    print("=" * 80)

    conn = get_connection()

    # 会場コードと名前
    query_venues = """
    SELECT code, name FROM venues ORDER BY code
    """
    df_venues = pd.read_sql_query(query_venues, conn)

    # 会場別のコース勝率
    query_venue_course = """
    SELECT
        r.venue_code,
        v.name as venue_name,
        rd.pit_number,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    LEFT JOIN venues v ON r.venue_code = v.code
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY r.venue_code, rd.pit_number
    ORDER BY r.venue_code, rd.pit_number
    """

    df_venue_course = pd.read_sql_query(query_venue_course, conn)

    # ピボットテーブル作成
    pivot_venue = df_venue_course.pivot(index=['venue_code', 'venue_name'], columns='pit_number', values='win_rate')

    print("\n=== 会場別コース勝率 ===")
    print(pivot_venue.to_string())

    # 1コース勝率でソート
    df_course1 = df_venue_course[df_venue_course['pit_number'] == 1].sort_values('win_rate', ascending=False)
    print("\n=== 1コース勝率ランキング ===")
    print(df_course1[['venue_code', 'venue_name', 'total_races', 'wins', 'win_rate']].to_string(index=False))

    # 特定会場の詳細分析 (桐生01, 江戸川07, 児島14, 宮島13, 丸亀15)
    target_venues = ['01', '07', '14', '13', '15']

    print("\n=== 重点分析対象会場の詳細 ===")
    for venue in target_venues:
        df_v = df_venue_course[df_venue_course['venue_code'] == venue]
        if len(df_v) > 0:
            venue_name = df_v['venue_name'].iloc[0]
            print(f"\n--- {venue}: {venue_name} ---")
            print(df_v[['pit_number', 'total_races', 'wins', 'win_rate']].to_string(index=False))

    conn.close()

    return df_venue_course

def analyze_venue_wind_impact():
    """
    分析3: 会場×風向き×コース勝率
    """
    print("\n" + "=" * 80)
    print("分析3: 会場×風向き×風速×コース勝率")
    print("=" * 80)

    conn = get_connection()

    # 会場×風向き×風速×コース勝率
    query = """
    SELECT
        r.venue_code,
        v.name as venue_name,
        CASE
            WHEN rc.wind_direction LIKE '%向い%' THEN '向かい風'
            WHEN rc.wind_direction LIKE '%追い%' THEN '追い風'
            ELSE 'その他'
        END as wind_type,
        CASE
            WHEN rc.wind_speed < 2 THEN '0-2m'
            WHEN rc.wind_speed < 4 THEN '2-4m'
            WHEN rc.wind_speed < 6 THEN '4-6m'
            ELSE '6m+'
        END as wind_speed_range,
        rd.pit_number,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    LEFT JOIN venues v ON r.venue_code = v.code
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_direction IS NOT NULL
    AND rc.wind_speed IS NOT NULL
    AND res.is_invalid = 0
    GROUP BY r.venue_code, wind_type, wind_speed_range, rd.pit_number
    ORDER BY r.venue_code, wind_type, wind_speed_range, rd.pit_number
    """

    df = pd.read_sql_query(query, conn)
    print(f"\n取得データ件数: {len(df)}")

    # 重点会場の詳細分析
    target_venues = ['01', '07', '14', '13', '15']

    for venue in target_venues:
        df_v = df[df['venue_code'] == venue]
        if len(df_v) > 0:
            venue_name = df_v['venue_name'].iloc[0]
            print(f"\n=== {venue}: {venue_name} ===")

            # 風タイプ×風速×コースでピボット
            for wind_type in ['向かい風', '追い風', 'その他']:
                df_wt = df_v[df_v['wind_type'] == wind_type]
                if len(df_wt) > 0:
                    print(f"\n--- {wind_type} ---")
                    pivot = df_wt.pivot_table(
                        index='wind_speed_range',
                        columns='pit_number',
                        values='win_rate',
                        aggfunc='mean'
                    )
                    print(pivot.to_string())

    conn.close()

    return df

def analyze_strong_wind_impact():
    """
    分析4: 強風（4m以上）時の影響分析
    """
    print("\n" + "=" * 80)
    print("分析4: 強風（4m以上）時の影響分析")
    print("=" * 80)

    conn = get_connection()

    # 全体平均
    query_overall = """
    SELECT
        rd.pit_number,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    ORDER BY rd.pit_number
    """
    df_overall = pd.read_sql_query(query_overall, conn)
    print("\n=== 全体平均（ベースライン）===")
    print(df_overall.to_string(index=False))

    # 強風（4m+）×向かい風時
    query_strong_headwind = """
    SELECT
        rd.pit_number,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_direction LIKE '%向い%'
    AND rc.wind_speed >= 4
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    ORDER BY rd.pit_number
    """
    df_strong_headwind = pd.read_sql_query(query_strong_headwind, conn)
    print("\n=== 強風（4m+）× 向かい風 ===")
    print(df_strong_headwind.to_string(index=False))

    # 強風（4m+）×追い風時
    query_strong_tailwind = """
    SELECT
        rd.pit_number,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_direction LIKE '%追い%'
    AND rc.wind_speed >= 4
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    ORDER BY rd.pit_number
    """
    df_strong_tailwind = pd.read_sql_query(query_strong_tailwind, conn)
    print("\n=== 強風（4m+）× 追い風 ===")
    print(df_strong_tailwind.to_string(index=False))

    # 変化率計算
    print("\n=== 強風時の勝率変化（ベースライン比）===")
    baseline_rates = df_overall.set_index('pit_number')['win_rate']

    print("\n向かい風4m+時の変化:")
    if len(df_strong_headwind) > 0:
        headwind_rates = df_strong_headwind.set_index('pit_number')['win_rate']
        for pit in range(1, 7):
            if pit in baseline_rates.index and pit in headwind_rates.index:
                change = headwind_rates[pit] - baseline_rates[pit]
                change_pct = (headwind_rates[pit] / baseline_rates[pit] - 1) * 100
                print(f"  {pit}コース: {baseline_rates[pit]:.1f}% → {headwind_rates[pit]:.1f}% ({change:+.1f}pt, {change_pct:+.1f}%)")

    print("\n追い風4m+時の変化:")
    if len(df_strong_tailwind) > 0:
        tailwind_rates = df_strong_tailwind.set_index('pit_number')['win_rate']
        for pit in range(1, 7):
            if pit in baseline_rates.index and pit in tailwind_rates.index:
                change = tailwind_rates[pit] - baseline_rates[pit]
                change_pct = (tailwind_rates[pit] / baseline_rates[pit] - 1) * 100
                print(f"  {pit}コース: {baseline_rates[pit]:.1f}% → {tailwind_rates[pit]:.1f}% ({change:+.1f}pt, {change_pct:+.1f}%)")

    conn.close()

def analyze_venue_stability():
    """
    分析5: 会場安定性分析（予測精度の観点から）
    """
    print("\n" + "=" * 80)
    print("分析5: 会場安定性分析（インコース勝率のばらつき）")
    print("=" * 80)

    conn = get_connection()

    # 会場×月別の1コース勝率
    query = """
    SELECT
        r.venue_code,
        v.name as venue_name,
        strftime('%Y-%m', r.race_date) as month,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' AND res.pit_number = 1 THEN 1 ELSE 0 END) as course1_wins,
        ROUND(AVG(CASE WHEN res.rank = '1' AND res.pit_number = 1 THEN 1.0 ELSE 0.0 END) * 100, 2) as course1_win_rate
    FROM races r
    LEFT JOIN venues v ON r.venue_code = v.code
    JOIN results res ON r.id = res.race_id
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY r.venue_code, month
    ORDER BY r.venue_code, month
    """

    df = pd.read_sql_query(query, conn)

    # 会場別の統計
    venue_stats = df.groupby(['venue_code', 'venue_name']).agg({
        'total_races': 'sum',
        'course1_wins': 'sum',
        'course1_win_rate': ['mean', 'std', 'min', 'max']
    }).reset_index()

    venue_stats.columns = ['venue_code', 'venue_name', 'total_races', 'course1_wins',
                           'mean_win_rate', 'std_win_rate', 'min_win_rate', 'max_win_rate']
    venue_stats['actual_win_rate'] = (venue_stats['course1_wins'] / venue_stats['total_races'] * 100).round(2)
    venue_stats['volatility'] = venue_stats['max_win_rate'] - venue_stats['min_win_rate']

    # 安定性でソート（標準偏差が小さい順）
    venue_stats_sorted = venue_stats.sort_values('std_win_rate', ascending=True)

    print("\n=== 会場別1コース勝率の安定性（標準偏差が小さい順 = 安定）===")
    print(venue_stats_sorted[['venue_code', 'venue_name', 'total_races', 'actual_win_rate',
                              'std_win_rate', 'min_win_rate', 'max_win_rate', 'volatility']].to_string(index=False))

    # 安定会場 vs 不安定会場
    stable_venues = venue_stats_sorted.head(8)
    unstable_venues = venue_stats_sorted.tail(8)

    print("\n=== 安定会場（予測しやすい）===")
    print(stable_venues[['venue_code', 'venue_name', 'actual_win_rate', 'std_win_rate']].to_string(index=False))

    print("\n=== 不安定会場（予測しにくい）===")
    print(unstable_venues[['venue_code', 'venue_name', 'actual_win_rate', 'std_win_rate']].to_string(index=False))

    conn.close()

    return venue_stats

def generate_wind_adjustment_coefficients():
    """
    風向き補正係数の生成
    """
    print("\n" + "=" * 80)
    print("風向き補正係数の算出")
    print("=" * 80)

    conn = get_connection()

    # ベースライン取得
    query_baseline = """
    SELECT
        rd.pit_number,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as baseline_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    ORDER BY rd.pit_number
    """
    df_baseline = pd.read_sql_query(query_baseline, conn)
    baseline_dict = dict(zip(df_baseline['pit_number'], df_baseline['baseline_rate']))

    # 風向き×風速×コース別勝率
    query_wind = """
    SELECT
        CASE
            WHEN rc.wind_direction LIKE '%向い%' THEN 'headwind'
            WHEN rc.wind_direction LIKE '%追い%' THEN 'tailwind'
            ELSE 'other'
        END as wind_type,
        CASE
            WHEN rc.wind_speed < 2 THEN '0-2'
            WHEN rc.wind_speed < 4 THEN '2-4'
            WHEN rc.wind_speed < 6 THEN '4-6'
            ELSE '6+'
        END as wind_speed_range,
        rd.pit_number,
        COUNT(*) as total_races,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_direction IS NOT NULL
    AND rc.wind_speed IS NOT NULL
    AND res.is_invalid = 0
    GROUP BY wind_type, wind_speed_range, rd.pit_number
    ORDER BY wind_type, wind_speed_range, rd.pit_number
    """

    df_wind = pd.read_sql_query(query_wind, conn)

    # 補正係数計算
    coefficients = {}

    print("\n=== 風向き補正係数 ===")
    for wind_type in ['headwind', 'tailwind']:
        coefficients[wind_type] = {}
        df_wt = df_wind[df_wind['wind_type'] == wind_type]

        print(f"\n--- {wind_type} ---")
        for wind_range in ['0-2', '2-4', '4-6', '6+']:
            coefficients[wind_type][wind_range] = {}
            df_wr = df_wt[df_wt['wind_speed_range'] == wind_range]

            print(f"\n風速 {wind_range}m:")
            for pit in range(1, 7):
                df_pit = df_wr[df_wr['pit_number'] == pit]
                if len(df_pit) > 0 and df_pit['total_races'].iloc[0] >= 100:
                    actual_rate = df_pit['win_rate'].iloc[0]
                    base_rate = baseline_dict.get(pit, 0)
                    if base_rate > 0:
                        coef = actual_rate / base_rate
                        coefficients[wind_type][wind_range][pit] = round(coef, 3)
                        change_pct = (coef - 1) * 100
                        samples = df_pit['total_races'].iloc[0]
                        print(f"  {pit}コース: 係数={coef:.3f} ({change_pct:+.1f}%) [n={samples}]")

    conn.close()

    return coefficients

def main():
    """メイン実行"""
    print("=" * 80)
    print("風向き×コース別勝率 & 会場特性 詳細分析")
    print("対象期間: 2024-01-01 ~ 2025-12-31")
    print("=" * 80)

    # 分析1: 風向き×コース別勝率
    df_wind, df_baseline = analyze_wind_direction_course()

    # 分析2: 会場特性
    df_venue = analyze_venue_characteristics()

    # 分析3: 会場×風向き
    df_venue_wind = analyze_venue_wind_impact()

    # 分析4: 強風時の影響
    analyze_strong_wind_impact()

    # 分析5: 会場安定性
    venue_stats = analyze_venue_stability()

    # 補正係数生成
    coefficients = generate_wind_adjustment_coefficients()

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

    return coefficients

if __name__ == "__main__":
    main()
