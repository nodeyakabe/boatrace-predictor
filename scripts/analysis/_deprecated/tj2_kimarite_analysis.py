#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TJ-2: 決まり手パターン × 予測コース分析

予測1着コース（race_predictions）と実際の決まり手（results.kimarite）の
組み合わせでROI偏りを発見し、フィルター条件を設計する。

kimarite充足率: ~16.5%（= 1/6 ≒ 全レースで1着者分補完済み）
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

# ===========================
# 定数
# ===========================

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"
MIN_SAMPLE = 50

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

KIMARITE_ORDER = ['逃げ', 'まくり', '差し', 'まくり差し', '抜き', 'その他']


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ===========================
# Step 1: データ充足率確認
# ===========================

def check_data_coverage(conn, start_year, end_year):
    print("=" * 60)
    print("Step 1: データ充足率確認")
    print("=" * 60)

    query = """
    SELECT
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT rp.race_id) as predicted_races,
        COUNT(DISTINCT ki.race_id) as kimarite_races,
        COUNT(DISTINCT CASE WHEN rp.race_id IS NOT NULL AND ki.race_id IS NOT NULL
                            THEN r.id END) as both_available
    FROM races r
    LEFT JOIN (
        SELECT DISTINCT race_id FROM race_predictions
        WHERE prediction_type='before' AND rank_prediction=1
    ) rp ON r.id = rp.race_id
    LEFT JOIN (
        SELECT DISTINCT race_id FROM results
        WHERE is_invalid=0 AND CAST(rank AS INTEGER)=1
          AND kimarite IS NOT NULL AND kimarite != ''
    ) ki ON r.id = ki.race_id
    WHERE r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
    """.format(sy=start_year, ey=end_year)

    df = pd.read_sql_query(query, conn)
    row = df.iloc[0]

    total = int(row['total_races'])
    predicted = int(row['predicted_races'])
    kimarite = int(row['kimarite_races'])
    both = int(row['both_available'])

    print(f"\n  期間: {start_year}-01-01 〜 {end_year}-12-31")
    print(f"  総レース数:                   {total:>8,}件")
    print(f"  before予測あり:               {predicted:>8,}件 ({predicted/total*100:.1f}%)" if total > 0 else "  before予測あり:               0件")
    print(f"  kimarite(1着者)あり:          {kimarite:>8,}件 ({kimarite/total*100:.1f}%)" if total > 0 else "  kimarite(1着者)あり:          0件")
    print(f"  両方揃い（分析可能レース数）: {both:>8,}件 ({both/total*100:.1f}%)" if total > 0 else "  両方揃い（分析可能レース数）: 0件")

    return both


# ===========================
# Step 2: 決まり手の全体分布
# ===========================

def analyze_kimarite_distribution(conn, start_year, end_year):
    print("\n" + "=" * 60)
    print("Step 2: 決まり手の全体分布")
    print("=" * 60)

    query = """
    SELECT
        CASE WHEN kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
             THEN kimarite ELSE 'その他' END as km,
        COUNT(*) as cnt
    FROM results res
    JOIN races r ON res.race_id = r.id
    WHERE r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
      AND res.is_invalid = 0
      AND CAST(res.rank AS INTEGER) = 1
      AND res.kimarite IS NOT NULL AND res.kimarite != ''
    GROUP BY km
    ORDER BY cnt DESC
    """.format(sy=start_year, ey=end_year)

    df = pd.read_sql_query(query, conn)

    if df.empty:
        print("  データなし")
        return df

    total = df['cnt'].sum()
    print(f"\n  総件数: {total:,}件\n")
    print(f"  {'決まり手':>10} {'件数':>8} {'割合':>8}")
    print(f"  {'-'*30}")

    for _, row in df.iterrows():
        pct = row['cnt'] / total * 100
        print(f"  {row['km']:>10} {int(row['cnt']):>8,} {pct:>7.1f}%")

    return df


# ===========================
# Step 3: 予測コース × 決まり手 クロス集計（的中率）
# ===========================

