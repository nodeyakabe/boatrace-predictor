#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TJ-8: 払戻金オッズ歪み分析

事前オッズ（trifecta_odds.odds）と実際の払戻金（payouts.amount）の乖離を分析し、
バックテスト精度への影響を評価する。

DB仕様:
- payouts.amount: 整数（100円賭けた場合の払戻額、例: 14320 = 143.20倍）
- trifecta_odds.odds: REAL（倍率、例: 143.2）
- combination形式: 両テーブルとも '1-2-3' 形式（直接JOIN可能）
"""
import sqlite3
import sys
import io
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
MIN_SAMPLE = 30

VENUE_NAMES = {
    1:'桐生', 2:'戸田', 3:'江戸川', 4:'平和島', 5:'多摩川', 6:'浜名湖',
    7:'蒲郡', 8:'常滑', 9:'津', 10:'三国', 11:'琵琶湖', 12:'住之江',
    13:'尼崎', 14:'鳴門', 15:'丸亀', 16:'児島', 17:'宮島', 18:'徳山',
    19:'下関', 20:'若松', 21:'芦屋', 22:'福岡', 23:'唐津', 24:'大村'
}

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ===========================
# Step 1: データ充足率確認と形式検証
# ===========================

def check_data_coverage(conn, start_year, end_year):
    print("=" * 60)
    print("Step 1: データ充足率確認と形式検証")
    print("=" * 60)

    # 期間内のtrifecta payouts件数とJOIN成功率
    query_coverage = f"""
    SELECT COUNT(*) as total_payouts,
           SUM(CASE WHEN t.odds IS NOT NULL THEN 1 ELSE 0 END) as matched,
           ROUND(100.0 * SUM(CASE WHEN t.odds IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as match_rate
    FROM payouts p
    JOIN races r ON p.race_id = r.id
    LEFT JOIN trifecta_odds t ON p.race_id = t.race_id AND p.combination = t.combination
    WHERE p.bet_type = 'trifecta'
      AND r.race_date BETWEEN '{start_year}-01-01' AND '{end_year}-12-31'
    """
    row = conn.execute(query_coverage).fetchone()
    print(f"\n[データ充足率]")
    print(f"  三連単払戻件数: {row['total_payouts']:,}件")
    print(f"  trifecta_oddsとのJOIN成功: {row['matched']:,}件")
    print(f"  JOIN成功率（combination一致率）: {row['match_rate']:.2f}%")

    # サンプルデータ5件表示
    query_sample = f"""
    SELECT
        p.combination as payout_combo,
        t.combination as odds_combo,
        p.amount,
        t.odds
    FROM payouts p
    JOIN races r ON p.race_id = r.id
    JOIN trifecta_odds t ON p.race_id = t.race_id AND p.combination = t.combination
    WHERE p.bet_type = 'trifecta'
      AND t.odds > 0
      AND r.race_date BETWEEN '{start_year}-01-01' AND '{end_year}-12-31'
    LIMIT 5
    """
    rows = conn.execute(query_sample).fetchall()
    print(f"\n[サンプルデータ（5件）]")
    print(f"  {'payout_combo':>12} {'odds_combo':>12} {'amount':>10} {'odds':>8} {'amount/odds/100':>15}")
    for r in rows:
        ratio = r['amount'] / (r['odds'] * 100.0) if r['odds'] and r['odds'] > 0 else None
        ratio_str = f"{ratio:.4f}" if ratio is not None else "N/A"
        print(f"  {r['payout_combo']:>12} {r['odds_combo']:>12} {r['amount']:>10,} {r['odds']:>8.1f} {ratio_str:>15}")


# ===========================
# Step 2: 全体バイアス分布
# ===========================

def analyze_bias_distribution(conn, start_year, end_year):
    print("\n" + "=" * 60)
    print("Step 2: 全体バイアス分布")
    print("=" * 60)

    query = f"""
    SELECT
        p.race_id,
        CAST(r.venue_code AS INTEGER) as venue_code,
        strftime('%Y', r.race_date) as year,
        p.combination,
        t.odds,
        p.amount,
        CAST(p.amount AS REAL) / (t.odds * 100.0) as ratio
    FROM payouts p
    JOIN races r ON p.race_id = r.id
    JOIN trifecta_odds t ON p.race_id = t.race_id AND p.combination = t.combination
    WHERE p.bet_type = 'trifecta'
      AND t.odds > 0
      AND r.race_date BETWEEN '{start_year}-01-01' AND '{end_year}-12-31'
    """
    print("  全件データを取得中...")
    df = pd.read_sql_query(query, conn)

    if df is None or len(df) == 0:
        print("  データなし。スキップ。")
        return None

    print(f"  取得件数: {len(df):,}件")

    print(f"\n[全体バイアス統計]")
    print(f"  サンプル数: {len(df):,}件")
    print(f"  ratio の統計:")
    print(f"    平均: {df['ratio'].mean():.4f} (1.0 = 完全一致)")
    print(f"    中央値: {df['ratio'].median():.4f}")
    print(f"    標準偏差: {df['ratio'].std():.4f}")
    print(f"    10%ile: {df['ratio'].quantile(0.10):.4f}")
    print(f"    90%ile: {df['ratio'].quantile(0.90):.4f}")

    ratio_high = (df['ratio'] > 1.0).sum()
    ratio_low = (df['ratio'] < 1.0).sum()
    print(f"  ※ratio >> 1.0 のケース (>1.0): {ratio_high:,}件 (実払戻が事前オッズより高い)")
    print(f"  ※ratio << 1.0 のケース (<1.0): {ratio_low:,}件 (実払戻が事前オッズより低い)")

    # 外れ値
    outlier_low = (df['ratio'] < 0.1).sum()
    outlier_high = (df['ratio'] > 5.0).sum()
    total = len(df)
    print(f"\n[外れ値]")
    print(f"  ratio < 0.1: {outlier_low:,}件 ({outlier_low/total*100:.3f}%)")
    print(f"  ratio > 5.0: {outlier_high:,}件 ({outlier_high/total*100:.3f}%)")

    # 外れ値除外後のクリーン版統計
    df_clean = df[(df['ratio'] >= 0.1) & (df['ratio'] <= 5.0)].copy()
    print(f"\n[クリーン版統計（外れ値除外後: 0.1 <= ratio <= 5.0）]")
    print(f"  サンプル数: {len(df_clean):,}件")
    print(f"    平均: {df_clean['ratio'].mean():.4f}")
    print(f"    中央値: {df_clean['ratio'].median():.4f}")
    print(f"    標準偏差: {df_clean['ratio'].std():.4f}")
    print(f"    10%ile: {df_clean['ratio'].quantile(0.10):.4f}")
    print(f"    90%ile: {df_clean['ratio'].quantile(0.90):.4f}")

    return df


# ===========================
# Step 3: オッズ帯別バイアス
# ===========================

def get_odds_band(odds):
    if odds < 10:
        return '10倍未満'
    elif odds < 30:
        return '10-30倍'
    elif odds < 100:
        return '30-100倍'
    elif odds < 300:
        return '100-300倍'
    else:
        return '300倍+'

def analyze_bias_by_odds_band(df):
    print("\n" + "=" * 60)
    print("Step 3: オッズ帯別バイアス")
    print("=" * 60)

    df = df.copy()
    df['odds_band'] = df['odds'].apply(get_odds_band)

    band_order = ['10倍未満', '10-30倍', '30-100倍', '100-300倍', '300倍+']
    df['odds_band'] = pd.Categorical(df['odds_band'], categories=band_order, ordered=True)

    grouped = df.groupby('odds_band', observed=False)['ratio'].agg(
        cnt='count',
        ratio_mean='mean',
        ratio_median='median',
        ratio_std='std'
    ).reset_index()

    print(f"\n{'オッズ帯':<12} {'件数':>8} {'ratio平均':>10} {'ratio中央値':>12} {'標準偏差':>10}")
    print("-" * 60)
    for _, row in grouped.iterrows():
        if row['cnt'] > 0:
            print(f"  {str(row['odds_band']):<12} {int(row['cnt']):>8,} {row['ratio_mean']:>10.4f} {row['ratio_median']:>12.4f} {row['ratio_std']:>10.4f}")

    # 外れ値除外後のオッズ帯別統計
    df_clean = df[(df['ratio'] >= 0.1) & (df['ratio'] <= 5.0)].copy()
    grouped_clean = df_clean.groupby('odds_band', observed=False)['ratio'].agg(
        cnt='count',
        ratio_mean='mean',
        ratio_median='median',
        ratio_std='std'
    ).reset_index()

    print(f"\n[クリーン版（外れ値除外後）]")
    print(f"{'オッズ帯':<12} {'件数':>8} {'ratio平均':>10} {'ratio中央値':>12} {'標準偏差':>10}")
    print("-" * 60)
    for _, row in grouped_clean.iterrows():
        if row['cnt'] > 0:
            print(f"  {str(row['odds_band']):<12} {int(row['cnt']):>8,} {row['ratio_mean']:>10.4f} {row['ratio_median']:>12.4f} {row['ratio_std']:>10.4f}")

    return grouped


# ===========================
# Step 4: 年度別バイアス
# ===========================

def analyze_bias_by_year(df):
    print("\n" + "=" * 60)
    print("Step 4: 年度別バイアス")
    print("=" * 60)

    grouped = df.groupby('year')['ratio'].agg(
        cnt='count',
        ratio_mean='mean',
        ratio_median='median'
    ).reset_index()

    print(f"\n{'年度':>6} {'件数':>8} {'ratio平均':>10} {'ratio中央値':>12}")
    print("-" * 40)
    for _, row in grouped.iterrows():
        print(f"  {row['year']:>6} {int(row['cnt']):>8,} {row['ratio_mean']:>10.4f} {row['ratio_median']:>12.4f}")

    return grouped


# ===========================
# Step 5: 予測レースでの実ROI vs 計算ROI（コア分析）
# ===========================

def analyze_roi_discrepancy(conn, start_year, end_year):
    print("\n" + "=" * 60)
    print("Step 5: 予測レースでの実ROI vs 計算ROI（コア分析）")
    print("=" * 60)

    query = f"""
    WITH pred_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) AS pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN CAST(rank AS INTEGER)=1 THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN CAST(rank AS INTEGER)=2 THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN CAST(rank AS INTEGER)=3 THEN pit_number END) AS TEXT) AS actual_combo
        FROM results
        WHERE is_invalid = 0
        GROUP BY race_id
    )
    SELECT
        pc.confidence,
        COUNT(*) as total_races,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        ROUND(100.0 * SUM(
            CASE WHEN pc.pred_combo = ac.actual_combo AND t.odds IS NOT NULL
                 THEN t.odds * 100 ELSE 0 END
        ) / (COUNT(*) * 100), 2) AS roi_odds_based,
        ROUND(100.0 * SUM(
            CASE WHEN pc.pred_combo = ac.actual_combo AND pay.amount IS NOT NULL
                 THEN pay.amount ELSE 0 END
        ) / (COUNT(*) * 100), 2) AS roi_payout_based
    FROM pred_combos pc
    JOIN races r ON pc.race_id = r.id
    LEFT JOIN actual_combos ac ON pc.race_id = ac.race_id
    LEFT JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    LEFT JOIN payouts pay ON pc.race_id = pay.race_id
        AND pay.combination = pc.pred_combo AND pay.bet_type = 'trifecta'
    WHERE r.race_date BETWEEN '{start_year}-01-01' AND '{end_year}-12-31'
      AND t.odds IS NOT NULL
    GROUP BY pc.confidence
    ORDER BY pc.confidence
    """

    print("  信頼度別ROI比較データを取得中...")
    df = pd.read_sql_query(query, conn)

    if df is None or len(df) == 0:
        print("  予測データなし。スキップ。")
        return None

    print(f"\n[信頼度別ROI比較]")
    print(f"{'信頼度':>6} {'件数':>8} {'的中':>6} {'的中率':>8} {'オッズROI':>10} {'実払戻ROI':>10} {'差分':>8}")
    print("-" * 65)

    total_races = 0
    total_hits = 0
    total_roi_odds = 0.0
    total_roi_payout = 0.0

    for _, row in df.iterrows():
        conf = row['confidence']
        total_r = int(row['total_races'])
        hits = int(row['hits'])
        hit_rate = hits / total_r * 100 if total_r > 0 else 0
        roi_odds = row['roi_odds_based'] if row['roi_odds_based'] is not None else 0.0
        roi_pay = row['roi_payout_based'] if row['roi_payout_based'] is not None else 0.0
        diff = roi_pay - roi_odds
        sign = '+' if diff >= 0 else ''
        print(f"  {conf:>6} {total_r:>8,} {hits:>6,} {hit_rate:>7.2f}% {roi_odds:>9.2f}% {roi_pay:>9.2f}% {sign}{diff:>6.2f}pt")

        total_races += total_r
        total_hits += hits
        total_roi_odds += roi_odds * total_r
        total_roi_payout += roi_pay * total_r

    # 合計行
    if total_races > 0:
        overall_hit_rate = total_hits / total_races * 100
        overall_roi_odds = total_roi_odds / total_races
        overall_roi_payout = total_roi_payout / total_races
        overall_diff = overall_roi_payout - overall_roi_odds
        sign = '+' if overall_diff >= 0 else ''
        print("-" * 65)
        print(f"  {'合計':>6} {total_races:>8,} {total_hits:>6,} {overall_hit_rate:>7.2f}% {overall_roi_odds:>9.2f}% {overall_roi_payout:>9.2f}% {sign}{overall_diff:>6.2f}pt")

    return {
        'df': df,
        'total_races': total_races,
        'total_hits': total_hits,
        'overall_roi_odds': overall_roi_odds if total_races > 0 else 0.0,
        'overall_roi_payout': overall_roi_payout if total_races > 0 else 0.0,
        'overall_diff': overall_diff if total_races > 0 else 0.0
    }


# ===========================
# Step 6: 外れ値分析（巨大乖離ケースの特定）
# ===========================

def analyze_outliers(df):
    print("\n" + "=" * 60)
    print("Step 6: 外れ値分析（巨大乖離ケースの特定）")
    print("=" * 60)

    total = len(df)
    outliers = df[(df['ratio'] < 0.05) | (df['ratio'] > 10.0)].copy()
    n_outliers = len(outliers)
    pct = n_outliers / total * 100 if total > 0 else 0

    print(f"\n[外れ値概要]")
    print(f"  ratio < 0.05 または ratio > 10.0: {n_outliers:,}件 (全体の{pct:.3f}%)")

    if n_outliers == 0:
        print("  外れ値なし。")
    else:
        # ratio < 0.05
        out_low = df[df['ratio'] < 0.05]
        print(f"  ratio < 0.05（実払戻が事前オッズより大幅に低い）: {len(out_low):,}件")

        # ratio > 10.0
        out_high = df[df['ratio'] > 10.0]
        print(f"  ratio > 10.0（実払戻が事前オッズより大幅に高い）: {len(out_high):,}件")

        # 年度別偏り
        print(f"\n[外れ値の年度別分布]")
        year_dist = outliers.groupby('year').size().reset_index(name='count')
        for _, row in year_dist.iterrows():
            print(f"    {row['year']}年: {int(row['count']):,}件")

        # 会場別偏り（TOP5）
        print(f"\n[外れ値の会場別分布（TOP5）]")
        venue_dist = outliers.groupby('venue_code').size().reset_index(name='count')
        venue_dist = venue_dist.sort_values('count', ascending=False).head(5)
        for _, row in venue_dist.iterrows():
            vc = int(row['venue_code'])
            vname = VENUE_NAMES.get(vc, f"会場{vc}")
            print(f"    {vname}（{vc}）: {int(row['count']):,}件")

    # 高オッズ（odds > 1000倍）フラグ
    high_odds = df[df['odds'] > 1000]
    print(f"\n[超高オッズ（1000倍超）]")
    print(f"  件数: {len(high_odds):,}件 (全体の{len(high_odds)/total*100:.3f}%)")
    if len(high_odds) > 0:
        print(f"  ratio平均: {high_odds['ratio'].mean():.4f}")
        print(f"  ratio中央値: {high_odds['ratio'].median():.4f}")

    # 外れ値除外の影響評価
    df_no_outlier = df[(df['ratio'] >= 0.05) & (df['ratio'] <= 10.0)].copy()
    print(f"\n[外れ値除外のROI影響評価]")
    print(f"  除外前 ratio平均: {df['ratio'].mean():.4f}")
    print(f"  除外後 ratio平均: {df_no_outlier['ratio'].mean():.4f}")
    print(f"  変化: {df_no_outlier['ratio'].mean() - df['ratio'].mean():+.4f}")

    return outliers


# ===========================
# Step 7: 結論とバックテストへの提言
# ===========================

def summarize_and_recommend(roi_results, df_bias=None):
    print("\n" + "=" * 60)
    print("Step 7: 結論とバックテストへの提言")
    print("=" * 60)

    print(f"\n=== TJ-8 分析結論 ===")
    print(f"【バックテスト精度評価】")

    if df_bias is not None and len(df_bias) > 0:
        df_clean = df_bias[(df_bias['ratio'] >= 0.1) & (df_bias['ratio'] <= 5.0)]
        median_ratio = df_clean['ratio'].median()
        median_bias_pct = (median_ratio - 1.0) * 100

        print(f"  事前オッズ vs 実払戻の中央値乖離: {median_bias_pct:+.2f}%")
        print(f"  (ratio中央値: {median_ratio:.4f}, 1.0 = 完全一致)")

        if abs(median_bias_pct) < 2.0:
            accuracy_judgment = "十分"
        elif abs(median_bias_pct) < 5.0:
            accuracy_judgment = "要注意"
        else:
            accuracy_judgment = "要補正"

        correction_factor = 1.0 / median_ratio if median_ratio > 0 else 1.0
    else:
        median_ratio = 1.0
        median_bias_pct = 0.0
        accuracy_judgment = "データ不足"
        correction_factor = 1.0

    if roi_results is not None:
        roi_diff = roi_results.get('overall_diff', 0.0)
        roi_odds = roi_results.get('overall_roi_odds', 0.0)
        roi_payout = roi_results.get('overall_roi_payout', 0.0)
        print(f"  バックテストROIへの推定影響: {roi_diff:+.2f}pt")
        print(f"  (オッズベースROI: {roi_odds:.2f}%, 実払戻ベースROI: {roi_payout:.2f}%)")
    else:
        print(f"  バックテストROIへの推定影響: 予測データなしのため算出不可")

    print(f"\n【推奨事項】")
    print(f"  ○ 現行のオッズベースROI計算は実用上 [{accuracy_judgment}]")
    print(f"  ○ 補正係数（推奨）: {correction_factor:.4f}")
    print(f"    → 事前オッズROI × {correction_factor:.4f} ≒ 実払戻ROI")

    if df_bias is not None and len(df_bias) > 0:
        df_band = df_bias.copy()
        df_band['odds_band'] = df_band['odds'].apply(get_odds_band)
        high_odds_band = df_band[df_band['odds_band'] == '300倍+']
        if len(high_odds_band) >= MIN_SAMPLE:
            high_median = high_odds_band['ratio'].median()
            high_bias_pct = (high_median - 1.0) * 100
            over_under = "過大" if high_bias_pct < 0 else "過小"
            bias_abs = abs(high_bias_pct)
        else:
            high_median = 1.0
            high_bias_pct = 0.0
            over_under = "不明"
            bias_abs = 0.0

        outlier_cnt = ((df_bias['ratio'] < 0.05) | (df_bias['ratio'] > 10.0)).sum()
        outlier_pct = outlier_cnt / len(df_bias) * 100

        print(f"\n【発見した問題】")
        print(f"  ・高オッズ帯(300倍+)での乖離 ratio中央値={high_median:.4f} ({high_bias_pct:+.2f}%) → 高オッズ帯の期待収益を {bias_abs:.1f}% {over_under}評価")
        print(f"  ・外れ値（ratio < 0.05 or > 10）: {outlier_cnt:,}件（全体の{outlier_pct:.3f}%）→ バックテストに影響{'大' if outlier_pct > 0.1 else '小'}")

    print(f"\n【次のアクション】")
    print(f"  1. docs/HANDOVER.md の「バックテスト注意事項」に追記")
    print(f"  2. 高オッズ帯(300倍+)の条件ではROI評価に注意")
    if accuracy_judgment == "要補正":
        print(f"  3. （補正が必要）config/settings.py に補正係数 {correction_factor:.4f} を追加")
    else:
        print(f"  3. 現状のオッズベースROI計算で実用上問題なし")


# ===========================
# メイン実行
# ===========================

def main():
    parser = argparse.ArgumentParser(description='TJ-8: 払戻金オッズ歪み分析')
    parser.add_argument('--start-year', type=int, default=2020)
    parser.add_argument('--end-year', type=int, default=2025)
    args = parser.parse_args()

    print(f"TJ-8: 払戻金オッズ歪み分析 ({args.start_year}-{args.end_year}年)")
    print("=" * 60)

    conn = get_connection()
    try:
        check_data_coverage(conn, args.start_year, args.end_year)
        df = analyze_bias_distribution(conn, args.start_year, args.end_year)
        if df is not None and len(df) > 0:
            analyze_bias_by_odds_band(df)
            analyze_bias_by_year(df)
        roi_results = analyze_roi_discrepancy(conn, args.start_year, args.end_year)
        if df is not None and len(df) > 0:
            analyze_outliers(df)
        summarize_and_recommend(roi_results, df)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
