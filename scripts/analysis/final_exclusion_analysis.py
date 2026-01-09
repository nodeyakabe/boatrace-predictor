# -*- coding: utf-8 -*-
"""
最終除外条件分析スクリプト

詳細な年度別検証と統計検定を行い、採用/不採用を決定する
"""

import sqlite3
import sys
import io
from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


def get_connection():
    return sqlite3.connect(DATABASE_PATH)


def fetch_data():
    query = """
    WITH full_predictions AS (
        SELECT
            rp.race_id,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence
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
        fp.pred_1st,
        fp.pred_2nd,
        fp.pred_3rd,
        fp.confidence,
        rr.actual_1st,
        rr.actual_2nd,
        rr.actual_3rd,
        CASE WHEN fp.pred_1st = rr.actual_1st
             AND fp.pred_2nd = rr.actual_2nd
             AND fp.pred_3rd = rr.actual_3rd
             THEN 1 ELSE 0 END as is_hit,
        e1.racer_rank as c1_rank,
        e1.second_rate as c1_second_rate,
        e1.win_rate as c1_win_rate,
        e1.local_win_rate as c1_local_win_rate,
        e1.racer_age as c1_age,
        e1.racer_weight as c1_weight,
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
    """
    conn = get_connection()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def calc_stats(df):
    if len(df) == 0:
        return {'count': 0, 'hits': 0, 'hit_rate': 0, 'roi': 0, 'profit': 0}

    total = len(df)
    hits = df['is_hit'].sum()
    bet = total * 100
    payout = df[df['is_hit'] == 1]['payout'].fillna(0).sum()
    roi = payout / bet * 100 if bet > 0 else 0
    profit = payout - bet

    return {
        'count': total,
        'hits': hits,
        'hit_rate': hits / total * 100,
        'roi': roi,
        'profit': profit
    }


def yearly_analysis(df, label=""):
    """年度別分析と安定性判定"""
    print(f"\n  【年度別分析】{label}")
    yearly_data = []
    for year in sorted(df['year'].unique()):
        year_df = df[df['year'] == year]
        if len(year_df) >= 3:
            stats = calc_stats(year_df)
            yearly_data.append({
                'year': year,
                'count': stats['count'],
                'roi': stats['roi'],
                'profit': stats['profit']
            })
            mark = "o" if stats['roi'] >= 100 else "x"
            print(f"    {year}: {stats['count']:3d}件, ROI {stats['roi']:6.1f}%, {stats['profit']:+8,.0f}円 {mark}")

    if len(yearly_data) >= 4:
        black_years = sum(1 for y in yearly_data if y['roi'] >= 100)
        total_years = len(yearly_data)
        stable = black_years >= total_years * 0.5
        print(f"  → 安定性: {black_years}/{total_years}年黒字 {'[安定]' if stable else '[不安定]'}")
        return stable, black_years, total_years
    return None, 0, 0


def chi_square_test(df, col, threshold):
    """カイ二乗検定"""
    df_valid = df[df[col].notna()].copy()
    if len(df_valid) < 50:
        return None, None

    df_valid['group'] = df_valid[col].apply(lambda x: 'above' if x >= threshold else 'below')
    contingency = pd.crosstab(df_valid['group'], df_valid['is_hit'])

    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        return None, None

    try:
        chi2, p, dof, expected = stats.chi2_contingency(contingency)
        return chi2, p
    except:
        return None, None


