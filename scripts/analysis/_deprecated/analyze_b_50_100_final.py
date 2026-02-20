# -*- coding: utf-8 -*-
"""
B×50-100条件の詳細分析スクリプト（最終版）

分析対象: confidence='B', c1_rank IN ('A1','B1'), odds 50-100
期間: 2020-2025年（6年間）
方式: パターンH（3点買い400円）
"""

import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def get_all_data():
    """B×50-100条件に該当する全データを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    query = """
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            CAST(SUBSTR(r.race_date, 1, 4) AS INTEGER) as year,
            rp.confidence,
            e1.racer_rank as c1_rank,
            e1.second_rate as c1_second_rate,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.confidence = 'B'
        AND e1.racer_rank IN ('A1', 'B1')
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_bets AS (
        SELECT
            rb.*,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = rb.race_id
                 AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                ), 0
            ) as pred_odds,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    )
    SELECT
        race_id,
        venue_code,
        race_date,
        race_number,
        year,
        confidence,
        c1_rank,
        c1_second_rate,
        p1 as predicted_1st,
        pred_odds,
        CASE WHEN p1 = actual_1st AND p2 = actual_2nd AND p3 = actual_3rd THEN 1 ELSE 0 END as trifecta_hit,
        CASE WHEN p1 = actual_1st AND p2 = actual_2nd AND p3 = actual_3rd THEN pred_odds * 100 ELSE 0 END as payout
    FROM race_bets
    WHERE pred_odds >= 50 AND pred_odds < 100
    ORDER BY race_date, race_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    columns = ['race_id', 'venue_code', 'race_date', 'race_number', 'year', 'confidence',
               'c1_rank', 'c1_second_rate', 'predicted_1st', 'pred_odds', 'trifecta_hit', 'payout']

    return [dict(zip(columns, row)) for row in rows]


def calculate_roi(data, bet_per_race=400):
    """ROI calculation (Pattern H: 3-point bet 400 yen)"""
    n = len(data)
    if n == 0:
        return {'n': 0, 'hits': 0, 'hit_rate': 0, 'investment': 0, 'payout': 0, 'profit': 0, 'roi': 0}

    hits = sum(1 for d in data if d['trifecta_hit'] == 1)
    investment = n * bet_per_race
    payout = sum(d['payout'] for d in data if d['trifecta_hit'] == 1) / 100 * bet_per_race
    profit = payout - investment
    roi = payout / investment * 100 if investment > 0 else 0

    return {
        'n': n,
        'hits': hits,
        'hit_rate': hits / n * 100 if n > 0 else 0,
        'investment': investment,
        'payout': int(payout),
        'profit': int(profit),
        'roi': roi
    }


def get_odds_band(odds):
    """Get odds band label"""
    if 50 <= odds < 60:
        return '50-60'
    elif 60 <= odds < 70:
        return '60-70'
    elif 70 <= odds < 80:
        return '70-80'
    elif 80 <= odds < 90:
        return '80-90'
    elif 90 <= odds < 100:
        return '90-100'
    return 'other'


def analyze_by_field(data, field_name, label_func=None):
    """Analyze by a specific field"""
    groups = {}
    for d in data:
        if label_func:
            key = label_func(d)
        else:
            key = d.get(field_name)
        if key not in groups:
            groups[key] = []
        groups[key].append(d)

    results = []
    for key in sorted(groups.keys()):
        stats = calculate_roi(groups[key])
        stats['category'] = key
        results.append(stats)

    return sorted(results, key=lambda x: -x['roi'])


