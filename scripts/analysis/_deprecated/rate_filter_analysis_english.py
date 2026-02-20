# -*- coding: utf-8 -*-
"""
Rate Filter Analysis - English Output Version
"""

import sqlite3
import pandas as pd
pd.set_option('display.width', 200)
pd.set_option('display.max_columns', 20)
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'
conn = sqlite3.connect(DB_PATH)

# Get base data
query = '''
SELECT
    rp.race_id,
    substr(r.race_date, 1, 4) as year,
    r.venue_code,
    r.race_number,
    rp.confidence,
    rp.pit_number as pred1_pit,
    pred2.pit_number as pred2_pit,
    pred3.pit_number as pred3_pit,
    e1.racer_rank as c1_rank,
    e1.second_rate as c1_second_rate,
    e1.third_rate as c1_third_rate,
    e2.second_rate as pred2_second_rate,
    e2.third_rate as pred2_third_rate,
    e3.second_rate as pred3_second_rate,
    e3.third_rate as pred3_third_rate,
    t.odds,
    CASE WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3' THEN 1 ELSE 0 END as is_hit,
    COALESCE(p.amount, 0) as payout
FROM race_predictions rp
JOIN races r ON rp.race_id = r.id
JOIN entries e1 ON rp.race_id = e1.race_id AND e1.pit_number = 1
JOIN race_predictions pred2 ON rp.race_id = pred2.race_id
    AND pred2.prediction_type = rp.prediction_type AND pred2.rank_prediction = 2
JOIN entries e2 ON rp.race_id = e2.race_id AND pred2.pit_number = e2.pit_number
JOIN race_predictions pred3 ON rp.race_id = pred3.race_id
    AND pred3.prediction_type = rp.prediction_type AND pred3.rank_prediction = 3
JOIN entries e3 ON rp.race_id = e3.race_id AND pred3.pit_number = e3.pit_number
LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = rp.pit_number || '-' || pred2.pit_number || '-' || pred3.pit_number
LEFT JOIN results res1 ON rp.race_id = res1.race_id AND rp.pit_number = res1.pit_number
LEFT JOIN results res2 ON rp.race_id = res2.race_id AND pred2.pit_number = res2.pit_number
LEFT JOIN results res3 ON rp.race_id = res3.race_id AND pred3.pit_number = res3.pit_number
LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
    AND p.combination = rp.pit_number || '-' || pred2.pit_number || '-' || pred3.pit_number
WHERE rp.prediction_type = 'before'
    AND rp.rank_prediction = 1
    AND rp.confidence IN ('A', 'B', 'C', 'D')
'''
df = pd.read_sql_query(query, conn)
df = df[df['odds'].notna() & (df['odds'] > 0)]

print("=" * 100)
print("RATE FILTER CANDIDATE ANALYSIS")
print("=" * 100)
print(f"Total valid records: {len(df):,}")
print(f"Years: {sorted(df['year'].unique())}")
print(f"Confidence distribution: {df['confidence'].value_counts().to_dict()}")
print()

# ============================================================
# CANDIDATE 1: A x A1 x 14-16 + 2nd pred 3rd rate >= 35% exclusion
# ============================================================
print("=" * 100)
print("CANDIDATE 1: A x A1 x 14-16 + 2nd predictor 3rd rate >= 35% exclusion")
print("=" * 100)

base_filter_1 = (df['confidence'] == 'A') & (df['c1_rank'] == 'A1') & (df['odds'] >= 14) & (df['odds'] < 16)
df_base1 = df[base_filter_1].copy()
df_filtered1 = df_base1[df_base1['pred2_third_rate'] < 35].copy()

print()
print("Year-by-Year Analysis:")
print("-" * 110)
print(f"{'Year':^6} | {'N(before)':^9} | {'N(after)':^9} | {'Excluded':^8} | {'Hits(B)':^8} | {'Hits(A)':^8} | {'ROI(B)':^10} | {'ROI(A)':^10} | {'Profit(B)':^12} | {'Profit(A)':^12}")
print("-" * 110)