def main():
    print("=" * 80)
    print("最終除外条件分析レポート")
    print("=" * 80)
    print()

    df = fetch_data()
    print(f"データ期間: {df['race_date'].min()} ~ {df['race_date'].max()}")
    print(f"総レース数: {len(df):,}件")
    print()

    results = []

    # ========================================
    # 1. D×35-60倍 (A1/A2/B1, 9R除外, 三国除外)
    # ========================================
    print("=" * 80)
    print("1. D×35-60倍 の除外条件検証")
    print("=" * 80)

    df_d35 = df[
        (df['confidence'] == 'D') &
        (df['pred_odds'] >= 35) & (df['pred_odds'] < 60) &
        (df['c1_rank'].isin(['A1', 'A2', 'B1'])) &
        (df['race_number'] != 9) &
        (df['venue_code'] != '10')
    ].copy()

    current = calc_stats(df_d35)
    print(f"\n【現行条件】{current['count']}件, ROI {current['roi']:.1f}%, 収支 {current['profit']:+,.0f}円")

    # 除外案: 1コース2連率で絞る
    print("\n--- 1コース2連率による絞り込み ---")

    # 2連率 20-30%のみ
    df_2030 = df_d35[(df_d35['c1_second_rate'] >= 20) & (df_d35['c1_second_rate'] < 30)]
    stats_2030 = calc_stats(df_2030)
    print(f"\n2連率 20-30%のみ: {stats_2030['count']}件, ROI {stats_2030['roi']:.1f}%")
    stable, bk, ty = yearly_analysis(df_2030)

    # 2連率 40-50%のみ
    df_4050 = df_d35[(df_d35['c1_second_rate'] >= 40) & (df_d35['c1_second_rate'] < 50)]
    stats_4050 = calc_stats(df_4050)
    print(f"\n2連率 40-50%のみ: {stats_4050['count']}件, ROI {stats_4050['roi']:.1f}%")
    stable2, bk2, ty2 = yearly_analysis(df_4050)

    # 統合案: 20-30% OR 40-50%
    df_combined = df_d35[
        ((df_d35['c1_second_rate'] >= 20) & (df_d35['c1_second_rate'] < 30)) |
        ((df_d35['c1_second_rate'] >= 40) & (df_d35['c1_second_rate'] < 50))
    ]
    stats_combined = calc_stats(df_combined)
    print(f"\n【推奨】2連率 20-30% OR 40-50%: {stats_combined['count']}件, ROI {stats_combined['roi']:.1f}%")
    stable3, bk3, ty3 = yearly_analysis(df_combined)

    # 効果計算
    roi_gain = stats_combined['roi'] - current['roi']
    profit_gain = stats_combined['profit'] - current['profit']

    chi2, p = chi_square_test(df_d35, 'c1_second_rate', 25)
    sig = "***" if p and p < 0.001 else "**" if p and p < 0.01 else "*" if p and p < 0.05 else ""

    p_str = f"{p:.4f}" if p else "N/A"
    print(f"\n【統計検定】カイ二乗検定: p={p_str} {sig}")
    print(f"【効果】ROI {roi_gain:+.1f}pt, 収支 {profit_gain:+,.0f}円")

    if p and p < 0.05 and stable3:
        print("【判定】★ 採用推奨（統計有意 & 年度安定）")
        results.append({
            'condition': 'D×35-60倍',
            'filter': '1コース2連率 20-30% OR 40-50%',
            'status': '採用推奨',
            'roi_gain': roi_gain,
            'profit_gain': profit_gain,
            'p_value': p,
            'stable': True
        })
    elif p and p < 0.05:
        print("【判定】△ 要観察（統計有意だが年度不安定）")
        results.append({
            'condition': 'D×35-60倍',
            'filter': '1コース2連率 20-30% OR 40-50%',
            'status': '要観察',
            'roi_gain': roi_gain,
            'profit_gain': profit_gain,
            'p_value': p,
            'stable': False
        })

    # ========================================
    # 2. D×40-50×B1
    # ========================================
    print()
    print("=" * 80)
    print("2. D×40-50×B1 の除外条件検証")
    print("=" * 80)

    df_d40 = df[
        (df['confidence'] == 'D') &
        (df['pred_odds'] >= 40) & (df['pred_odds'] < 50) &
        (df['c1_rank'] == 'B1')
    ].copy()

    current = calc_stats(df_d40)
    print(f"\n【現行条件】{current['count']}件, ROI {current['roi']:.1f}%, 収支 {current['profit']:+,.0f}円")

    # 2連率 20-30%のみ
    df_2030 = df_d40[(df_d40['c1_second_rate'] >= 20) & (df_d40['c1_second_rate'] < 30)]
    stats_2030 = calc_stats(df_2030)
    print(f"\n【推奨】2連率 20-30%のみ: {stats_2030['count']}件, ROI {stats_2030['roi']:.1f}%")
    stable, bk, ty = yearly_analysis(df_2030)

    roi_gain = stats_2030['roi'] - current['roi']
    profit_gain = stats_2030['profit'] - current['profit']

    chi2, p = chi_square_test(df_d40, 'c1_second_rate', 25)
    sig = "***" if p and p < 0.001 else "**" if p and p < 0.01 else "*" if p and p < 0.05 else ""

    p_str = f"{p:.4f}" if p else "N/A"
    print(f"\n【統計検定】カイ二乗検定: p={p_str} {sig}")
    print(f"【効果】ROI {roi_gain:+.1f}pt, 収支 {profit_gain:+,.0f}円")

    # サンプルが少ないため追加条件
    if stats_2030['count'] >= 100 and stable:
        print("【判定】★ 採用推奨（年度安定 & サンプル十分）")
        results.append({
            'condition': 'D×40-50×B1',
            'filter': '1コース2連率 20-30%',
            'status': '採用推奨',
            'roi_gain': roi_gain,
            'profit_gain': profit_gain,
            'p_value': p,
            'stable': True
        })
    elif stable:
        print("【判定】△ 要観察（年度安定だがサンプル少）")
        results.append({
            'condition': 'D×40-50×B1',
            'filter': '1コース2連率 20-30%',
            'status': '要観察',
            'roi_gain': roi_gain,
            'profit_gain': profit_gain,
            'p_value': p,
            'stable': True
        })

    # ========================================
    # 3. D×5コース予測
    # ========================================
    print()
    print("=" * 80)
    print("3. D×5コース予測 の除外条件検証")
    print("=" * 80)

    df_d5 = df[
        (df['confidence'] == 'D') &
        (df['pred_1st'] == 5) &
        (df['pred_odds'] >= 10) & (df['pred_odds'] < 200)
    ].copy()

    current = calc_stats(df_d5)
    print(f"\n【現行条件】{current['count']}件, ROI {current['roi']:.1f}%, 収支 {current['profit']:+,.0f}円")

    # 9R以降
    df_9r = df_d5[df_d5['race_number'] >= 9]
    stats_9r = calc_stats(df_9r)
    print(f"\n9R以降のみ: {stats_9r['count']}件, ROI {stats_9r['roi']:.1f}%")
    stable, bk, ty = yearly_analysis(df_9r)

    roi_gain = stats_9r['roi'] - current['roi']
    profit_gain = stats_9r['profit'] - current['profit']

    chi2, p = chi_square_test(df_d5, 'race_number', 9)
    sig = "***" if p and p < 0.001 else "**" if p and p < 0.01 else "*" if p and p < 0.05 else ""

    p_str = f"{p:.4f}" if p else "N/A"
    print(f"\n【統計検定】カイ二乗検定: p={p_str} {sig}")
    print(f"【効果】ROI {roi_gain:+.1f}pt, 収支 {profit_gain:+,.0f}円")

    # サンプル数が少なすぎる
    if stats_9r['count'] < 50:
        print("【判定】✕ 不採用（サンプル不足: <50件）")
        results.append({
            'condition': 'D×5コース予測',
            'filter': '9R以降',
            'status': '不採用',
            'roi_gain': roi_gain,
            'profit_gain': profit_gain,
            'p_value': p,
            'stable': stable
        })

    # ========================================
    # 4. C×20-30×B1+会場
    # ========================================
    print()
    print("=" * 80)
    print("4. C×20-30×B1+会場 の除外条件検証")
    print("=" * 80)

    c_venues = ['23', '18', '05', '04', '09', '15', '08', '24', '20', '17']
    df_c = df[
        (df['confidence'] == 'C') &
        (df['pred_odds'] >= 20) & (df['pred_odds'] < 30) &
        (df['c1_rank'] == 'B1') &
        (df['venue_code'].isin(c_venues))
    ].copy()

    current = calc_stats(df_c)
    print(f"\n【現行条件】{current['count']}件, ROI {current['roi']:.1f}%, 収支 {current['profit']:+,.0f}円")

    # 各変数での分析
    print("\n--- 各変数の分析 ---")

    # 1コース勝率
    df_high_wr = df_c[df_c['c1_win_rate'] >= 5.0]
    stats_high = calc_stats(df_high_wr)
    print(f"\n1コース勝率 >= 5.0: {stats_high['count']}件, ROI {stats_high['roi']:.1f}%")
    yearly_analysis(df_high_wr)

    # 1コース2連率
    df_high_sr = df_c[(df_c['c1_second_rate'] >= 20) & (df_c['c1_second_rate'] < 35)]
    stats_sr = calc_stats(df_high_sr)
    print(f"\n1コース2連率 20-35%: {stats_sr['count']}件, ROI {stats_sr['roi']:.1f}%")
    yearly_analysis(df_high_sr)

    # 選手年齢
    df_age = df_c[(df_c['c1_age'] >= 30) & (df_c['c1_age'] < 50)]
    stats_age = calc_stats(df_age)
    print(f"\n選手年齢 30-50歳: {stats_age['count']}件, ROI {stats_age['roi']:.1f}%")
    yearly_analysis(df_age)

    # ========================================
    # 最終まとめ
    # ========================================
    print()
    print("=" * 80)
    print("最終まとめ")
    print("=" * 80)

    print("\n【採用推奨の除外条件】")
    print("-" * 60)

    adopted = [r for r in results if r['status'] == '採用推奨']
    if adopted:
        for r in adopted:
            print(f"\n条件: {r['condition']}")
            print(f"  フィルター: {r['filter']}")
            print(f"  効果: ROI {r['roi_gain']:+.1f}pt, 収支 {r['profit_gain']:+,.0f}円")
            print(f"  p値: {r['p_value']:.4f if r['p_value'] else 'N/A'}")
    else:
        print("  なし")

    print("\n【要観察（条件付き採用可能）】")
    print("-" * 60)
    observed = [r for r in results if r['status'] == '要観察']
    if observed:
        for r in observed:
            print(f"\n条件: {r['condition']}")
            print(f"  フィルター: {r['filter']}")
            print(f"  効果: ROI {r['roi_gain']:+.1f}pt, 収支 {r['profit_gain']:+,.0f}円")
            print(f"  注意: 年度安定性または統計的有意性に課題あり")
    else:
        print("  なし")

    print("\n【不採用】")
    print("-" * 60)
    rejected = [r for r in results if r['status'] == '不採用']
    if rejected:
        for r in rejected:
            print(f"\n条件: {r['condition']}")
            print(f"  フィルター: {r['filter']}")
            print(f"  理由: サンプル不足または年度不安定")
    else:
        print("  なし")


if __name__ == "__main__":
    main()
