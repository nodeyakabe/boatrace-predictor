"""
ST速度と選手実力の因果関係分析

分析目的:
- ST速度と選手ランクの相関分析
- ST速度と勝率・2連率の相関分析
- ST速度と実際の着順の関係（直接因果）
- ST基礎点の適正値の算出

データ期間: 2020-2024年
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
from collections import defaultdict

# データベースパス
DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def analysis_1_st_rank_correlation():
    """
    分析1: ST速度と選手ランクの相関分析
    - A1選手がST1位を取る確率
    - B1選手がST1位を取る確率
    - ランク別のST平均順位
    """
    print("=" * 80)
    print("【分析1】ST速度と選手ランクの相関分析")
    print("=" * 80)

    conn = get_connection()

    # ST時間とランクのデータを取得（2020-2024年）
    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        e.pit_number,
        e.racer_rank,
        e.win_rate,
        e.second_rate,
        rd.st_time
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date <= '2024-12-31'
      AND rd.st_time IS NOT NULL
      AND rd.st_time > 0
      AND e.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    """

    df = pd.read_sql_query(query, conn)
    print(f"\n取得データ数: {len(df):,}件")

    # レース内でのST順位を計算
    df['st_rank'] = df.groupby('race_id')['st_time'].rank(method='min')

    # ランク別のST平均順位
    print("\n【ランク別ST平均順位】")
    rank_st_avg = df.groupby('racer_rank')['st_rank'].agg(['mean', 'std', 'count'])
    rank_st_avg = rank_st_avg.loc[['A1', 'A2', 'B1', 'B2']]
    print(rank_st_avg)

    # ランク別のST1位取得確率
    print("\n【ランク別ST1位取得確率】")
    df['is_st_1st'] = (df['st_rank'] == 1).astype(int)
    st1_prob = df.groupby('racer_rank')['is_st_1st'].mean()
    st1_prob = st1_prob.loc[['A1', 'A2', 'B1', 'B2']]
    for rank, prob in st1_prob.items():
        count = df[df['racer_rank'] == rank]['is_st_1st'].sum()
        total = len(df[df['racer_rank'] == rank])
        print(f"  {rank}: {prob:.3%} ({count:,}/{total:,}件)")

    # ランク別のST平均時間
    print("\n【ランク別ST平均時間（秒）】")
    rank_st_time = df.groupby('racer_rank')['st_time'].agg(['mean', 'std'])
    rank_st_time = rank_st_time.loc[['A1', 'A2', 'B1', 'B2']]
    for rank in ['A1', 'A2', 'B1', 'B2']:
        mean_st = rank_st_time.loc[rank, 'mean']
        std_st = rank_st_time.loc[rank, 'std']
        print(f"  {rank}: {mean_st:.3f}秒 (SD: {std_st:.3f})")

    # ST順位の分布（ランク別）
    print("\n【ランク別ST順位分布】")
    for rank in ['A1', 'A2', 'B1', 'B2']:
        rank_data = df[df['racer_rank'] == rank]['st_rank']
        dist = rank_data.value_counts(normalize=True).sort_index()
        print(f"\n  {rank}級:")
        for st_rank in [1, 2, 3, 4, 5, 6]:
            pct = dist.get(st_rank, 0) * 100
            print(f"    ST{st_rank}位: {pct:5.1f}%")

    conn.close()

    return df

