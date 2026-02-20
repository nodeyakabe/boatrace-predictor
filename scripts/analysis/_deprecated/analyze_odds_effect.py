# -*- coding: utf-8 -*-
"""
Analyze the effect of odds filtering on ROI
- Compare: all races vs with odds filter
- Understand why odds filter reduces ROI
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'

def get_conn():
    return sqlite3.connect(str(DB_PATH))

def analyze_odds_effect():
    conn = get_conn()

    # Get 2025 data with odds
    df = pd.read_sql_query("""
        SELECT
            rp.race_id,
            rp.confidence,
            e.racer_rank,
            e.motor_second_rate,
            p.amount as trifecta_payout,
            res.rank as actual_rank,
            t.odds as trifecta_odds
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
        LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
            AND t.combination = (
                SELECT GROUP_CONCAT(pit_number, '-')
                FROM (
                    SELECT pit_number
                    FROM race_predictions rp2
                    WHERE rp2.race_id = rp.race_id AND rp2.prediction_type = 'before'
                    ORDER BY rank_prediction
                    LIMIT 3
                )
            )
        WHERE rp.prediction_type = 'before'
          AND substr(r.race_date, 1, 4) = '2025'
          AND rp.rank_prediction = 1
          AND res.is_invalid = 0
    """, conn)
    conn.close()

    df['motor_40plus'] = df['motor_second_rate'] >= 40
    df['is_hit'] = df['actual_rank'] == '1'

    print("=" * 80)
    print("ODDS FILTER EFFECT ANALYSIS")
    print("=" * 80)

    # Check odds data availability
    has_odds = df['trifecta_odds'].notna().sum()
    print(f"\nRecords with odds data: {has_odds:,} / {len(df):,} ({has_odds/len(df)*100:.1f}%)")

    # Analyze A x B1 x Motor40%+
    print("\n" + "=" * 80)
    print("A x B1 x Motor40%+ Analysis")
    print("=" * 80)

    subset = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'B1') & (df['motor_40plus'] == True)]
    print(f"\nTotal records: {len(subset)}")

    # All races (no odds filter)
    hits_all = subset[subset['is_hit'] == True]
    roi_all = hits_all['trifecta_payout'].sum() / (len(subset) * 100) * 100 if len(subset) > 0 else 0
    print(f"\nAll races (no odds filter):")
    print(f"  Records: {len(subset)}, Hits: {len(hits_all)}, ROI: {roi_all:.1f}%")

    # With odds data only
    subset_with_odds = subset[subset['trifecta_odds'].notna()]
    if len(subset_with_odds) > 0:
        hits_with_odds = subset_with_odds[subset_with_odds['is_hit'] == True]
        roi_with_odds = hits_with_odds['trifecta_payout'].sum() / (len(subset_with_odds) * 100) * 100
        print(f"\nWith odds data only:")
        print(f"  Records: {len(subset_with_odds)}, Hits: {len(hits_with_odds)}, ROI: {roi_with_odds:.1f}%")

    # Analyze odds distribution of hits vs misses
    if len(subset_with_odds) > 0:
        print("\n--- Odds Distribution ---")
        print(f"Hits (actual_rank=1) avg odds: {subset_with_odds[subset_with_odds['is_hit']==True]['trifecta_odds'].mean():.1f}")
        print(f"Misses avg odds: {subset_with_odds[subset_with_odds['is_hit']==False]['trifecta_odds'].mean():.1f}")

        # Odds range analysis
        print("\n--- Odds Range Analysis ---")
        ranges = [(0, 10), (10, 20), (20, 30), (30, 50), (50, 100), (100, 9999)]
        for low, high in ranges:
            in_range = subset_with_odds[(subset_with_odds['trifecta_odds'] >= low) & (subset_with_odds['trifecta_odds'] < high)]
            if len(in_range) > 0:
                hits = in_range[in_range['is_hit'] == True]
                roi = hits['trifecta_payout'].sum() / (len(in_range) * 100) * 100
                print(f"  {low}-{high} odds: {len(in_range)} records, {len(hits)} hits, ROI {roi:.1f}%")

    # Compare A x A2 x Motor40%+ (the one that failed)
    print("\n" + "=" * 80)
    print("A x A2 x Motor40%+ Analysis (FAILED condition)")
    print("=" * 80)

    subset_a2 = df[(df['confidence'] == 'A') & (df['racer_rank'] == 'A2') & (df['motor_40plus'] == True)]
    print(f"\nTotal records: {len(subset_a2)}")

    hits_a2_all = subset_a2[subset_a2['is_hit'] == True]
    roi_a2_all = hits_a2_all['trifecta_payout'].sum() / (len(subset_a2) * 100) * 100 if len(subset_a2) > 0 else 0
    print(f"\nAll races (no odds filter):")
    print(f"  Records: {len(subset_a2)}, Hits: {len(hits_a2_all)}, ROI: {roi_a2_all:.1f}%")

    subset_a2_odds = subset_a2[subset_a2['trifecta_odds'].notna()]
    if len(subset_a2_odds) > 0:
        hits_a2_odds = subset_a2_odds[subset_a2_odds['is_hit'] == True]
        roi_a2_odds = hits_a2_odds['trifecta_payout'].sum() / (len(subset_a2_odds) * 100) * 100
        print(f"\nWith odds data only:")
        print(f"  Records: {len(subset_a2_odds)}, Hits: {len(hits_a2_odds)}, ROI: {roi_a2_odds:.1f}%")

        # Odds range analysis
        print("\n--- Odds Range Analysis ---")
        for low, high in ranges:
            in_range = subset_a2_odds[(subset_a2_odds['trifecta_odds'] >= low) & (subset_a2_odds['trifecta_odds'] < high)]
            if len(in_range) > 0:
                hits = in_range[in_range['is_hit'] == True]
                roi = hits['trifecta_payout'].sum() / (len(in_range) * 100) * 100
                print(f"  {low}-{high} odds: {len(in_range)} records, {len(hits)} hits, ROI {roi:.1f}%")

    return df

if __name__ == "__main__":
    df = analyze_odds_effect()
