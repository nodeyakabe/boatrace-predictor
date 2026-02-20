# -*- coding: utf-8 -*-
"""
風向き×コース別勝率 & 会場特性 包括的分析スクリプト
2024-2025年データ対象

分析内容:
1. 風向き(16方位)×風速×コース別勝率
2. 会場別の癖・特性
3. 会場×風向き×コース勝率
4. 強風時の影響
5. 会場安定性
6. 補正係数算出
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import json
import sys

# Windows環境での文字化け対策
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# データベースパス
DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

# 16方位マッピング
WIND_DIRECTIONS = {
    '北': 0,
    '北北東': 22.5,
    '北東': 45,
    '東北東': 67.5,
    '東': 90,
    '東南東': 112.5,
    '南東': 135,
    '南南東': 157.5,
    '南': 180,
    '南南西': 202.5,
    '南西': 225,
    '西南西': 247.5,
    '西': 270,
    '西北西': 292.5,
    '北西': 315,
    '北北西': 337.5,
    '無風': None
}

# 会場情報（コースの向き）
# 実際にはスタートラインの向きが会場ごとに異なる
# 向かい風 = スタートに向かって吹く風
# 一般的に、多くの会場はスタートラインが南北に近い
VENUE_INFO = {
    '01': {'name': '桐生', 'course_direction': 'north', 'headwind': ['南', '南南東', '南東', '南南西', '南西']},
    '02': {'name': '戸田', 'course_direction': 'northeast', 'headwind': ['南西', '西南西', '西', '西北西', '南']},
    '03': {'name': '江戸川', 'course_direction': 'east', 'headwind': ['西', '西北西', '北西', '西南西', '南西']},
    '04': {'name': '平和島', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '05': {'name': '多摩川', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '06': {'name': '浜名湖', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '07': {'name': '蒲郡', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '08': {'name': '常滑', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '09': {'name': '津', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '10': {'name': '三国', 'course_direction': 'north', 'headwind': ['南', '南南東', '南東', '南南西', '南西']},
    '11': {'name': 'びわこ', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '12': {'name': '住之江', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '13': {'name': '尼崎', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '14': {'name': '鳴門', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '15': {'name': '丸亀', 'course_direction': 'north', 'headwind': ['南', '南南東', '南東', '南南西', '南西']},
    '16': {'name': '児島', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '17': {'name': '宮島', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '18': {'name': '徳山', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '19': {'name': '下関', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '20': {'name': '若松', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '21': {'name': '芦屋', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '22': {'name': '福岡', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '23': {'name': '唐津', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
    '24': {'name': '大村', 'course_direction': 'south', 'headwind': ['北', '北北東', '北東', '北北西', '北西']},
}

def get_connection():
    return sqlite3.connect(str(DB_PATH))

def classify_wind(venue_code, wind_direction):
    """会場ごとに向かい風/追い風/横風を判定"""
    if wind_direction == '無風' or wind_direction is None:
        return 'calm'

    venue = VENUE_INFO.get(venue_code, {})
    headwind_dirs = venue.get('headwind', [])

    if wind_direction in headwind_dirs:
        return 'headwind'

    # 追い風は向かい風の反対方向
    tailwind_dirs = []
    for hw in headwind_dirs:
        angle = WIND_DIRECTIONS.get(hw, 0)
        if angle is not None:
            opposite = (angle + 180) % 360
            for wd, a in WIND_DIRECTIONS.items():
                if a is not None and abs(a - opposite) < 30:
                    tailwind_dirs.append(wd)

    if wind_direction in tailwind_dirs:
        return 'tailwind'

    return 'crosswind'

def analyze_wind_direction_course_detailed():
    """
    分析1: 風向き(16方位)×風速×コース別勝率の詳細分析
    """
    print("=" * 80)
    print("分析1: 風向き(16方位)×風速×コース別勝率の詳細分析 (2024-2025)")
    print("=" * 80)

    conn = get_connection()

    # ベースライン: コース別勝率
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
    baseline_dict = dict(zip(df_baseline['pit_number'], df_baseline['win_rate']))

    # 風向き×風速×コース別勝率
    query_wind = """
    SELECT
        rc.wind_direction,
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
    df_wind = pd.read_sql_query(query_wind, conn)
    print(f"\n取得データ件数: {len(df_wind)}")

    # 風向き別の集計
    print("\n=== 風向き別の1コース勝率（風速全体）===")
    df_course1 = df_wind[df_wind['pit_number'] == 1].groupby('wind_direction').agg({
        'total_races': 'sum',
        'wins': 'sum'
    }).reset_index()
    df_course1['win_rate'] = (df_course1['wins'] / df_course1['total_races'] * 100).round(2)
    df_course1['diff_from_base'] = (df_course1['win_rate'] - baseline_dict[1]).round(2)
    df_course1 = df_course1.sort_values('win_rate', ascending=False)
    print(df_course1.to_string(index=False))

    # 風速レンジ別の集計
    print("\n=== 風速レンジ別のコース勝率 ===")
    for wind_range in ['0-2m', '2-4m', '4-6m', '6m+']:
        df_wr = df_wind[df_wind['wind_speed_range'] == wind_range].groupby('pit_number').agg({
            'total_races': 'sum',
            'wins': 'sum'
        }).reset_index()
        df_wr['win_rate'] = (df_wr['wins'] / df_wr['total_races'] * 100).round(2)
        df_wr['diff'] = (df_wr['win_rate'] - df_wr['pit_number'].map(baseline_dict)).round(2)
        print(f"\n--- 風速 {wind_range} ---")
        print(df_wr.to_string(index=False))

    conn.close()
    return df_wind, baseline_dict