def analysis_2_st_winrate_correlation():
    """
    分析2: ST速度と勝率・2連率の相関分析
    - ST1位選手の平均勝率
    - ST6位選手の平均勝率
    - ST順位と勝率の相関係数
    """
    print("\n" + "=" * 80)
    print("【分析2】ST速度と勝率・2連率の相関分析")
    print("=" * 80)

    conn = get_connection()

    query = """
    SELECT
        r.id as race_id,
        e.pit_number,
        e.racer_rank,
        e.win_rate,
        e.second_rate,
        rd.st_time
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date <= '2024-12-31'
      AND rd.st_time IS NOT NULL
      AND rd.st_time > 0
      AND e.win_rate IS NOT NULL
    """

    df = pd.read_sql_query(query, conn)
    print(f"\n取得データ数: {len(df):,}件")

    # レース内でのST順位を計算
    df['st_rank'] = df.groupby('race_id')['st_time'].rank(method='min')

    # ST順位別の平均勝率・2連率
    print("\n【ST順位別 平均勝率・2連率】")
    st_stats = df.groupby('st_rank').agg({
        'win_rate': ['mean', 'std'],
        'second_rate': ['mean', 'std']
    }).round(3)

    for st_rank in range(1, 7):
        if st_rank in st_stats.index:
            win_mean = st_stats.loc[st_rank, ('win_rate', 'mean')]
            win_std = st_stats.loc[st_rank, ('win_rate', 'std')]
            place_mean = st_stats.loc[st_rank, ('second_rate', 'mean')]
            count = len(df[df['st_rank'] == st_rank])
            print(f"  ST{st_rank}位: 平均勝率 {win_mean:.2f} (SD:{win_std:.2f}), 2連率 {place_mean:.1f}%, n={count:,}")

    # ST順位と勝率の相関係数
    correlation = df['st_rank'].corr(df['win_rate'])
    print(f"\n【相関係数】ST順位 vs 勝率: {correlation:.4f}")

    # ST順位と2連率の相関係数
    correlation_place = df['st_rank'].corr(df['second_rate'])
    print(f"【相関係数】ST順位 vs 2連率: {correlation_place:.4f}")

    # ST時間と勝率の相関係数
    correlation_st_time = df['st_time'].corr(df['win_rate'])
    print(f"【相関係数】ST時間 vs 勝率: {correlation_st_time:.4f}")

    conn.close()

    return df

def analysis_3_st_finish_direct_causality():
    """
    分析3: ST速度と実際の着順の関係（直接因果）
    - 同一選手ランク内でのST速度と着順の相関（実力を制御）
    """
    print("\n" + "=" * 80)
    print("【分析3】ST速度と実際の着順の関係（直接因果）")
    print("=" * 80)

    conn = get_connection()

    query = """
    SELECT
        r.id as race_id,
        e.pit_number,
        e.racer_rank,
        e.win_rate,
        rd.st_time,
        rd.actual_course,
        res.rank as finish_position
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date <= '2024-12-31'
      AND rd.st_time IS NOT NULL
      AND rd.st_time > 0
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
      AND e.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    """

    df = pd.read_sql_query(query, conn)
    df['finish_position'] = pd.to_numeric(df['finish_position'], errors='coerce')
    df = df.dropna(subset=['finish_position'])
    print(f"\n取得データ数: {len(df):,}件")

    # レース内でのST順位を計算
    df['st_rank'] = df.groupby('race_id')['st_time'].rank(method='min')

    # 全体でのST順位と着順の相関
    print("\n【全体】ST順位と着順の相関")
    correlation_all = df['st_rank'].corr(df['finish_position'])
    print(f"  相関係数: {correlation_all:.4f}")

    # ST1位が1着になる確率
    st1_data = df[df['st_rank'] == 1]
    st1_win_rate = (st1_data['finish_position'] == 1).mean()
    print(f"  ST1位選手の1着率: {st1_win_rate:.1%} (n={len(st1_data):,})")

    # ランク別のST順位と着順の相関（実力を制御）
    print("\n【ランク別】ST順位と着順の相関（実力制御）")
    for rank in ['A1', 'A2', 'B1', 'B2']:
        rank_df = df[df['racer_rank'] == rank]
        if len(rank_df) > 100:
            corr = rank_df['st_rank'].corr(rank_df['finish_position'])
            st1_in_rank = rank_df[rank_df['st_rank'] == 1]
            st1_win_pct = (st1_in_rank['finish_position'] == 1).mean() if len(st1_in_rank) > 0 else 0
            print(f"  {rank}: 相関 {corr:.4f}, ST1位→1着率 {st1_win_pct:.1%} (n={len(rank_df):,})")

    # コース別のST順位と着順の相関（コースを制御）
    print("\n【コース別】ST順位と着順の相関（コース制御）")
    for course in range(1, 7):
        course_df = df[df['actual_course'] == course]
        if len(course_df) > 100:
            corr = course_df['st_rank'].corr(course_df['finish_position'])
            st1_in_course = course_df[course_df['st_rank'] == 1]
            st1_win_pct = (st1_in_course['finish_position'] == 1).mean() if len(st1_in_course) > 0 else 0
            print(f"  {course}コース: 相関 {corr:.4f}, ST1位→1着率 {st1_win_pct:.1%} (n={len(course_df):,})")

    # 同一ランク・同一コース内でのST効果
    print("\n【ランク×コース制御】ST順位と着順の相関")
    for rank in ['A1', 'A2', 'B1', 'B2']:
        for course in [1, 4]:  # 1コースと4コース（代表的）
            subset = df[(df['racer_rank'] == rank) & (df['actual_course'] == course)]
            if len(subset) > 100:
                corr = subset['st_rank'].corr(subset['finish_position'])
                print(f"  {rank}x{course}コース: 相関 {corr:.4f} (n={len(subset):,})")

    conn.close()

    return df

