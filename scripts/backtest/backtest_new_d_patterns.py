# -*- coding: utf-8 -*-
"""
新規Dパターンのバックテスト検証
================================

2026-01-05追加パターンの効果を検証:
1. D × 5コース予測（6年連続黒字）
2. 三国(06) × D × 50-100倍 × B1（5/6年黒字）

使用例:
    python scripts/backtest/backtest_new_d_patterns.py
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime


def load_data(db_path: str) -> pd.DataFrame:
    """ml_analysis_featuresからデータを読み込む"""
    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            race_id,
            venue_code,
            year,
            race_date,
            race_number,
            confidence,
            predicted_pit,
            course1_rank,
            predicted_odds,
            odds_band,
            is_trifecta_hit,
            trifecta_payout
        FROM ml_analysis_features
        WHERE prediction_type = 'before'
        AND confidence = 'D'
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"Dランクデータ読み込み: {len(df):,}件")
    return df


def analyze_pattern_1(df: pd.DataFrame) -> dict:
    """パターン1: D × 5コース予測"""
    print("\n" + "=" * 60)
    print("パターン1: D × 5コース予測")
    print("=" * 60)

    # 5コース予測のみ
    mask = df['predicted_pit'].astype(str).str.replace('.0', '', regex=False) == '5'
    subset = df[mask].copy()

    print(f"\n対象レース数: {len(subset):,}件")

    if len(subset) == 0:
        return {}

    # 全体集計
    hits = subset['is_trifecta_hit'].sum()
    total = len(subset)
    payout = subset['trifecta_payout'].sum()
    investment = total * 100

    hit_rate = hits / total * 100
    roi = payout / investment * 100
    profit = payout - investment

    print(f"的中: {hits}件 / {total}件 ({hit_rate:.2f}%)")
    print(f"投資: {investment:,}円")
    print(f"払戻: {payout:,.0f}円")
    print(f"収支: {profit:+,.0f}円")
    print(f"ROI: {roi:.1f}%")

    # 年度別
    print("\n--- 年度別内訳 ---")
    yearly_results = []
    for year in sorted(subset['year'].unique()):
        year_data = subset[subset['year'] == year]
        y_total = len(year_data)
        y_hits = year_data['is_trifecta_hit'].sum()
        y_payout = year_data['trifecta_payout'].sum()
        y_invest = y_total * 100
        y_roi = y_payout / y_invest * 100 if y_invest > 0 else 0
        y_profit = y_payout - y_invest

        status = "+" if y_profit > 0 else "-"
        print(f"  {year}: {y_total}件, {y_hits}的中, ROI {y_roi:.1f}%, {y_profit:+,.0f}円 [{status}]")
        yearly_results.append({
            'year': year, 'total': y_total, 'hits': y_hits,
            'roi': y_roi, 'profit': y_profit
        })

    positive_years = sum(1 for r in yearly_results if r['profit'] > 0)
    print(f"\n黒字年数: {positive_years}/{len(yearly_results)}年")

    # 級別内訳
    print("\n--- 1コース級別内訳 ---")
    for rank in ['A1', 'A2', 'B1', 'B2']:
        rank_data = subset[subset['course1_rank'] == rank]
        if len(rank_data) > 0:
            r_total = len(rank_data)
            r_payout = rank_data['trifecta_payout'].sum()
            r_invest = r_total * 100
            r_roi = r_payout / r_invest * 100 if r_invest > 0 else 0
            r_profit = r_payout - r_invest
            print(f"  {rank}: {r_total}件, ROI {r_roi:.1f}%, {r_profit:+,.0f}円")

    return {
        'name': 'D×5コース予測',
        'total': total,
        'hits': hits,
        'roi': roi,
        'profit': profit,
        'positive_years': positive_years,
    }


def analyze_pattern_2(df: pd.DataFrame) -> dict:
    """パターン2: 三国(06) × D × 50-100倍 × B1"""
    print("\n" + "=" * 60)
    print("パターン2: 三国(06) × D × 50-100倍 × B1")
    print("=" * 60)

    # 条件適用
    venue_code_str = df['venue_code'].astype(str).str.zfill(2)
    mask = (
        (venue_code_str == '06') &  # 三国
        (df['course1_rank'] == 'B1') &  # B1級
        (df['predicted_odds'] >= 50) &
        (df['predicted_odds'] < 100)
    )
    subset = df[mask].copy()

    print(f"\n対象レース数: {len(subset):,}件")

    if len(subset) == 0:
        return {}

    # 全体集計
    hits = subset['is_trifecta_hit'].sum()
    total = len(subset)
    payout = subset['trifecta_payout'].sum()
    investment = total * 100

    hit_rate = hits / total * 100
    roi = payout / investment * 100
    profit = payout - investment

    print(f"的中: {hits}件 / {total}件 ({hit_rate:.2f}%)")
    print(f"投資: {investment:,}円")
    print(f"払戻: {payout:,.0f}円")
    print(f"収支: {profit:+,.0f}円")
    print(f"ROI: {roi:.1f}%")

    # 年度別
    print("\n--- 年度別内訳 ---")
    yearly_results = []
    for year in sorted(subset['year'].unique()):
        year_data = subset[subset['year'] == year]
        y_total = len(year_data)
        y_hits = year_data['is_trifecta_hit'].sum()
        y_payout = year_data['trifecta_payout'].sum()
        y_invest = y_total * 100
        y_roi = y_payout / y_invest * 100 if y_invest > 0 else 0
        y_profit = y_payout - y_invest

        status = "+" if y_profit > 0 else "-"
        print(f"  {year}: {y_total}件, {y_hits}的中, ROI {y_roi:.1f}%, {y_profit:+,.0f}円 [{status}]")
        yearly_results.append({
            'year': year, 'total': y_total, 'hits': y_hits,
            'roi': y_roi, 'profit': y_profit
        })

    positive_years = sum(1 for r in yearly_results if r['profit'] > 0)
    print(f"\n黒字年数: {positive_years}/{len(yearly_results)}年")

    return {
        'name': '三国×D×50-100×B1',
        'total': total,
        'hits': hits,
        'roi': roi,
        'profit': profit,
        'positive_years': positive_years,
    }


def analyze_existing_d_conditions(df: pd.DataFrame) -> dict:
    """既存D条件との重複確認と増分効果"""
    print("\n" + "=" * 60)
    print("既存D条件との重複・増分効果分析")
    print("=" * 60)

    # 既存条件1: D × B1 × 40-50倍
    existing1_mask = (
        (df['course1_rank'] == 'B1') &
        (df['predicted_odds'] >= 40) &
        (df['predicted_odds'] < 50)
    )

    # 既存条件2: D × A1/A2/B1 × 35-60倍（9R除外、三国除外）
    venue_code_str = df['venue_code'].astype(str).str.zfill(2)
    existing2_mask = (
        (df['course1_rank'].isin(['A1', 'A2', 'B1'])) &
        (df['predicted_odds'] >= 35) &
        (df['predicted_odds'] < 60) &
        (df['race_number'] != 9) &
        (venue_code_str != '10')  # 三国(10)除外
    )

    # 新パターン1: D × 5コース予測
    new1_mask = df['predicted_pit'].astype(str).str.replace('.0', '', regex=False) == '5'

    # 新パターン2: 三国 × D × 50-100 × B1
    new2_mask = (
        (venue_code_str == '06') &
        (df['course1_rank'] == 'B1') &
        (df['predicted_odds'] >= 50) &
        (df['predicted_odds'] < 100)
    )

    # 既存条件に含まれるか
    existing_mask = existing1_mask | existing2_mask

    # 新パターン1で既存に含まれないもの
    new1_unique = new1_mask & ~existing_mask
    # 新パターン2で既存に含まれないもの
    new2_unique = new2_mask & ~existing_mask

    print("\n--- 新パターン1（5コース予測）---")
    print(f"  全体: {new1_mask.sum()}件")
    print(f"  既存条件と重複: {(new1_mask & existing_mask).sum()}件")
    print(f"  新規追加分: {new1_unique.sum()}件")

    if new1_unique.sum() > 0:
        unique_subset = df[new1_unique]
        u_payout = unique_subset['trifecta_payout'].sum()
        u_invest = len(unique_subset) * 100
        u_roi = u_payout / u_invest * 100
        u_profit = u_payout - u_invest
        print(f"  → 新規分ROI: {u_roi:.1f}%, 収支: {u_profit:+,.0f}円")

    print("\n--- 新パターン2（三国×50-100×B1）---")
    print(f"  全体: {new2_mask.sum()}件")
    print(f"  既存条件と重複: {(new2_mask & existing_mask).sum()}件")
    print(f"  新規追加分: {new2_unique.sum()}件")

    if new2_unique.sum() > 0:
        unique_subset = df[new2_unique]
        u_payout = unique_subset['trifecta_payout'].sum()
        u_invest = len(unique_subset) * 100
        u_roi = u_payout / u_invest * 100
        u_profit = u_payout - u_invest
        print(f"  → 新規分ROI: {u_roi:.1f}%, 収支: {u_profit:+,.0f}円")

    # 全新規追加分
    all_new = (new1_unique | new2_unique)
    print(f"\n--- 全新規追加分 ---")
    print(f"  合計: {all_new.sum()}件")

    if all_new.sum() > 0:
        all_new_subset = df[all_new]
        all_payout = all_new_subset['trifecta_payout'].sum()
        all_invest = len(all_new_subset) * 100
        all_roi = all_payout / all_invest * 100
        all_profit = all_payout - all_invest
        print(f"  → ROI: {all_roi:.1f}%, 収支: {all_profit:+,.0f}円")

    return {
        'new1_unique': new1_unique.sum(),
        'new2_unique': new2_unique.sum(),
        'total_new': all_new.sum(),
    }


def main():
    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

    print("=" * 60)
    print("新規Dパターンバックテスト検証")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # データ読み込み
    df = load_data(str(db_path))

    # パターン分析
    result1 = analyze_pattern_1(df)
    result2 = analyze_pattern_2(df)

    # 既存条件との重複分析
    overlap = analyze_existing_d_conditions(df)

    # サマリー
    print("\n" + "=" * 60)
    print("検証結果サマリー")
    print("=" * 60)

    if result1:
        print(f"\n1. {result1['name']}")
        print(f"   → {result1['total']}件, ROI {result1['roi']:.1f}%, 収支 {result1['profit']:+,.0f}円")
        print(f"   → 黒字年数: {result1['positive_years']}/6年 → {'採用推奨' if result1['positive_years'] >= 4 else '要検討'}")

    if result2:
        print(f"\n2. {result2['name']}")
        print(f"   → {result2['total']}件, ROI {result2['roi']:.1f}%, 収支 {result2['profit']:+,.0f}円")
        print(f"   → 黒字年数: {result2['positive_years']}/6年 → {'採用推奨' if result2['positive_years'] >= 4 else '要検討'}")

    print(f"\n新規追加レース数: {overlap['total_new']}件（既存条件と重複しない分）")


if __name__ == "__main__":
    main()