for year in sorted(df_base1['year'].unique()):
    df_y_b = df_base1[df_base1['year'] == year]
    df_y_a = df_filtered1[df_filtered1['year'] == year]

    n_b = len(df_y_b)
    n_a = len(df_y_a)
    hits_b = df_y_b['is_hit'].sum()
    hits_a = df_y_a['is_hit'].sum()
    pay_b = (df_y_b['is_hit'] * df_y_b['payout']).sum()
    pay_a = (df_y_a['is_hit'] * df_y_a['payout']).sum()
    roi_b = pay_b / (n_b * 100) * 100 if n_b > 0 else 0
    roi_a = pay_a / (n_a * 100) * 100 if n_a > 0 else 0
    profit_b = pay_b - n_b * 100
    profit_a = pay_a - n_a * 100

    print(f"{year:^6} | {n_b:^9} | {n_a:^9} | {n_b-n_a:^8} | {hits_b:^8} | {hits_a:^8} | {roi_b:>9.1f}% | {roi_a:>9.1f}% | {profit_b:>+11,.0f} | {profit_a:>+11,.0f}")

# Total
n_b = len(df_base1)
n_a = len(df_filtered1)
hits_b = df_base1['is_hit'].sum()
hits_a = df_filtered1['is_hit'].sum()
pay_b = (df_base1['is_hit'] * df_base1['payout']).sum()
pay_a = (df_filtered1['is_hit'] * df_filtered1['payout']).sum()
roi_b = pay_b / (n_b * 100) * 100 if n_b > 0 else 0
roi_a = pay_a / (n_a * 100) * 100 if n_a > 0 else 0
profit_b = pay_b - n_b * 100
profit_a = pay_a - n_a * 100

print("-" * 110)
print(f"{'TOTAL':^6} | {n_b:^9} | {n_a:^9} | {n_b-n_a:^8} | {hits_b:^8} | {hits_a:^8} | {roi_b:>9.1f}% | {roi_a:>9.1f}% | {profit_b:>+11,.0f} | {profit_a:>+11,.0f}")
print()
print(f"[EFFECT] ROI: {roi_a - roi_b:+.1f}pt, Profit: {profit_a - profit_b:+,.0f} yen")
pos_years_b = sum(1 for year in df_base1['year'].unique() if (df_base1[df_base1['year']==year]['is_hit'] * df_base1[df_base1['year']==year]['payout']).sum() - len(df_base1[df_base1['year']==year]) * 100 > 0)
pos_years_a = sum(1 for year in df_filtered1['year'].unique() if len(df_filtered1[df_filtered1['year']==year]) > 0 and (df_filtered1[df_filtered1['year']==year]['is_hit'] * df_filtered1[df_filtered1['year']==year]['payout']).sum() - len(df_filtered1[df_filtered1['year']==year]) * 100 > 0)
print(f"[STABILITY] Profitable years: {pos_years_b}/6 -> {pos_years_a}/6")

# ============================================================
# CANDIDATE 2
# ============================================================
print()
print("=" * 100)
print("CANDIDATE 2: A x A1 x 14-16 + 2nd predictor 2nd rate >= 25% exclusion")
print("=" * 100)

df_filtered2 = df_base1[df_base1['pred2_second_rate'] < 25].copy()

print()
print("Year-by-Year Analysis:")
print("-" * 110)
print(f"{'Year':^6} | {'N(before)':^9} | {'N(after)':^9} | {'Excluded':^8} | {'Hits(B)':^8} | {'Hits(A)':^8} | {'ROI(B)':^10} | {'ROI(A)':^10} | {'Profit(B)':^12} | {'Profit(A)':^12}")
print("-" * 110)

for year in sorted(df_base1['year'].unique()):
    df_y_b = df_base1[df_base1['year'] == year]
    df_y_a = df_filtered2[df_filtered2['year'] == year]

    n_b = len(df_y_b)
    n_a = len(df_y_a)
    hits_b = df_y_b['is_hit'].sum()
    hits_a = df_y_a['is_hit'].sum()
    pay_b = (df_y_b['is_hit'] * df_y_b['payout']).sum()
    pay_a = (df_y_a['is_hit'] * df_y_a['payout']).sum()
    roi_b = pay_b / (n_b * 100) * 100 if n_b > 0 else 0
    roi_a = pay_a / (n_a * 100) * 100 if n_a > 0 else 0
    profit_b = pay_b - n_b * 100
    profit_a = pay_a - n_a * 100

    print(f"{year:^6} | {n_b:^9} | {n_a:^9} | {n_b-n_a:^8} | {hits_b:^8} | {hits_a:^8} | {roi_b:>9.1f}% | {roi_a:>9.1f}% | {profit_b:>+11,.0f} | {profit_a:>+11,.0f}")

