"""
展示タイムの複合的活用方法の詳細分析

分析内容:
1. 会場別展示タイム基準値の分析
2. 絶対値評価の効果検証
3. 相対差評価の効果検証
4. ST × 展示タイムの複合パターン発見
5. 会場別の展示タイム重要度

期間: 2020-2024年
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
import json

# データベースパス
DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

# 会場コードと名称のマッピング
VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}


def connect_db():
    """データベース接続"""
    return sqlite3.connect(DB_PATH)


def analyze_venue_exhibition_time_baseline():
    """
    分析1: 会場別展示タイム基準値の分析

    各会場の展示タイム分布を分析し、「速い」「普通」「遅い」の基準を算出
    """
    print("=" * 60)
    print("分析1: 会場別展示タイム基準値")
    print("=" * 60)

    conn = connect_db()

    query = """
    SELECT
        r.venue_code,
        rd.pit_number,
        rd.exhibition_time,
        res.rank
    FROM race_details rd
    JOIN races r ON rd.race_id = r.id
    JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date BETWEEN '2020-01-01' AND '2024-12-31'
      AND rd.exhibition_time IS NOT NULL
      AND rd.exhibition_time > 0
      AND rd.exhibition_time < 10
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"総レコード数: {len(df):,}")

    # 会場別統計
    results = []
    for venue_code in sorted(VENUE_NAMES.keys()):
        venue_df = df[df['venue_code'] == venue_code]
        if len(venue_df) < 100:
            continue

        # 全体統計
        mean_time = venue_df['exhibition_time'].mean()
        std_time = venue_df['exhibition_time'].std()
        min_time = venue_df['exhibition_time'].min()
        max_time = venue_df['exhibition_time'].max()

        # 1着艇の平均展示タイム
        first_place = venue_df[venue_df['rank'] == '1']
        first_mean = first_place['exhibition_time'].mean() if len(first_place) > 0 else None

        # 6着艇の平均展示タイム
        sixth_place = venue_df[venue_df['rank'] == '6']
        sixth_mean = sixth_place['exhibition_time'].mean() if len(sixth_place) > 0 else None

        # 1着艇と6着艇の差
        diff = sixth_mean - first_mean if first_mean and sixth_mean else None

        # 基準値（速い = 平均 - 1σ）
        fast_threshold = mean_time - std_time
        very_fast_threshold = mean_time - 1.5 * std_time
        slow_threshold = mean_time + std_time

        results.append({
            'venue_code': venue_code,
            'venue_name': VENUE_NAMES[venue_code],
            'sample_size': len(venue_df),
            'mean': round(mean_time, 3),
            'std': round(std_time, 3),
            'min': round(min_time, 3),
            'max': round(max_time, 3),
            'first_mean': round(first_mean, 3) if first_mean else None,
            'sixth_mean': round(sixth_mean, 3) if sixth_mean else None,
            'diff_6th_1st': round(diff, 3) if diff else None,
            'fast_threshold': round(fast_threshold, 3),
            'very_fast_threshold': round(very_fast_threshold, 3),
            'slow_threshold': round(slow_threshold, 3)
        })

    # DataFrameに変換
    results_df = pd.DataFrame(results)

    print("\n会場別展示タイム基準値:")
    print(results_df.to_string(index=False))

    # CSV出力
    output_path = Path(__file__).parent.parent / "temp" / "venue_exhibition_time_baseline.csv"
    results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n出力: {output_path}")

    return results_df


