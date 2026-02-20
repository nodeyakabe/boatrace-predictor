# -*- coding: utf-8 -*-
"""
事前情報を活用した除外条件の調査スクリプト

調査対象の購入条件:
1. D×35-60: 信頼度D、オッズ35-60倍、1コースA1/A2/B1、9R除外、三国除外
2. D×40-50×B1: 信頼度D、オッズ40-50倍、1コースB1のみ
3. D×5コース予測: 信頼度D、5コース艇が1着予測、オッズ10-200倍
4. C×20-30×B1+会場: 信頼度C、オッズ20-30倍、1コースB1、特定会場のみ

調査項目:
- 1コース選手の勝率 (national_win_rate, local_win_rate)
- 1コース選手の2連率 (national_second_rate)
- 選手年齢 (age)
- 選手体重 (weight)
- レース番号 (race_number)
- 曜日 (race_dateから算出)
- 月 (季節性)
- 予測買い目のオッズ順位
"""

import sqlite3
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


def get_connection():
    """データベース接続を取得"""
    return sqlite3.connect(DATABASE_PATH)


def fetch_analysis_data():
    """
    分析用データを取得
    - race_predictions: 予測データ
    - entries: 選手情報
    - races: レース情報
    - results: 結果
    - trifecta_odds: オッズ
    - payouts: 払戻
    """
    query = """
    WITH predicted_ranks AS (
        -- 1着予測のみを取得（prediction_type = 'before' を優先、なければ 'advance'）
        SELECT
            rp.race_id,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence,
            rp.total_score,
            rp.prediction_type,
            ROW_NUMBER() OVER (PARTITION BY rp.race_id ORDER BY
                CASE WHEN rp.prediction_type = 'before' THEN 1 ELSE 2 END,
                rp.rank_prediction
            ) as rn
        FROM race_predictions rp
        WHERE rp.rank_prediction = 1
    ),
    first_predictions AS (
        SELECT
            race_id,
            pit_number as predicted_first,
            confidence,
            total_score,
            prediction_type
        FROM predicted_ranks
        WHERE rn = 1
    ),
    full_predictions AS (
        -- 各レースの1-2-3予測を取得
        SELECT
            rp.race_id,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.total_score END) as total_score
        FROM race_predictions rp
        WHERE rp.prediction_type IN ('before', 'advance')
        GROUP BY rp.race_id
        HAVING pred_1st IS NOT NULL AND pred_2nd IS NOT NULL AND pred_3rd IS NOT NULL
    ),
    race_results AS (
        -- 実際の1-2-3着を取得
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
        FROM results
        WHERE rank IN ('1', '2', '3') AND is_invalid = 0
        GROUP BY race_id
        HAVING actual_1st IS NOT NULL AND actual_2nd IS NOT NULL AND actual_3rd IS NOT NULL
    )
    SELECT
        r.id as race_id,
        r.venue_code,
        r.race_date,
        r.race_number,
        substr(r.race_date, 1, 4) as year,
        -- 曜日（0=月曜, 6=日曜）
        CAST(strftime('%w', r.race_date) AS INTEGER) as weekday,
        -- 月
        CAST(substr(r.race_date, 6, 2) AS INTEGER) as month,
        -- 予測情報
        fp.pred_1st,
        fp.pred_2nd,
        fp.pred_3rd,
        fp.confidence,
        fp.total_score,
        -- 結果
        rr.actual_1st,
        rr.actual_2nd,
        rr.actual_3rd,
        -- 的中判定
        CASE WHEN fp.pred_1st = rr.actual_1st
             AND fp.pred_2nd = rr.actual_2nd
             AND fp.pred_3rd = rr.actual_3rd
             THEN 1 ELSE 0 END as is_hit,
        -- 1コース選手情報
        e1.racer_rank as c1_rank,
        e1.win_rate as c1_win_rate,
        e1.second_rate as c1_second_rate,
        e1.local_win_rate as c1_local_win_rate,
        e1.local_second_rate as c1_local_second_rate,
        e1.racer_age as c1_age,
        e1.racer_weight as c1_weight,
        e1.motor_second_rate as c1_motor_rate,
        -- オッズ情報
        t.odds as pred_odds,
        -- 払戻金
        p.amount as payout
    FROM races r
    INNER JOIN full_predictions fp ON r.id = fp.race_id
    INNER JOIN race_results rr ON r.id = rr.race_id
    LEFT JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = fp.pred_1st || '-' || fp.pred_2nd || '-' || fp.pred_3rd
    LEFT JOIN payouts p ON r.id = p.race_id
        AND p.bet_type = 'trifecta'
        AND p.combination = rr.actual_1st || '-' || rr.actual_2nd || '-' || rr.actual_3rd
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date <= '2025-12-31'
    ORDER BY r.race_date, r.venue_code, r.race_number
    """

    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()

    return df


