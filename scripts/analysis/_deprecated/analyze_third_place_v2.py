# -*- coding: utf-8 -*-
"""
3着候補選択の改善分析 v3
Opusの推奨調査設計に基づく実施

Step2: B×A1フィルタのみ（全会場・全オッズ帯）で3着分布分析
Step3: レース文脈の特徴量探索（p3/p4スコア差・コース・ランク差）
Step4: オッズ帯別サブグループ（Step2の結果がオッズ帯で変わるか）

【調査設計の方針（Opus確認済み）】
- B信頼度×A1ランクは維持（p3/p4予測の信頼性を保つため）
- オッズ・会場・月条件は除外（「どこに賭けるか」条件は3着分布と独立）
- 案D（コースバイアス）は単独分析せず、Step3の特徴量の一つとして使用
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import sqlite3
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")


# ============================================================
# データ取得
# ============================================================

def load_base_data(conn):
    """
    B信頼度×A1ランクの全レース（2020-2025）を取得
    オッズ・会場・月は絞らない
    """
    print("データ取得中（B×A1 全会場・全オッズ帯）...")
    query = """
    SELECT
        r.id AS race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        -- 予測順位別pit番号
        rp1.pit_number AS p1_pit,
        rp2.pit_number AS p2_pit,
        rp3.pit_number AS p3_pit,
        rp4.pit_number AS p4_pit,
        -- スコア
        rp1.total_score AS p1_score,
        rp2.total_score AS p2_score,
        rp3.total_score AS p3_score,
        rp4.total_score AS p4_score,
        -- 1コース選手のランク
        e1.racer_rank AS c1_racer_rank,
        -- 予測1位選手（p1）のpit（コース番号）
        rp1.pit_number AS p1_course,
        -- 予測3位選手のランク
        ep3.racer_rank AS p3_racer_rank,
        -- 予測4位選手のランク
        ep4.racer_rank AS p4_racer_rank,
        -- 実際の着順
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') AS actual_1st,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') AS actual_2nd,
        (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') AS actual_3rd,
        -- p3軸オッズ
        COALESCE((
            SELECT o.odds FROM trifecta_odds o
            WHERE o.race_id = r.id
              AND o.combination = CAST(rp1.pit_number AS TEXT) || '-'
                               || CAST(rp2.pit_number AS TEXT) || '-'
                               || CAST(rp3.pit_number AS TEXT)
        ), 0) AS odds_p3,
        -- p4軸オッズ
        COALESCE((
            SELECT o.odds FROM trifecta_odds o
            WHERE o.race_id = r.id
              AND o.combination = CAST(rp1.pit_number AS TEXT) || '-'
                               || CAST(rp2.pit_number AS TEXT) || '-'
                               || CAST(rp4.pit_number AS TEXT)
        ), 0) AS odds_p4
    FROM races r
    JOIN race_predictions rp1 ON r.id = rp1.race_id
        AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        AND rp1.confidence = 'B'
    JOIN race_predictions rp2 ON r.id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id
        AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN race_predictions rp4 ON r.id = rp4.race_id
        AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        AND e1.racer_rank = 'A1'
    LEFT JOIN entries ep3 ON r.id = ep3.race_id AND ep3.pit_number = rp3.pit_number
    LEFT JOIN entries ep4 ON r.id = ep4.race_id AND ep4.pit_number = rp4.pit_number
    WHERE r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    """
    df = pd.read_sql_query(query, conn)
    print(f"  取得件数: {len(df):,}件")
    return df


def add_columns(df):
    """派生カラムを追加"""
    # p1-p2が順序通りに1-2着
    df['p12_hit'] = (df['actual_1st'] == df['p1_pit']) & (df['actual_2nd'] == df['p2_pit'])

    # 3着が予測何位だったか
    def third_pred_rank(row):
        third = row['actual_3rd']
        if pd.isna(third):
            return None
        for r in [1, 2, 3, 4]:
            if row.get(f'p{r}_pit') == third:
                return r
        return 5  # p5以下

    df['actual_third_pred_rank'] = df.apply(third_pred_rank, axis=1)

    # 的中フラグ（p3着・p4着）
    df['p3_is_third'] = (df['p12_hit']) & (df['actual_3rd'] == df['p3_pit'])
    df['p4_is_third'] = (df['p12_hit']) & (df['actual_3rd'] == df['p4_pit'])

    # スコア差
    df['score_diff_p3_p4'] = df['p3_score'] - df['p4_score']

    # コース差（p3とp4のコース番号差）
    df['course_diff_p3_p4'] = df['p3_pit'] - df['p4_pit']
    # 外コースが3着に来やすいか（p4のコースがp3より外）
    df['p4_is_outer'] = df['p4_pit'] > df['p3_pit']

    # ランク順位変換（比較用）
    rank_order = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4, None: 9}
    df['p3_rank_num'] = df['p3_racer_rank'].map(rank_order).fillna(9)
    df['p4_rank_num'] = df['p4_racer_rank'].map(rank_order).fillna(9)
    # p4のランクがp3より上（p4の方が実力上）
    df['p4_rank_better'] = df['p4_rank_num'] < df['p3_rank_num']

    return df


# ============================================================
# Step2: 3着分布分析（全会場・全オッズ帯）
# ============================================================

def step2_third_distribution(df):
    print("\n" + "="*60)
    print("【Step2】3着予測順位分布（B×A1 全会場・全オッズ帯）")
    print("="*60)

    n_total = len(df)
    hit_df = df[df['p12_hit']].copy()
    n_hit = len(hit_df)

    print(f"全対象レース: {n_total:,}件")
    print(f"p1-p2が1-2着的中: {n_hit:,}件 ({n_hit/n_total*100:.1f}%)")
    print()

    dist = hit_df['actual_third_pred_rank'].value_counts().sort_index()
    total = dist.sum()

    print(f"3着に来た艇の予測順位分布（p1-p2的中 {n_hit}件）:")
    print(f"{'予測順位':>8} | {'件数':>6} | {'割合':>7} | {'累積':>7}")
    print("-" * 38)
    cumulative = 0
    for rank, count in dist.items():
        pct = count / total * 100
        cumulative += pct
        label = f"p{int(rank)}" if rank <= 4 else "p5+"
        print(f"{label:>8} | {count:>6} | {pct:>6.1f}% | {cumulative:>6.1f}%")

    print()
    p3_rate = dist.get(3, 0) / total * 100
    p4_rate = dist.get(4, 0) / total * 100
    diff = p3_rate - p4_rate

    print(f"p3の3着率: {p3_rate:.1f}%")
    print(f"p4の3着率: {p4_rate:.1f}%")
    print(f"差（p3-p4）: +{diff:.1f}pt")

    # 二項検定（p3 vs p4 の差が有意か）
    n_p3 = dist.get(3, 0)
    n_p4 = dist.get(4, 0)
    n_p3_or_p4 = n_p3 + n_p4
    if n_p3_or_p4 > 0:
        # 帰無仮説: p3とp4が同確率（50%ずつ）で3着に来る
        binom_result = scipy_stats.binomtest(n_p3, n_p3_or_p4, p=0.5, alternative='greater')
        print(f"\n二項検定（p3 vs p4 が同率か）: p={binom_result.pvalue:.4f}")
        if binom_result.pvalue < 0.05:
            print("  → p3の方が有意に多い（p<0.05）")
        else:
            print("  → 有意差なし（p>=0.05）")

    return hit_df, p3_rate, p4_rate


# ============================================================
# Step3: 特徴量探索
# ============================================================

def step3_feature_exploration(df, hit_df):
    print("\n" + "="*60)
    print("【Step3】特徴量探索: p4がp3を上回る条件を探す")
    print("="*60)

    n_hit = len(hit_df)

    # ------- 3-1: スコア差フィルタ -------
    print("\n--- 3-1: p3/p4スコア差 × 3着率 ---")
    print(f"スコア差（p3-p4）: 平均={hit_df['score_diff_p3_p4'].mean():.1f}  中央値={hit_df['score_diff_p3_p4'].median():.1f}")
    print()
    print(f"{'スコア差':>12} | {'件数':>6} | {'p3的中':>7} | {'p4的中':>7} | {'p3率':>7} | {'p4率':>7} | {'差':>6}")
    print("-" * 68)

    bins = [(-99, 0), (0, 2), (2, 4), (4, 6), (6, 10), (10, 99)]
    for lo, hi in bins:
        s = hit_df[(hit_df['score_diff_p3_p4'] >= lo) & (hit_df['score_diff_p3_p4'] < hi)]
        n = len(s)
        if n < 5:
            continue
        n_p3 = s['p3_is_third'].sum()
        n_p4 = s['p4_is_third'].sum()
        p3r = n_p3 / n * 100
        p4r = n_p4 / n * 100
        label = f"{lo}~{hi}pt" if hi < 99 else f"{lo}pt+"
        print(f"{label:>12} | {n:>6} | {n_p3:>7} | {n_p4:>7} | {p3r:>6.1f}% | {p4r:>6.1f}% | {p3r-p4r:>+5.1f}pt")

    # ------- 3-2: p4のコースがp3より外 -------
    print("\n--- 3-2: p4がp3より外コースかどうか ---")
    for label, mask in [
        ("p4が外コース（p4_pit > p3_pit）", hit_df['p4_is_outer']),
        ("p4が内コース（p4_pit < p3_pit）", ~hit_df['p4_is_outer']),
    ]:
        s = hit_df[mask]
        n = len(s)
        if n < 5:
            continue
        p3r = s['p3_is_third'].mean() * 100
        p4r = s['p4_is_third'].mean() * 100
        print(f"  {label}: {n}件 | p3率{p3r:.1f}% / p4率{p4r:.1f}% | 差{p3r-p4r:+.1f}pt")

    # ------- 3-3: コース番号別（p4の絶対コース） -------
    print("\n--- 3-3: p4のコース番号別 p4的中率 ---")
    print(f"{'p4コース':>8} | {'件数':>6} | {'p4的中':>7} | {'p4率':>7} | {'p3率':>7}")
    print("-" * 42)
    for course in range(2, 7):
        s = hit_df[hit_df['p4_pit'] == course]
        n = len(s)
        if n < 5:
            continue
        p4r = s['p4_is_third'].mean() * 100
        p3r = s['p3_is_third'].mean() * 100
        n_p4 = s['p4_is_third'].sum()
        print(f"{course}コース  | {n:>6} | {n_p4:>7} | {p4r:>6.1f}% | {p3r:>6.1f}%")

    # p3のコース番号別
    print(f"\n--- 3-4: p3のコース番号別 p3的中率 ---")
    print(f"{'p3コース':>8} | {'件数':>6} | {'p3的中':>7} | {'p3率':>7} | {'p4率':>7}")
    print("-" * 42)
    for course in range(2, 7):
        s = hit_df[hit_df['p3_pit'] == course]
        n = len(s)
        if n < 5:
            continue
        p3r = s['p3_is_third'].mean() * 100
        p4r = s['p4_is_third'].mean() * 100
        n_p3 = s['p3_is_third'].sum()
        print(f"{course}コース  | {n:>6} | {n_p3:>7} | {p3r:>6.1f}% | {p4r:>6.1f}%")

    # ------- 3-5: 選手ランク差 -------
    print("\n--- 3-5: p4のランクがp3より上のとき ---")
    for label, mask in [
        ("p4ランクがp3より上（実力逆転）", hit_df['p4_rank_better']),
        ("p3ランクがp4以上（通常）",       ~hit_df['p4_rank_better']),
    ]:
        s = hit_df[mask]
        n = len(s)
        if n < 5:
            continue
        p3r = s['p3_is_third'].mean() * 100
        p4r = s['p4_is_third'].mean() * 100
        print(f"  {label}: {n}件 | p3率{p3r:.1f}% / p4率{p4r:.1f}% | 差{p3r-p4r:+.1f}pt")

    # ------- 3-6: 複合条件（p4が外コース AND p4ランクが上） -------
    print("\n--- 3-6: 複合条件（p4が外コースかつp4ランクがp3より上） ---")
    mask_combo = hit_df['p4_is_outer'] & hit_df['p4_rank_better']
    s = hit_df[mask_combo]
    n = len(s)
    if n >= 5:
        p3r = s['p3_is_third'].mean() * 100
        p4r = s['p4_is_third'].mean() * 100
        print(f"  件数: {n}件 | p3率{p3r:.1f}% / p4率{p4r:.1f}% | 差{p3r-p4r:+.1f}pt")
    else:
        print(f"  件数不足（{n}件）")


# ============================================================
# Step4: オッズ帯別サブグループ
# ============================================================

def step4_odds_subgroup(df):
    print("\n" + "="*60)
    print("【Step4】オッズ帯別サブグループ（p3軸オッズ基準）")
    print("="*60)
    print("Step2の結論がオッズ帯によって変わるかを確認")
    print()

    hit_df = df[df['p12_hit']].copy()

    print(f"{'オッズ帯':>12} | {'p12的中':>7} | {'p3率':>7} | {'p4率':>7} | {'差':>6}")
    print("-" * 50)

    bins = [(0, 10), (10, 20), (20, 30), (30, 50), (50, 80), (80, 9999)]
    for lo, hi in bins:
        # p3軸オッズがこの帯に入るレース（オッズ0はデータなし = スキップ）
        s = hit_df[(hit_df['odds_p3'] >= lo) & (hit_df['odds_p3'] < hi)]
        n = len(s)
        if n < 10:
            continue
        p3r = s['p3_is_third'].mean() * 100
        p4r = s['p4_is_third'].mean() * 100
        label = f"{lo}-{hi}倍" if hi < 9999 else f"{lo}倍+"
        print(f"{label:>12} | {n:>7} | {p3r:>6.1f}% | {p4r:>6.1f}% | {p3r-p4r:>+5.1f}pt")

    # オッズデータなしのレース
    s_no_odds = hit_df[hit_df['odds_p3'] == 0]
    print(f"{'オッズ未収集':>12} | {len(s_no_odds):>7} | {'--':>6}  | {'--':>6}  | {'--':>6}")


# ============================================================
# Main
# ============================================================

def main():
    conn = sqlite3.connect(DB_PATH)

    print("=" * 60)
    print("3着候補選択の改善分析 v3")
    print("B×A1 全会場・全オッズ帯（2020-2025）")
    print("=" * 60)

    df = load_base_data(conn)
    df = add_columns(df)

    hit_df, p3_rate, p4_rate = step2_third_distribution(df)
    step3_feature_exploration(df, hit_df)
    step4_odds_subgroup(df)

    print("\n" + "="*60)
    print("調査完了")
    print("="*60)

    conn.close()


if __name__ == '__main__':
    main()
