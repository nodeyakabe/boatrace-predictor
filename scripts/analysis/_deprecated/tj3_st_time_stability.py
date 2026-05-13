"""
TJ-3: STタイム安定度（ばらつき）分析

ST（スタートタイム）の安定性（ばらつきの小さい選手）が予測精度に影響するか分析する。

st_timeカラムの格納形式:
- st_time >= 1: コース番号付き複合値（例: 1.09 → コース1、ST=0.09秒）
- 0 < st_time < 1: コース1のST時間（actual_courseで確認）
- st_time < 0: フライング（負値がそのまま実ST秒数）

実ST秒数の計算:
- st_time >= 1: st_time - FLOOR(st_time)
- 0 < st_time < 1: st_time
- st_time < 0: st_time（フライング）
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

# ===========================
# ヘルパー関数
# ===========================

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def calc_actual_st(st_time):
    """st_timeから実ST秒数を計算"""
    if st_time is None:
        return None
    if st_time >= 1:
        return st_time - int(st_time)
    else:
        return st_time  # フライング（負値）または0<st<1


# ===========================
# Step 1: STタイム分布の把握
# ===========================

def analyze_st_distribution(conn):
    print("=" * 60)
    print("Step 1: STタイム分布の把握")
    print("=" * 60)

    # 全体の実ST分布（フライング除外）
    query = """
    SELECT
        CASE
            WHEN st_time >= 1 THEN st_time - CAST(CAST(st_time AS INTEGER) AS REAL)
            WHEN st_time > 0 AND st_time < 1 THEN st_time
            ELSE st_time
        END as actual_st
    FROM race_details
    WHERE st_time IS NOT NULL AND st_time != 0
    """
    df = pd.read_sql_query(query, conn)

    print(f"\n[全体統計] n={len(df):,}件")
    print(f"  フライング (actual_st < 0): {(df['actual_st'] < 0).sum():,}件 ({(df['actual_st'] < 0).mean()*100:.1f}%)")
    df_valid = df[df['actual_st'] >= 0]
    print(f"  正常ST (actual_st >= 0): {len(df_valid):,}件")
    print(f"  平均ST: {df_valid['actual_st'].mean():.4f}秒")
    print(f"  中央値ST: {df_valid['actual_st'].median():.4f}秒")
    print(f"  標準偏差: {df_valid['actual_st'].std():.4f}秒")
    print(f"  最小: {df_valid['actual_st'].min():.4f}秒")
    print(f"  最大: {df_valid['actual_st'].max():.4f}秒")

    # パーセンタイル分布
    percentiles = [10, 25, 50, 75, 90, 95]
    print(f"\n  パーセンタイル分布 (正常ST):")
    for p in percentiles:
        print(f"    {p}%ile: {np.percentile(df_valid['actual_st'], p):.4f}秒")

    # コース別ST平均
    query_course = """
    SELECT
        actual_course,
        COUNT(*) as cnt,
        AVG(CASE
            WHEN st_time >= 1 THEN st_time - CAST(CAST(st_time AS INTEGER) AS REAL)
            WHEN st_time > 0 AND st_time < 1 THEN st_time
            ELSE st_time
        END) as avg_st,
        MIN(CASE
            WHEN st_time >= 1 THEN st_time - CAST(CAST(st_time AS INTEGER) AS REAL)
            WHEN st_time > 0 AND st_time < 1 THEN st_time
            ELSE st_time
        END) as min_st,
        MAX(CASE
            WHEN st_time >= 1 THEN st_time - CAST(CAST(st_time AS INTEGER) AS REAL)
            WHEN st_time > 0 AND st_time < 1 THEN st_time
            ELSE st_time
        END) as max_st
    FROM race_details
    WHERE st_time IS NOT NULL AND st_time != 0 AND actual_course > 0
        AND st_time > 0  -- フライング除外
    GROUP BY actual_course
    ORDER BY actual_course
    """
    df_course = pd.read_sql_query(query_course, conn)
    print(f"\n[コース別ST平均 (正常ST, actual_courseあり)]")
    print(f"{'コース':>6} {'件数':>8} {'平均ST':>8} {'最小ST':>8} {'最大ST':>8}")
    for _, row in df_course.iterrows():
        print(f"  {int(row['actual_course']):>4} {int(row['cnt']):>8,} {row['avg_st']:>8.4f} {row['min_st']:>8.4f} {row['max_st']:>8.4f}")

    return df_valid


# ===========================
# Step 2: 選手別ST標準偏差計算
# ===========================

def calc_racer_st_stability(conn, min_races=12, lookback_races=24):
    """
    各選手の過去N走のST標準偏差を計算する。
    フライングは除外（安定度の計算対象外）。
    """
    print("\n" + "=" * 60)
    print(f"Step 2: 選手別ST安定度計算 (過去{lookback_races}走、最低{min_races}走)")
    print("=" * 60)

    # racer_numberと実ST時間を取得（正常ST=フライング除外）
    query = """
    SELECT
        e.racer_number,
        e.race_id,
        r.race_date,
        CASE
            WHEN rd.st_time >= 1 THEN rd.st_time - CAST(CAST(rd.st_time AS INTEGER) AS REAL)
            WHEN rd.st_time > 0 AND rd.st_time < 1 THEN rd.st_time
            ELSE NULL
        END as actual_st
    FROM entries e
    JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    JOIN races r ON e.race_id = r.id
    WHERE rd.st_time IS NOT NULL
        AND rd.st_time > 0  -- フライング除外（NULL扱い）
        AND rd.st_time != 0
        AND e.racer_number IS NOT NULL
    ORDER BY e.racer_number, r.race_date, e.race_id
    """
    print("  選手別STデータを取得中...")
    df = pd.read_sql_query(query, conn)
    df = df.dropna(subset=['actual_st'])
    print(f"  取得件数: {len(df):,}件, 選手数: {df['racer_number'].nunique():,}人")

    # 選手別・日付順に並べ、直近lookback_races走のSTDEVを計算
    print(f"  直近{lookback_races}走のSTDEVを計算中...")
    df = df.sort_values(['racer_number', 'race_date', 'race_id'])

    def rolling_stdev(group):
        group = group.copy()
        group['st_stdev'] = group['actual_st'].rolling(
            window=lookback_races, min_periods=min_races
        ).std()
        group['st_mean'] = group['actual_st'].rolling(
            window=lookback_races, min_periods=min_races
        ).mean()
        group['st_count'] = group['actual_st'].rolling(
            window=lookback_races, min_periods=min_races
        ).count()
        return group

    df = df.groupby('racer_number', group_keys=False).apply(rolling_stdev)
    df_with_stdev = df.dropna(subset=['st_stdev'])
    print(f"  STDEV計算可能件数: {len(df_with_stdev):,}件")

    # STDEV分布
    print(f"\n[ST標準偏差の分布]")
    percentiles = [10, 25, 50, 75, 90, 95]
    for p in percentiles:
        print(f"  {p}%ile STDEV: {np.percentile(df_with_stdev['st_stdev'], p):.4f}秒")
    print(f"  平均STDEV: {df_with_stdev['st_stdev'].mean():.4f}秒")
    print(f"  最小STDEV: {df_with_stdev['st_stdev'].min():.4f}秒")
    print(f"  最大STDEV: {df_with_stdev['st_stdev'].max():.4f}秒")

    return df_with_stdev


# ===========================
# Step 3: 予測1位選手のST安定度と的中率の相関
# ===========================

def analyze_prediction_accuracy_by_st_stability(conn, df_st_stability):
    """
    予測1位選手のST標準偏差別に的中率を分析する。
    """
    print("\n" + "=" * 60)
    print("Step 3: ST安定度別の予測精度分析")
    print("=" * 60)

    # 予測1位 + 結果 + 信頼度 + 実ST
    query_pred = """
    SELECT
        rp.race_id,
        rp.pit_number,
        rp.racer_number,
        rp.confidence,
        r.race_date,
        res.rank as actual_rank,
        e.avg_st
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    LEFT JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    WHERE rp.rank_prediction = 1
        AND rp.prediction_type = 'advance'
        AND r.race_date >= '2020-01-01'
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
    ORDER BY r.race_date, rp.race_id
    """
    print("  予測1位データを取得中...")
    df_pred = pd.read_sql_query(query_pred, conn)
    print(f"  予測1位件数: {len(df_pred):,}件")

    # ST安定度データと結合 (race_idとracer_numberで)
    # df_st_stability には race_id と racer_number がある
    # 各レースでの「その時点での」STDEV（当日時点の過去N走）を結合
    df_st_merge = df_st_stability[['race_id', 'racer_number', 'st_stdev', 'st_mean', 'st_count']].copy()
    df_st_merge['race_id'] = df_st_merge['race_id'].astype(str)
    df_pred['race_id'] = df_pred['race_id'].astype(str)
    df_pred['racer_number'] = df_pred['racer_number'].astype(str)
    df_st_merge['racer_number'] = df_st_merge['racer_number'].astype(str)

    df_merged = df_pred.merge(df_st_merge, on=['race_id', 'racer_number'], how='left')
    print(f"  STDEV結合後: {len(df_merged):,}件, STDEV有り: {df_merged['st_stdev'].notna().sum():,}件")

    df_merged['hit_1st'] = (df_merged['actual_rank'] == '1').astype(int)

    # STDEV有りのデータのみで分析
    df_analysis = df_merged[df_merged['st_stdev'].notna()].copy()
    print(f"  分析対象: {len(df_analysis):,}件")

    # 全体の1位的中率
    overall_hit = df_analysis['hit_1st'].mean()
    print(f"\n  全体1位的中率: {overall_hit*100:.2f}%")

    # STDEV分位数でグループ分け
    print(f"\n[ST安定度（STDEV）別の1位的中率]")
    bins = [0, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.15, 1.0]
    labels = ['0-0.02', '0.02-0.03', '0.03-0.04', '0.04-0.05', '0.05-0.06',
              '0.06-0.07', '0.07-0.08', '0.08-0.10', '0.10-0.15', '0.15+']
    df_analysis['stdev_group'] = pd.cut(df_analysis['st_stdev'], bins=bins, labels=labels)

    grouped = df_analysis.groupby('stdev_group', observed=False).agg(
        cnt=('hit_1st', 'count'),
        hit_cnt=('hit_1st', 'sum'),
        hit_rate=('hit_1st', 'mean')
    ).reset_index()

    print(f"  {'STDEV範囲':>12} {'件数':>8} {'1位的中':>8} {'的中率':>8} {'全体比':>8}")
    for _, row in grouped.iterrows():
        if row['cnt'] > 0:
            diff = (row['hit_rate'] - overall_hit) * 100
            sign = '+' if diff >= 0 else ''
            print(f"  {str(row['stdev_group']):>12} {int(row['cnt']):>8,} {int(row['hit_cnt']):>8,} {row['hit_rate']*100:>7.2f}% {sign}{diff:>6.2f}pt")

    # 信頼度別×STDEV別分析
    print(f"\n[信頼度別×ST安定度別の1位的中率]")
    for conf in ['A', 'B', 'C']:
        df_conf = df_analysis[df_analysis['confidence'] == conf]
        if len(df_conf) < 100:
            continue
        hit_conf = df_conf['hit_1st'].mean()
        print(f"\n  信頼度 {conf} (n={len(df_conf):,}, 的中率={hit_conf*100:.2f}%)")

        # STDEV四分位数でグループ分け
        q25 = df_conf['st_stdev'].quantile(0.25)
        q50 = df_conf['st_stdev'].quantile(0.50)
        q75 = df_conf['st_stdev'].quantile(0.75)
        print(f"    Q1(安定): STDEV < {q25:.3f}秒")
        print(f"    Q2: {q25:.3f} <= STDEV < {q50:.3f}秒")
        print(f"    Q3: {q50:.3f} <= STDEV < {q75:.3f}秒")
        print(f"    Q4(不安定): STDEV >= {q75:.3f}秒")

        df_conf = df_conf.copy()
        df_conf['quartile'] = pd.qcut(df_conf['st_stdev'], q=4, labels=['Q1(安定)', 'Q2', 'Q3', 'Q4(不安定)'])
        q_grouped = df_conf.groupby('quartile', observed=False).agg(
            cnt=('hit_1st', 'count'),
            hit_rate=('hit_1st', 'mean')
        )
        for qname, qrow in q_grouped.iterrows():
            diff = (qrow['hit_rate'] - hit_conf) * 100
            sign = '+' if diff >= 0 else ''
            print(f"    {qname}: n={int(qrow['cnt']):,}, 的中率={qrow['hit_rate']*100:.2f}% ({sign}{diff:.2f}pt)")

    return df_analysis, df_merged


# ===========================
# Step 4: 除外閾値のROI影響試算
# ===========================

def analyze_exclusion_threshold_effect(conn, df_merged):
    """
    予測1位のST標準偏差 > 閾値のレースを除外した場合のROI影響を試算。
    """
    print("\n" + "=" * 60)
    print("Step 4: 除外閾値のROI影響試算")
    print("=" * 60)

    # オッズデータを取得（三連単）
    query_odds = """
    SELECT
        rp.race_id,
        rp.confidence,
        rp.pit_number as pred_1st_pit,
        res1.rank as rank1,
        t.odds as trifecta_odds_val,
        res1.trifecta_odds as result_odds
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    LEFT JOIN results res1 ON rp.race_id = res1.race_id AND rp.pit_number = res1.pit_number
    WHERE rp.rank_prediction = 1
        AND rp.prediction_type = 'advance'
        AND r.race_date >= '2020-01-01'
        AND res1.rank IS NOT NULL
        AND res1.is_invalid = 0
    ORDER BY r.race_date
    """

    # df_mergedに結果odds情報があるか確認
    # df_mergedにはhit_1st, confidence, st_stdevがある
    # 簡易的なROI計算（的中率ベース）のみ実施

    # 信頼度別の平均オッズを取得
    query_avg_odds = """
    SELECT
        rp.confidence,
        AVG(res.trifecta_odds) as avg_hit_odds,
        COUNT(*) as cnt
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE rp.rank_prediction = 1
        AND rp.prediction_type = 'advance'
        AND r.race_date >= '2020-01-01'
        AND res.rank = '1'
        AND res.is_invalid = 0
        AND res.trifecta_odds IS NOT NULL
    GROUP BY rp.confidence
    """
    df_avg_odds = pd.read_sql_query(query_avg_odds, conn)
    print(f"\n[信頼度別の平均的中オッズ（参考）]")
    for _, row in df_avg_odds.iterrows():
        print(f"  信頼度 {row['confidence']}: 平均オッズ={row['avg_hit_odds']:.1f}倍, 的中件数={int(row['cnt']):,}")

    # df_mergedにresult_oddsを追加
    query_with_odds = """
    SELECT
        rp.race_id,
        rp.racer_number,
        res.trifecta_odds as hit_odds
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE rp.rank_prediction = 1
        AND rp.prediction_type = 'advance'
        AND r.race_date >= '2020-01-01'
        AND res.rank = '1'
        AND res.is_invalid = 0
        AND res.trifecta_odds IS NOT NULL
    """
    df_odds = pd.read_sql_query(query_with_odds, conn)
    df_odds['race_id'] = df_odds['race_id'].astype(str)
    df_odds['racer_number'] = df_odds['racer_number'].astype(str)

    # df_mergedに結合
    df_calc = df_merged.copy()
    df_calc['race_id'] = df_calc['race_id'].astype(str)
    df_calc['racer_number'] = df_calc['racer_number'].astype(str)
    df_calc = df_calc.merge(df_odds, on=['race_id', 'racer_number'], how='left')
    df_calc['hit_odds'] = df_calc['hit_odds'].fillna(0)

    # STDEVが計算可能なデータのみ
    df_calc_valid = df_calc[df_calc['st_stdev'].notna()].copy()
    print(f"\n分析対象: {len(df_calc_valid):,}件 (STDEV有り)")

    # ベースライン（STDEV制限なし）
    baseline_cnt = len(df_calc_valid)
    baseline_hit_cnt = df_calc_valid['hit_1st'].sum()
    baseline_hit_rate = df_calc_valid['hit_1st'].mean()
    # 簡易ROI: 的中時のオッズ合計 / 購入件数 × 100
    # ただしオッズ情報は三連単以外の情報がないので的中率ベースで代用
    # 信頼度別に分けて計算
    print(f"\n[ベースライン（除外なし）]")
    print(f"  購入件数: {baseline_cnt:,}件")
    print(f"  1位的中: {int(baseline_hit_cnt):,}件 ({baseline_hit_rate*100:.2f}%)")

    # 閾値探索（0.01秒刻みで0.03〜0.15秒）
    thresholds = [round(t * 0.01, 2) for t in range(3, 16)]

    print(f"\n[閾値別の除外効果（予測1位のST STDEV > 閾値のレースを除外）]")
    print(f"{'閾値':>8} {'残件数':>8} {'除外%':>8} {'1位的中率':>10} {'変化':>8}")

    results_threshold = []
    for threshold in thresholds:
        df_filtered = df_calc_valid[df_calc_valid['st_stdev'] <= threshold]
        if len(df_filtered) < 100:
            continue
        hit_rate = df_filtered['hit_1st'].mean()
        excluded_pct = (1 - len(df_filtered) / baseline_cnt) * 100
        diff = (hit_rate - baseline_hit_rate) * 100
        sign = '+' if diff >= 0 else ''
        print(f"  <= {threshold:.2f}秒 {len(df_filtered):>8,} {excluded_pct:>7.1f}% {hit_rate*100:>9.2f}% {sign}{diff:.2f}pt")
        results_threshold.append({
            'threshold': threshold,
            'remaining': len(df_filtered),
            'excluded_pct': excluded_pct,
            'hit_rate': hit_rate,
            'diff_pt': diff
        })

    # 信頼度別の閾値効果
    for conf in ['A', 'B', 'C']:
        df_conf = df_calc_valid[df_calc_valid['confidence'] == conf]
        if len(df_conf) < 100:
            continue
        conf_baseline_hit = df_conf['hit_1st'].mean()
        print(f"\n[信頼度 {conf} の閾値別効果] (ベースライン的中率: {conf_baseline_hit*100:.2f}%)")
        print(f"{'閾値':>8} {'残件数':>8} {'除外%':>8} {'的中率':>10} {'変化':>8}")
        for threshold in thresholds:
            df_filtered = df_conf[df_conf['st_stdev'] <= threshold]
            if len(df_filtered) < 50:
                continue
            hit_rate = df_filtered['hit_1st'].mean()
            excluded_pct = (1 - len(df_filtered) / len(df_conf)) * 100
            diff = (hit_rate - conf_baseline_hit) * 100
            sign = '+' if diff >= 0 else ''
            print(f"  <= {threshold:.2f}秒 {len(df_filtered):>8,} {excluded_pct:>7.1f}% {hit_rate*100:>9.2f}% {sign}{diff:.2f}pt")

    return results_threshold


# ===========================
# Step 5: entries.avg_stとの比較
# ===========================

def compare_with_avg_st(conn):
    """
    entries.avg_st（事前公開の平均ST）との比較分析。
    """
    print("\n" + "=" * 60)
    print("Step 5: entries.avg_st（公式平均ST）との比較")
    print("=" * 60)

    # avg_st充足率確認
    query = """
    SELECT
        COUNT(*) as total,
        COUNT(avg_st) as has_avg_st,
        AVG(avg_st) as mean_avg_st,
        MIN(avg_st) as min_avg_st,
        MAX(avg_st) as max_avg_st
    FROM entries
    WHERE avg_st IS NOT NULL AND avg_st > 0
    """
    df = pd.read_sql_query(query, conn)
    row = df.iloc[0]
    print(f"\n  avg_st有り: {int(row['has_avg_st']):,}件")
    print(f"  平均avg_st: {row['mean_avg_st']:.4f}秒")
    print(f"  最小avg_st: {row['min_avg_st']:.4f}秒")
    print(f"  最大avg_st: {row['max_avg_st']:.4f}秒")

    # 予測1位のavg_stと的中率の相関
    query_pred = """
    SELECT
        rp.confidence,
        e.avg_st,
        CASE WHEN res.rank = '1' THEN 1 ELSE 0 END as hit_1st
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE rp.rank_prediction = 1
        AND rp.prediction_type = 'advance'
        AND r.race_date >= '2020-01-01'
        AND res.is_invalid = 0
        AND e.avg_st IS NOT NULL AND e.avg_st > 0
    """
    df_pred = pd.read_sql_query(query_pred, conn)
    print(f"\n  予測1位のavg_stデータ: {len(df_pred):,}件")

    overall_hit = df_pred['hit_1st'].mean()
    print(f"  全体1位的中率: {overall_hit*100:.2f}%")

    # avg_st別グループ分析
    bins = [0, 0.10, 0.13, 0.15, 0.17, 0.20, 0.25, 0.30, 1.0]
    labels = ['<0.10', '0.10-0.13', '0.13-0.15', '0.15-0.17', '0.17-0.20', '0.20-0.25', '0.25-0.30', '0.30+']
    df_pred['avg_st_group'] = pd.cut(df_pred['avg_st'], bins=bins, labels=labels)

    grouped = df_pred.groupby('avg_st_group', observed=False).agg(
        cnt=('hit_1st', 'count'),
        hit_rate=('hit_1st', 'mean')
    )
    print(f"\n[avg_st別の1位的中率]")
    print(f"  {'avg_ST範囲':>12} {'件数':>8} {'的中率':>8} {'全体比':>8}")
    for gname, row in grouped.iterrows():
        if row['cnt'] > 0:
            diff = (row['hit_rate'] - overall_hit) * 100
            sign = '+' if diff >= 0 else ''
            print(f"  {str(gname):>12} {int(row['cnt']):>8,} {row['hit_rate']*100:>7.2f}% {sign}{diff:.2f}pt")

    # f_count（フライング回数）別分析
    query_f = """
    SELECT
        e.f_count,
        COUNT(*) as cnt,
        AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as hit_rate
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE rp.rank_prediction = 1
        AND rp.prediction_type = 'advance'
        AND r.race_date >= '2020-01-01'
        AND res.is_invalid = 0
        AND e.f_count IS NOT NULL
    GROUP BY e.f_count
    ORDER BY e.f_count
    """
    df_f = pd.read_sql_query(query_f, conn)
    print(f"\n[フライング回数別の1位的中率]")
    print(f"  {'F回数':>6} {'件数':>8} {'的中率':>8} {'全体比':>8}")
    for _, row in df_f.iterrows():
        diff = (row['hit_rate'] - overall_hit) * 100
        sign = '+' if diff >= 0 else ''
        print(f"  {int(row['f_count']):>6} {int(row['cnt']):>8,} {row['hit_rate']*100:>7.2f}% {sign}{diff:.2f}pt")


# ===========================
# Step 6: フライングリスクレースの除外効果
# ===========================

def analyze_flying_risk_exclusion(conn):
    """
    フライングリスクが高いレース（F持ち選手がいる）を除外した効果を試算。
    """
    print("\n" + "=" * 60)
    print("Step 6: フライング・遅れリスクレースの除外効果")
    print("=" * 60)

    # 各レースにf_count > 0の選手がいるかどうかフラグ
    query = """
    SELECT
        rp.race_id,
        rp.confidence,
        MAX(e.f_count) as max_f_count,
        SUM(e.f_count) as sum_f_count,
        MAX(e.l_count) as max_l_count,
        CASE WHEN res.rank = '1' THEN 1 ELSE 0 END as hit_1st
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    JOIN entries e ON rp.race_id = e.race_id
    JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE rp.rank_prediction = 1
        AND rp.prediction_type = 'advance'
        AND r.race_date >= '2020-01-01'
        AND res.is_invalid = 0
        AND e.f_count IS NOT NULL
    GROUP BY rp.race_id, rp.confidence, res.rank
    """
    df = pd.read_sql_query(query, conn)
    print(f"\n  分析対象: {len(df):,}件")

    overall_hit = df['hit_1st'].mean()
    print(f"  全体1位的中率: {overall_hit*100:.2f}%")

    # F持ち有無別
    for f_threshold in [0, 1, 2]:
        label = f"F持ち選手あり (max_f_count > {f_threshold})"
        df_f = df[df['max_f_count'] > f_threshold]
        df_nof = df[df['max_f_count'] <= f_threshold]
        if len(df_f) < 10:
            continue
        hit_f = df_f['hit_1st'].mean()
        hit_nof = df_nof['hit_1st'].mean()
        print(f"\n  [F回数閾値: > {f_threshold}]")
        print(f"    {label}: n={len(df_f):,}, 的中率={hit_f*100:.2f}% (全体比: {(hit_f-overall_hit)*100:+.2f}pt)")
        print(f"    F持ち選手なし (max_f_count <= {f_threshold}): n={len(df_nof):,}, 的中率={hit_nof*100:.2f}% (全体比: {(hit_nof-overall_hit)*100:+.2f}pt)")


# ===========================
# メイン実行
# ===========================

def main():
    print("=" * 60)
    print("TJ-3: STタイム安定度（ばらつき）分析")
    print("=" * 60)

    conn = get_connection()

    try:
        # Step 1: STタイム分布
        df_valid = analyze_st_distribution(conn)

        # Step 2: 選手別ST安定度
        df_st_stability = calc_racer_st_stability(conn, min_races=12, lookback_races=24)

        # Step 3: 予測精度との相関
        df_analysis, df_merged = analyze_prediction_accuracy_by_st_stability(conn, df_st_stability)

        # Step 4: 除外閾値のROI影響
        results_threshold = analyze_exclusion_threshold_effect(conn, df_merged)

        # Step 5: entries.avg_stとの比較
        compare_with_avg_st(conn)

        # Step 6: フライングリスク除外効果
        analyze_flying_risk_exclusion(conn)

        # 最終まとめ
        print("\n" + "=" * 60)
        print("【分析まとめ】")
        print("=" * 60)
        if results_threshold:
            best = max(results_threshold, key=lambda x: x['diff_pt'])
            print(f"\n最も効果的な閾値: STDEV <= {best['threshold']:.2f}秒")
            print(f"  除外率: {best['excluded_pct']:.1f}%")
            print(f"  的中率改善: {best['diff_pt']:+.2f}pt")
            print(f"  残件数: {best['remaining']:,}件")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