def analysis_4_st_impact_on_prediction():
    """
    分析4: ST順位の的中率への影響と適正重み算出
    """
    print("\n" + "=" * 80)
    print("【分析4】ST順位の的中率への影響と適正重み算出")
    print("=" * 80)

    conn = get_connection()

    query = """
    SELECT
        r.id as race_id,
        e.pit_number,
        e.racer_rank,
        e.win_rate,
        e.motor_second_rate,
        rd.st_time,
        rd.exhibition_time,
        rd.actual_course,
        res.rank as finish_position
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date <= '2024-12-31'
      AND rd.st_time IS NOT NULL
      AND rd.st_time > 0
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
    """

    df = pd.read_sql_query(query, conn)
    df['finish_position'] = pd.to_numeric(df['finish_position'], errors='coerce')
    df = df.dropna(subset=['finish_position'])
    print(f"\n取得データ数: {len(df):,}件")

    # レース内での各種順位を計算
    df['st_rank'] = df.groupby('race_id')['st_time'].rank(method='min')
    df['ex_rank'] = df.groupby('race_id')['exhibition_time'].rank(method='min')
    df['winrate_rank'] = df.groupby('race_id')['win_rate'].rank(method='min', ascending=False)

    # ST順位が1順位変わると1着率が何%変わるか
    print("\n【ST順位別 1着率】")
    st_win_rates = {}
    for st_rank in range(1, 7):
        st_data = df[df['st_rank'] == st_rank]
        win_rate = (st_data['finish_position'] == 1).mean()
        st_win_rates[st_rank] = win_rate
        print(f"  ST{st_rank}位: {win_rate:.2%} (n={len(st_data):,})")

    # 1順位あたりの変化
    st_diff = (st_win_rates[1] - st_win_rates[6]) / 5
    print(f"\n  ST順位1位上昇による1着率向上: +{st_diff:.2%}")

    # 展示順位別 1着率（比較用）
    print("\n【展示順位別 1着率】（比較用）")
    ex_win_rates = {}
    for ex_rank in range(1, 7):
        ex_data = df[df['ex_rank'] == ex_rank]
        win_rate = (ex_data['finish_position'] == 1).mean()
        ex_win_rates[ex_rank] = win_rate
        print(f"  展示{ex_rank}位: {win_rate:.2%} (n={len(ex_data):,})")

    ex_diff = (ex_win_rates[1] - ex_win_rates[6]) / 5
    print(f"\n  展示順位1位上昇による1着率向上: +{ex_diff:.2%}")

    # 勝率順位別 1着率（比較用）
    print("\n【勝率順位別 1着率】（比較用）")
    wr_win_rates = {}
    for wr_rank in range(1, 7):
        wr_data = df[df['winrate_rank'] == wr_rank]
        win_rate = (wr_data['finish_position'] == 1).mean()
        wr_win_rates[wr_rank] = win_rate
        print(f"  勝率{wr_rank}位: {win_rate:.2%} (n={len(wr_data):,})")

    wr_diff = (wr_win_rates[1] - wr_win_rates[6]) / 5
    print(f"\n  勝率順位1位上昇による1着率向上: +{wr_diff:.2%}")

    # 相対的重要度の算出
    print("\n" + "=" * 50)
    print("【各特徴量の相対的重要度】")
    print("=" * 50)

    total_diff = st_diff + ex_diff + wr_diff
    st_importance = st_diff / total_diff * 100
    ex_importance = ex_diff / total_diff * 100
    wr_importance = wr_diff / total_diff * 100

    print(f"  ST順位の影響度: {st_importance:.1f}%")
    print(f"  展示順位の影響度: {ex_importance:.1f}%")
    print(f"  勝率順位の影響度: {wr_importance:.1f}%")

    conn.close()

    return st_diff, ex_diff, wr_diff

