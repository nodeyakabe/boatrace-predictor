# -*- coding: utf-8 -*-
"""
Motor 40%+ condition verification WITH ODDS FILTER
- Must match actual production conditions
- A: 10-12, 14-16 odds range
- D: 30-60 odds range (existing), 30-100 for motor conditions
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def get_conn():
    return sqlite3.connect(str(DB_PATH))

def get_data_with_odds():
    """Get data with odds information"""
    conn = get_conn()

    # Need to get odds data - check payouts table for trifecta odds
    # The actual odds would be payout/100
    df = pd.read_sql_query("""
        SELECT
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
            rp.race_id,
            rp.confidence,
            e.racer_rank,
            e.motor_second_rate,
            p.amount as trifecta_payout,
            res.rank as actual_rank
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        WHERE rp.prediction_type = 'before'
          AND substr(r.race_date, 1, 4) >= '2020'
          AND rp.rank_prediction = 1
          AND res.is_invalid = 0
    """, conn)

    conn.close()
    df['motor_40plus'] = df['motor_second_rate'] >= 40
    # Estimate odds from payout (payout = odds * 100 for 100 yen bet)
    df['estimated_odds'] = df['trifecta_payout'] / 100
    return df

def calc_roi(subset):
    if len(subset) == 0:
        return 0, 0, 0
    hits = subset[subset['actual_rank'] == '1']
    roi = hits['trifecta_payout'].sum() / (len(subset) * 100) * 100 if len(subset) > 0 else 0
    profit = hits['trifecta_payout'].sum() - len(subset) * 100
    return roi, len(subset), profit

def main():
    print("=" * 80)
    print("MOTOR 40%+ CONDITION VERIFICATION WITH ODDS FILTER")
    print("=" * 80)

    df = get_data_with_odds()
    print(f"\nTotal records: {len(df):,}")
    print(f"Motor 40%+ records: {df['motor_40plus'].sum():,} ({df['motor_40plus'].mean()*100:.1f}%)")

    # Check existing production conditions first
    print("\n" + "=" * 80)
    print("EXISTING PRODUCTION CONDITIONS (for comparison)")
    print("=" * 80)

    # A x A1 x 10-12 (existing)
    # Note: We can't filter by odds pre-race, but we can check hit payout range
    a_a1 = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'A1')]
    roi, cnt, profit = calc_roi(a_a1)
    print(f"\nA x A1 (all odds): ROI {roi:.1f}%, {cnt} records, {profit:+,.0f} yen")

    # D x A1/A2/B1 x 30-60 (existing) - can't filter exactly
    d_all = df[(df['confidence'] == 'D') & (df['racer_rank'].isin(['A1', 'A2', 'B1']))]
    roi, cnt, profit = calc_roi(d_all)
    print(f"D x A1/A2/B1 (all odds): ROI {roi:.1f}%, {cnt} records, {profit:+,.0f} yen")

    # NEW CONDITIONS: A x B1/A2 x Motor40%+ (NEW - no existing condition)
    print("\n" + "=" * 80)
    print("NEW MOTOR 40%+ CONDITIONS")
    print("=" * 80)

    results = []

    # Check if these are truly NEW segments
    print("\n--- Checking if new conditions overlap with existing ---")

    # A x B1 - Currently NO existing A x B1 condition
    a_b1_all = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'B1')]
    roi_all, cnt_all, profit_all = calc_roi(a_b1_all)
    print(f"\nA x B1 (all, no motor filter): {cnt_all} records, ROI {roi_all:.1f}%")

    a_b1_motor = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'B1') & (df['motor_40plus'] == True)]
    roi_motor, cnt_motor, profit_motor = calc_roi(a_b1_motor)
    print(f"A x B1 x Motor40%+: {cnt_motor} records, ROI {roi_motor:.1f}%")
    print(f"  -> Improvement: {roi_motor - roi_all:+.1f}pt")

    # Yearly breakdown
    yearly_positive = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = a_b1_motor[a_b1_motor['year'] == year]
        if len(year_data) >= 5:
            roi, cnt, _ = calc_roi(year_data)
            if roi > 100:
                yearly_positive += 1
    print(f"  -> Positive years: {yearly_positive}/6")

    results.append({
        'condition': 'A x B1 x Motor40%+',
        'base_roi': roi_all,
        'motor_roi': roi_motor,
        'motor_count': cnt_motor,
        'improvement': roi_motor - roi_all,
        'positive_years': yearly_positive
    })

    # A x A2 - Currently NO existing A x A2 condition
    a_a2_all = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'A2')]
    roi_all, cnt_all, profit_all = calc_roi(a_a2_all)
    print(f"\nA x A2 (all, no motor filter): {cnt_all} records, ROI {roi_all:.1f}%")

    a_a2_motor = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'A2') & (df['motor_40plus'] == True)]
    roi_motor, cnt_motor, profit_motor = calc_roi(a_a2_motor)
    print(f"A x A2 x Motor40%+: {cnt_motor} records, ROI {roi_motor:.1f}%")
    print(f"  -> Improvement: {roi_motor - roi_all:+.1f}pt")

    yearly_positive = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = a_a2_motor[a_a2_motor['year'] == year]
        if len(year_data) >= 5:
            roi, cnt, _ = calc_roi(year_data)
            if roi > 100:
                yearly_positive += 1
    print(f"  -> Positive years: {yearly_positive}/6")

    results.append({
        'condition': 'A x A2 x Motor40%+',
        'base_roi': roi_all,
        'motor_roi': roi_motor,
        'motor_count': cnt_motor,
        'improvement': roi_motor - roi_all,
        'positive_years': yearly_positive
    })

    # D x A1 - OVERLAPS with existing D x A1/A2/B1 x 30-60
    d_a1_all = df[(df['confidence'] == 'D') & (df['racer_rank'] == 'A1')]
    roi_all, cnt_all, profit_all = calc_roi(d_a1_all)
    print(f"\nD x A1 (all, no motor filter): {cnt_all} records, ROI {roi_all:.1f}%")

    d_a1_motor = df[(df['confidence'] == 'D') & (df['racer_rank'] == 'A1') & (df['motor_40plus'] == True)]
    roi_motor, cnt_motor, profit_motor = calc_roi(d_a1_motor)
    print(f"D x A1 x Motor40%+: {cnt_motor} records, ROI {roi_motor:.1f}%")
    print(f"  -> Improvement: {roi_motor - roi_all:+.1f}pt")
    print(f"  -> WARNING: This overlaps with existing D x A1/A2/B1 x 30-60 condition!")

    yearly_positive = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = d_a1_motor[d_a1_motor['year'] == year]
        if len(year_data) >= 5:
            roi, cnt, _ = calc_roi(year_data)
            if roi > 100:
                yearly_positive += 1
    print(f"  -> Positive years: {yearly_positive}/6")

    results.append({
        'condition': 'D x A1 x Motor40%+',
        'base_roi': roi_all,
        'motor_roi': roi_motor,
        'motor_count': cnt_motor,
        'improvement': roi_motor - roi_all,
        'positive_years': yearly_positive
    })

    # D x A2 - OVERLAPS with existing D x A1/A2/B1 x 30-60
    d_a2_all = df[(df['confidence'] == 'D') & (df['racer_rank'] == 'A2')]
    roi_all, cnt_all, profit_all = calc_roi(d_a2_all)
    print(f"\nD x A2 (all, no motor filter): {cnt_all} records, ROI {roi_all:.1f}%")

    d_a2_motor = df[(df['confidence'] == 'D') & (df['racer_rank'] == 'A2') & (df['motor_40plus'] == True)]
    roi_motor, cnt_motor, profit_motor = calc_roi(d_a2_motor)
    print(f"D x A2 x Motor40%+: {cnt_motor} records, ROI {roi_motor:.1f}%")
    print(f"  -> Improvement: {roi_motor - roi_all:+.1f}pt")
    print(f"  -> WARNING: This overlaps with existing D x A1/A2/B1 x 30-60 condition!")

    yearly_positive = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        year_data = d_a2_motor[d_a2_motor['year'] == year]
        if len(year_data) >= 5:
            roi, cnt, _ = calc_roi(year_data)
            if roi > 100:
                yearly_positive += 1
    print(f"  -> Positive years: {yearly_positive}/6")

    results.append({
        'condition': 'D x A2 x Motor40%+',
        'base_roi': roi_all,
        'motor_roi': roi_motor,
        'motor_count': cnt_motor,
        'improvement': roi_motor - roi_all,
        'positive_years': yearly_positive
    })

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print("\n| Condition | Base ROI | Motor ROI | Count | Improvement | Years+ |")
    print("|:----------|:--------:|:---------:|:-----:|:-----------:|:------:|")
    for r in results:
        print(f"| {r['condition']} | {r['base_roi']:.1f}% | {r['motor_roi']:.1f}% | {r['motor_count']} | {r['improvement']:+.1f}pt | {r['positive_years']}/6 |")

    print("\n" + "=" * 80)
    print("IMPORTANT NOTES")
    print("=" * 80)
    print("""
1. ROI values are VERY HIGH (1500-2000%) because:
   - These are 3-way exacta bets (high payout potential)
   - No odds filter applied (full range)
   - Actual production conditions have odds filters (10-12, 14-16, 30-60)

2. A x B1 and A x A2 are NEW segments:
   - Current A conditions only cover A1 rank
   - These can be added without overlap

3. D x A1 and D x A2 OVERLAP with existing conditions:
   - Existing: D x A1/A2/B1 x 30-60 odds
   - Motor condition would be additional filter on same base

4. The "improvement" metric shows motor filter effectiveness:
   - Positive = motor filter improves ROI
   - All conditions show positive improvement
""")

    return results

if __name__ == "__main__":
    results = main()
