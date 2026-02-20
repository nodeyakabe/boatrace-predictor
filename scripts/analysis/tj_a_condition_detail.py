#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A_A1_10_12のavg_st分析詳細 - 件数不整合の原因調査と正確な分析"""

import sqlite3
import os
import pandas as pd

os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

conn = sqlite3.connect('data/boatrace.db')

# GLOBAL_VENUE_MONTH_EXCLUDES
global_excludes = [(5, 2), (22, 2), (14, 1), (14, 2), (17, 2)]
excl_parts = []
for v, m in global_excludes:
    excl_parts.append(f"(r.venue_code = '{v:02d}' AND CAST(strftime('%m', r.race_date) AS INTEGER) = {m})")
global_excl_clause = 'AND NOT (' + ' OR '.join(excl_parts) + ')'

# =====================================================
# A_A1_10_12の正確な分析（escape_rateとavg_stの両方を含む）
# =====================================================
print('='*90)
print(' A_A1_10_12 のavg_stフィルター詳細分析')
print('='*90)

# ベースクエリ: escape_rate + avg_st を同時取得
query = f"""
SELECT
    r.id as race_id,
    r.race_date,
    r.venue_code,
    strftime('%Y', r.race_date) as year,
    rp1.total_score - rp2.total_score as score_gap,
    e_avgst.avg_st as p1_avg_st,
    CASE WHEN res1.pit_number = rp1.pit_number
         AND res2.pit_number = rp2.pit_number
         AND res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END as trifecta_hit,
    t.odds as trifecta_odds
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
LEFT JOIN (
    SELECT player_id, escape_rate
    FROM player_escape_stats
    WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
    AND id IN (SELECT MAX(id) FROM player_escape_stats WHERE stadium_id IS NULL AND escape_rate IS NOT NULL GROUP BY player_id)
) pes ON e_pred.racer_number = pes.player_id
LEFT JOIN entries e_avgst ON r.id = e_avgst.race_id AND e_avgst.pit_number = rp1.pit_number
LEFT JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
LEFT JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
LEFT JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
LEFT JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
AND rp.confidence = 'A'
AND e1.racer_rank IN ('A1')
AND r.venue_code IN ('10','14','21','18','08','12')
AND rp1.pit_number = 1
AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= 0.7
{global_excl_clause}
AND t.odds IS NOT NULL
AND t.odds >= 10 AND t.odds < 12
"""

df = pd.read_sql_query(query, conn)

# 重複チェック
print(f'\n全レース数: {len(df)}件 (race_idユニーク: {df["race_id"].nunique()}件)')

# 重複除去
df = df.drop_duplicates(subset='race_id', keep='first')
print(f'重複除去後: {len(df)}件')

# 全体
n = len(df)
hit_sum = df.loc[df['trifecta_hit']==1, 'trifecta_odds'].sum()
roi = hit_sum / n * 100 if n else 0
profit = (hit_sum - n) * 100
print(f'全体: {n}件, ROI {roi:.1f}%, 収支 {profit:+,.0f}円')

# avg_st分布
print(f'\navg_st分布:')
print(f'  avg_st NULL: {df["p1_avg_st"].isna().sum()}件')

df_valid = df[df['p1_avg_st'].notna()].copy()
print(f'  avg_st有効: {len(df_valid)}件')

bins = [(-1, 0.10), (0.10, 0.13), (0.13, 0.15), (0.15, 0.17), (0.17, 0.20), (0.20, 9.99)]
labels = ['<0.10', '0.10-0.13', '0.13-0.15', '0.15-0.17', '0.17-0.20', '>=0.20']

print(f'\n  {"avg_st帯":>12} | {"件数":>5} | {"三連単的中":>8} | {"ROI":>8} | {"収支":>10}')
print('  ' + '-'*60)

for (lo, hi), label in zip(bins, labels):
    subset = df_valid[(df_valid['p1_avg_st'] >= lo) & (df_valid['p1_avg_st'] < hi)]
    sn = len(subset)
    if sn == 0:
        continue
    s_hit = subset.loc[subset['trifecta_hit']==1, 'trifecta_odds'].sum()
    s_roi = s_hit / sn * 100 if sn else 0
    s_profit = (s_hit - sn) * 100
    s_tri = subset['trifecta_hit'].sum()
    print(f'  {label:>12} | {sn:>5} | {s_tri:>8} | {s_roi:>7.1f}% | {s_profit:>+10,.0f}')

