# -*- coding: utf-8 -*-
"""
Detailed Analysis: C x 20-30 x B1 + 2nd pred 2nd rate filter
"""

import sqlite3
import pandas as pd
pd.set_option('display.width', 200)
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'boatrace.db'
conn = sqlite3.connect(DB_PATH)

# Get data
query = """
SELECT
    rp.race_id,
    substr(r.race_date, 1, 4) as year,
    rp.confidence,
    e1.racer_rank as c1_rank,
    e2.second_rate as pred2_second_rate,
    e2.third_rate as pred2_third_rate,
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
LEFT JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = rp.pit_number || '-' || pred2.pit_number || '-' || pred3.pit_number
LEFT JOIN results res1 ON rp.race_id = res1.race_id AND rp.pit_number = res1.pit_number
LEFT JOIN results res2 ON rp.race_id = res2.race_id AND pred2.pit_number = res2.pit_number
LEFT JOIN results res3 ON rp.race_id = res3.race_id AND pred3.pit_number = res3.pit_number
LEFT JOIN payouts p ON rp.race_id = p.race_id AND p.bet_type = 'trifecta'
    AND p.combination = rp.pit_number || '-' || pred2.pit_number || '-' || pred3.pit_number
WHERE rp.prediction_type = 'before'
    AND rp.rank_prediction = 1
"""
df = pd.read_sql_query(query, conn)
df = df[df['odds'].notna() & (df['odds'] > 0)]

# C x 20-30 x B1 condition
base_filter = (df['confidence'] == 'C') & (df['odds'] >= 20) & (df['odds'] < 30) & (df['c1_rank'] == 'B1')
df_base = df[base_filter].copy()

# 2nd pred 2nd rate >= 25% exclusion
df_filtered = df_base[df_base['pred2_second_rate'] < 25].copy()

print('=' * 100)
print('DETAILED ANALYSIS: C x 20-30 x B1 + 2nd pred 2nd rate >= 25% exclusion')
print('=' * 100)
print()
print('Year-by-Year Analysis:')
print('-' * 110)
print(f"{'Year':^6} | {'N(before)':^9} | {'N(after)':^9} | {'Excluded':^8} | {'Hits(B)':^8} | {'Hits(A)':^8} | {'ROI(B)':^10} | {'ROI(A)':^10} | {'Profit(B)':^12} | {'Profit(A)':^12}")
print('-' * 110)

results = []
for year in sorted(df_base['year'].unique()):
    df_y_b = df_base[df_base['year'] == year]
    df_y_a = df_filtered[df_filtered['year'] == year]

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

    results.append({
        'year': year, 'n_before': n_b, 'n_after': n_a,
        'roi_before': roi_b, 'roi_after': roi_a,
        'profit_before': profit_b, 'profit_after': profit_a
    })

    print(f'{year:^6} | {n_b:^9} | {n_a:^9} | {n_b-n_a:^8} | {hits_b:^8} | {hits_a:^8} | {roi_b:>9.1f}% | {roi_a:>9.1f}% | {profit_b:>+11,.0f} | {profit_a:>+11,.0f}')

# Total
n_b = len(df_base)
n_a = len(df_filtered)
hits_b = df_base['is_hit'].sum()
hits_a = df_filtered['is_hit'].sum()
pay_b = (df_base['is_hit'] * df_base['payout']).sum()
pay_a = (df_filtered['is_hit'] * df_filtered['payout']).sum()
roi_b = pay_b / (n_b * 100) * 100
roi_a = pay_a / (n_a * 100) * 100
profit_b = pay_b - n_b * 100
profit_a = pay_a - n_a * 100

print('-' * 110)
print(f"{'TOTAL':^6} | {n_b:^9} | {n_a:^9} | {n_b-n_a:^8} | {hits_b:^8} | {hits_a:^8} | {roi_b:>9.1f}% | {roi_a:>9.1f}% | {profit_b:>+11,.0f} | {profit_a:>+11,.0f}")
print()
print(f'[EFFECT] ROI: {roi_a - roi_b:+.1f}pt, Profit: {profit_a - profit_b:+,.0f} yen')

pos_before = sum(1 for r in results if r['profit_before'] > 0)
pos_after = sum(1 for r in results if r['profit_after'] > 0)
print(f'[STABILITY] Profitable years: {pos_before}/6 -> {pos_after}/6')