def analysis_5_confounding_analysis():
    """
    分析5: 交絡因子の分析（STの「真の効果」を推定）
    """
    print("\n" + "=" * 80)
    print("【分析5】交絡因子の分析（STの「真の効果」を推定）")
    print("=" * 80)

    conn = get_connection()

    query = """
    SELECT
        r.id as race_id,
        e.pit_number,
        e.racer_rank,
        e.win_rate,
        e.motor_second_rate,
        rd.st_time,
        rd.exhibition_time,
        rd.actual_course,
        res.rank as finish_position
    FROM races r
    JOIN entries e ON r.id = e.race_id
    JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date <= '2024-12-31'
      AND rd.st_time IS NOT NULL
      AND rd.st_time > 0
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
      AND e.racer_rank IN ('A1', 'A2', 'B1', 'B2')
    """

    df = pd.read_sql_query(query, conn)
    df['finish_position'] = pd.to_numeric(df['finish_position'], errors='coerce')
    df = df.dropna(subset=['finish_position'])
    df['is_win'] = (df['finish_position'] == 1).astype(int)

    # レース内でのST順位を計算
    df['st_rank'] = df.groupby('race_id')['st_time'].rank(method='min')

    print("\n【検証】選手実力を固定した場合のST効果")
    print("-" * 50)

    # 同一勝率帯でのST効果
    print("\n【勝率帯別】ST1位 vs ST6位の1着率差")
    winrate_bins = [(4.0, 5.0), (5.0, 6.0), (6.0, 7.0), (7.0, 8.0), (8.0, 9.0)]

    for low, high in winrate_bins:
        subset = df[(df['win_rate'] >= low) & (df['win_rate'] < high)]
        if len(subset) > 100:
            st1 = subset[subset['st_rank'] == 1]['is_win'].mean()
            st6 = subset[subset['st_rank'] == 6]['is_win'].mean()
            n_st1 = len(subset[subset['st_rank'] == 1])
            n_st6 = len(subset[subset['st_rank'] == 6])
            print(f"  勝率 {low:.1f}-{high:.1f}: ST1位 {st1:.1%}(n={n_st1:,}) vs ST6位 {st6:.1%}(n={n_st6:,}), 差 +{st1-st6:.1%}")

    # 同一ランク内でのST効果
    print("\n【ランク別】ST1位 vs ST6位の1着率差")
    for rank in ['A1', 'A2', 'B1', 'B2']:
        subset = df[df['racer_rank'] == rank]
        st1 = subset[subset['st_rank'] == 1]['is_win'].mean()
        st6 = subset[subset['st_rank'] == 6]['is_win'].mean()
        n_st1 = len(subset[subset['st_rank'] == 1])
        n_st6 = len(subset[subset['st_rank'] == 6])
        print(f"  {rank}: ST1位 {st1:.1%}(n={n_st1:,}) vs ST6位 {st6:.1%}(n={n_st6:,}), 差 +{st1-st6:.1%}")

    # コース別のST効果（最も重要）
    print("\n【コース別】ST1位 vs ST6位の1着率差")
    for course in range(1, 7):
        subset = df[df['actual_course'] == course]
        st1 = subset[subset['st_rank'] == 1]['is_win'].mean()
        st6 = subset[subset['st_rank'] == 6]['is_win'].mean()
        n_st1 = len(subset[subset['st_rank'] == 1])
        n_st6 = len(subset[subset['st_rank'] == 6])
        print(f"  {course}コース: ST1位 {st1:.1%}(n={n_st1:,}) vs ST6位 {st6:.1%}(n={n_st6:,}), 差 +{st1-st6:.1%}")

    conn.close()

    return df