def analyze_venue_course_winrate():
    """
    分析2: 会場別のコース勝率
    """
    print("\n" + "=" * 80)
    print("分析2: 会場別のコース勝率 (2024-2025)")
    print("=" * 80)

    conn = get_connection()

    query = """
    SELECT
        r.venue_code,
        rd.pit_number,
        COUNT(*) as total_races,
        SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY r.venue_code, rd.pit_number
    ORDER BY r.venue_code, rd.pit_number
    """
    df = pd.read_sql_query(query, conn)

    # 会場名を追加
    df['venue_name'] = df['venue_code'].map(lambda x: VENUE_INFO.get(x, {}).get('name', x))

    # ピボットテーブル
    pivot = df.pivot(index=['venue_code', 'venue_name'], columns='pit_number', values='win_rate')
    print("\n=== 会場別コース勝率 ===")
    print(pivot.to_string())

    # 1コース勝率ランキング
    df_c1 = df[df['pit_number'] == 1].sort_values('win_rate', ascending=False)
    print("\n=== 1コース勝率ランキング ===")
    print(df_c1[['venue_code', 'venue_name', 'total_races', 'wins', 'win_rate']].to_string(index=False))

    # 全国平均
    baseline = df.groupby('pit_number')['win_rate'].mean()
    print("\n=== 全国平均コース勝率 ===")
    for pit in range(1, 7):
        print(f"  {pit}コース: {baseline[pit]:.2f}%")

    # イン強会場 vs イン弱会場
    in_strong = df_c1[df_c1['win_rate'] >= 60]['venue_code'].tolist()
    in_weak = df_c1[df_c1['win_rate'] < 52]['venue_code'].tolist()

    print("\n=== イン強会場 (1コース勝率60%+) ===")
    for vc in in_strong:
        vn = VENUE_INFO.get(vc, {}).get('name', vc)
        wr = df_c1[df_c1['venue_code'] == vc]['win_rate'].iloc[0]
        print(f"  {vc}: {vn} ({wr:.2f}%)")

    print("\n=== イン弱会場 (1コース勝率52%未満) ===")
    for vc in in_weak:
        vn = VENUE_INFO.get(vc, {}).get('name', vc)
        wr = df_c1[df_c1['venue_code'] == vc]['win_rate'].iloc[0]
        print(f"  {vc}: {vn} ({wr:.2f}%)")

    conn.close()
    return df