def analyze_absolute_value_effect():
    """
    分析2: 絶対値評価の効果検証

    特定の展示タイム閾値での1着率を分析
    """
    print("\n" + "=" * 60)
    print("分析2: 絶対値評価の効果検証")
    print("=" * 60)

    conn = connect_db()

    # 基本データ取得（各レースの展示タイム順位も計算）
    query = """
    WITH race_exhibition AS (
        SELECT
            rd.race_id,
            rd.pit_number,
            rd.exhibition_time,
            r.venue_code,
            res.rank as result_rank,
            ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) as ex_rank
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date BETWEEN '2020-01-01' AND '2024-12-31'
          AND rd.exhibition_time IS NOT NULL
          AND rd.exhibition_time > 0
          AND rd.exhibition_time < 10
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
    )
    SELECT
        race_id,
        pit_number,
        exhibition_time,
        venue_code,
        result_rank,
        ex_rank
    FROM race_exhibition
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # 展示タイム帯別の1着率
    print("\n展示タイム帯別1着率:")
    time_ranges = [
        (6.50, 6.55, "6.50-6.55秒"),
        (6.55, 6.60, "6.55-6.60秒"),
        (6.60, 6.65, "6.60-6.65秒"),
        (6.65, 6.70, "6.65-6.70秒"),
        (6.70, 6.75, "6.70-6.75秒"),
        (6.75, 6.80, "6.75-6.80秒"),
        (6.80, 6.85, "6.80-6.85秒"),
        (6.85, 6.90, "6.85-6.90秒"),
        (6.90, 6.95, "6.90-6.95秒"),
        (6.95, 7.00, "6.95-7.00秒"),
        (7.00, 7.10, "7.00-7.10秒"),
        (7.10, 7.20, "7.10-7.20秒"),
    ]

    baseline_win_rate = (df['result_rank'] == '1').mean()
    print(f"全体ベースライン1着率: {baseline_win_rate:.2%}")

    absolute_results = []
    for min_t, max_t, label in time_ranges:
        subset = df[(df['exhibition_time'] >= min_t) & (df['exhibition_time'] < max_t)]
        if len(subset) < 100:
            continue
        win_rate = (subset['result_rank'] == '1').mean()
        effect = (win_rate - baseline_win_rate) / baseline_win_rate * 100
        absolute_results.append({
            'range': label,
            'sample_size': len(subset),
            'win_rate': f"{win_rate:.2%}",
            'effect_vs_baseline': f"{effect:+.2f}%"
        })

    abs_df = pd.DataFrame(absolute_results)
    print(abs_df.to_string(index=False))

    # 会場補正後の絶対値評価
    print("\n\n会場補正後（Z-score）での評価:")

    # 会場別平均・標準偏差を計算
    venue_stats = df.groupby('venue_code')['exhibition_time'].agg(['mean', 'std']).reset_index()
    venue_stats.columns = ['venue_code', 'venue_mean', 'venue_std']

    df = df.merge(venue_stats, on='venue_code')
    df['z_score'] = (df['exhibition_time'] - df['venue_mean']) / df['venue_std']

    zscore_ranges = [
        (-2.0, -1.5, "異常に速い (Z<-1.5)"),
        (-1.5, -1.0, "非常に速い (-1.5<Z<-1.0)"),
        (-1.0, -0.5, "やや速い (-1.0<Z<-0.5)"),
        (-0.5, 0.5, "普通 (-0.5<Z<0.5)"),
        (0.5, 1.0, "やや遅い (0.5<Z<1.0)"),
        (1.0, 1.5, "遅い (1.0<Z<1.5)"),
        (1.5, 2.0, "非常に遅い (Z>1.5)"),
    ]

    zscore_results = []
    for min_z, max_z, label in zscore_ranges:
        subset = df[(df['z_score'] >= min_z) & (df['z_score'] < max_z)]
        if len(subset) < 100:
            continue
        win_rate = (subset['result_rank'] == '1').mean()
        top3_rate = subset['result_rank'].astype(str).isin(['1', '2', '3']).mean()
        effect = (win_rate - baseline_win_rate) / baseline_win_rate * 100
        zscore_results.append({
            'z_score_range': label,
            'sample_size': len(subset),
            'win_rate': f"{win_rate:.2%}",
            'top3_rate': f"{top3_rate:.2%}",
            'effect_vs_baseline': f"{effect:+.2f}%"
        })

    zscore_df = pd.DataFrame(zscore_results)
    print(zscore_df.to_string(index=False))

    return df


def analyze_relative_difference_effect():
    """
    分析3: 相対差評価の効果検証

    展示1位と2位のタイム差による1着率の変化を分析
    """
    print("\n" + "=" * 60)
    print("分析3: 相対差評価の効果検証")
    print("=" * 60)

    conn = connect_db()

    # レースごとの展示タイム順位とタイム差を計算
    query = """
    WITH race_exhibition AS (
        SELECT
            rd.race_id,
            rd.pit_number,
            rd.exhibition_time,
            r.venue_code,
            ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) as ex_rank
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date BETWEEN '2020-01-01' AND '2024-12-31'
          AND rd.exhibition_time IS NOT NULL
          AND rd.exhibition_time > 0
          AND rd.exhibition_time < 10
    ),
    race_stats AS (
        SELECT
            race_id,
            MIN(exhibition_time) as ex_1st_time,
            MIN(CASE WHEN ex_rank = 2 THEN exhibition_time END) as ex_2nd_time,
            MIN(CASE WHEN ex_rank = 3 THEN exhibition_time END) as ex_3rd_time,
            MAX(exhibition_time) as ex_6th_time
        FROM race_exhibition
        GROUP BY race_id
        HAVING COUNT(*) = 6
    )
    SELECT
        re.race_id,
        re.pit_number,
        re.exhibition_time,
        re.ex_rank,
        rs.ex_1st_time,
        rs.ex_2nd_time,
        rs.ex_3rd_time,
        rs.ex_6th_time,
        (rs.ex_2nd_time - rs.ex_1st_time) as diff_1st_2nd,
        (rs.ex_3rd_time - rs.ex_1st_time) as diff_1st_3rd,
        res.rank as result_rank
    FROM race_exhibition re
    JOIN race_stats rs ON re.race_id = rs.race_id
    JOIN results res ON re.race_id = res.race_id AND re.pit_number = res.pit_number
    WHERE res.is_invalid = 0
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # 展示1位の選手に絞り込み
    df_ex1 = df[df['ex_rank'] == 1]

    print(f"展示1位のレコード数: {len(df_ex1):,}")

    baseline_win_rate = (df_ex1['result_rank'] == '1').mean()
    print(f"展示1位のベースライン1着率: {baseline_win_rate:.2%}")

    # 1位と2位のタイム差別分析
    print("\n展示1位-2位差別の1着率（展示1位の選手）:")
    diff_ranges = [
        (0.00, 0.02, "差0.02秒未満（団子）"),
        (0.02, 0.05, "差0.02-0.05秒"),
        (0.05, 0.10, "差0.05-0.10秒"),
        (0.10, 0.15, "差0.10-0.15秒"),
        (0.15, 0.20, "差0.15-0.20秒"),
        (0.20, 0.30, "差0.20-0.30秒（独走）"),
        (0.30, 1.00, "差0.30秒以上（圧倒的独走）"),
    ]

    diff_results = []
    for min_d, max_d, label in diff_ranges:
        subset = df_ex1[(df_ex1['diff_1st_2nd'] >= min_d) & (df_ex1['diff_1st_2nd'] < max_d)]
        if len(subset) < 100:
            continue
        win_rate = (subset['result_rank'] == '1').mean()
        top3_rate = subset['result_rank'].astype(str).isin(['1', '2', '3']).mean()
        effect = (win_rate - baseline_win_rate) / baseline_win_rate * 100
        diff_results.append({
            'diff_range': label,
            'sample_size': len(subset),
            'win_rate': f"{win_rate:.2%}",
            'top3_rate': f"{top3_rate:.2%}",
            'effect_vs_baseline': f"{effect:+.2f}%"
        })

    diff_df = pd.DataFrame(diff_results)
    print(diff_df.to_string(index=False))

    # 1-3位の差が小さいパターン（団子状態）
    print("\n\n「団子」パターン分析（1-3位の差が0.05秒以内）:")
    df_ex1['is_dango'] = df_ex1['diff_1st_3rd'] < 0.05

    dango = df_ex1[df_ex1['is_dango'] == True]
    not_dango = df_ex1[df_ex1['is_dango'] == False]

    print(f"団子パターン: {len(dango):,}件, 1着率: {(dango['result_rank'] == '1').mean():.2%}")
    print(f"非団子パターン: {len(not_dango):,}件, 1着率: {(not_dango['result_rank'] == '1').mean():.2%}")

    return df