def analyze_course_kimarite_cross(conn, start_year, end_year):
    print("\n" + "=" * 60)
    print("Step 3: 予測コース × 決まり手 クロス集計（的中率）")
    print("=" * 60)

    query = """
    SELECT
        rp.pit_number AS pred_pit,
        CASE WHEN res_1st.kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
             THEN res_1st.kimarite ELSE 'その他' END AS km,
        CASE WHEN res_pred.pit_number = res_1st.pit_number THEN 1 ELSE 0 END AS hit
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    JOIN results res_1st ON rp.race_id = res_1st.race_id
        AND res_1st.is_invalid = 0 AND CAST(res_1st.rank AS INTEGER) = 1
        AND res_1st.kimarite IS NOT NULL AND res_1st.kimarite != ''
    LEFT JOIN results res_pred ON rp.race_id = res_pred.race_id
        AND res_pred.pit_number = rp.pit_number AND res_pred.is_invalid = 0
    WHERE rp.prediction_type = 'before' AND rp.rank_prediction = 1
      AND r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
    """.format(sy=start_year, ey=end_year)

    df = pd.read_sql_query(query, conn)

    if df.empty:
        print("  データなし")
        return df

    # pandasで集計
    cross = df.groupby(['pred_pit', 'km']).agg(
        cnt=('hit', 'count'),
        hit_cnt=('hit', 'sum')
    ).reset_index()
    cross['hit_rate'] = (cross['hit_cnt'] / cross['cnt'] * 100).round(2)
    cross = cross[cross['cnt'] >= MIN_SAMPLE]

    if cross.empty:
        print(f"  サンプル数 {MIN_SAMPLE} 件以上のデータなし")
        return cross

    # 表形式表示（予測コース × 決まり手のピボット）
    km_cols = [k for k in KIMARITE_ORDER if k in cross['km'].unique()]
    pivot_rate = cross.pivot_table(
        index='pred_pit', columns='km', values='hit_rate', aggfunc='first'
    ).reindex(columns=km_cols, fill_value=None)
    pivot_cnt = cross.pivot_table(
        index='pred_pit', columns='km', values='cnt', aggfunc='first'
    ).reindex(columns=km_cols, fill_value=None)

    print(f"\n  [予測コース × 決まり手 的中率(%)] (n>={MIN_SAMPLE}のみ表示)")
    header = f"  {'予測':>4} " + "".join(f"{k:>10}" for k in km_cols)
    print(header)
    print(f"  {'-'*len(header)}")

    for pit in sorted(cross['pred_pit'].unique()):
        row_str = f"  {int(pit):>4} "
        for km in km_cols:
            if pit in pivot_rate.index and km in pivot_rate.columns:
                val = pivot_rate.loc[pit, km]
                cnt_val = pivot_cnt.loc[pit, km] if km in pivot_cnt.columns else None
                if pd.notna(val) and cnt_val is not None and pd.notna(cnt_val):
                    row_str += f"{val:>9.1f}%"
                else:
                    row_str += f"{'---':>10}"
            else:
                row_str += f"{'---':>10}"
        print(row_str)

    return cross


# ===========================
# Step 4: ROI計算（三連単・予測順位ベースオッズ使用）
# ===========================