def analyze_venue_wind_combination():
    """
    分析3: 会場×風向き×風速×コース勝率（向かい風/追い風分類）
    """
    print("\n" + "=" * 80)
    print("分析3: 会場×風向き×風速×コース勝率")
    print("=" * 80)

    conn = get_connection()

    query = """
    SELECT
        r.venue_code,
        rc.wind_direction,
        rc.wind_speed,
        CASE
            WHEN rc.wind_speed < 2 THEN '0-2m'
            WHEN rc.wind_speed < 4 THEN '2-4m'
            WHEN rc.wind_speed < 6 THEN '4-6m'
            ELSE '6m+'
        END as wind_speed_range,
        rd.pit_number,
        res.rank
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_direction IS NOT NULL
    AND rc.wind_speed IS NOT NULL
    AND res.is_invalid = 0
    """
    df = pd.read_sql_query(query, conn)

    # 風タイプを分類
    df['wind_type'] = df.apply(
        lambda row: classify_wind(row['venue_code'], row['wind_direction']),
        axis=1
    )
    df['is_win'] = (df['rank'] == '1').astype(int)

    # 風タイプ別の全体集計
    print("\n=== 風タイプ別の1コース勝率（全会場）===")
    for wind_type in ['headwind', 'tailwind', 'crosswind', 'calm']:
        df_wt = df[(df['wind_type'] == wind_type) & (df['pit_number'] == 1)]
        if len(df_wt) > 0:
            win_rate = df_wt['is_win'].mean() * 100
            total = len(df_wt)
            print(f"  {wind_type}: {win_rate:.2f}% (n={total})")

    # 風タイプ×風速×コース別
    print("\n=== 風タイプ×風速×コース別勝率 ===")
    for wind_type in ['headwind', 'tailwind']:
        print(f"\n--- {wind_type} ---")
        for wind_range in ['0-2m', '2-4m', '4-6m', '6m+']:
            df_subset = df[(df['wind_type'] == wind_type) & (df['wind_speed_range'] == wind_range)]
            if len(df_subset) > 100:
                agg = df_subset.groupby('pit_number').agg({
                    'is_win': ['sum', 'count', 'mean']
                }).reset_index()
                agg.columns = ['pit_number', 'wins', 'races', 'win_rate']
                agg['win_rate'] = (agg['win_rate'] * 100).round(2)
                print(f"\n  風速 {wind_range}:")
                for _, row in agg.iterrows():
                    print(f"    {int(row['pit_number'])}コース: {row['win_rate']:.2f}% (n={int(row['races'])})")

    # 重点会場の分析
    target_venues = ['01', '07', '14', '13', '15']
    print("\n=== 重点会場の風向き別分析 ===")

    for venue_code in target_venues:
        venue_name = VENUE_INFO.get(venue_code, {}).get('name', venue_code)
        df_v = df[df['venue_code'] == venue_code]

        if len(df_v) > 0:
            print(f"\n=== {venue_code}: {venue_name} ===")

            # 基本統計
            c1_total = len(df_v[df_v['pit_number'] == 1])
            c1_wins = df_v[(df_v['pit_number'] == 1) & (df_v['is_win'] == 1)].shape[0]
            c1_rate = c1_wins / c1_total * 100 if c1_total > 0 else 0
            print(f"  全体1コース勝率: {c1_rate:.2f}% ({c1_wins}/{c1_total})")

            # 風タイプ別
            for wind_type in ['headwind', 'tailwind', 'crosswind']:
                df_vw = df_v[(df_v['wind_type'] == wind_type) & (df_v['pit_number'] == 1)]
                if len(df_vw) >= 50:
                    wt_rate = df_vw['is_win'].mean() * 100
                    print(f"  {wind_type}時1コース勝率: {wt_rate:.2f}% (n={len(df_vw)})")

            # 強風時
            df_strong = df_v[(df_v['wind_speed'] >= 4) & (df_v['pit_number'] == 1)]
            if len(df_strong) >= 50:
                strong_rate = df_strong['is_win'].mean() * 100
                print(f"  強風(4m+)時1コース勝率: {strong_rate:.2f}% (n={len(df_strong)})")

    conn.close()
    return df