def filter_by_condition(df, condition_name):
    """
    購入条件でフィルタリング
    """
    # C条件用会場フィルター
    c_venues = ['23', '18', '05', '04', '09', '15', '08', '24', '20', '17']

    if condition_name == 'D_35_60':
        # D×35-60: 信頼度D、オッズ35-60倍、1コースA1/A2/B1、9R除外、三国除外
        mask = (
            (df['confidence'] == 'D') &
            (df['pred_odds'] >= 35) & (df['pred_odds'] < 60) &
            (df['c1_rank'].isin(['A1', 'A2', 'B1'])) &
            (df['race_number'] != 9) &
            (df['venue_code'] != '10')
        )
    elif condition_name == 'D_40_50_B1':
        # D×40-50×B1: 信頼度D、オッズ40-50倍、1コースB1のみ
        mask = (
            (df['confidence'] == 'D') &
            (df['pred_odds'] >= 40) & (df['pred_odds'] < 50) &
            (df['c1_rank'] == 'B1')
        )
    elif condition_name == 'D_5course':
        # D×5コース予測: 信頼度D、5コース艇が1着予測、オッズ10-200倍
        mask = (
            (df['confidence'] == 'D') &
            (df['pred_1st'] == 5) &
            (df['pred_odds'] >= 10) & (df['pred_odds'] < 200)
        )
    elif condition_name == 'C_20_30_B1':
        # C×20-30×B1+会場: 信頼度C、オッズ20-30倍、1コースB1、特定会場のみ
        mask = (
            (df['confidence'] == 'C') &
            (df['pred_odds'] >= 20) & (df['pred_odds'] < 30) &
            (df['c1_rank'] == 'B1') &
            (df['venue_code'].isin(c_venues))
        )
    else:
        mask = pd.Series([True] * len(df))

    return df[mask].copy()


def analyze_segment(df, segment_col, segment_name, min_samples=30):
    """
    セグメント別の成績を分析
    """
    results = []

    # NaN除外
    df_valid = df[df[segment_col].notna()].copy()

    if len(df_valid) == 0:
        return pd.DataFrame()

    # セグメントのビニング（数値の場合）
    if df_valid[segment_col].dtype in ['float64', 'int64']:
        # 四分位数でビニング
        try:
            df_valid['segment'] = pd.qcut(df_valid[segment_col], q=4, duplicates='drop')
        except ValueError:
            # ビニングできない場合はそのまま
            df_valid['segment'] = df_valid[segment_col]
    else:
        df_valid['segment'] = df_valid[segment_col]

    segments = df_valid['segment'].unique()

    for seg in segments:
        seg_df = df_valid[df_valid['segment'] == seg]

        if len(seg_df) < min_samples:
            continue

        # 成績計算
        total = len(seg_df)
        hits = seg_df['is_hit'].sum()
        hit_rate = hits / total * 100 if total > 0 else 0

        # 投資額と払戻
        bet_amount = total * 100  # 1点100円想定
        payout_total = seg_df[seg_df['is_hit'] == 1]['payout'].fillna(0).sum()
        roi = payout_total / bet_amount * 100 if bet_amount > 0 else 0
        profit = payout_total - bet_amount

        results.append({
            'segment_name': segment_name,
            'segment_value': str(seg),
            'count': total,
            'hits': hits,
            'hit_rate': hit_rate,
            'roi': roi,
            'profit': profit
        })

    return pd.DataFrame(results)