def analyze_course_kimarite_roi(conn, start_year, end_year):
    print("\n" + "=" * 60)
    print("Step 4: 予測コース × 決まり手別 ROI分析")
    print("=" * 60)

    query = """
    WITH race_data AS (
        SELECT
            rp1.race_id,
            rp1.pit_number AS pred1,
            rp2.pit_number AS pred2,
            rp3.pit_number AS pred3,
            rp1.confidence,
            -- 実際の1着者の情報（決まり手含む）
            res_1st.pit_number AS actual_1st_pit,
            CASE WHEN res_1st.kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
                 THEN res_1st.kimarite ELSE 'その他' END AS km,
            -- 的中判定（1着-2着-3着が予測順通り）
            CASE WHEN res_1st.pit_number = rp1.pit_number
                  AND res_2nd.pit_number = rp2.pit_number
                  AND res_3rd.pit_number = rp3.pit_number
                 THEN 1 ELSE 0 END AS hit,
            -- オッズ（予測組み合わせ）
            t.odds
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp1.race_id = r.id
        -- 実際の1着者
        JOIN results res_1st ON rp1.race_id = res_1st.race_id
            AND res_1st.is_invalid = 0 AND CAST(res_1st.rank AS INTEGER) = 1
            AND res_1st.kimarite IS NOT NULL AND res_1st.kimarite != ''
        -- 実際の2着者
        LEFT JOIN results res_2nd ON rp1.race_id = res_2nd.race_id
            AND res_2nd.is_invalid = 0 AND CAST(res_2nd.rank AS INTEGER) = 2
        -- 実際の3着者
        LEFT JOIN results res_3rd ON rp1.race_id = res_3rd.race_id
            AND res_3rd.is_invalid = 0 AND CAST(res_3rd.rank AS INTEGER) = 3
        -- 予測順位ベースのオッズ
        LEFT JOIN trifecta_odds t ON rp1.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
          AND t.odds IS NOT NULL
    )
    SELECT
        pred1,
        km,
        COUNT(*) as total,
        SUM(hit) as hits,
        ROUND(100.0 * SUM(hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(CASE WHEN hit=1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 2) as roi
    FROM race_data
    GROUP BY pred1, km
    """.format(sy=start_year, ey=end_year)

    df = pd.read_sql_query(query, conn)

    if df.empty:
        print("  データなし（オッズデータが不足している可能性があります）")
        return df

    df_filtered = df[df['total'] >= MIN_SAMPLE].sort_values('roi', ascending=False)

    if df_filtered.empty:
        print(f"  サンプル数 {MIN_SAMPLE} 件以上のデータなし")
        return df_filtered

    print(f"\n  [予測コース × 決まり手 ROI分析] (n>={MIN_SAMPLE}, ROI降順)")
    print(f"  {'予測コース':>8} {'決まり手':>10} {'件数':>8} {'的中数':>8} {'的中率':>8} {'ROI':>10}")
    print(f"  {'-'*60}")

    for _, row in df_filtered.iterrows():
        marker = " ★" if row['roi'] >= 150 else ""
        print(f"  {int(row['pred1']):>8} {row['km']:>10} {int(row['total']):>8,} {int(row['hits']):>8,} {row['hit_rate']:>7.2f}% {row['roi']:>9.1f}%{marker}")

    # ROI高い・低いの概要
    n_high = (df_filtered['roi'] >= 150).sum()
    n_low = (df_filtered['roi'] < 80).sum()
    print(f"\n  ROI >= 150%: {n_high}件, ROI < 80%: {n_low}件")

    # ROI全体平均
    overall_roi = df['roi'].mean()
    print(f"  全体平均ROI: {overall_roi:.1f}%")

    return df_filtered


# ===========================
# Step 5: 信頼度 × 決まり手 ROI
# ===========================