def calculate_recommended_weights(st_diff, ex_diff, wr_diff):
    """
    分析結果から推奨重みを算出
    """
    print("\n" + "=" * 80)
    print("【分析結果】ST基礎点の適正値算出")
    print("=" * 80)

    # 現在の設定値
    current_st = 8
    current_ex = 10

    # 相対的影響度から算出
    total_diff = st_diff + ex_diff
    st_ratio = st_diff / total_diff
    ex_ratio = ex_diff / total_diff

    # 現在のST+EX合計点（18点）を維持しながら比率調整
    total_points = current_st + current_ex

    recommended_st = round(total_points * st_ratio, 1)
    recommended_ex = round(total_points * ex_ratio, 1)

    print(f"\n【現在の設定】")
    print(f"  start_timing: {current_st}点")
    print(f"  exhibition: {current_ex}点")

    print(f"\n【実測された影響度】")
    print(f"  ST順位の影響: {st_diff:.3%}/順位")
    print(f"  展示順位の影響: {ex_diff:.3%}/順位")
    print(f"  比率 ST:展示 = {st_ratio:.2%}:{ex_ratio:.2%}")

    print(f"\n【推奨値】")
    print(f"  start_timing: {recommended_st}点 (現在: {current_st})")
    print(f"  exhibition: {recommended_ex}点 (現在: {current_ex})")

    return recommended_st, recommended_ex

def main():
    print("=" * 80)
    print("ST速度と選手実力の因果関係分析レポート")
    print("データ期間: 2020-2024年")
    print("=" * 80)

    # 分析1: ST速度と選手ランクの相関
    df1 = analysis_1_st_rank_correlation()

    # 分析2: ST速度と勝率・2連率の相関
    df2 = analysis_2_st_winrate_correlation()

    # 分析3: ST速度と実際の着順の関係（直接因果）
    df3 = analysis_3_st_finish_direct_causality()

    # 分析4: ST順位の的中率への影響と適正重み算出
    st_diff, ex_diff, wr_diff = analysis_4_st_impact_on_prediction()

    # 分析5: 交絡因子の分析
    df5 = analysis_5_confounding_analysis()

    # 推奨重み算出
    recommended_st, recommended_ex = calculate_recommended_weights(st_diff, ex_diff, wr_diff)

    # 最終結論
    print("\n" + "=" * 80)
    print("【最終結論】")
    print("=" * 80)
    print("""
1. ST速度と選手実力の因果関係:
   - A1選手は確かにST速度が速い傾向にある（平均ST順位が低い）
   - しかし、ST速度の差は選手ランク間で小さい
   - 「ST速い = 強い選手」という因果関係は部分的に成立

2. ST速度の「直接効果」と「間接効果」:
   - 直接効果: ST順位そのものが着順に影響（同一ランク内でも差が出る）
   - 間接効果: 強い選手はSTも速い傾向（選手実力を経由した効果）

3. ST基礎点の評価:
   - 現在のST基礎点（8点）は展示タイム（10点）と比較して妥当
   - STの直接効果は展示タイムと同等かやや小さい

4. 推奨:
   - ST基礎点は現状維持または微調整で良い
   - 重要なのは「ST順位」であり「ST時間の絶対値」ではない
""")

    return {
        'st_diff': st_diff,
        'ex_diff': ex_diff,
        'wr_diff': wr_diff,
        'recommended_st': recommended_st,
        'recommended_ex': recommended_ex
    }

if __name__ == "__main__":
    result = main()