def yearly_analysis(data, field_name, label_func=None):
    """Yearly stability analysis"""
    years = sorted(set(d['year'] for d in data))

    # Get unique categories
    if label_func:
        categories = sorted(set(label_func(d) for d in data))
    else:
        categories = sorted(set(d[field_name] for d in data if d.get(field_name)))

    results = {}
    for cat in categories:
        yearly_data = {}
        if label_func:
            cat_data = [d for d in data if label_func(d) == cat]
        else:
            cat_data = [d for d in data if d.get(field_name) == cat]

        for year in years:
            year_data = [d for d in cat_data if d['year'] == year]
            yearly_data[year] = calculate_roi(year_data)

        # Total stats
        total_stats = calculate_roi(cat_data)

        # Count black years (ROI >= 100% and n >= 10)
        black_years = sum(1 for y in years if yearly_data[y]['roi'] >= 100 and yearly_data[y]['n'] >= 10)

        # Recent 4 years black years
        recent_years = [y for y in years if y >= 2022]
        recent_black = sum(1 for y in recent_years if yearly_data[y]['roi'] >= 100 and yearly_data[y]['n'] >= 10)

        results[cat] = {
            'yearly': yearly_data,
            'total': total_stats,
            'black_years': black_years,
            'recent_black': recent_black,
            'recommended': recent_black >= 3 and total_stats['n'] >= 50
        }

    return results, years