def analyze_confidence_kimarite_roi(conn, start_year, end_year):
    print("\n" + "=" * 60)
    print("Step 5: 信頼度 × 決まり手別 ROI分析")
    print("=" * 60)

    query = """
    WITH race_data AS (
        SELECT
            rp1.race_id,
            rp1.pit_number AS pred1,
            rp2.pit_number AS pred2,
            rp3.pit_number AS pred3,
            rp1.confidence,
            CASE WHEN res_1st.kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
                 THEN res_1st.kimarite ELSE 'その他' END AS km,
            CASE WHEN res_1st.pit_number = rp1.pit_number
                  AND res_2nd.pit_number = rp2.pit_number
                  AND res_3rd.pit_number = rp3.pit_number
                 THEN 1 ELSE 0 END AS hit,
            t.odds
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp1.race_id = r.id
        JOIN results res_1st ON rp1.race_id = res_1st.race_id
            AND res_1st.is_invalid = 0 AND CAST(res_1st.rank AS INTEGER) = 1
            AND res_1st.kimarite IS NOT NULL AND res_1st.kimarite != ''
        LEFT JOIN results res_2nd ON rp1.race_id = res_2nd.race_id
            AND res_2nd.is_invalid = 0 AND CAST(res_2nd.rank AS INTEGER) = 2
        LEFT JOIN results res_3rd ON rp1.race_id = res_3rd.race_id
            AND res_3rd.is_invalid = 0 AND CAST(res_3rd.rank AS INTEGER) = 3
        LEFT JOIN trifecta_odds t ON rp1.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
          AND t.odds IS NOT NULL
    )
    SELECT
        confidence,
        km,
        COUNT(*) as total,
        SUM(hit) as hits,
        ROUND(100.0 * SUM(hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(CASE WHEN hit=1 THEN odds * 100 ELSE 0 END) / (COUNT(*) * 100), 2) as roi
    FROM race_data
    GROUP BY confidence, km
    """.format(sy=start_year, ey=end_year)

    df = pd.read_sql_query(query, conn)

    if df.empty:
        print("  データなし")
        return df

    df_filtered = df[df['total'] >= MIN_SAMPLE].sort_values(['confidence', 'roi'], ascending=[True, False])

    print(f"\n  [信頼度 × 決まり手 ROI分析] (n>={MIN_SAMPLE}, 信頼度→ROI降順)")
    print(f"  {'信頼度':>6} {'決まり手':>10} {'件数':>8} {'的中数':>8} {'的中率':>8} {'ROI':>10}")
    print(f"  {'-'*55}")

    current_conf = None
    for _, row in df_filtered.iterrows():
        if row['confidence'] != current_conf:
            current_conf = row['confidence']
            print(f"  --- 信頼度: {current_conf} ---")
        marker = " ★" if row['roi'] >= 150 else ""
        print(f"  {row['confidence']:>6} {row['km']:>10} {int(row['total']):>8,} {int(row['hits']):>8,} {row['hit_rate']:>7.2f}% {row['roi']:>9.1f}%{marker}")

    return df_filtered


# ===========================
# Step 6: 会場別 × 決まり手別 ROI（stadium_attack_statsと照合）
# ===========================