n_a = len(df_filtered2)
pay_a = (df_filtered2['is_hit'] * df_filtered2['payout']).sum()
roi_a = pay_a / (n_a * 100) * 100 if n_a > 0 else 0
profit_a = pay_a - n_a * 100

print("-" * 110)
print(f"{'TOTAL':^6} | {n_b:^9} | {n_a:^9} | {n_b-n_a:^8} | {hits_b:^8} | {df_filtered2['is_hit'].sum():^8} | {roi_b:>9.1f}% | {roi_a:>9.1f}% | {profit_b:>+11,.0f} | {profit_a:>+11,.0f}")
print(f"[EFFECT] ROI: {roi_a - roi_b:+.1f}pt, Profit: {profit_a - profit_b:+,.0f} yen")

# ============================================================
# CANDIDATE 3
# ============================================================
print()
print("=" * 100)
print("CANDIDATE 3: A x A1 x 10-12 + 3rd predictor 2nd rate < 55% exclusion")
print("=" * 100)

base_filter_3 = (df['confidence'] == 'A') & (df['c1_rank'] == 'A1') & (df['odds'] >= 10) & (df['odds'] < 12)
df_base3 = df[base_filter_3].copy()
df_filtered3 = df_base3[df_base3['pred3_second_rate'] >= 55].copy()

print()
print("Year-by-Year Analysis:")
print("-" * 110)
print(f"{'Year':^6} | {'N(before)':^9} | {'N(after)':^9} | {'Excluded':^8} | {'Hits(B)':^8} | {'Hits(A)':^8} | {'ROI(B)':^10} | {'ROI(A)':^10} | {'Profit(B)':^12} | {'Profit(A)':^12}")
print("-" * 110)

for year in sorted(df_base3['year'].unique()):
    df_y_b = df_base3[df_base3['year'] == year]
    df_y_a = df_filtered3[df_filtered3['year'] == year]

    n_b = len(df_y_b)
    n_a = len(df_y_a)
    hits_b = df_y_b['is_hit'].sum()
    hits_a = df_y_a['is_hit'].sum()
    pay_b = (df_y_b['is_hit'] * df_y_b['payout']).sum()
    pay_a = (df_y_a['is_hit'] * df_y_a['payout']).sum()
    roi_b = pay_b / (n_b * 100) * 100 if n_b > 0 else 0
    roi_a = pay_a / (n_a * 100) * 100 if n_a > 0 else 0
    profit_b = pay_b - n_b * 100
    profit_a = pay_a - n_a * 100

    print(f"{year:^6} | {n_b:^9} | {n_a:^9} | {n_b-n_a:^8} | {hits_b:^8} | {hits_a:^8} | {roi_b:>9.1f}% | {roi_a:>9.1f}% | {profit_b:>+11,.0f} | {profit_a:>+11,.0f}")

n_b = len(df_base3)
n_a = len(df_filtered3)
hits_b = df_base3['is_hit'].sum()
hits_a = df_filtered3['is_hit'].sum()
pay_b = (df_base3['is_hit'] * df_base3['payout']).sum()
pay_a = (df_filtered3['is_hit'] * df_filtered3['payout']).sum()
roi_b = pay_b / (n_b * 100) * 100 if n_b > 0 else 0
roi_a = pay_a / (n_a * 100) * 100 if n_a > 0 else 0
profit_b = pay_b - n_b * 100
profit_a = pay_a - n_a * 100