def main():
    print("=" * 70)
    print("B x 50-100 DETAILED ANALYSIS REPORT (2020-2025)")
    print("=" * 70)
    print("\nTarget: confidence='B', c1_rank IN ('A1','B1'), odds 50-100")
    print("Period: 2020-2025 (6 years)")
    print("Method: Pattern H (3-point bet 400yen)")

    data = get_all_data()
    print(f"\nTotal records: {len(data)}")

    if len(data) == 0:
        print("\nNo data found.")
        return

    # Total stats
    total_stats = calculate_roi(data)
    print(f"\n### TOTAL STATS (B x 50-100)")
    print(f"- Cases: {total_stats['n']}")
    print(f"- Hits: {total_stats['hits']} ({total_stats['hit_rate']:.1f}%)")
    print(f"- ROI: {total_stats['roi']:.1f}%")
    print(f"- Profit: {total_stats['profit']:+,}yen")

    # ========================================
    # 1. C1 rank analysis (A1 vs B1)
    # ========================================
    print("\n" + "=" * 70)
    print("## 1. 1-COURSE RACER RANK (A1 vs B1)")
    print("=" * 70)

    rank_results = analyze_by_field(data, 'c1_rank')
    print("\n| Rank | Cases | Hits | Hit% | ROI | Profit |")
    print("|:-----|------:|-----:|-----:|----:|-------:|")
    for r in rank_results:
        print(f"| {r['category']} | {r['n']} | {r['hits']} | {r['hit_rate']:.1f}% | {r['roi']:.1f}% | {r['profit']:+,}yen |")

    yearly_rank, years = yearly_analysis(data, 'c1_rank')
    print(f"\n### Yearly ROI by rank")
    print("| Rank | " + " | ".join(str(y) for y in years) + " | Black | Recommend |")
    print("|:-----|" + ":----:|" * len(years) + ":----:|:--------:|")
    for cat in sorted(yearly_rank.keys()):
        info = yearly_rank[cat]
        roi_str = " | ".join(f"{info['yearly'][y]['roi']:.0f}%({info['yearly'][y]['n']})" if info['yearly'][y]['n'] > 0 else "-" for y in years)
        rec = "YES" if info['recommended'] else "-"
        print(f"| {cat} | {roi_str} | {info['black_years']}/{len(years)} | {rec} |")

    # ========================================
    # 2. Odds band analysis
    # ========================================
    print("\n" + "=" * 70)
    print("## 2. ODDS BAND (50-60, 60-70, 70-80, 80-90, 90-100)")
    print("=" * 70)

    odds_results = analyze_by_field(data, None, lambda d: get_odds_band(d['pred_odds']))
    print("\n| Odds Band | Cases | Hits | Hit% | ROI | Profit |")
    print("|:----------|------:|-----:|-----:|----:|-------:|")
    for r in odds_results:
        print(f"| {r['category']} | {r['n']} | {r['hits']} | {r['hit_rate']:.1f}% | {r['roi']:.1f}% | {r['profit']:+,}yen |")

    yearly_odds, years = yearly_analysis(data, None, lambda d: get_odds_band(d['pred_odds']))
    print(f"\n### Yearly ROI by odds band")
    print("| OddsBand | " + " | ".join(str(y) for y in years) + " | Black | Recommend |")
    print("|:---------|" + ":----:|" * len(years) + ":----:|:--------:|")
    for cat in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        if cat in yearly_odds:
            info = yearly_odds[cat]
            roi_str = " | ".join(f"{info['yearly'][y]['roi']:.0f}%({info['yearly'][y]['n']})" if info['yearly'][y]['n'] > 0 else "-" for y in years)
            rec = "YES" if info['recommended'] else "-"
            print(f"| {cat} | {roi_str} | {info['black_years']}/{len(years)} | {rec} |")

    # ========================================
    # 3. Predicted 1st course
    # ========================================
    print("\n" + "=" * 70)
    print("## 3. PREDICTED 1ST COURSE (1-6)")
    print("=" * 70)

    course_results = analyze_by_field(data, 'predicted_1st')
    print("\n| Course | Cases | Hits | Hit% | ROI | Profit |")
    print("|:-------|------:|-----:|-----:|----:|-------:|")
    for r in course_results:
        print(f"| {int(r['category'])} | {r['n']} | {r['hits']} | {r['hit_rate']:.1f}% | {r['roi']:.1f}% | {r['profit']:+,}yen |")

    yearly_course, years = yearly_analysis(data, 'predicted_1st')
    print(f"\n### Yearly ROI by predicted course")
    print("| Course | " + " | ".join(str(y) for y in years) + " | Black | Recommend |")
    print("|:-------|" + ":----:|" * len(years) + ":----:|:--------:|")
    for cat in sorted(yearly_course.keys()):
        info = yearly_course[cat]
        roi_str = " | ".join(f"{info['yearly'][y]['roi']:.0f}%({info['yearly'][y]['n']})" if info['yearly'][y]['n'] > 0 else "-" for y in years)
        rec = "YES" if info['recommended'] else "-"
        print(f"| {int(cat)} | {roi_str} | {info['black_years']}/{len(years)} | {rec} |")

    # ========================================
    # 4. Race number
    # ========================================
    print("\n" + "=" * 70)
    print("## 4. RACE NUMBER")
    print("=" * 70)

    # First half vs second half
    half_results = analyze_by_field(data, None, lambda d: 'zenhan(1-6R)' if d['race_number'] <= 6 else 'kouhan(7-12R)')
    print("\n### First half vs Second half")
    print("| Half | Cases | Hits | Hit% | ROI | Profit |")
    print("|:-----|------:|-----:|-----:|----:|-------:|")
    for r in half_results:
        print(f"| {r['category']} | {r['n']} | {r['hits']} | {r['hit_rate']:.1f}% | {r['roi']:.1f}% | {r['profit']:+,}yen |")

    yearly_half, years = yearly_analysis(data, None, lambda d: 'zenhan(1-6R)' if d['race_number'] <= 6 else 'kouhan(7-12R)')
    print(f"\n### Yearly ROI by race half")
    print("| Half | " + " | ".join(str(y) for y in years) + " | Black | Recommend |")
    print("|:-----|" + ":----:|" * len(years) + ":----:|:--------:|")
    for cat in ['zenhan(1-6R)', 'kouhan(7-12R)']:
        if cat in yearly_half:
            info = yearly_half[cat]
            roi_str = " | ".join(f"{info['yearly'][y]['roi']:.0f}%({info['yearly'][y]['n']})" if info['yearly'][y]['n'] > 0 else "-" for y in years)
            rec = "YES" if info['recommended'] else "-"
            print(f"| {cat} | {roi_str} | {info['black_years']}/{len(years)} | {rec} |")

    # Detailed race number
    race_results = analyze_by_field(data, 'race_number')
    print("\n### Detailed by race number")
    print("| R# | Cases | Hits | Hit% | ROI | Profit |")
    print("|:---|------:|-----:|-----:|----:|-------:|")
    for r in race_results:
        print(f"| {int(r['category'])}R | {r['n']} | {r['hits']} | {r['hit_rate']:.1f}% | {r['roi']:.1f}% | {r['profit']:+,}yen |")

    # ========================================
    # 5. Yearly trend
    # ========================================
    print("\n" + "=" * 70)
    print("## 5. YEARLY TREND")
    print("=" * 70)

    year_results = analyze_by_field(data, 'year')
    print("\n| Year | Cases | Hits | Hit% | ROI | Profit |")
    print("|:-----|------:|-----:|-----:|----:|-------:|")
    for r in year_results:
        print(f"| {int(r['category'])} | {r['n']} | {r['hits']} | {r['hit_rate']:.1f}% | {r['roi']:.1f}% | {r['profit']:+,}yen |")

    # ========================================
    # 6. Combination analysis
    # ========================================
    print("\n" + "=" * 70)
    print("## 6. COMBINATION ANALYSIS")
    print("=" * 70)

    # B1 x odds bands (B1 has more samples)
    print("\n### B1 x Odds Band")
    b1_data = [d for d in data if d['c1_rank'] == 'B1']
    for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        band_data = [d for d in b1_data if get_odds_band(d['pred_odds']) == band]
        if len(band_data) >= 30:
            stats = calculate_roi(band_data)
            print(f"- B1 x {band}: {stats['n']} cases, ROI {stats['roi']:.1f}%, Profit {stats['profit']:+,}yen")

            # Yearly breakdown
            for year in sorted(set(d['year'] for d in band_data)):
                year_data = [d for d in band_data if d['year'] == year]
                year_stats = calculate_roi(year_data)
                if year_stats['n'] >= 5:
                    print(f"    {year}: {year_stats['n']} cases, ROI {year_stats['roi']:.1f}%")

    # A1 x odds bands
    print("\n### A1 x Odds Band")
    a1_data = [d for d in data if d['c1_rank'] == 'A1']
    a1_stats = calculate_roi(a1_data)
    print(f"- A1 TOTAL: {a1_stats['n']} cases, ROI {a1_stats['roi']:.1f}%, Profit {a1_stats['profit']:+,}yen")
    if a1_stats['n'] >= 10:
        for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
            band_data = [d for d in a1_data if get_odds_band(d['pred_odds']) == band]
            if len(band_data) >= 5:
                stats = calculate_roi(band_data)
                print(f"  - A1 x {band}: {stats['n']} cases, ROI {stats['roi']:.1f}%")

    # ========================================
    # 7. Red exclusion simulation
    # ========================================
    print("\n" + "=" * 70)
    print("## 7. RED EXCLUSION SIMULATION")
    print("=" * 70)

    # Find red odds bands
    red_bands = []
    for band in ['50-60', '60-70', '70-80', '80-90', '90-100']:
        band_data = [d for d in data if get_odds_band(d['pred_odds']) == band]
        stats = calculate_roi(band_data)
        if stats['roi'] < 100 and stats['n'] >= 30:
            red_bands.append(band)
            print(f"- {band}: ROI {stats['roi']:.1f}% ({stats['n']} cases) -> EXCLUDE CANDIDATE")

    if red_bands:
        remaining = [d for d in data if get_odds_band(d['pred_odds']) not in red_bands]
        remaining_stats = calculate_roi(remaining)
        print(f"\nAfter excluding {red_bands}:")
        print(f"- Cases: {remaining_stats['n']}")
        print(f"- ROI: {remaining_stats['roi']:.1f}%")
        print(f"- Profit: {remaining_stats['profit']:+,}yen")
        print(f"- Improvement: {remaining_stats['roi'] - total_stats['roi']:+.1f}pt")

        # Yearly check for remaining
        print("\n### Yearly breakdown after exclusion:")
        for year in sorted(set(d['year'] for d in remaining)):
            year_data = [d for d in remaining if d['year'] == year]
            year_stats = calculate_roi(year_data)
            if year_stats['n'] > 0:
                status = "BLACK" if year_stats['roi'] >= 100 else "RED"
                print(f"  {year}: {year_stats['n']} cases, ROI {year_stats['roi']:.1f}% [{status}]")

    # ========================================
    # 8. Best combination (B1 x good odds bands)
    # ========================================
    print("\n" + "=" * 70)
    print("## 8. RECOMMENDED COMBINATION")
    print("=" * 70)

    # B1 x (60-70 OR 90-100)
    good_bands = ['60-70', '90-100']
    b1_good = [d for d in b1_data if get_odds_band(d['pred_odds']) in good_bands]
    if len(b1_good) >= 50:
        stats = calculate_roi(b1_good)
        print(f"\n### B1 x (60-70 OR 90-100)")
        print(f"- Cases: {stats['n']}")
        print(f"- ROI: {stats['roi']:.1f}%")
        print(f"- Profit: {stats['profit']:+,}yen")

        # Yearly check
        black_count = 0
        print("\n  Yearly breakdown:")
        for year in sorted(set(d['year'] for d in b1_good)):
            year_data = [d for d in b1_good if d['year'] == year]
            year_stats = calculate_roi(year_data)
            if year_stats['n'] > 0:
                status = "BLACK" if year_stats['roi'] >= 100 else "RED"
                if year_stats['roi'] >= 100 and year_stats['n'] >= 10:
                    black_count += 1
                print(f"  {year}: {year_stats['n']} cases, ROI {year_stats['roi']:.1f}% [{status}]")

        print(f"\n  Black years: {black_count}/6")
        if black_count >= 4:
            print("  -> MEETS RECOMMENDATION CRITERIA (4+ years black)")
        elif stats['n'] >= 50:
            print("  -> Has sufficient samples but unstable yearly performance")

    # ========================================
    # SUMMARY
    # ========================================
    print("\n" + "=" * 70)
    print("## SUMMARY")
    print("=" * 70)

    print("\n### Current B×50-100 performance:")
    print(f"- Total: {total_stats['n']} cases, ROI {total_stats['roi']:.1f}%, Profit {total_stats['profit']:+,}yen")

    print("\n### Potential improvements (by improvement effect):")

    improvements = []

    # Check excluding red odds bands
    if red_bands:
        remaining = [d for d in data if get_odds_band(d['pred_odds']) not in red_bands]
        remaining_stats = calculate_roi(remaining)
        if remaining_stats['n'] >= 50:
            improvements.append({
                'condition': f'Exclude {red_bands}',
                'n': remaining_stats['n'],
                'roi': remaining_stats['roi'],
                'profit': remaining_stats['profit'],
                'improvement': remaining_stats['roi'] - total_stats['roi']
            })

    # Check B1 only
    if b1_stats := calculate_roi(b1_data):
        if b1_stats['n'] >= 50:
            improvements.append({
                'condition': 'B1 only',
                'n': b1_stats['n'],
                'roi': b1_stats['roi'],
                'profit': b1_stats['profit'],
                'improvement': b1_stats['roi'] - total_stats['roi']
            })

    # Check B1 x good odds
    if len(b1_good) >= 50:
        b1_good_stats = calculate_roi(b1_good)
        improvements.append({
            'condition': 'B1 x (60-70 OR 90-100)',
            'n': b1_good_stats['n'],
            'roi': b1_good_stats['roi'],
            'profit': b1_good_stats['profit'],
            'improvement': b1_good_stats['roi'] - total_stats['roi']
        })

    # Sort by improvement
    improvements.sort(key=lambda x: -x['improvement'])

    print("\n| Condition | Cases | ROI | Profit | vs Current |")
    print("|:----------|------:|----:|-------:|-----------:|")
    for imp in improvements:
        print(f"| {imp['condition']} | {imp['n']} | {imp['roi']:.1f}% | {imp['profit']:+,}yen | {imp['improvement']:+.1f}pt |")

    # Check if any meet criteria (50+ cases, 3+ black years in recent 4)
    print("\n### Recommendation based on criteria (50+ cases, 3+/4 recent black years):")
    for imp in improvements:
        print(f"- {imp['condition']}: Needs yearly stability check")


if __name__ == "__main__":
    main()
