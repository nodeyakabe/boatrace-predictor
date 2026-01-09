# -*- coding: utf-8 -*-
"""
B×50-100条件の詳細分析スクリプト v2

分析対象: confidence='B', c1_rank IN ('A1','B1'), odds 50-100
期間: 2022-2025年
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
    JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
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

    df['year'] = pd.to_datetime(df['race_date']).dt.year

    df['odds_band'] = pd.cut(
        df['odds_1_2_3'],
        bins=[50, 60, 70, 80, 90, 100],
        labels=['50-60', '60-70', '70-80', '80-90', '90-100'],
        right=False
    )

    df['race_half'] = df['race_number'].apply(lambda x: 'zenhan(1-6R)' if x <= 6 else 'kouhan(7-12R)')

    return df


def calculate_roi(df, bet_per_race=400):
    """ROI calculation (Pattern H: 3-point bet 400 yen)"""
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
        'hits': int(hits),
        'hit_rate': hits / n * 100 if n > 0 else 0,
        'investment': investment,
        'payout': int(payout),
        'profit': int(profit),
        'roi': roi
    }


def analyze_by_category(df, category_col, category_name, output_lines):
    """Category-based analysis"""
    output_lines.append(f"\n{'='*60}")
    output_lines.append(f"## {category_name}")
    output_lines.append(f"{'='*60}")

    results = []
    for cat in sorted(df[category_col].dropna().unique()):
        subset = df[df[category_col] == cat]
        stats = calculate_roi(subset)
        stats['category'] = cat
        results.append(stats)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('roi', ascending=False)

    output_lines.append(f"\n| {category_name} | kensu | tekichu | tekichu_rate | ROI | shushi |")
    output_lines.append(f"|:--|:--:|:--:|:--:|:--:|:--:|")

    for _, row in results_df.iterrows():
        output_lines.append(f"| {row['category']} | {row['n']} | {row['hits']} | {row['hit_rate']:.1f}% | {row['roi']:.1f}% | {row['profit']:+,}yen |")

    return results_df


def analyze_yearly_stability(df, category_col, category_name, output_lines):
    """Yearly stability analysis"""
    output_lines.append(f"\n### {category_name} x yearly ROI")

    years = sorted(df['year'].unique())
    categories = sorted(df[category_col].dropna().unique())

    output_lines.append(f"\n| {category_name} | " + " | ".join([str(y) for y in years]) + " | black_years | recommend |")
    output_lines.append("|:--|" + ":--:|" * len(years) + ":--:|:--:|")

    recommendations = []

    for cat in categories:
        yearly_data = []
        black_years = 0

        for year in years:
            subset = df[(df[category_col] == cat) & (df['year'] == year)]
            stats = calculate_roi(subset)
            yearly_data.append((stats['n'], stats['roi']))
            if stats['roi'] >= 100 and stats['n'] >= 10:
                black_years += 1

        full_stats = calculate_roi(df[df[category_col] == cat])

        recent_black = sum(1 for i, (n, roi) in enumerate(yearly_data) if roi >= 100 and n >= 10 and years[i] >= 2022)
        is_recommended = (recent_black >= 3 and full_stats['n'] >= 50)

        roi_str = " | ".join([f"{roi:.0f}%({n})" if n > 0 else "-" for n, roi in yearly_data])
        rec_str = "**YES**" if is_recommended else "-"

        output_lines.append(f"| {cat} | {roi_str} | {black_years}/{len(years)} | {rec_str} |")

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

    output_lines = []

    output_lines.append("="*60)
    output_lines.append("B x 50-100 DETAILED ANALYSIS REPORT")
    output_lines.append("="*60)
    output_lines.append(f"\nTarget: confidence='B', c1_rank IN ('A1','B1'), odds 50-100")
    output_lines.append(f"Period: 2022-2025")
    output_lines.append(f"Method: Pattern H (3-point bet 400yen)")

    df = get_b_50_100_data(str(db_path))

    if len(df) == 0:
        output_lines.append("\nNo data found.")
        print("\n".join(output_lines))
        return

    total_stats = calculate_roi(df)
    output_lines.append(f"\n### TOTAL STATS (B x 50-100)")
    output_lines.append(f"- kensu: {total_stats['n']}")
    output_lines.append(f"- tekichu: {total_stats['hits']} ({total_stats['hit_rate']:.1f}%)")
    output_lines.append(f"- ROI: {total_stats['roi']:.1f}%")
    output_lines.append(f"- shushi: {total_stats['profit']:+,}yen")

    all_recommendations = []

    # 1. 1course senshi no kyubetsu
    output_lines.append("\n" + "="*60)
    output_lines.append("## 1. 1course senshi kyubetsu (A1 vs B1)")
    output_lines.append("="*60)
    analyze_by_category(df, 'c1_rank', '1course kyubetsu', output_lines)
    rank_recs = analyze_yearly_stability(df, 'c1_rank', '1course kyubetsu', output_lines)
    all_recommendations.extend(rank_recs)

    # 2. Odds band
    output_lines.append("\n" + "="*60)
    output_lines.append("## 2. Odds band (50-60, 60-70, 70-80, 80-90, 90-100)")
    output_lines.append("="*60)
    analyze_by_category(df, 'odds_band', 'odds_band', output_lines)
    odds_recs = analyze_yearly_stability(df, 'odds_band', 'odds_band', output_lines)
    all_recommendations.extend(odds_recs)

    # 3. Predicted 1st course
    output_lines.append("\n" + "="*60)
    output_lines.append("## 3. Predicted 1st course")
    output_lines.append("="*60)
    analyze_by_category(df, 'predicted_1st_pit', 'pred_1st_course', output_lines)
    course_recs = analyze_yearly_stability(df, 'predicted_1st_pit', 'pred_1st_course', output_lines)
    all_recommendations.extend(course_recs)

    # 4. Race number
    output_lines.append("\n" + "="*60)
    output_lines.append("## 4. Race number")
    output_lines.append("="*60)
    analyze_by_category(df, 'race_half', 'race_half', output_lines)
    analyze_by_category(df, 'race_number', 'race_number', output_lines)
    race_recs = analyze_yearly_stability(df, 'race_half', 'race_half', output_lines)
    all_recommendations.extend(race_recs)

    # 5. Yearly trend
    output_lines.append("\n" + "="*60)
    output_lines.append("## 5. Yearly trend (all)")
    output_lines.append("="*60)
    analyze_by_category(df, 'year', 'year', output_lines)

    # Recommendations summary
    output_lines.append("\n" + "="*60)
    output_lines.append("## RECOMMENDATION SUMMARY (by improvement effect)")
    output_lines.append("="*60)

    if all_recommendations:
        recs_df = pd.DataFrame(all_recommendations)
        recs_df['improvement'] = recs_df['roi'] - total_stats['roi']
        recs_df = recs_df.sort_values('improvement', ascending=False)

        output_lines.append("\n| joken | kensu | ROI | shushi | vs_genzai | black_years |")
        output_lines.append("|:--|:--:|:--:|:--:|:--:|:--:|")

        for _, row in recs_df.iterrows():
            output_lines.append(f"| {row['category']} | {row['n']} | {row['roi']:.1f}% | {row['profit']:+,}yen | {row['improvement']:+.1f}pt | {row['black_years']}years |")
    else:
        output_lines.append("\nNo recommended conditions (no conditions with 50+ cases and 3+ black years in recent 4 years)")

    # Combination analysis
    output_lines.append("\n" + "="*60)
    output_lines.append("## 6. Combination analysis")
    output_lines.append("="*60)

    # A1 x odds bands
    output_lines.append("\n### A1 x odds_band")
    a1_df = df[df['c1_rank'] == 'A1']
    for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        subset = a1_df[a1_df['odds_band'] == band]
        if len(subset) >= 10:
            stats = calculate_roi(subset)
            output_lines.append(f"- A1 x {band}: {stats['n']} cases, ROI {stats['roi']:.1f}%, shushi {stats['profit']:+,}yen")
    if len(a1_df) > 0:
        a1_stats = calculate_roi(a1_df)
        output_lines.append(f"- A1 TOTAL: {a1_stats['n']} cases, ROI {a1_stats['roi']:.1f}%, shushi {a1_stats['profit']:+,}yen")

    # B1 x odds bands
    output_lines.append("\n### B1 x odds_band")
    b1_df = df[df['c1_rank'] == 'B1']
    for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        subset = b1_df[b1_df['odds_band'] == band]
        if len(subset) >= 10:
            stats = calculate_roi(subset)
            output_lines.append(f"- B1 x {band}: {stats['n']} cases, ROI {stats['roi']:.1f}%, shushi {stats['profit']:+,}yen")
    if len(b1_df) > 0:
        b1_stats = calculate_roi(b1_df)
        output_lines.append(f"- B1 TOTAL: {b1_stats['n']} cases, ROI {b1_stats['roi']:.1f}%, shushi {b1_stats['profit']:+,}yen")

    # Red exclusion simulation
    output_lines.append("\n" + "="*60)
    output_lines.append("## 7. Red exclusion simulation")
    output_lines.append("="*60)

    output_lines.append("\n### Odds band (exclude red conditions)")
    excluded_bands = []
    for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        subset = df[df['odds_band'] == band]
        stats = calculate_roi(subset)
        if stats['roi'] < 100 and stats['n'] >= 20:
            excluded_bands.append(band)
            output_lines.append(f"- {band}: ROI {stats['roi']:.1f}% ({stats['n']} cases) -> EXCLUDE CANDIDATE")

    if excluded_bands:
        remaining = df[~df['odds_band'].isin(excluded_bands)]
        remaining_stats = calculate_roi(remaining)
        output_lines.append(f"\nAfter exclusion: {remaining_stats['n']} cases, ROI {remaining_stats['roi']:.1f}%, shushi {remaining_stats['profit']:+,}yen")
        output_lines.append(f"Improvement: ROI {remaining_stats['roi'] - total_stats['roi']:+.1f}pt")

    # B1 x excluding red odds bands
    output_lines.append("\n### B1 x (60-70 OR 90-100) - Top performing odds bands only")
    b1_good_odds = b1_df[b1_df['odds_band'].isin(['60-70', '90-100'])]
    if len(b1_good_odds) >= 30:
        stats = calculate_roi(b1_good_odds)
        output_lines.append(f"- B1 x (60-70 OR 90-100): {stats['n']} cases, ROI {stats['roi']:.1f}%, shushi {stats['profit']:+,}yen")

        # Yearly breakdown
        output_lines.append("\n  Yearly breakdown:")
        for year in sorted(b1_good_odds['year'].unique()):
            year_subset = b1_good_odds[b1_good_odds['year'] == year]
            year_stats = calculate_roi(year_subset)
            output_lines.append(f"  - {year}: {year_stats['n']} cases, ROI {year_stats['roi']:.1f}%")

    # Print all
    print("\n".join(output_lines))


if __name__ == "__main__":
    main()