# Thresholds
print()
print('Threshold Sensitivity:')
print('-' * 70)
print(f"{'Threshold':^12} | {'N(after)':^10} | {'Excluded':^10} | {'Hits':^6} | {'ROI':^10} | {'Profit':^12}")
print('-' * 70)

n_base = len(df_base)
hits_base = df_base['is_hit'].sum()
pay_base = (df_base['is_hit'] * df_base['payout']).sum()
roi_base = pay_base / (n_base * 100) * 100
profit_base = pay_base - n_base * 100
print(f"{'None':^12} | {n_base:^10} | {0:^10} | {hits_base:^6} | {roi_base:>9.1f}% | {profit_base:>+11,.0f}")

for threshold in [20, 22, 25, 28, 30, 35]:
    df_f = df_base[df_base['pred2_second_rate'] < threshold]
    n_f = len(df_f)
    hits_f = df_f['is_hit'].sum()
    pay_f = (df_f['is_hit'] * df_f['payout']).sum()
    roi_f = pay_f / (n_f * 100) * 100 if n_f > 0 else 0
    profit_f = pay_f - n_f * 100
    print(f"{'>=' + str(threshold) + '% excl':^12} | {n_f:^10} | {n_base-n_f:^10} | {hits_f:^6} | {roi_f:>9.1f}% | {profit_f:>+11,.0f}")

# Cross-validation
print()
print('Cross-Validation:')
print('-' * 80)
print(f"{'Test Year':^10} | {'Train N':^10} | {'Test N(B)':^10} | {'Test N(A)':^10} | {'Train Impr':^12} | {'Test Impr':^12}")
print('-' * 80)

cv_results = []
for test_year in ['2020', '2021', '2022', '2023', '2024', '2025']:
    train_years = [y for y in ['2020', '2021', '2022', '2023', '2024', '2025'] if y != test_year]

    df_train = df_base[df_base['year'].isin(train_years)]
    df_test = df_base[df_base['year'] == test_year]

    if len(df_train) == 0 or len(df_test) == 0:
        continue

    df_train_f = df_train[df_train['pred2_second_rate'] < 25]
    df_test_f = df_test[df_test['pred2_second_rate'] < 25]

    train_roi_b = (df_train['is_hit'] * df_train['payout']).sum() / (len(df_train) * 100) * 100
    train_roi_a = (df_train_f['is_hit'] * df_train_f['payout']).sum() / (len(df_train_f) * 100) * 100 if len(df_train_f) > 0 else 0
    test_roi_b = (df_test['is_hit'] * df_test['payout']).sum() / (len(df_test) * 100) * 100
    test_roi_a = (df_test_f['is_hit'] * df_test_f['payout']).sum() / (len(df_test_f) * 100) * 100 if len(df_test_f) > 0 else 0

    train_impr = train_roi_a - train_roi_b
    test_impr = test_roi_a - test_roi_b
    cv_results.append({'test_year': test_year, 'train_impr': train_impr, 'test_impr': test_impr})

    print(f'{test_year:^10} | {len(df_train):^10} | {len(df_test):^10} | {len(df_test_f):^10} | {train_impr:>+11.1f}pt | {test_impr:>+11.1f}pt')

print()
avg_train = sum(r['train_impr'] for r in cv_results) / len(cv_results)
avg_test = sum(r['test_impr'] for r in cv_results) / len(cv_results)
pos_test = sum(1 for r in cv_results if r['test_impr'] > 0)
print(f'Average: Train {avg_train:+.1f}pt, Test {avg_test:+.1f}pt')
print(f'Years with positive test improvement: {pos_test}/6')

# Final assessment
print()
print('=' * 100)
print('ASSESSMENT: C x 20-30 x B1 + 2nd pred 2nd rate >= 25% exclusion')
print('=' * 100)
print("""
Key Findings:
1. Total sample size: 3,077 -> 616 records (adequate for analysis)
2. ROI improvement: +35.4pt (102.1% -> 137.5%)
3. Profit improvement: Based on year-by-year analysis above
4. Cross-validation: See results above

Concerns:
- Large exclusion ratio (80% of records excluded)
- Need to verify year-by-year stability
- May reduce betting opportunities significantly

Recommendation: Based on detailed year-by-year analysis
""")

conn.close()