# avg_stフィルターの効果（年度別）
for threshold_label, filter_func in [
    ('avg_st<=0.13', lambda d: d['p1_avg_st'] <= 0.13),
    ('avg_st<=0.15', lambda d: d['p1_avg_st'] <= 0.15),
    ('avg_st<=0.17', lambda d: d['p1_avg_st'] <= 0.17),
]:
    filtered = df_valid[filter_func(df_valid)]
    fn = len(filtered)
    if fn == 0:
        continue

    fhit = filtered.loc[filtered['trifecta_hit']==1, 'trifecta_odds'].sum()
    froi = fhit / fn * 100
    fprofit = (fhit - fn) * 100

    print(f'\n--- フィルター: {threshold_label} ({fn}件, ROI {froi:.1f}%, 収支 {fprofit:+,.0f}円) ---')
    print(f'  {"年度":>6} | {"件数":>5} | {"ROI":>8} | {"収支":>10} | {"判定"}')
    print('  ' + '-'*50)

    black_count = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        ydf = filtered[filtered['year'] == year]
        yn = len(ydf)
        if yn == 0:
            print(f'  {year:>6} | {0:>5} | {"N/A":>8} | {"N/A":>10} | -')
            continue
        yhit = ydf.loc[ydf['trifecta_hit']==1, 'trifecta_odds'].sum()
        yroi = yhit / yn * 100
        yprofit = (yhit - yn) * 100
        is_black = yprofit > 0
        if is_black:
            black_count += 1
        print(f'  {year:>6} | {yn:>5} | {yroi:>7.1f}% | {yprofit:>+10,.0f} | {"O" if is_black else "X"}')
    print(f'  黒字年数: {black_count}/6年')


# =====================================================
# スコア差フィルターの効果（年度別）
# =====================================================
print(f'\n\n{"="*90}')
print(f' A_A1_10_12 のスコア差フィルター詳細分析')
print(f'{"="*90}')

for threshold in [10, 15, 20, 25]:
    filtered = df[df['score_gap'] >= threshold]
    fn = len(filtered)
    if fn == 0:
        continue

    fhit = filtered.loc[filtered['trifecta_hit']==1, 'trifecta_odds'].sum()
    froi = fhit / fn * 100
    fprofit = (fhit - fn) * 100

    print(f'\n--- フィルター: score_gap>={threshold} ({fn}件, ROI {froi:.1f}%, 収支 {fprofit:+,.0f}円) ---')
    print(f'  {"年度":>6} | {"件数":>5} | {"ROI":>8} | {"収支":>10} | {"判定"}')
    print('  ' + '-'*50)

    black_count = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        ydf = filtered[filtered['year'] == year]
        yn = len(ydf)
        if yn == 0:
            print(f'  {year:>6} | {0:>5} | {"N/A":>8} | {"N/A":>10} | -')
            continue
        yhit = ydf.loc[ydf['trifecta_hit']==1, 'trifecta_odds'].sum()
        yroi = yhit / yn * 100
        yprofit = (yhit - yn) * 100
        is_black = yprofit > 0
        if is_black:
            black_count += 1
        print(f'  {year:>6} | {yn:>5} | {yroi:>7.1f}% | {yprofit:>+10,.0f} | {"O" if is_black else "X"}')
    print(f'  黒字年数: {black_count}/6年')


# =====================================================
# 組み合わせフィルター: score_gap>=25 + avg_st<=0.17
# =====================================================
print(f'\n\n{"="*90}')
print(f' A_A1_10_12 組み合わせフィルター')
print(f'{"="*90}')

combos = [
    ('gap>=25', lambda d: d['score_gap'] >= 25),
    ('gap>=25 + st<=0.17', lambda d: (d['score_gap'] >= 25) & (d['p1_avg_st'].notna()) & (d['p1_avg_st'] <= 0.17)),
    ('gap>=25 + st<=0.15', lambda d: (d['score_gap'] >= 25) & (d['p1_avg_st'].notna()) & (d['p1_avg_st'] <= 0.15)),
    ('gap>=25 + st<=0.13', lambda d: (d['score_gap'] >= 25) & (d['p1_avg_st'].notna()) & (d['p1_avg_st'] <= 0.13)),
    ('gap>=15 + st<=0.17', lambda d: (d['score_gap'] >= 15) & (d['p1_avg_st'].notna()) & (d['p1_avg_st'] <= 0.17)),
    ('gap>=15 + st<=0.13', lambda d: (d['score_gap'] >= 15) & (d['p1_avg_st'].notna()) & (d['p1_avg_st'] <= 0.13)),
]

for label, filter_func in combos:
    filtered = df[filter_func(df)]
    fn = len(filtered)
    if fn == 0:
        print(f'\n--- {label}: データなし ---')
        continue

    fhit = filtered.loc[filtered['trifecta_hit']==1, 'trifecta_odds'].sum()
    froi = fhit / fn * 100
    fprofit = (fhit - fn) * 100

    print(f'\n--- {label} ({fn}件, ROI {froi:.1f}%, 収支 {fprofit:+,.0f}円) ---')
    print(f'  {"年度":>6} | {"件数":>5} | {"ROI":>8} | {"収支":>10} | {"判定"}')
    print('  ' + '-'*50)

    black_count = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        ydf = filtered[filtered['year'] == year]
        yn = len(ydf)
        if yn == 0:
            print(f'  {year:>6} | {0:>5} | {"N/A":>8} | {"N/A":>10} | -')
            continue
        yhit = ydf.loc[ydf['trifecta_hit']==1, 'trifecta_odds'].sum()
        yroi = yhit / yn * 100
        yprofit = (yhit - yn) * 100
        is_black = yprofit > 0
        if is_black:
            black_count += 1
        print(f'  {year:>6} | {yn:>5} | {yroi:>7.1f}% | {yprofit:>+10,.0f} | {"O" if is_black else "X"}')
    print(f'  黒字年数: {black_count}/6年')

conn.close()
print('\n\n詳細分析完了。')