def chi_square_test(df, segment_col):
    """
    セグメント間の的中率に統計的有意差があるかカイ二乗検定
    """
    df_valid = df[df[segment_col].notna()].copy()

    if len(df_valid) == 0:
        return None, None

    # セグメントのビニング（数値の場合）
    if df_valid[segment_col].dtype in ['float64', 'int64']:
        try:
            df_valid['segment'] = pd.qcut(df_valid[segment_col], q=4, duplicates='drop')
        except ValueError:
            df_valid['segment'] = df_valid[segment_col]
    else:
        df_valid['segment'] = df_valid[segment_col]

    # クロス集計表
    contingency = pd.crosstab(df_valid['segment'], df_valid['is_hit'])

    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        return None, None

    # カイ二乗検定
    try:
        chi2, p_value, dof, expected = stats.chi2_contingency(contingency)
        return chi2, p_value
    except Exception:
        return None, None


def analyze_yearly_stability(df, segment_col, low_roi_segments):
    """
    低ROIセグメントの年度別安定性を確認
    """
    results = []

    df_valid = df[df[segment_col].notna()].copy()

    if len(df_valid) == 0:
        return pd.DataFrame()

    # セグメントのビニング
    if df_valid[segment_col].dtype in ['float64', 'int64']:
        try:
            df_valid['segment'] = pd.qcut(df_valid[segment_col], q=4, duplicates='drop')
        except ValueError:
            df_valid['segment'] = df_valid[segment_col]
    else:
        df_valid['segment'] = df_valid[segment_col]

    for seg in low_roi_segments:
        seg_df = df_valid[df_valid['segment'].astype(str) == str(seg)]

        if len(seg_df) == 0:
            continue

        for year in sorted(seg_df['year'].unique()):
            year_df = seg_df[seg_df['year'] == year]

            if len(year_df) < 10:
                continue

            total = len(year_df)
            hits = year_df['is_hit'].sum()
            bet_amount = total * 100
            payout_total = year_df[year_df['is_hit'] == 1]['payout'].fillna(0).sum()
            roi = payout_total / bet_amount * 100 if bet_amount > 0 else 0

            results.append({
                'segment': str(seg),
                'year': year,
                'count': total,
                'hits': hits,
                'roi': roi
            })

    return pd.DataFrame(results)