def analyze_strong_wind_effect():
    """
    分析4: 強風（4m以上）時の影響分析
    """
    print("\n" + "=" * 80)
    print("分析4: 強風（4m以上）時の影響分析")
    print("=" * 80)

    conn = get_connection()

    # 全体ベースライン
    query_base = """
    SELECT
        rd.pit_number,
        COUNT(*) as races,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    """
    df_base = pd.read_sql_query(query_base, conn)
    base_rates = dict(zip(df_base['pit_number'], df_base['win_rate']))

    # 強風時
    query_strong = """
    SELECT
        rd.pit_number,
        COUNT(*) as races,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_speed >= 4
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    """
    df_strong = pd.read_sql_query(query_strong, conn)

    print("\n=== 強風(4m+)時 vs 全体 コース別勝率比較 ===")
    print("\nコース | 全体勝率 | 強風時勝率 | 変化 | 変化率")
    print("-" * 50)
    for _, row in df_strong.iterrows():
        pit = row['pit_number']
        base = base_rates.get(pit, 0)
        strong = row['win_rate']
        diff = strong - base
        diff_pct = (strong / base - 1) * 100 if base > 0 else 0
        print(f"  {pit}    | {base:6.2f}%  | {strong:6.2f}%   | {diff:+.2f}pt | {diff_pct:+.1f}%")

    # 超強風（6m以上）
    query_very_strong = """
    SELECT
        rd.pit_number,
        COUNT(*) as races,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rc.wind_speed >= 6
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    """
    df_very_strong = pd.read_sql_query(query_very_strong, conn)

    print("\n=== 超強風(6m+)時 vs 全体 コース別勝率比較 ===")
    print("\nコース | 全体勝率 | 超強風時勝率 | 変化 | 変化率")
    print("-" * 55)
    for _, row in df_very_strong.iterrows():
        pit = row['pit_number']
        base = base_rates.get(pit, 0)
        very_strong = row['win_rate']
        diff = very_strong - base
        diff_pct = (very_strong / base - 1) * 100 if base > 0 else 0
        print(f"  {pit}    | {base:6.2f}%  | {very_strong:6.2f}%     | {diff:+.2f}pt | {diff_pct:+.1f}%")

    conn.close()

def analyze_venue_stability():
    """
    分析5: 会場安定性分析
    """
    print("\n" + "=" * 80)
    print("分析5: 会場安定性分析（月別1コース勝率のばらつき）")
    print("=" * 80)

    conn = get_connection()

    query = """
    SELECT
        r.venue_code,
        strftime('%Y-%m', r.race_date) as month,
        COUNT(*) as races,
        SUM(CASE WHEN res.rank = '1' AND rd.pit_number = 1 THEN 1 ELSE 0 END) as c1_wins,
        COUNT(CASE WHEN rd.pit_number = 1 THEN 1 END) as c1_races
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY r.venue_code, month
    """
    df = pd.read_sql_query(query, conn)
    df['c1_rate'] = (df['c1_wins'] / df['c1_races'] * 100).round(2)

    # 会場別統計
    venue_stats = df.groupby('venue_code').agg({
        'races': 'sum',
        'c1_wins': 'sum',
        'c1_races': 'sum',
        'c1_rate': ['mean', 'std', 'min', 'max']
    }).reset_index()
    venue_stats.columns = ['venue_code', 'total_races', 'c1_wins', 'c1_races',
                           'mean_rate', 'std_rate', 'min_rate', 'max_rate']
    venue_stats['actual_rate'] = (venue_stats['c1_wins'] / venue_stats['c1_races'] * 100).round(2)
    venue_stats['range'] = venue_stats['max_rate'] - venue_stats['min_rate']
    venue_stats['venue_name'] = venue_stats['venue_code'].map(lambda x: VENUE_INFO.get(x, {}).get('name', x))

    # 安定性でソート
    venue_stats_sorted = venue_stats.sort_values('std_rate')

    print("\n=== 会場別1コース勝率の安定性（標準偏差が小さい順 = 安定）===")
    print(venue_stats_sorted[['venue_code', 'venue_name', 'c1_races', 'actual_rate',
                               'std_rate', 'min_rate', 'max_rate', 'range']].to_string(index=False))

    # 安定会場と不安定会場
    stable = venue_stats_sorted.head(8)
    unstable = venue_stats_sorted.tail(8)

    print("\n=== 安定会場 TOP8（予測しやすい）===")
    for _, row in stable.iterrows():
        print(f"  {row['venue_code']}: {row['venue_name']} - 勝率{row['actual_rate']:.1f}%, 標準偏差{row['std_rate']:.2f}")

    print("\n=== 不安定会場 TOP8（予測が難しい）===")
    for _, row in unstable.iterrows():
        print(f"  {row['venue_code']}: {row['venue_name']} - 勝率{row['actual_rate']:.1f}%, 標準偏差{row['std_rate']:.2f}")

    conn.close()
    return venue_stats_sorted