print("-" * 110)
print(f"{'TOTAL':^6} | {n_b:^9} | {n_a:^9} | {n_b-n_a:^8} | {hits_b:^8} | {hits_a:^8} | {roi_b:>9.1f}% | {roi_a:>9.1f}% | {profit_b:>+11,.0f} | {profit_a:>+11,.0f}")
print(f"[EFFECT] ROI: {roi_a - roi_b:+.1f}pt, Profit: {profit_a - profit_b:+,.0f} yen")

# ============================================================
# THRESHOLD SENSITIVITY
# ============================================================
print()
print("=" * 100)
print("THRESHOLD SENSITIVITY: A x A1 x 14-16 - 2nd predictor 3rd rate")
print("=" * 100)
print()
print(f"{'Threshold':^12} | {'N(after)':^10} | {'Excluded':^10} | {'Hits':^6} | {'ROI':^10} | {'Profit':^12}")
print("-" * 70)

n_base = len(df_base1)
hits_base = df_base1['is_hit'].sum()
pay_base = (df_base1['is_hit'] * df_base1['payout']).sum()
roi_base = pay_base / (n_base * 100) * 100
profit_base = pay_base - n_base * 100
print(f"{'None':^12} | {n_base:^10} | {0:^10} | {hits_base:^6} | {roi_base:>9.1f}% | {profit_base:>+11,.0f}")

for threshold in [25, 30, 35, 40, 45, 50]:
    df_f = df_base1[df_base1['pred2_third_rate'] < threshold]
    n_f = len(df_f)
    hits_f = df_f['is_hit'].sum()
    pay_f = (df_f['is_hit'] * df_f['payout']).sum()
    roi_f = pay_f / (n_f * 100) * 100 if n_f > 0 else 0
    profit_f = pay_f - n_f * 100
    print(f"{'>=' + str(threshold) + '% excl':^12} | {n_f:^10} | {n_base-n_f:^10} | {hits_f:^6} | {roi_f:>9.1f}% | {profit_f:>+11,.0f}")

# ============================================================
# OTHER CONDITIONS
# ============================================================
print()
print("=" * 100)
print("OTHER CONDITIONS - RATE FILTER APPLICABILITY")
print("=" * 100)

for cond_name, cond_filter in [
    ('B x 50-100', (df['confidence'] == 'B') & (df['odds'] >= 50) & (df['odds'] < 100) & (df['c1_rank'].isin(['A1', 'B1']))),
    ('C x 20-30 x B1', (df['confidence'] == 'C') & (df['odds'] >= 20) & (df['odds'] < 30) & (df['c1_rank'] == 'B1')),
    ('D x 35-60', (df['confidence'] == 'D') & (df['odds'] >= 35) & (df['odds'] < 60) & (df['c1_rank'].isin(['A1', 'A2', 'B1']))),
    ('D x 40-50 x B1', (df['confidence'] == 'D') & (df['odds'] >= 40) & (df['odds'] < 50) & (df['c1_rank'] == 'B1')),
]:
    df_c = df[cond_filter].copy()
    if len(df_c) == 0:
        continue
    print(f"")
    print(f"--- {cond_name} (n={len(df_c)}) ---")

    roi_base = (df_c['is_hit'] * df_c['payout']).sum() / (len(df_c) * 100) * 100

    for rate_col, rate_name in [('pred2_second_rate', '2nd pred 2nd rate'), ('pred2_third_rate', '2nd pred 3rd rate')]:
        for threshold in [25, 30, 35, 40]:
            df_f = df_c[df_c[rate_col] < threshold]
            if len(df_f) == 0 or len(df_f) == len(df_c):
                continue
            roi_f = (df_f['is_hit'] * df_f['payout']).sum() / (len(df_f) * 100) * 100 if len(df_f) > 0 else 0
            improvement = roi_f - roi_base
            if improvement > 10:
                print(f"  {rate_name} >= {threshold}% excl: {len(df_c)} -> {len(df_f)} | ROI {roi_base:.1f}% -> {roi_f:.1f}% ({improvement:+.1f}pt)")

# ============================================================
# CROSS-VALIDATION
# ============================================================
print()
print("=" * 100)
print("CROSS-VALIDATION: Leave-One-Year-Out")
print("=" * 100)

