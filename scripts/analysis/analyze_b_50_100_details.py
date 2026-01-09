"""
B×50-100条件の詳細分析スクリプト

分析対象: confidence='B', c1_rank IN ('A1','B1'), odds 50-100
期間: 2022-2025年

分析項目:
1. 1コース選手の級別 (A1 vs B1)
2. オッズ帯の細分化 (50-60, 60-70, 70-80, 80-90, 90-100)
3. 予測1着コース別 (1-6コース)
4. レース番号 (1-12R)
5. 年度別の安定性
"""

import sqlite3
import pandas as pd
from pathlib import Path


def get_b_50_100_data(db_path: str):
    """B×50-100条件に該当するデータを取得"""
    conn = sqlite3.connect(db_path)

    query = """
    WITH prediction_1st AS (
        SELECT
            race_id,
            pit_number,
            confidence,
            rank_prediction,
            prediction_type
        FROM race_predictions
        WHERE rank_prediction = 1
          AND prediction_type = 'before'
    ),
    result_ranks AS (
        SELECT
            race_id,
            pit_number,
            CAST(rank AS INTEGER) as rank_int
        FROM results
        WHERE rank IS NOT NULL
          AND rank != ''
          AND is_invalid = 0
    ),
    race_1st_2nd_3rd AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank_int = 1 THEN pit_number END) as actual_1st,
            MAX(CASE WHEN rank_int = 2 THEN pit_number END) as actual_2nd,
            MAX(CASE WHEN rank_int = 3 THEN pit_number END) as actual_3rd
        FROM result_ranks
        GROUP BY race_id
        HAVING actual_1st IS NOT NULL AND actual_2nd IS NOT NULL AND actual_3rd IS NOT NULL
    ),
    trifecta_payout AS (
        SELECT
            race_id,
            amount as payout
        FROM payouts
        WHERE bet_type = 'trifecta'
    )
    SELECT
        r.id as race_id,
        r.venue_code,
        r.race_date,
        r.race_number,
        p.pit_number as predicted_1st_pit,
        p.confidence,
        e.racer_rank as c1_rank,
        e.second_rate as c1_second_rate,
        t.odds as odds_1_2_3,
        res.actual_1st,
        res.actual_2nd,
        res.actual_3rd,
        pay.payout,
        CASE
            WHEN res.actual_1st = p.pit_number THEN 1
            ELSE 0
        END as pred_1st_hit,
        p2.pit_number as pred_2nd_pit,
        p3.pit_number as pred_3rd_pit,
        CASE
            WHEN res.actual_1st = p.pit_number
             AND res.actual_2nd = p2.pit_number
             AND res.actual_3rd = p3.pit_number THEN 1
            ELSE 0
        END as trifecta_hit
    FROM races r
    JOIN prediction_1st p ON r.id = p.race_id
    JOIN race_predictions p2 ON r.id = p2.race_id AND p2.rank_prediction = 2 AND p2.prediction_type = 'before'
    JOIN race_predictions p3 ON r.id = p3.race_id AND p3.rank_prediction = 3 AND p3.prediction_type = 'before'
    JOIN entries e ON r.id = e.race_id AND e.pit_number = 1  -- 1コース選手の情報
    JOIN race_1st_2nd_3rd res ON r.id = res.race_id
    JOIN trifecta_odds t ON r.id = t.race_id AND t.combination = '1-2-3'
    LEFT JOIN trifecta_payout pay ON r.id = pay.race_id
    WHERE p.confidence = 'B'
      AND e.racer_rank IN ('A1', 'B1')
      AND t.odds >= 50 AND t.odds < 100
      AND r.race_date >= '2022-01-01' AND r.race_date <= '2025-12-31'
    ORDER BY r.race_date, r.race_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # 年度カラムを追加
    df['year'] = pd.to_datetime(df['race_date']).dt.year

    # オッズ帯カラムを追加
    df['odds_band'] = pd.cut(
        df['odds_1_2_3'],
        bins=[50, 60, 70, 80, 90, 100],
        labels=['50-60', '60-70', '70-80', '80-90', '90-100'],
        right=False
    )

    # レース番号帯カラムを追加
    df['race_half'] = df['race_number'].apply(lambda x: '前半(1-6R)' if x <= 6 else '後半(7-12R)')

    return df


def calculate_roi(df, bet_per_race=400):
    """ROIを計算（パターンH: 3点買い400円）"""
    n = len(df)
    if n == 0:
        return {'n': 0, 'hits': 0, 'hit_rate': 0, 'investment': 0, 'payout': 0, 'profit': 0, 'roi': 0}

    hits = df['trifecta_hit'].sum()
    investment = n * bet_per_race
    payout = df[df['trifecta_hit'] == 1]['payout'].sum() / 100 * bet_per_race if hits > 0 else 0
    profit = payout - investment
    roi = payout / investment * 100 if investment > 0 else 0

    return {
        'n': n,
        'hits': hits,
        'hit_rate': hits / n * 100 if n > 0 else 0,
        'investment': investment,
        'payout': payout,
        'profit': profit,
        'roi': roi
    }


def analyze_by_category(df, category_col, category_name):
    """カテゴリ別の分析"""
    print(f"\n{'='*60}")
    print(f"## {category_name}別分析")
    print(f"{'='*60}")

    results = []
    for cat in df[category_col].dropna().unique():
        subset = df[df[category_col] == cat]
        stats = calculate_roi(subset)
        stats['category'] = cat
        results.append(stats)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('roi', ascending=False)

    print(f"\n| {category_name} | 件数 | 的中 | 的中率 | ROI | 収支 |")
    print(f"|:--|:--:|:--:|:--:|:--:|:--:|")

    for _, row in results_df.iterrows():
        print(f"| {row['category']} | {row['n']} | {row['hits']:.0f} | {row['hit_rate']:.1f}% | {row['roi']:.1f}% | {row['profit']:+,.0f}円 |")

    return results_df


def analyze_yearly_stability(df, category_col, category_name):
    """年度別の安定性分析"""
    print(f"\n### {category_name}別×年度別ROI")

    years = sorted(df['year'].unique())
    categories = df[category_col].dropna().unique()

    print(f"\n| {category_name} | " + " | ".join([str(y) for y in years]) + " | 黒字年数 | 採用推奨 |")
    print("|:--|" + ":--:|" * len(years) + ":--:|:--:|")

    recommendations = []

    for cat in categories:
        yearly_roi = []
        black_years = 0

        for year in years:
            subset = df[(df[category_col] == cat) & (df['year'] == year)]
            stats = calculate_roi(subset)
            yearly_roi.append(stats['roi'])
            if stats['roi'] >= 100 and stats['n'] >= 10:
                black_years += 1

        # 全体統計
        full_stats = calculate_roi(df[df[category_col] == cat])

        # 推奨判断: 直近4年で3年以上黒字、かつ50件以上
        recent_black = sum(1 for i, roi in enumerate(yearly_roi) if roi >= 100 and years[i] >= 2022)
        is_recommended = (recent_black >= 3 and full_stats['n'] >= 50)

        roi_str = " | ".join([f"{roi:.0f}%" if roi > 0 else "-" for roi in yearly_roi])
        rec_str = "**推奨**" if is_recommended else "-"

        print(f"| {cat} | {roi_str} | {black_years}/{len(years)} | {rec_str} |")

        if is_recommended:
            recommendations.append({
                'category': cat,
                'n': full_stats['n'],
                'roi': full_stats['roi'],
                'profit': full_stats['profit'],
                'black_years': black_years
            })

    return recommendations


def main():
    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

    print("="*60)
    print("B×50-100条件 詳細分析レポート")
    print("="*60)
    print(f"\n対象: confidence='B', c1_rank IN ('A1','B1'), odds 50-100")
    print(f"期間: 2022-2025年")
    print(f"方式: パターンH（3点買い400円）")

    # データ取得
    df = get_b_50_100_data(str(db_path))

    if len(df) == 0:
        print("\nデータが見つかりませんでした。")
        return

    # 全体統計
    total_stats = calculate_roi(df)
    print(f"\n### 全体統計（B×50-100）")
    print(f"- 件数: {total_stats['n']}")
    print(f"- 的中: {total_stats['hits']:.0f}件 ({total_stats['hit_rate']:.1f}%)")
    print(f"- ROI: {total_stats['roi']:.1f}%")
    print(f"- 収支: {total_stats['profit']:+,.0f}円")

    all_recommendations = []

    # 1. 1コース選手の級別分析
    print("\n" + "="*60)
    print("## 1. 1コース選手の級別分析 (A1 vs B1)")
    print("="*60)
    rank_results = analyze_by_category(df, 'c1_rank', '1コース級別')
    rank_recs = analyze_yearly_stability(df, 'c1_rank', '1コース級別')
    all_recommendations.extend(rank_recs)

    # 2. オッズ帯の細分化
    print("\n" + "="*60)
    print("## 2. オッズ帯別分析 (50-60, 60-70, 70-80, 80-90, 90-100)")
    print("="*60)
    odds_results = analyze_by_category(df, 'odds_band', 'オッズ帯')
    odds_recs = analyze_yearly_stability(df, 'odds_band', 'オッズ帯')
    all_recommendations.extend(odds_recs)

    # 3. 予測1着コース別
    print("\n" + "="*60)
    print("## 3. 予測1着コース別分析")
    print("="*60)
    course_results = analyze_by_category(df, 'predicted_1st_pit', '予測1着コース')
    course_recs = analyze_yearly_stability(df, 'predicted_1st_pit', '予測1着コース')
    all_recommendations.extend(course_recs)

    # 4. レース番号分析
    print("\n" + "="*60)
    print("## 4. レース番号別分析")
    print("="*60)
    race_results = analyze_by_category(df, 'race_half', 'レース帯')

    # 詳細なレース番号別
    print("\n### 詳細レース番号別")
    race_num_results = analyze_by_category(df, 'race_number', 'レース番号')
    race_recs = analyze_yearly_stability(df, 'race_half', 'レース帯')
    all_recommendations.extend(race_recs)

    # 5. 年度別推移
    print("\n" + "="*60)
    print("## 5. 年度別推移（全体）")
    print("="*60)
    analyze_by_category(df, 'year', '年度')

    # 推奨条件まとめ
    print("\n" + "="*60)
    print("## 推奨条件まとめ（改善効果の大きい順）")
    print("="*60)

    if all_recommendations:
        recs_df = pd.DataFrame(all_recommendations)
        recs_df['improvement'] = recs_df['roi'] - total_stats['roi']
        recs_df = recs_df.sort_values('improvement', ascending=False)

        print("\n| 条件 | 件数 | ROI | 収支 | 現状比 | 黒字年数 |")
        print("|:--|:--:|:--:|:--:|:--:|:--:|")

        for _, row in recs_df.iterrows():
            print(f"| {row['category']} | {row['n']} | {row['roi']:.1f}% | {row['profit']:+,.0f}円 | {row['improvement']:+.1f}pt | {row['black_years']}年 |")
    else:
        print("\n推奨条件はありませんでした（50件以上かつ直近4年で3年以上黒字を満たす条件なし）")

    # 組み合わせ分析
    print("\n" + "="*60)
    print("## 6. 有力な組み合わせ分析")
    print("="*60)

    # A1 × 各オッズ帯
    print("\n### A1 × オッズ帯")
    a1_df = df[df['c1_rank'] == 'A1']
    for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        subset = a1_df[a1_df['odds_band'] == band]
        if len(subset) >= 30:
            stats = calculate_roi(subset)
            print(f"- A1×{band}: {stats['n']}件, ROI {stats['roi']:.1f}%, 収支 {stats['profit']:+,.0f}円")

    # B1 × 各オッズ帯
    print("\n### B1 × オッズ帯")
    b1_df = df[df['c1_rank'] == 'B1']
    for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        subset = b1_df[b1_df['odds_band'] == band]
        if len(subset) >= 30:
            stats = calculate_roi(subset)
            print(f"- B1×{band}: {stats['n']}件, ROI {stats['roi']:.1f}%, 収支 {stats['profit']:+,.0f}円")

    # 赤字除外シミュレーション
    print("\n" + "="*60)
    print("## 7. 赤字条件除外シミュレーション")
    print("="*60)

    # オッズ帯で赤字のものを特定
    print("\n### オッズ帯別（赤字条件を除外した場合）")
    excluded_bands = []
    for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        subset = df[df['odds_band'] == band]
        stats = calculate_roi(subset)
        if stats['roi'] < 100 and stats['n'] >= 30:
            excluded_bands.append(band)
            print(f"- {band}: ROI {stats['roi']:.1f}% -> 除外候補")

    if excluded_bands:
        remaining = df[~df['odds_band'].isin(excluded_bands)]
        remaining_stats = calculate_roi(remaining)
        print(f"\n除外後: {remaining_stats['n']}件, ROI {remaining_stats['roi']:.1f}%, 収支 {remaining_stats['profit']:+,.0f}円")
        print(f"改善効果: ROI {remaining_stats['roi'] - total_stats['roi']:+.1f}pt")


if __name__ == "__main__":
    main()