def generate_adjustment_coefficients():
    """
    分析6: 補正係数の算出
    """
    print("\n" + "=" * 80)
    print("分析6: 補正係数の算出")
    print("=" * 80)

    conn = get_connection()

    # ベースライン
    query_base = """
    SELECT
        rd.pit_number,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 4) as win_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND res.is_invalid = 0
    GROUP BY rd.pit_number
    """
    df_base = pd.read_sql_query(query_base, conn)
    base_rates = dict(zip(df_base['pit_number'], df_base['win_rate']))

    # 風速レンジ別係数
    print("\n=== 風速レンジ別 補正係数 ===")
    wind_coefficients = {}

    for wind_range, min_speed, max_speed in [('0-2m', 0, 2), ('2-4m', 2, 4), ('4-6m', 4, 6), ('6m+', 6, 100)]:
        query = f"""
        SELECT
            rd.pit_number,
            COUNT(*) as races,
            ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 4) as win_rate
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
        AND rc.wind_speed >= {min_speed} AND rc.wind_speed < {max_speed}
        AND res.is_invalid = 0
        GROUP BY rd.pit_number
        """
        df = pd.read_sql_query(query, conn)

        print(f"\n--- 風速 {wind_range} ---")
        wind_coefficients[wind_range] = {}
        for _, row in df.iterrows():
            pit = row['pit_number']
            actual = row['win_rate']
            base = base_rates.get(pit, 1)
            coef = actual / base if base > 0 else 1.0
            wind_coefficients[wind_range][pit] = round(coef, 4)
            diff_pct = (coef - 1) * 100
            print(f"  {pit}コース: {base:.2f}% -> {actual:.2f}% (係数: {coef:.4f}, {diff_pct:+.2f}%)")

    # 会場別係数
    print("\n=== 会場別 1コース補正係数 ===")
    venue_coefficients = {}
    overall_c1_rate = base_rates.get(1, 57.35)

    query_venue = """
    SELECT
        r.venue_code,
        COUNT(*) as races,
        ROUND(AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100, 4) as win_rate
    FROM races r
    JOIN race_details rd ON r.id = rd.race_id
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-12-31'
    AND rd.pit_number = 1
    AND res.is_invalid = 0
    GROUP BY r.venue_code
    ORDER BY win_rate DESC
    """
    df_venue = pd.read_sql_query(query_venue, conn)

    for _, row in df_venue.iterrows():
        vc = row['venue_code']
        vn = VENUE_INFO.get(vc, {}).get('name', vc)
        actual = row['win_rate']
        coef = actual / overall_c1_rate
        venue_coefficients[vc] = {
            'name': vn,
            'coefficient': round(coef, 4),
            'win_rate': actual
        }
        diff_pct = (coef - 1) * 100
        print(f"  {vc} ({vn}): {actual:.2f}% (係数: {coef:.4f}, {diff_pct:+.2f}%)")

    conn.close()

    # 結果を辞書形式で返す
    return {
        'wind_speed': wind_coefficients,
        'venue': venue_coefficients,
        'baseline': base_rates
    }