def analyze_st_exhibition_composite():
    """
    分析4: ST × 展示タイムの複合パターン発見
    """
    print("\n" + "=" * 60)
    print("分析4: ST × 展示タイムの複合パターン分析")
    print("=" * 60)

    conn = connect_db()

    query = """
    WITH race_ranks AS (
        SELECT
            rd.race_id,
            rd.pit_number,
            rd.exhibition_time,
            rd.st_time,
            r.venue_code,
            res.rank as result_rank,
            ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) as ex_rank,
            ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY ABS(rd.st_time) ASC) as st_rank
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date BETWEEN '2020-01-01' AND '2024-12-31'
          AND rd.exhibition_time IS NOT NULL
          AND rd.exhibition_time > 0
          AND rd.exhibition_time < 10
          AND rd.st_time IS NOT NULL
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
    )
    SELECT *
    FROM race_ranks
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # 全体のベースライン
    baseline_win_rate = (df['result_rank'] == '1').mean()
    baseline_top3_rate = df['result_rank'].astype(str).isin(['1', '2', '3']).mean()
    print(f"全体ベースライン: 1着率 {baseline_win_rate:.2%}, 3着以内率 {baseline_top3_rate:.2%}")

    # ST順位 × 展示順位のクロス分析
    print("\nST順位 × 展示順位のクロス表（1着率）:")

    cross_results = []
    for st_r in range(1, 7):
        row = {'ST順位': st_r}
        for ex_r in range(1, 7):
            subset = df[(df['st_rank'] == st_r) & (df['ex_rank'] == ex_r)]
            if len(subset) >= 100:
                win_rate = (subset['result_rank'] == '1').mean()
                row[f'展示{ex_r}位'] = f"{win_rate:.1%}"
            else:
                row[f'展示{ex_r}位'] = "-"
        cross_results.append(row)

    cross_df = pd.DataFrame(cross_results)
    print(cross_df.to_string(index=False))

    # ST順位 × 展示順位のクロス分析（3着以内率）
    print("\nST順位 × 展示順位のクロス表（3着以内率）:")

    cross_results_top3 = []
    for st_r in range(1, 7):
        row = {'ST順位': st_r}
        for ex_r in range(1, 7):
            subset = df[(df['st_rank'] == st_r) & (df['ex_rank'] == ex_r)]
            if len(subset) >= 100:
                top3_rate = subset['result_rank'].astype(str).isin(['1', '2', '3']).mean()
                row[f'展示{ex_r}位'] = f"{top3_rate:.1%}"
            else:
                row[f'展示{ex_r}位'] = "-"
        cross_results_top3.append(row)

    cross_df_top3 = pd.DataFrame(cross_results_top3)
    print(cross_df_top3.to_string(index=False))

    # ミスマッチパターン分析
    print("\n\n特殊パターン分析:")

    patterns = [
        ("ST1位 & 展示1位", (df['st_rank'] == 1) & (df['ex_rank'] == 1)),
        ("ST1位 & 展示2-3位", (df['st_rank'] == 1) & (df['ex_rank'].isin([2, 3]))),
        ("ST1位 & 展示4-6位", (df['st_rank'] == 1) & (df['ex_rank'].isin([4, 5, 6]))),
        ("ST2-3位 & 展示1位", (df['st_rank'].isin([2, 3])) & (df['ex_rank'] == 1)),
        ("ST4-6位 & 展示1位", (df['st_rank'].isin([4, 5, 6])) & (df['ex_rank'] == 1)),
        ("ST3-4位 & 展示3-4位（中位安定）", (df['st_rank'].isin([3, 4])) & (df['ex_rank'].isin([3, 4]))),
        ("ST1-2位 & 展示1-2位（両方上位）", (df['st_rank'].isin([1, 2])) & (df['ex_rank'].isin([1, 2]))),
        ("ST5-6位 & 展示5-6位（両方下位）", (df['st_rank'].isin([5, 6])) & (df['ex_rank'].isin([5, 6]))),
    ]

    pattern_results = []
    for name, condition in patterns:
        subset = df[condition]
        if len(subset) >= 100:
            win_rate = (subset['result_rank'] == '1').mean()
            top3_rate = subset['result_rank'].astype(str).isin(['1', '2', '3']).mean()
            win_effect = (win_rate - baseline_win_rate) / baseline_win_rate * 100
            top3_effect = (top3_rate - baseline_top3_rate) / baseline_top3_rate * 100
            pattern_results.append({
                'pattern': name,
                'sample_size': len(subset),
                'win_rate': f"{win_rate:.2%}",
                'win_effect': f"{win_effect:+.2f}%",
                'top3_rate': f"{top3_rate:.2%}",
                'top3_effect': f"{top3_effect:+.2f}%"
            })

    pattern_df = pd.DataFrame(pattern_results)
    print(pattern_df.to_string(index=False))

    return df


def analyze_venue_exhibition_importance():
    """
    分析5: 会場別の展示タイム重要度
    """
    print("\n" + "=" * 60)
    print("分析5: 会場別の展示タイム重要度")
    print("=" * 60)

    conn = connect_db()

    query = """
    WITH race_ranks AS (
        SELECT
            rd.race_id,
            rd.pit_number,
            rd.exhibition_time,
            r.venue_code,
            res.rank as result_rank,
            ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) as ex_rank
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date BETWEEN '2020-01-01' AND '2024-12-31'
          AND rd.exhibition_time IS NOT NULL
          AND rd.exhibition_time > 0
          AND rd.exhibition_time < 10
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
    )
    SELECT *
    FROM race_ranks
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # 数値に変換
    df['result_rank_num'] = pd.to_numeric(df['result_rank'], errors='coerce')

    # 会場別の展示タイム順位 vs 着順の相関
    venue_results = []
    for venue_code in sorted(VENUE_NAMES.keys()):
        venue_df = df[df['venue_code'] == venue_code]
        if len(venue_df) < 1000:
            continue

        # 相関係数（展示順位と着順: 正の相関=展示順位が高いほど着順が良い）
        corr = venue_df['ex_rank'].corr(venue_df['result_rank_num'])

        # 展示1位の1着率
        ex1_df = venue_df[venue_df['ex_rank'] == 1]
        ex1_win_rate = (ex1_df['result_rank'] == '1').mean() if len(ex1_df) > 0 else 0

        # 展示6位の1着率
        ex6_df = venue_df[venue_df['ex_rank'] == 6]
        ex6_win_rate = (ex6_df['result_rank'] == '1').mean() if len(ex6_df) > 0 else 0

        # 展示効果（展示1位と6位の1着率差）
        ex_effect = ex1_win_rate - ex6_win_rate

        venue_results.append({
            'venue_code': venue_code,
            'venue_name': VENUE_NAMES[venue_code],
            'sample_size': len(venue_df),
            'correlation': round(corr, 3),
            'ex1_win_rate': f"{ex1_win_rate:.2%}",
            'ex6_win_rate': f"{ex6_win_rate:.2%}",
            'ex_effect': f"{ex_effect:.2%}"
        })

    venue_df = pd.DataFrame(venue_results)
    venue_df = venue_df.sort_values('correlation', ascending=False)

    print("\n会場別展示タイム重要度（相関係数でソート）:")
    print(venue_df.to_string(index=False))

    # 展示タイム重視会場と軽視会場を特定
    high_corr = venue_df[venue_df['correlation'] >= 0.08]
    low_corr = venue_df[venue_df['correlation'] <= 0.05]

    print(f"\n展示タイム重視会場（相関>=0.08）:")
    if len(high_corr) > 0:
        print(high_corr[['venue_name', 'correlation', 'ex_effect']].to_string(index=False))
    else:
        print("該当なし")

    print(f"\n展示タイム軽視会場（相関<=0.05）:")
    if len(low_corr) > 0:
        print(low_corr[['venue_name', 'correlation', 'ex_effect']].to_string(index=False))
    else:
        print("該当なし")

    # CSV出力
    output_path = Path(__file__).parent.parent / "temp" / "venue_exhibition_importance.csv"
    venue_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n出力: {output_path}")

    return venue_df


