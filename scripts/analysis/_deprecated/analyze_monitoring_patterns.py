# -*- coding: utf-8 -*-
"""
継続監視パターンの深掘り分析
============================

Opus分析で「継続監視」とされた6パターンを深掘りし、
採用/不採用を判断する。

継続監視パターン:
1. C × 信頼度C × 50-70倍 × B1 (ROI 261.7%, 3年黒字)
2. D × 2コース予測 (ROI 121.3%, 4年黒字)
3. D × 高配当100倍+ (ROI 223.7%, 5年黒字)
4. 鳴門(14) × D × 30-50倍 (ROI 271.9%, 4年黒字)
5. 若松(20) × D (ROI 155.1%, 5年黒字)
6. 芦屋(21) × D × 30-50倍 × A1 (ROI 411.7%, 3年黒字)

使用例:
    python scripts/analysis/analyze_monitoring_patterns.py
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime


def load_data(db_path: str) -> pd.DataFrame:
    """データを読み込む"""
    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            maf.*,
            CASE
                WHEN maf.wind_direction IN ('北', '北北東', '北東', '北北西', '北西') THEN 'north'
                WHEN maf.wind_direction IN ('南', '南南東', '南東', '南南西', '南西') THEN 'south'
                WHEN maf.wind_direction IN ('東', '東北東', '東南東') THEN 'east'
                WHEN maf.wind_direction IN ('西', '西北西', '西南西') THEN 'west'
                ELSE 'unknown'
            END as wind_direction_group
        FROM ml_analysis_features maf
        WHERE maf.prediction_type = 'before'
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    df['predicted_pit_str'] = df['predicted_pit'].astype(str).str.replace('.0', '', regex=False)
    df['venue_code_str'] = df['venue_code'].astype(str).str.zfill(2)

    print(f"データ読み込み: {len(df):,}件")
    return df


def analyze_pattern(df: pd.DataFrame, name: str, mask, min_samples: int = 50):
    """パターンを詳細分析"""
    print(f"\n{'=' * 60}")
    print(f"パターン: {name}")
    print("=" * 60)

    subset = df[mask].copy()
    total = len(subset)

    if total < min_samples:
        print(f"サンプル数不足: {total}件 < {min_samples}件")
        return None

    hits = subset['is_trifecta_hit'].sum()
    payout = subset['trifecta_payout'].sum()
    investment = total * 100
    roi = payout / investment * 100
    profit = payout - investment

    print(f"\n【基本統計】")
    print(f"  レース数: {total:,}件")
    print(f"  的中: {hits}件 ({hits/total*100:.2f}%)")
    print(f"  ROI: {roi:.1f}%")
    print(f"  収支: {profit:+,.0f}円")

    # 年度別
    print(f"\n【年度別成績】")
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
        print(f"  {year}: {y_total:>4}件, {y_hits:>2}的中, ROI {y_roi:>6.1f}%, {y_profit:>+8,.0f}円 [{status}]")
        yearly_results.append({
            'year': year, 'total': y_total, 'hits': y_hits,
            'roi': y_roi, 'profit': y_profit
        })

    positive_years = sum(1 for r in yearly_results if r['profit'] > 0)
    total_years = len(yearly_results)

    # 直近2年の傾向
    recent_years = sorted(subset['year'].unique())[-2:]
    recent_profit = sum(r['profit'] for r in yearly_results if r['year'] in recent_years)

    print(f"\n【安定性評価】")
    print(f"  黒字年数: {positive_years}/{total_years}年")
    print(f"  直近2年収支: {recent_profit:+,.0f}円")

    # 判定
    if positive_years >= 4 and recent_profit > 0:
        verdict = "採用推奨"
    elif positive_years >= 4 or (positive_years >= 3 and recent_profit > 0):
        verdict = "条件付き採用可"
    else:
        verdict = "不採用推奨"

    print(f"\n【判定】 → {verdict}")

    return {
        'name': name,
        'total': total,
        'roi': roi,
        'profit': profit,
        'positive_years': positive_years,
        'total_years': total_years,
        'recent_profit': recent_profit,
        'verdict': verdict
    }


def main():
    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

    print("=" * 60)
    print("継続監視パターン深掘り分析")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    df = load_data(str(db_path))
    results = []

    # パターン1: C × 50-70倍 × B1
    mask1 = (
        (df['confidence'] == 'C') &
        (df['course1_rank'] == 'B1') &
        (df['predicted_odds'] >= 50) &
        (df['predicted_odds'] < 70)
    )
    r1 = analyze_pattern(df, "C × 50-70倍 × B1", mask1)
    if r1:
        results.append(r1)

    # パターン2: D × 2コース予測
    mask2 = (
        (df['confidence'] == 'D') &
        (df['predicted_pit_str'] == '2')
    )
    r2 = analyze_pattern(df, "D × 2コース予測", mask2)
    if r2:
        results.append(r2)

    # パターン3: D × 高配当100倍+
    mask3 = (
        (df['confidence'] == 'D') &
        (df['predicted_odds'] >= 100)
    )
    r3 = analyze_pattern(df, "D × 100倍+", mask3)
    if r3:
        results.append(r3)

    # パターン4: 鳴門(14) × D × 30-50倍
    mask4 = (
        (df['confidence'] == 'D') &
        (df['venue_code_str'] == '14') &  # 鳴門
        (df['predicted_odds'] >= 30) &
        (df['predicted_odds'] < 50)
    )
    r4 = analyze_pattern(df, "鳴門 × D × 30-50倍", mask4)
    if r4:
        results.append(r4)

    # パターン5: 若松(20) × D
    mask5 = (
        (df['confidence'] == 'D') &
        (df['venue_code_str'] == '20')  # 若松
    )
    r5 = analyze_pattern(df, "若松 × D", mask5)
    if r5:
        results.append(r5)

    # パターン6: 芦屋(21) × D × 30-50倍 × A1
    mask6 = (
        (df['confidence'] == 'D') &
        (df['venue_code_str'] == '21') &  # 芦屋
        (df['course1_rank'] == 'A1') &
        (df['predicted_odds'] >= 30) &
        (df['predicted_odds'] < 50)
    )
    r6 = analyze_pattern(df, "芦屋 × D × 30-50倍 × A1", mask6)
    if r6:
        results.append(r6)

    # サマリー
    print("\n" + "=" * 60)
    print("分析結果サマリー")
    print("=" * 60)

    adopted = []
    conditional = []
    rejected = []

    for r in results:
        if r['verdict'] == "採用推奨":
            adopted.append(r)
        elif r['verdict'] == "条件付き採用可":
            conditional.append(r)
        else:
            rejected.append(r)

    print(f"\n【採用推奨】 {len(adopted)}件")
    for r in adopted:
        print(f"  - {r['name']}: ROI {r['roi']:.1f}%, {r['positive_years']}/{r['total_years']}年黒字, 直近2年 {r['recent_profit']:+,.0f}円")

    print(f"\n【条件付き採用可】 {len(conditional)}件")
    for r in conditional:
        print(f"  - {r['name']}: ROI {r['roi']:.1f}%, {r['positive_years']}/{r['total_years']}年黒字, 直近2年 {r['recent_profit']:+,.0f}円")

    print(f"\n【不採用推奨】 {len(rejected)}件")
    for r in rejected:
        print(f"  - {r['name']}: ROI {r['roi']:.1f}%, {r['positive_years']}/{r['total_years']}年黒字, 直近2年 {r['recent_profit']:+,.0f}円")


if __name__ == "__main__":
    main()