def analyze_venue_kimarite_roi(conn, start_year, end_year):
    print("\n" + "=" * 60)
    print("Step 6: 会場別 × 決まり手別 ROI分析")
    print("=" * 60)

    query = """
    WITH race_data AS (
        SELECT
            r.venue_code,
            rp1.pit_number AS pred1,
            rp2.pit_number AS pred2,
            rp3.pit_number AS pred3,
            CASE WHEN res_1st.kimarite IN ('逃げ','まくり','差し','まくり差し','抜き')
                 THEN res_1st.kimarite ELSE 'その他' END AS km,
            CASE WHEN res_1st.pit_number = rp1.pit_number
                  AND res_2nd.pit_number = rp2.pit_number
                  AND res_3rd.pit_number = rp3.pit_number
                 THEN 1 ELSE 0 END AS hit,
            t.odds
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races r ON rp1.race_id = r.id
        JOIN results res_1st ON rp1.race_id = res_1st.race_id
            AND res_1st.is_invalid = 0 AND CAST(res_1st.rank AS INTEGER) = 1
            AND res_1st.kimarite IS NOT NULL AND res_1st.kimarite != ''
        LEFT JOIN results res_2nd ON rp1.race_id = res_2nd.race_id
            AND res_2nd.is_invalid = 0 AND CAST(res_2nd.rank AS INTEGER) = 2
        LEFT JOIN results res_3rd ON rp1.race_id = res_3rd.race_id
            AND res_3rd.is_invalid = 0 AND CAST(res_3rd.rank AS INTEGER) = 3
        LEFT JOIN trifecta_odds t ON rp1.race_id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND r.race_date BETWEEN '{sy}-01-01' AND '{ey}-12-31'
          AND t.odds IS NOT NULL
    )
    SELECT
        rd.venue_code,
        rd.km,
        COUNT(*) as total,
        SUM(rd.hit) as hits,
        ROUND(100.0 * SUM(rd.hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(CASE WHEN rd.hit=1 THEN rd.odds * 100 ELSE 0 END) / (COUNT(*) * 100), 2) as roi
    FROM race_data rd
    GROUP BY rd.venue_code, rd.km
    """.format(sy=start_year, ey=end_year)

    df = pd.read_sql_query(query, conn)

    if df.empty:
        print("  データなし")
        return df

    # stadium_attack_statsをJOIN（年度平均）
    query_stats = """
    SELECT
        venue_code,
        AVG(maki_rate) as maki_rate,
        AVG(sashi_rate) as sashi_rate
    FROM stadium_attack_stats
    GROUP BY venue_code
    """
    try:
        df_stats = pd.read_sql_query(query_stats, conn)
        has_stats = not df_stats.empty
    except Exception:
        has_stats = False
        df_stats = pd.DataFrame()

    df_filtered = df[df['total'] >= MIN_SAMPLE].sort_values('roi', ascending=False)

    if df_filtered.empty:
        print(f"  サンプル数 {MIN_SAMPLE} 件以上のデータなし")
        return df_filtered

    # まくり系を中心に表示（実まくり率との対比）
    print(f"\n  [会場別 × 決まり手 ROI分析（上位30件）] (n>={MIN_SAMPLE}, ROI降順)")
    if has_stats:
        print(f"  {'会場':>6} {'決まり手':>10} {'件数':>8} {'的中率':>8} {'ROI':>10} {'会場まくり率':>12} {'会場差し率':>10}")
        print(f"  {'-'*70}")
    else:
        print(f"  {'会場':>6} {'決まり手':>10} {'件数':>8} {'的中率':>8} {'ROI':>10}")
        print(f"  {'-'*50}")

    display_limit = 30
    for idx, (_, row) in enumerate(df_filtered.iterrows()):
        if idx >= display_limit:
            print(f"  ... （残り{len(df_filtered)-display_limit}件省略）")
            break
        venue_code = int(row['venue_code']) if pd.notna(row['venue_code']) else 0
        venue_name = VENUE_NAMES.get(venue_code, f"会場{venue_code}")
        marker = " ★" if row['roi'] >= 150 else ""

        if has_stats and venue_code in df_stats['venue_code'].values:
            stat_row = df_stats[df_stats['venue_code'] == venue_code].iloc[0]
            maki_r = stat_row['maki_rate']
            sashi_r = stat_row['sashi_rate']
            maki_str = f"{maki_r*100:.1f}%" if pd.notna(maki_r) else "  N/A"
            sashi_str = f"{sashi_r*100:.1f}%" if pd.notna(sashi_r) else "  N/A"
            print(f"  {venue_name:>6} {row['km']:>10} {int(row['total']):>8,} {row['hit_rate']:>7.2f}% {row['roi']:>9.1f}%{marker} {maki_str:>12} {sashi_str:>10}")
        else:
            print(f"  {venue_name:>6} {row['km']:>10} {int(row['total']):>8,} {row['hit_rate']:>7.2f}% {row['roi']:>9.1f}%{marker}")

    # まくり系ROIと会場まくり率の相関確認
    if has_stats:
        df_maki = df_filtered[df_filtered['km'].isin(['まくり', 'まくり差し'])].copy()
        df_maki['venue_code_int'] = df_maki['venue_code'].astype(int)
        df_maki = df_maki.merge(df_stats, left_on='venue_code_int', right_on='venue_code', how='left')

        if len(df_maki) >= 5 and df_maki['maki_rate'].notna().sum() >= 5:
            corr = df_maki['roi'].corr(df_maki['maki_rate'])
            print(f"\n  [まくり系ROI × 会場まくり率の相関係数]: {corr:.3f}")
            if abs(corr) > 0.3:
                print(f"  → 相関あり: 会場まくり率が高いほどまくり系のROIが{'高い' if corr > 0 else '低い'}")
            else:
                print(f"  → 相関弱い（会場まくり率とまくり系ROIは独立している可能性）")

    return df_filtered


# ===========================
# Step 7: 高ROI組み合わせ抽出とフィルター候補提案
# ===========================