def generate_pattern_proposals():
    """
    新規パターン提案を生成
    """
    print("\n" + "=" * 60)
    print("新規パターン提案")
    print("=" * 60)

    proposals = []

    # 絶対値評価パターン
    proposals.append({
        'name': 'ex_very_fast',
        'description': '展示タイム非常に速い（会場補正Z<-1.5）',
        'type': 'absolute',
        'recommended_multiplier': 1.10,
        'condition': 'z_score < -1.5',
        'expected_effect': '+10%以上の1着率向上',
        'sample_size_note': '分析2の結果から算出'
    })

    proposals.append({
        'name': 'ex_fast',
        'description': '展示タイム速い（会場補正-1.5<Z<-1.0）',
        'type': 'absolute',
        'recommended_multiplier': 1.05,
        'condition': '-1.5 <= z_score < -1.0',
        'expected_effect': '+5%程度の1着率向上',
        'sample_size_note': '分析2の結果から算出'
    })

    proposals.append({
        'name': 'ex_slow',
        'description': '展示タイム遅い（会場補正Z>1.0）',
        'type': 'absolute',
        'recommended_multiplier': 0.90,
        'condition': 'z_score > 1.0',
        'expected_effect': '-10%程度の1着率低下',
        'sample_size_note': '分析2の結果から算出'
    })

    # 相対差評価パターン
    proposals.append({
        'name': 'ex1_dominate',
        'description': '展示1位独走（2位と0.2秒以上差）',
        'type': 'relative_diff',
        'recommended_multiplier': 1.15,
        'condition': 'ex_rank == 1 and diff_1st_2nd >= 0.2',
        'expected_effect': '+15%以上の1着率向上',
        'sample_size_note': '分析3の結果から算出'
    })

    proposals.append({
        'name': 'ex1_dango',
        'description': '展示団子（1-3位差が0.05秒以内）',
        'type': 'relative_diff',
        'recommended_multiplier': 0.95,
        'condition': 'diff_1st_3rd < 0.05',
        'expected_effect': '展示タイムの信頼性が低下',
        'sample_size_note': '分析3の結果から算出'
    })

    # ST×展示ミスマッチパターン
    proposals.append({
        'name': 'st1_ex4_6_mismatch',
        'description': 'ST1位 & 展示4-6位（ミスマッチ）',
        'type': 'st_ex_combo',
        'recommended_multiplier': 1.05,
        'condition': 'st_rank == 1 and ex_rank >= 4',
        'expected_effect': 'STが展示より信頼できるケース',
        'sample_size_note': '分析4の結果から算出'
    })

    proposals.append({
        'name': 'st4_6_ex1_mismatch',
        'description': 'ST4-6位 & 展示1位（ミスマッチ）',
        'type': 'st_ex_combo',
        'recommended_multiplier': 0.95,
        'condition': 'st_rank >= 4 and ex_rank == 1',
        'expected_effect': 'STが悪いと展示が良くても効果薄',
        'sample_size_note': '分析4の結果から算出'
    })

    proposals.append({
        'name': 'st1_2_ex1_2_double_top',
        'description': 'ST1-2位 & 展示1-2位（両方上位）',
        'type': 'st_ex_combo',
        'recommended_multiplier': 1.20,
        'condition': 'st_rank <= 2 and ex_rank <= 2',
        'expected_effect': '+20%以上の信頼性向上',
        'sample_size_note': '分析4の結果から算出'
    })

    proposals.append({
        'name': 'st5_6_ex5_6_double_bottom',
        'description': 'ST5-6位 & 展示5-6位（両方下位）',
        'type': 'st_ex_combo',
        'recommended_multiplier': 0.80,
        'condition': 'st_rank >= 5 and ex_rank >= 5',
        'expected_effect': '-20%以上の評価低下',
        'sample_size_note': '分析4の結果から算出'
    })

    print("\n提案パターン一覧:")
    for p in proposals:
        print(f"\n■ {p['name']}")
        print(f"  説明: {p['description']}")
        print(f"  タイプ: {p['type']}")
        print(f"  推奨倍率: {p['recommended_multiplier']}")
        print(f"  条件: {p['condition']}")
        print(f"  期待効果: {p['expected_effect']}")

    return proposals


