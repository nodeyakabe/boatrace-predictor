# -*- coding: utf-8 -*-
"""
Motor 40%+ condition implementation verification
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

def get_data_for_verification():
    conn = get_conn()
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
    print("MOTOR 40%+ CONDITION VERIFICATION")
    print("=" * 80)

    df = get_data_for_verification()
    print(f"\nTotal records: {len(df):,}")
    print(f"Motor 40%+ records: {df['motor_40plus'].sum():,} ({df['motor_40plus'].mean()*100:.1f}%)")

    results = []
    conditions = [
        ('A', 'B1', 'A x B1 x Motor40%+'),
        ('A', 'A2', 'A x A2 x Motor40%+'),
        ('D', 'A1', 'D x A1 x Motor40%+'),
        ('D', 'A2', 'D x A2 x Motor40%+'),
    ]

    print("\n" + "=" * 80)
    print("6-YEAR DATA VERIFICATION (2020-2025)")
    print("=" * 80)

    for conf, rank, name in conditions:
        print(f"\n--- {name} ---")

        # Baseline
        base = df[(df['confidence'] == conf) & (df['racer_rank'] == rank)]
        base_roi, base_cnt, base_profit = calc_roi(base)

        # Motor 40%+
        motor = df[(df['confidence'] == conf) & (df['racer_rank'] == rank) & (df['motor_40plus'] == True)]
        motor_roi, motor_cnt, motor_profit = calc_roi(motor)

        print(f"  Baseline: ROI {base_roi:.1f}%, {base_cnt:,} records, profit {base_profit:+,.0f} yen")
        print(f"  Motor40%+: ROI {motor_roi:.1f}%, {motor_cnt:,} records, profit {motor_profit:+,.0f} yen")
        print(f"  Improvement: {motor_roi - base_roi:+.1f}pt")

        # Yearly check
        yearly_positive = 0
        yearly_data = []
        for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
            year_subset = motor[motor['year'] == year]
            if len(year_subset) >= 5:
                roi, cnt, _ = calc_roi(year_subset)
                if roi > 100:
                    yearly_positive += 1
                yearly_data.append(f"{year}:{roi:.0f}%({cnt})")

        print(f"  Yearly: {', '.join(yearly_data)}")
        print(f"  Positive years: {yearly_positive}/6")

        status = 'PASS' if yearly_positive >= 5 and motor_roi > 100 else 'FAIL'
        results.append({
            'condition': name,
            'roi': motor_roi,
            'count': motor_cnt,
            'profit': motor_profit,
            'positive_years': yearly_positive,
            'status': status
        })

    # 2025 comparison
    print("\n" + "=" * 80)
    print("2025 DATA COMPARISON")
    print("=" * 80)

    df_2025 = df[df['year'] == '2025']
    total_new_profit = 0

    print("\nNew conditions (Motor 40%+):")
    for conf, rank, name in conditions:
        subset = df_2025[(df_2025['confidence'] == conf) & (df_2025['racer_rank'] == rank) & (df_2025['motor_40plus'] == True)]
        roi, cnt, profit = calc_roi(subset)
        print(f"  {name}: ROI {roi:.1f}%, {cnt} records, {profit:+,.0f} yen")
        total_new_profit += profit

    print(f"\nTotal additional profit (2025): {total_new_profit:+,.0f} yen")

    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)

    passed = [r for r in results if r['status'] == 'PASS']
    failed = [r for r in results if r['status'] == 'FAIL']

    print(f"\nPASS: {len(passed)}/{len(results)}")
    for r in passed:
        print(f"  [PASS] {r['condition']}: ROI {r['roi']:.1f}%, {r['positive_years']} years positive")

    if failed:
        print(f"\nFAIL: {len(failed)}")
        for r in failed:
            print(f"  [FAIL] {r['condition']}: ROI {r['roi']:.1f}%, {r['positive_years']} years positive")

    total_profit = sum(r['profit'] for r in results)
    print(f"\n6-year total profit from motor conditions: {total_profit:+,.0f} yen")
    print(f"2025 additional profit: {total_new_profit:+,.0f} yen")

    if len(passed) >= 3:
        print("\n=> Implementation verified successfully. Production ready.")
    else:
        print("\n=> Some conditions underperformed. Review needed.")

    return results

if __name__ == "__main__":
    results = main()