def main():
    """メイン処理"""
    print("=" * 80)
    print("事前情報を活用した除外条件の調査")
    print("=" * 80)
    print()

    # データ取得
    print("データ取得中...")
    df = fetch_analysis_data()
    print(f"総レース数: {len(df):,}件")
    print(f"期間: {df['race_date'].min()} ~ {df['race_date'].max()}")
    print()

    # 購入条件リスト
    conditions = [
        ('D_35_60', 'D×35-60倍（A1/A2/B1、9R除外、三国除外）'),
        ('D_40_50_B1', 'D×40-50倍×B1'),
        ('D_5course', 'D×5コース予測'),
        ('C_20_30_B1', 'C×20-30倍×B1+会場'),
    ]

    # 分析対象の事前情報
    analysis_cols = [
        ('c1_win_rate', '1コース勝率'),
        ('c1_second_rate', '1コース2連率'),
        ('c1_local_win_rate', '1コース当地勝率'),
        ('c1_age', '1コース選手年齢'),
        ('c1_weight', '1コース選手体重'),
        ('race_number', 'レース番号'),
        ('weekday', '曜日'),
        ('month', '月'),
    ]

    all_results = []
    recommendations = []

    for cond_key, cond_name in conditions:
        print("=" * 80)
        print(f"条件: {cond_name}")
        print("=" * 80)

        df_cond = filter_by_condition(df, cond_key)

        if len(df_cond) == 0:
            print("該当データなし")
            continue

        # 全体成績
        total = len(df_cond)
        hits = df_cond['is_hit'].sum()
        hit_rate = hits / total * 100 if total > 0 else 0
        bet_amount = total * 100
        payout_total = df_cond[df_cond['is_hit'] == 1]['payout'].fillna(0).sum()
        roi = payout_total / bet_amount * 100 if bet_amount > 0 else 0

        print(f"全体: {total}件, 的中{hits}件({hit_rate:.2f}%), ROI {roi:.1f}%")
        print()

        for col, col_name in analysis_cols:
            print(f"--- {col_name} ---")

            # セグメント分析
            seg_results = analyze_segment(df_cond, col, col_name)

            if len(seg_results) == 0:
                print("  分析不可（データ不足またはNaN）")
                continue

            # カイ二乗検定
            chi2, p_value = chi_square_test(df_cond, col)

            if p_value is not None:
                sig = "***" if p_value < 0.001 else "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
                print(f"  カイ二乗検定: p={p_value:.4f} {sig}")

            # セグメント別成績表示
            for _, row in seg_results.iterrows():
                roi_indicator = "LOW" if row['roi'] < 80 else "HIGH" if row['roi'] > 150 else ""
                print(f"  {row['segment_value']}: {row['count']}件, ROI {row['roi']:.1f}% {roi_indicator}")

            # 低ROIセグメント（80%未満）を抽出
            low_roi_segs = seg_results[seg_results['roi'] < 80]

            if len(low_roi_segs) > 0 and p_value is not None and p_value < 0.05:
                print()
                print(f"  >> 有望な除外候補あり（p < 0.05）")

                for _, row in low_roi_segs.iterrows():
                    # 年度別安定性確認
                    yearly = analyze_yearly_stability(df_cond, col, [row['segment_value']])

                    if len(yearly) > 0:
                        low_years = yearly[yearly['roi'] < 100]
                        stable = len(low_years) >= len(yearly) * 0.5  # 半数以上の年で赤字

                        rec = {
                            'condition': cond_name,
                            'segment': col_name,
                            'value': row['segment_value'],
                            'count': row['count'],
                            'roi': row['roi'],
                            'p_value': p_value,
                            'yearly_stable': stable,
                            'low_years': len(low_years),
                            'total_years': len(yearly)
                        }
                        recommendations.append(rec)
                        all_results.append(rec)

                        if stable:
                            print(f"  >> {row['segment_value']}: 年度安定性あり（{len(low_years)}/{len(yearly)}年で赤字）")
                        else:
                            print(f"  >> {row['segment_value']}: 年度安定性なし（{len(low_years)}/{len(yearly)}年で赤字）")

            print()

    # サマリー
    print()
    print("=" * 80)
    print("除外条件候補のサマリー")
    print("=" * 80)

    if len(recommendations) > 0:
        rec_df = pd.DataFrame(recommendations)
        rec_df = rec_df.sort_values(['p_value', 'roi'])

        print("\n統計的に有意な低ROIセグメント（p < 0.05）:")
        print("-" * 80)

        for _, row in rec_df.iterrows():
            stable_mark = "[安定]" if row['yearly_stable'] else "[不安定]"
            sig = "***" if row['p_value'] < 0.001 else "**" if row['p_value'] < 0.01 else "*"
            print(f"{row['condition']}")
            print(f"  除外候補: {row['segment']} = {row['value']}")
            print(f"  成績: {row['count']}件, ROI {row['roi']:.1f}%")
            print(f"  統計: p={row['p_value']:.4f} {sig}")
            print(f"  年度安定性: {stable_mark} ({row['low_years']}/{row['total_years']}年で赤字)")
            print()

        # 最終推奨
        print()
        print("=" * 80)
        print("最終的な採用推奨")
        print("=" * 80)

        # 条件: p < 0.05 かつ 年度安定性あり
        recommended = rec_df[(rec_df['p_value'] < 0.05) & (rec_df['yearly_stable'] == True)]

        if len(recommended) > 0:
            print("\n採用推奨（p < 0.05 かつ 年度安定性あり）:")
            for _, row in recommended.iterrows():
                print(f"  - {row['condition']}: {row['segment']} = {row['value']} を除外")
                print(f"    (ROI {row['roi']:.1f}%, p={row['p_value']:.4f})")
        else:
            print("\n統計的に有意かつ年度安定性のある除外条件は見つかりませんでした。")
    else:
        print("\n統計的に有意な除外条件候補は見つかりませんでした。")

    return all_results


if __name__ == "__main__":
    results = main()