print()
print("--- Candidate 1: A x A1 x 14-16 + 2nd pred 3rd rate >= 35% exclusion ---")
print(f"{'Test Year':^10} | {'Train N':^10} | {'Test N(B)':^10} | {'Test N(A)':^10} | {'Train Impr':^12} | {'Test Impr':^12}")
print("-" * 80)

cv_results = []
for test_year in ['2020', '2021', '2022', '2023', '2024', '2025']:
    train_years = [y for y in ['2020', '2021', '2022', '2023', '2024', '2025'] if y != test_year]

    df_train = df_base1[df_base1['year'].isin(train_years)]
    df_test = df_base1[df_base1['year'] == test_year]

    if len(df_train) == 0 or len(df_test) == 0:
        continue

    # Training set
    df_train_filtered = df_train[df_train['pred2_third_rate'] < 35]
    train_roi_before = (df_train['is_hit'] * df_train['payout']).sum() / (len(df_train) * 100) * 100
    train_roi_after = (df_train_filtered['is_hit'] * df_train_filtered['payout']).sum() / (len(df_train_filtered) * 100) * 100 if len(df_train_filtered) > 0 else 0

    # Test set
    df_test_filtered = df_test[df_test['pred2_third_rate'] < 35]
    test_roi_before = (df_test['is_hit'] * df_test['payout']).sum() / (len(df_test) * 100) * 100
    test_roi_after = (df_test_filtered['is_hit'] * df_test_filtered['payout']).sum() / (len(df_test_filtered) * 100) * 100 if len(df_test_filtered) > 0 else 0

    cv_results.append({
        'test_year': test_year,
        'train_improvement': train_roi_after - train_roi_before,
        'test_improvement': test_roi_after - test_roi_before
    })

    print(f"{test_year:^10} | {len(df_train):^10} | {len(df_test):^10} | {len(df_test_filtered):^10} | {train_roi_after - train_roi_before:>+11.1f}pt | {test_roi_after - test_roi_before:>+11.1f}pt")

print()
avg_train = sum(r['train_improvement'] for r in cv_results) / len(cv_results)
avg_test = sum(r['test_improvement'] for r in cv_results) / len(cv_results)
consistent = sum(1 for r in cv_results if r['test_improvement'] > 0)
print(f"Average: Train {avg_train:+.1f}pt, Test {avg_test:+.1f}pt")
print(f"Years with positive test improvement: {consistent}/6")

# ============================================================
# FINAL RECOMMENDATION
# ============================================================
print()
print("=" * 100)
print("FINAL RECOMMENDATION")
print("=" * 100)
print("""
## Candidate 1: A x A1 x 14-16 + 2nd pred 3rd rate >= 35% exclusion
   - Verdict: [DO NOT IMPLEMENT]
   - Reason: Extremely small sample size (only 3-5 records per year after filtering)
   - Risk: High overfitting risk, statistically unreliable

## Candidate 2: A x A1 x 14-16 + 2nd pred 2nd rate >= 25% exclusion
   - Verdict: [DO NOT IMPLEMENT]
   - Reason: Same as Candidate 1, insufficient sample size

## Candidate 3: A x A1 x 10-12 + 3rd pred 2nd rate < 55% exclusion
   - Verdict: [DO NOT IMPLEMENT]
   - Reason: Inconsistent year-over-year performance (2021: -250, 2022: -900 yen)

## Additional Findings - C x 20-30 x B1 Condition
   - 2nd pred 2nd rate >= 25% exclusion: ROI +35.4pt improvement (3077 -> 616 records)
   - Verdict: [WORTHY OF FURTHER INVESTIGATION]
   - Note: Sufficient sample size, but requires year-by-year stability check

## Summary
The originally identified p-values (p=0.0305, p=0.0097, p=0.0995) appear to be
artifacts of small sample sizes rather than genuine statistical effects.

The rate filter conditions should NOT be implemented at this time due to:
1. Insufficient sample sizes (especially for A x A1 x 14-16 conditions)
2. Year-over-year instability (2023 shows 0% ROI for filtered conditions)
3. High overfitting risk when filtering to only 3-5 records per year

Recommendation: Monitor these conditions as more data accumulates.
Revisit analysis when each condition has 100+ records per year.
""")

conn.close()