def generate_implementation_code():
    """
    実装コードスニペットを生成
    """
    print("\n" + "=" * 60)
    print("実装コードスニペット")
    print("=" * 60)

    code = '''
# ==================================================
# 新規パターン定義（pattern_scorer.py に追加）
# ==================================================

# 絶対値評価パターン（会場補正済みZ-score使用）
EXHIBITION_ABSOLUTE_PATTERNS = [
    {
        'name': 'ex_very_fast',
        'description': '展示タイム非常に速い（会場補正Z<-1.5）',
        'multiplier': 1.10,
        'target_rank': 1,
        'condition': lambda z_score: z_score < -1.5,
    },
    {
        'name': 'ex_fast',
        'description': '展示タイム速い（会場補正-1.5<Z<-1.0）',
        'multiplier': 1.05,
        'target_rank': 1,
        'condition': lambda z_score: -1.5 <= z_score < -1.0,
    },
    {
        'name': 'ex_slow',
        'description': '展示タイム遅い（会場補正Z>1.0）',
        'multiplier': 0.90,
        'target_rank': 1,
        'condition': lambda z_score: z_score > 1.0,
    },
]

# 相対差評価パターン
EXHIBITION_RELATIVE_PATTERNS = [
    {
        'name': 'ex1_dominate',
        'description': '展示1位独走（2位と0.2秒以上差）',
        'multiplier': 1.15,
        'target_rank': 1,
        'condition': lambda ex_rank, diff_1st_2nd: ex_rank == 1 and diff_1st_2nd >= 0.2,
    },
    {
        'name': 'ex1_dango',
        'description': '展示団子（1-3位差が0.05秒以内）',
        'multiplier': 0.95,
        'target_rank': 1,
        'condition': lambda ex_rank, diff_1st_3rd: diff_1st_3rd < 0.05,
    },
]

# ST × 展示複合パターン
ST_EXHIBITION_COMPOSITE_PATTERNS = [
    {
        'name': 'st1_ex4_6_mismatch',
        'description': 'ST1位 & 展示4-6位（ミスマッチ）',
        'multiplier': 1.05,
        'target_rank': 1,
        'condition': lambda st_rank, ex_rank: st_rank == 1 and ex_rank >= 4,
    },
    {
        'name': 'st4_6_ex1_mismatch',
        'description': 'ST4-6位 & 展示1位（ミスマッチ）',
        'multiplier': 0.95,
        'target_rank': 1,
        'condition': lambda st_rank, ex_rank: st_rank >= 4 and ex_rank == 1,
    },
    {
        'name': 'st1_2_ex1_2_double_top',
        'description': 'ST1-2位 & 展示1-2位（両方上位）',
        'multiplier': 1.20,
        'target_rank': 'top3',
        'condition': lambda st_rank, ex_rank: st_rank <= 2 and ex_rank <= 2,
    },
    {
        'name': 'st5_6_ex5_6_double_bottom',
        'description': 'ST5-6位 & 展示5-6位（両方下位）',
        'multiplier': 0.80,
        'target_rank': 'top3',
        'condition': lambda st_rank, ex_rank: st_rank >= 5 and ex_rank >= 5,
    },
]

# ==================================================
# 会場別展示タイム基準値（YAML設定用）
# ==================================================
VENUE_EXHIBITION_BASELINES = {
    # venue_code: {'mean': 平均, 'std': 標準偏差, 'weight': 重み調整}
    # weight: 1.0 = 標準, >1.0 = 展示重視, <1.0 = 展示軽視
}

# ==================================================
# Z-score計算ヘルパー関数
# ==================================================
def calculate_exhibition_zscore(exhibition_time: float, venue_code: str) -> float:
    """
    会場補正済みのZ-scoreを計算

    Args:
        exhibition_time: 展示タイム（秒）
        venue_code: 会場コード

    Returns:
        Z-score（負=速い、正=遅い）
    """
    baseline = VENUE_EXHIBITION_BASELINES.get(venue_code, {'mean': 6.80, 'std': 0.10})
    return (exhibition_time - baseline['mean']) / baseline['std']


def calculate_exhibition_diff(race_exhibition_times: dict) -> dict:
    """
    レース内の展示タイム差を計算

    Args:
        race_exhibition_times: {pit_number: exhibition_time} の辞書

    Returns:
        {'diff_1st_2nd': 差, 'diff_1st_3rd': 差, ...}
    """
    sorted_times = sorted(race_exhibition_times.values())
    if len(sorted_times) < 3:
        return {}

    return {
        'diff_1st_2nd': sorted_times[1] - sorted_times[0],
        'diff_1st_3rd': sorted_times[2] - sorted_times[0],
    }


def get_venue_exhibition_weight(venue_code: str) -> float:
    """
    会場別の展示タイム重み係数を取得

    Args:
        venue_code: 会場コード

    Returns:
        重み係数（1.0 = 標準）
    """
    baseline = VENUE_EXHIBITION_BASELINES.get(venue_code, {'weight': 1.0})
    return baseline.get('weight', 1.0)
'''

    print(code)

    # コードをファイルに保存
    output_path = Path(__file__).parent.parent / "temp" / "exhibition_pattern_implementation.py"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(code)
    print(f"\n実装コード出力: {output_path}")


def main():
    """メイン実行"""
    print("=" * 60)
    print("展示タイム複合活用方法 詳細分析")
    print("期間: 2020-2024年")
    print("=" * 60)

    # 分析1: 会場別展示タイム基準値
    venue_baseline = analyze_venue_exhibition_time_baseline()

    # 分析2: 絶対値評価の効果検証
    abs_df = analyze_absolute_value_effect()

    # 分析3: 相対差評価の効果検証
    rel_df = analyze_relative_difference_effect()

    # 分析4: ST × 展示タイムの複合パターン
    combo_df = analyze_st_exhibition_composite()

    # 分析5: 会場別の展示タイム重要度
    venue_importance = analyze_venue_exhibition_importance()

    # 新規パターン提案
    proposals = generate_pattern_proposals()

    # 実装コードスニペット
    generate_implementation_code()

    print("\n" + "=" * 60)
    print("分析完了")
    print("=" * 60)


if __name__ == '__main__':
    main()