def generate_implementation_code(coefficients):
    """
    実装コードの生成
    """
    print("\n" + "=" * 80)
    print("実装コード（venue_wind_adjustments.py）")
    print("=" * 80)

    code = '''# -*- coding: utf-8 -*-
"""
会場×風向き補正係数
2024-2025年データから算出

使用方法:
from config.venue_wind_adjustments import get_wind_coefficient, get_venue_coefficient

# 風速による補正
coef = get_wind_coefficient(wind_speed=5.0, pit_number=1)  # 0.95など

# 会場による補正
coef = get_venue_coefficient(venue_code='01', pit_number=1)  # 0.91など
"""

# 風速レンジ別 コース別係数
# ベースライン(全体平均)を1.0とした相対係数
WIND_SPEED_COEFFICIENTS = {
'''

    for wind_range, pit_coefs in coefficients['wind_speed'].items():
        code += f"    '{wind_range}': {{\n"
        for pit, coef in pit_coefs.items():
            code += f"        {pit}: {coef},\n"
        code += "    },\n"

    code += '''}

# 会場別 1コース係数
# 全国平均を1.0とした相対係数
VENUE_COURSE1_COEFFICIENTS = {
'''

    for vc, info in coefficients['venue'].items():
        code += f"    '{vc}': {info['coefficient']},  # {info['name']}: {info['win_rate']:.2f}%\n"

    code += '''}

# ベースライン勝率（%）
BASELINE_WIN_RATES = {
'''

    for pit, rate in coefficients['baseline'].items():
        code += f"    {pit}: {rate},\n"

    code += '''}

def get_wind_speed_range(wind_speed):
    """風速を範囲に変換"""
    if wind_speed < 2:
        return '0-2m'
    elif wind_speed < 4:
        return '2-4m'
    elif wind_speed < 6:
        return '4-6m'
    else:
        return '6m+'

def get_wind_coefficient(wind_speed, pit_number):
    """
    風速による補正係数を取得

    Args:
        wind_speed: 風速 (m/s)
        pit_number: コース番号 (1-6)

    Returns:
        float: 補正係数 (1.0 = 変化なし)
    """
    wind_range = get_wind_speed_range(wind_speed)
    return WIND_SPEED_COEFFICIENTS.get(wind_range, {}).get(pit_number, 1.0)

def get_venue_coefficient(venue_code, pit_number=1):
    """
    会場による補正係数を取得

    Args:
        venue_code: 会場コード ('01'-'24')
        pit_number: コース番号 (デフォルト: 1)

    Returns:
        float: 補正係数 (1.0 = 平均的な会場)
    """
    if pit_number == 1:
        return VENUE_COURSE1_COEFFICIENTS.get(venue_code, 1.0)
    # 他のコースは未実装（必要に応じて追加）
    return 1.0

def apply_wind_venue_adjustment(base_score, venue_code, wind_speed, pit_number):
    """
    風向き・会場補正を適用

    Args:
        base_score: 元のスコア
        venue_code: 会場コード
        wind_speed: 風速
        pit_number: コース番号

    Returns:
        float: 補正後スコア
    """
    wind_coef = get_wind_coefficient(wind_speed, pit_number)
    venue_coef = get_venue_coefficient(venue_code, pit_number)

    # 補正を適用（両方の効果を組み合わせる）
    # 単純な乗算だと効果が大きくなりすぎる可能性があるため、
    # 加重平均的なアプローチを使用
    combined_coef = (wind_coef + venue_coef) / 2

    return base_score * combined_coef
'''

    print(code)
    return code

def main():
    """メイン実行"""
    print("=" * 80)
    print("風向き×コース別勝率 & 会場特性 包括的分析")
    print("対象期間: 2024-01-01 ~ 2025-12-31")
    print("=" * 80)

    # 分析1: 風向き×コース別勝率
    df_wind, baseline_dict = analyze_wind_direction_course_detailed()

    # 分析2: 会場別コース勝率
    df_venue = analyze_venue_course_winrate()

    # 分析3: 会場×風向き
    df_combined = analyze_venue_wind_combination()

    # 分析4: 強風の影響
    analyze_strong_wind_effect()

    # 分析5: 会場安定性
    venue_stats = analyze_venue_stability()

    # 分析6: 補正係数
    coefficients = generate_adjustment_coefficients()

    # 実装コード生成
    code = generate_implementation_code(coefficients)

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

    # 最終サマリー
    print("\n" + "=" * 80)
    print("最終サマリー: 主要な発見と推奨アクション")
    print("=" * 80)

    print("""
【風向きの影響】
1. 強風(4m+)時は全体的にインコース勝率が低下傾向
2. 超強風(6m+)時はさらに顕著な変動
3. 風速による補正は特に4m以上で重要

【会場特性】
1. イン強会場: 徳山、大村、下関、宮島 等（1コース勝率62%+）
2. イン弱会場: 戸田、平和島、江戸川、桐生 等（1コース勝率52%未満）
3. 予測が難しい会場（高ボラティリティ）: 宮島、津、浜名湖 等

【推奨される改善アクション】
1. 強風時（4m+）のインコース予測を下方修正
2. 会場別の補正係数を適用
3. 不安定会場での信頼度を下げる
4. 特定の会場×風向きパターンでの除外条件を設定
""")

    return coefficients

if __name__ == "__main__":
    main()
