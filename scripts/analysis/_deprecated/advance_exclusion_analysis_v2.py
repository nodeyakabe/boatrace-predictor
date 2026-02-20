# -*- coding: utf-8 -*-
"""
事前情報を活用した除外条件の調査スクリプト v2

調査対象の購入条件:
1. D×35-60: 信頼度D、オッズ35-60倍、1コースA1/A2/B1、9R除外、三国除外
2. D×40-50×B1: 信頼度D、オッズ40-50倍、1コースB1のみ
3. D×5コース予測: 信頼度D、5コース艇が1着予測、オッズ10-200倍
4. C×20-30×B1+会場: 信頼度C、オッズ20-30倍、1コースB1、特定会場のみ
"""

import sqlite3
import sys
import io
from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime

# 標準出力のエンコーディングを設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


def get_connection():
    """データベース接続を取得"""
    return sqlite3.connect(DATABASE_PATH)


def fetch_analysis_data():
    """分析用データを取得"""
    query = """
    WITH full_predictions AS (
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
        CAST(strftime('%w', r.race_date) AS INTEGER) as weekday,
        CAST(substr(r.race_date, 6, 2) AS INTEGER) as month,
        fp.pred_1st,
        fp.pred_2nd,
        fp.pred_3rd,
        fp.confidence,
        fp.total_score,
        rr.actual_1st,
        rr.actual_2nd,
        rr.actual_3rd,
        CASE WHEN fp.pred_1st = rr.actual_1st
             AND fp.pred_2nd = rr.actual_2nd
             AND fp.pred_3rd = rr.actual_3rd
             THEN 1 ELSE 0 END as is_hit,
        e1.racer_rank as c1_rank,
        e1.win_rate as c1_win_rate,
        e1.second_rate as c1_second_rate,
        e1.local_win_rate as c1_local_win_rate,
        e1.local_second_rate as c1_local_second_rate,
        e1.racer_age as c1_age,
        e1.racer_weight as c1_weight,
        e1.motor_second_rate as c1_motor_rate,
        t.odds as pred_odds,
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
    """購入条件でフィルタリング"""
    c_venues = ['23', '18', '05', '04', '09', '15', '08', '24', '20', '17']

    if condition_name == 'D_35_60':
        mask = (
            (df['confidence'] == 'D') &
            (df['pred_odds'] >= 35) & (df['pred_odds'] < 60) &
            (df['c1_rank'].isin(['A1', 'A2', 'B1'])) &
            (df['race_number'] != 9) &
            (df['venue_code'] != '10')
        )
    elif condition_name == 'D_40_50_B1':
        mask = (
            (df['confidence'] == 'D') &
            (df['pred_odds'] >= 40) & (df['pred_odds'] < 50) &
            (df['c1_rank'] == 'B1')
        )
    elif condition_name == 'D_5course':
        mask = (
            (df['confidence'] == 'D') &
            (df['pred_1st'] == 5) &
            (df['pred_odds'] >= 10) & (df['pred_odds'] < 200)
        )
    elif condition_name == 'C_20_30_B1':
        mask = (
            (df['confidence'] == 'C') &
            (df['pred_odds'] >= 20) & (df['pred_odds'] < 30) &
            (df['c1_rank'] == 'B1') &
            (df['venue_code'].isin(c_venues))
        )
    else:
        mask = pd.Series([True] * len(df))

    return df[mask].copy()


def analyze_by_thresholds(df, segment_col, thresholds, segment_name):
    """閾値を使ったセグメント分析"""
    results = []
    df_valid = df[df[segment_col].notna()].copy()

    if len(df_valid) == 0:
        return pd.DataFrame()

    for i in range(len(thresholds) + 1):
        if i == 0:
            mask = df_valid[segment_col] < thresholds[0]
            label = f"< {thresholds[0]}"
        elif i == len(thresholds):
            mask = df_valid[segment_col] >= thresholds[-1]
            label = f">= {thresholds[-1]}"
        else:
            mask = (df_valid[segment_col] >= thresholds[i-1]) & (df_valid[segment_col] < thresholds[i])
            label = f"{thresholds[i-1]} - {thresholds[i]}"

        seg_df = df_valid[mask]

        if len(seg_df) < 30:
            continue

        total = len(seg_df)
        hits = seg_df['is_hit'].sum()
        hit_rate = hits / total * 100 if total > 0 else 0
        bet_amount = total * 100
        payout_total = seg_df[seg_df['is_hit'] == 1]['payout'].fillna(0).sum()
        roi = payout_total / bet_amount * 100 if bet_amount > 0 else 0
        profit = payout_total - bet_amount

        # 年度別
        yearly_data = []
        for year in sorted(seg_df['year'].unique()):
            year_df = seg_df[seg_df['year'] == year]
            if len(year_df) >= 5:
                y_bet = len(year_df) * 100
                y_payout = year_df[year_df['is_hit'] == 1]['payout'].fillna(0).sum()
                y_roi = y_payout / y_bet * 100 if y_bet > 0 else 0
                yearly_data.append({'year': year, 'roi': y_roi, 'count': len(year_df)})

        results.append({
            'segment_name': segment_name,
            'segment_value': label,
            'count': total,
            'hits': hits,
            'hit_rate': hit_rate,
            'roi': roi,
            'profit': profit,
            'yearly_data': yearly_data
        })

    return pd.DataFrame(results)


def chi_square_test_threshold(df, segment_col, thresholds):
    """閾値ベースのカイ二乗検定"""
    df_valid = df[df[segment_col].notna()].copy()

    if len(df_valid) == 0:
        return None, None

    # セグメントを作成
    df_valid['segment'] = pd.cut(df_valid[segment_col], bins=[-np.inf] + thresholds + [np.inf])

    contingency = pd.crosstab(df_valid['segment'], df_valid['is_hit'])

    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        return None, None

    try:
        chi2, p_value, dof, expected = stats.chi2_contingency(contingency)
        return chi2, p_value
    except Exception:
        return None, None


def main():
    print("=" * 80)
    print("事前情報を活用した除外条件の調査")
    print("=" * 80)
    print()

    print("データ取得中...")
    df = fetch_analysis_data()
    print(f"総レース数: {len(df):,}件")
    print(f"期間: {df['race_date'].min()} ~ {df['race_date'].max()}")
    print()

    conditions = [
        ('D_35_60', 'D x 35-60倍 (A1/A2/B1, 9R除外, 三国除外)'),
        ('D_40_50_B1', 'D x 40-50倍 x B1'),
        ('D_5course', 'D x 5コース予測'),
        ('C_20_30_B1', 'C x 20-30倍 x B1 + 会場'),
    ]

    # 分析対象と閾値
    analysis_items = [
        ('c1_win_rate', '1コース勝率', [3.0, 4.0, 5.0, 6.0]),
        ('c1_second_rate', '1コース2連率', [20, 30, 40, 50]),
        ('c1_local_win_rate', '1コース当地勝率', [3.0, 4.0, 5.0, 6.0]),
        ('c1_age', '1コース選手年齢', [25, 35, 45, 55]),
        ('c1_weight', '1コース選手体重', [50, 52, 54, 56]),
        ('race_number', 'レース番号', [3, 6, 9]),
        ('weekday', '曜日 (0=月, 6=日)', [1, 3, 5]),
        ('month', '月', [3, 6, 9]),
    ]

    all_recommendations = []

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

        print(f"全体: {total}件, 的中{hits}件 ({hit_rate:.2f}%), ROI {roi:.1f}%")
        print()

        for col, col_name, thresholds in analysis_items:
            print(f"--- {col_name} ---")

            # 閾値ベースの分析
            seg_results = analyze_by_thresholds(df_cond, col, thresholds, col_name)

            if len(seg_results) == 0:
                print("  分析不可(データ不足)")
                continue

            # カイ二乗検定
            chi2, p_value = chi_square_test_threshold(df_cond, col, thresholds)

            if p_value is not None:
                sig = "***" if p_value < 0.001 else "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
                print(f"  カイ二乗検定: p={p_value:.4f} {sig}")

            # セグメント別成績表示
            for _, row in seg_results.iterrows():
                roi_indicator = "[LOW]" if row['roi'] < 80 else "[HIGH]" if row['roi'] > 150 else ""
                print(f"  {row['segment_value']}: {row['count']}件, ROI {row['roi']:.1f}% {roi_indicator}")

                # 低ROIセグメントの年度別詳細
                if row['roi'] < 80 and p_value is not None and p_value < 0.05:
                    yearly = row['yearly_data']
                    if len(yearly) > 0:
                        low_years = sum(1 for y in yearly if y['roi'] < 100)
                        total_years = len(yearly)
                        stable = low_years >= total_years * 0.5

                        rec = {
                            'condition': cond_name,
                            'segment': col_name,
                            'value': row['segment_value'],
                            'count': row['count'],
                            'roi': row['roi'],
                            'p_value': p_value,
                            'yearly_stable': stable,
                            'low_years': low_years,
                            'total_years': total_years,
                            'yearly_detail': yearly
                        }
                        all_recommendations.append(rec)

            print()

    # サマリー
    print()
    print("=" * 80)
    print("除外条件候補のサマリー")
    print("=" * 80)

    if len(all_recommendations) > 0:
        rec_df = pd.DataFrame(all_recommendations)
        rec_df = rec_df.sort_values(['p_value', 'roi'])

        print("\n統計的に有意な低ROIセグメント (p < 0.05):")
        print("-" * 80)

        for _, row in rec_df.iterrows():
            stable_mark = "[安定]" if row['yearly_stable'] else "[不安定]"
            sig = "***" if row['p_value'] < 0.001 else "**" if row['p_value'] < 0.01 else "*"
            print(f"\n{row['condition']}")
            print(f"  除外候補: {row['segment']} = {row['value']}")
            print(f"  成績: {row['count']}件, ROI {row['roi']:.1f}%")
            print(f"  統計: p={row['p_value']:.4f} {sig}")
            print(f"  年度安定性: {stable_mark} ({row['low_years']}/{row['total_years']}年で赤字)")

            # 年度別詳細
            print("  年度別ROI:")
            for y in row['yearly_detail']:
                y_mark = "x" if y['roi'] < 100 else "o"
                print(f"    {y['year']}: {y['roi']:.1f}% ({y['count']}件) {y_mark}")

        # 最終推奨
        print()
        print("=" * 80)
        print("最終的な採用推奨")
        print("=" * 80)

        recommended = rec_df[(rec_df['p_value'] < 0.05) & (rec_df['yearly_stable'] == True)]

        if len(recommended) > 0:
            print("\n【採用推奨】 (p < 0.05 かつ 年度安定性あり):")
            for _, row in recommended.iterrows():
                print(f"  - {row['condition']}")
                print(f"    除外条件: {row['segment']} = {row['value']}")
                print(f"    期待効果: ROI +{100 - row['roi']:.1f}pt相当 (除外による)")
                print()
        else:
            print("\n統計的に有意かつ年度安定性のある除外条件は見つかりませんでした。")
    else:
        print("\n統計的に有意な除外条件候補は見つかりませんでした。")

    return all_recommendations


if __name__ == "__main__":
    results = main()