def generate_filter_candidates(df_roi):
    print("\n" + "=" * 60)
    print("Step 7: 高ROI組み合わせ抽出とフィルター候補")
    print("=" * 60)

    if df_roi is None or df_roi.empty:
        print("  ROIデータなし（Step 4でデータが取得できませんでした）")
        return

    # ROI >= 150% かつ件数 >= MIN_SAMPLE
    high_roi = df_roi[(df_roi['roi'] >= 150) & (df_roi['total'] >= MIN_SAMPLE)]

    print(f"\n=== 高ROI組み合わせ (ROI >= 150%, n >= {MIN_SAMPLE}) ===")

    if high_roi.empty:
        print(f"  ROI 150%以上の組み合わせなし")
        # 代わりに上位5件を表示
        top5 = df_roi.head(5)
        print(f"\n  参考: ROI上位5件:")
        for _, row in top5.iterrows():
            print(f"    予測コース: {int(row['pred1'])}, 決まり手: {row['km']}, "
                  f"ROI: {row['roi']:.1f}%, 件数: {int(row['total'])}")
    else:
        for _, row in high_roi.iterrows():
            print(f"  予測コース: {int(row['pred1'])}, 決まり手: {row['km']}, "
                  f"ROI: {row['roi']:.1f}%, 件数: {int(row['total'])}")

    print(f"""
【注意】決まり手はリアルタイムでは予測不可。
以下のような間接的なフィルター条件として活用することを推奨:
- 「まくりが多い会場（stadium_attack_stats.maki_rate >= 25%）× 3-4コース予測」
- 「まくり差しが多い会場 × オッズ高め」
- 「逃げが多い状況（1コース予測） × 低オッズ帯でのフィルタリング除外」

Tier1テスト候補コマンド例:
python scripts/backtest/quick_condition_test.py --condition-json '{{
  "id": "TJ2_MAKI_VENUE",
  "name": "まくり多発会場x3-4コース予測",
  "confidence": "B",
  "c1_rank": ["A1","A2","B1"],
  "odds_min": 30,
  "odds_max": 200,
  "use_pattern_h": true
}}'
""")

    # ROI < 80% の低ROI組み合わせ（除外候補）
    low_roi = df_roi[(df_roi['roi'] < 80) & (df_roi['total'] >= MIN_SAMPLE)]
    if not low_roi.empty:
        print(f"=== 低ROI組み合わせ（除外候補）: ROI < 80%, n >= {MIN_SAMPLE} ===")
        for _, row in low_roi.iterrows():
            print(f"  予測コース: {int(row['pred1'])}, 決まり手: {row['km']}, "
                  f"ROI: {row['roi']:.1f}%, 件数: {int(row['total'])}")
        print("\n  → これらの組み合わせはbetを避けることを推奨")


# ===========================
# メイン実行
# ===========================

def main():
    parser = argparse.ArgumentParser(description='TJ-2: 決まり手パターン × 予測コース分析')
    parser.add_argument('--start-year', type=int, default=2020)
    parser.add_argument('--end-year', type=int, default=2025)
    args = parser.parse_args()

    print(f"TJ-2: 決まり手パターン × 予測コース分析 ({args.start_year}-{args.end_year}年)")
    print("=" * 60)

    conn = get_connection()
    try:
        check_data_coverage(conn, args.start_year, args.end_year)
        analyze_kimarite_distribution(conn, args.start_year, args.end_year)
        analyze_course_kimarite_cross(conn, args.start_year, args.end_year)
        df_roi = analyze_course_kimarite_roi(conn, args.start_year, args.end_year)
        analyze_confidence_kimarite_roi(conn, args.start_year, args.end_year)
        analyze_venue_kimarite_roi(conn, args.start_year, args.end_year)
        generate_filter_candidates(df_roi)

        print("\n" + "=" * 60)
        print("【分析完了】")
        print("=" * 60)
        print("  高ROI組み合わせをStep 7で確認し、Tier1テストに進んでください。")
        print("  決まり手はリアルタイム予測不可のため、間接的フィルター（会場特性等）を活用してください。")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
