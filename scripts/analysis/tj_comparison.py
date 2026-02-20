#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TJ フィルター適用前後の比較分析 - 件数・ROI・収支の変化"""

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


def run_query(cand):
    c1_ranks_str = ','.join([f"'{r}'" for r in cand['c1_rank']])
    conf_clause = f"AND rp.confidence = '{cand['confidence']}'" if cand.get('confidence') else ''

    venue_clause = ''
    if cand.get('venue_filter'):
        vcs = ','.join([f"'{v:02d}'" for v in cand['venue_filter']])
        venue_clause = f'AND r.venue_code IN ({vcs})'

    month_clause = ''
    if cand.get('month_exclude'):
        ms = ','.join(map(str, cand['month_exclude']))
        month_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({ms})"

    pred_course_clause = ''
    if cand.get('predicted_course'):
        pred_course_clause = f'AND rp1.pit_number = {cand["predicted_course"]}'

    c1_sr_clause = ''
    if cand.get('c1_second_rate_min') is not None:
        c1_sr_clause += f'AND e1.second_rate >= {cand["c1_second_rate_min"]} '
    if cand.get('c1_second_rate_max') is not None:
        c1_sr_clause += f'AND e1.second_rate < {cand["c1_second_rate_max"]} '

    escape_join = ''
    escape_clause = ''
    if cand.get('escape_rate_min') is not None:
        escape_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN (
            SELECT player_id, escape_rate
            FROM player_escape_stats
            WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
            AND id IN (SELECT MAX(id) FROM player_escape_stats WHERE stadium_id IS NULL AND escape_rate IS NOT NULL GROUP BY player_id)
        ) pes ON e_pred.racer_number = pes.player_id
        """
        escape_clause = f'AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= {cand["escape_rate_min"]}'

    bias_join = ''
    bias_clause = ''

    score_gap_clause = ''
    if cand.get('min_score_gap') is not None:
        score_gap_clause = f'AND (rp1.total_score - rp2.total_score) >= {cand["min_score_gap"]}'

    avg_st_join = ''
    avg_st_clause = ''
    if cand.get('p1_avg_st_max') is not None:
        avg_st_join = """
        LEFT JOIN entries e_avgst ON r.id = e_avgst.race_id AND e_avgst.pit_number = rp1.pit_number
        """
        avg_st_clause = f'AND e_avgst.avg_st IS NOT NULL AND e_avgst.avg_st <= {cand["p1_avg_st_max"]}'

    if cand.get('use_pattern_h'):
        extra_joins = """
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        """
    else:
        extra_joins = ''

    query = f"""
    SELECT
        strftime('%Y', r.race_date) as year,
        CASE WHEN res1.pit_number = rp1.pit_number
             AND res2.pit_number = rp2.pit_number
             AND res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END as trifecta_hit,
        t.odds as trifecta_odds
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    {extra_joins}
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    {escape_join}
    {bias_join}
    {avg_st_join}
    LEFT JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
    LEFT JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
    LEFT JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    {conf_clause}
    AND e1.racer_rank IN ({c1_ranks_str})
    {venue_clause}
    {month_clause}
    {pred_course_clause}
    {c1_sr_clause}
    {escape_clause}
    {bias_clause}
    {score_gap_clause}
    {avg_st_clause}
    {global_excl_clause}
    AND t.odds IS NOT NULL
    AND t.odds >= {cand['odds_min']} AND t.odds < {cand['odds_max']}
    """

    return pd.read_sql_query(query, conn)


# =====================================================
# Tier 2候補に上がった4条件の前後比較
# =====================================================
comparisons = [
    # 1. A_A1_10_12 + avg_st<=0.13
    {
        'condition_name': 'A_A1_10_12',
        'filter_name': 'avg_st<=0.13',
        'base': {
            'confidence': 'A', 'c1_rank': ['A1'],
            'odds_min': 10, 'odds_max': 12,
            'venue_filter': [10, 14, 21, 18, 8, 12],
            'use_pattern_h': False, 'month_exclude': None,
            'predicted_course': 1, 'escape_rate_min': 0.70,
            'c1_second_rate_min': None, 'c1_second_rate_max': None,
            'min_score_gap': None, 'p1_avg_st_max': None,
        },
        'filtered': {
            'confidence': 'A', 'c1_rank': ['A1'],
            'odds_min': 10, 'odds_max': 12,
            'venue_filter': [10, 14, 21, 18, 8, 12],
            'use_pattern_h': False, 'month_exclude': None,
            'predicted_course': 1, 'escape_rate_min': 0.70,
            'c1_second_rate_min': None, 'c1_second_rate_max': None,
            'min_score_gap': None, 'p1_avg_st_max': 0.13,
        },
    },
    # 2. C_Naruto_A2 + avg_st<=0.17
    {
        'condition_name': 'C_Naruto_A2',
        'filter_name': 'avg_st<=0.17',
        'base': {
            'confidence': 'C', 'c1_rank': ['A2'],
            'odds_min': 30, 'odds_max': 80,
            'venue_filter': [14],
            'use_pattern_h': True, 'month_exclude': None,
            'predicted_course': None, 'escape_rate_min': None,
            'c1_second_rate_min': None, 'c1_second_rate_max': None,
            'min_score_gap': None, 'p1_avg_st_max': None,
        },
        'filtered': {
            'confidence': 'C', 'c1_rank': ['A2'],
            'odds_min': 30, 'odds_max': 80,
            'venue_filter': [14],
            'use_pattern_h': True, 'month_exclude': None,
            'predicted_course': None, 'escape_rate_min': None,
            'c1_second_rate_min': None, 'c1_second_rate_max': None,
            'min_score_gap': None, 'p1_avg_st_max': 0.17,
        },
    },
    # 3. C_Karatsu_B1 + avg_st<=0.17
    {
        'condition_name': 'C_Karatsu_B1',
        'filter_name': 'avg_st<=0.17',
        'base': {
            'confidence': 'C', 'c1_rank': ['B1'],
            'odds_min': 20, 'odds_max': 30,
            'venue_filter': [23],
            'use_pattern_h': False, 'month_exclude': None,
            'predicted_course': None, 'escape_rate_min': None,
            'c1_second_rate_min': None, 'c1_second_rate_max': None,
            'min_score_gap': None, 'p1_avg_st_max': None,
        },
        'filtered': {
            'confidence': 'C', 'c1_rank': ['B1'],
            'odds_min': 20, 'odds_max': 30,
            'venue_filter': [23],
            'use_pattern_h': False, 'month_exclude': None,
            'predicted_course': None, 'escape_rate_min': None,
            'c1_second_rate_min': None, 'c1_second_rate_max': None,
            'min_score_gap': None, 'p1_avg_st_max': 0.17,
        },
    },
    # 4. A_A1_10_12 + gap>=15 + st<=0.17 (組み合わせ)
    {
        'condition_name': 'A_A1_10_12',
        'filter_name': 'gap>=15 + avg_st<=0.17',
        'base': {
            'confidence': 'A', 'c1_rank': ['A1'],
            'odds_min': 10, 'odds_max': 12,
            'venue_filter': [10, 14, 21, 18, 8, 12],
            'use_pattern_h': False, 'month_exclude': None,
            'predicted_course': 1, 'escape_rate_min': 0.70,
            'c1_second_rate_min': None, 'c1_second_rate_max': None,
            'min_score_gap': None, 'p1_avg_st_max': None,
        },
        'filtered': {
            'confidence': 'A', 'c1_rank': ['A1'],
            'odds_min': 10, 'odds_max': 12,
            'venue_filter': [10, 14, 21, 18, 8, 12],
            'use_pattern_h': False, 'month_exclude': None,
            'predicted_course': 1, 'escape_rate_min': 0.70,
            'c1_second_rate_min': None, 'c1_second_rate_max': None,
            'min_score_gap': 15, 'p1_avg_st_max': 0.17,
        },
    },
]

print('='*100)
print(' 有望候補の前後比較（フィルター適用前 vs 適用後）')
print('='*100)

for comp in comparisons:
    df_base = run_query(comp['base'])
    df_filt = run_query(comp['filtered'])

    print(f'\n{"="*90}')
    print(f'{comp["condition_name"]} + {comp["filter_name"]}')
    print(f'{"="*90}')

    def calc_yearly(df):
        results = {}
        for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
            ydf = df[df['year'] == year]
            n = len(ydf)
            if n == 0:
                results[year] = {'n': 0, 'roi': 0, 'profit': 0, 'black': False}
                continue
            hit_sum = ydf.loc[ydf['trifecta_hit']==1, 'trifecta_odds'].sum()
            roi = hit_sum / n * 100
            profit = (hit_sum - n) * 100
            results[year] = {'n': n, 'roi': roi, 'profit': profit, 'black': profit > 0}
        return results

    base_yearly = calc_yearly(df_base)
    filt_yearly = calc_yearly(df_filt)

    # 全体
    n_base = len(df_base)
    n_filt = len(df_filt)
    hit_base = df_base.loc[df_base['trifecta_hit']==1, 'trifecta_odds'].sum()
    hit_filt = df_filt.loc[df_filt['trifecta_hit']==1, 'trifecta_odds'].sum()
    roi_base = hit_base / n_base * 100 if n_base else 0
    roi_filt = hit_filt / n_filt * 100 if n_filt else 0
    profit_base = (hit_base - n_base) * 100
    profit_filt = (hit_filt - n_filt) * 100
    black_base = sum(1 for y in base_yearly.values() if y['black'])
    black_filt = sum(1 for y in filt_yearly.values() if y['black'])

    print(f'\n  {"":>12} | {"適用前":>12} | {"適用後":>12} | {"変化":>12}')
    print('  ' + '-'*55)
    print(f'  {"件数":>12} | {n_base:>12,} | {n_filt:>12,} | {n_filt - n_base:>+12,}')
    print(f'  {"ROI":>12} | {roi_base:>11.1f}% | {roi_filt:>11.1f}% | {roi_filt - roi_base:>+11.1f}pt')
    print(f'  {"収支":>12} | {profit_base:>+12,.0f} | {profit_filt:>+12,.0f} | {profit_filt - profit_base:>+12,.0f}')
    print(f'  {"黒字年数":>12} | {black_base:>10}/6年 | {black_filt:>10}/6年 | {black_filt - black_base:>+12}')

    print(f'\n  年度別比較:')
    print(f'  {"年度":>6} | {"件数(前)":>8} {"件数(後)":>8} | {"ROI(前)":>8} {"ROI(後)":>8} | {"収支(前)":>10} {"収支(後)":>10} | {"判定変化"}')
    print('  ' + '-'*90)
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        b = base_yearly[year]
        f = filt_yearly[year]
        j_b = 'O' if b['black'] else 'X'
        j_f = 'O' if f['black'] else 'X'
        change = ''
        if j_b != j_f:
            change = f'{j_b}->{j_f}'
        else:
            change = j_f
        print(f'  {year:>6} | {b["n"]:>8} {f["n"]:>8} | {b["roi"]:>7.1f}% {f["roi"]:>7.1f}% | {b["profit"]:>+10,.0f} {f["profit"]:>+10,.0f} | {change}')

    # 除去されたレースの年度別分析
    # 差分（除去レース = base にあって filtered にない）
    n_removed = n_base - n_filt
    profit_removed = profit_base - profit_filt
    roi_removed = ((hit_base - hit_filt) / n_removed * 100) if n_removed > 0 else 0
    print(f'\n  除去レース: {n_removed}件, ROI {roi_removed:.1f}%, 収支 {profit_removed:+,.0f}円')

    # 最終判定
    is_improvement = (
        roi_filt > roi_base and
        profit_filt > profit_base and
        black_filt >= black_base and
        n_filt >= 50
    )
    is_partial = (
        (roi_filt > roi_base or profit_filt > profit_base) and
        black_filt >= black_base and
        n_filt >= 50
    )

    if is_improvement:
        print(f'\n  >>> PASS: 全面改善。Tier 2テスト推奨。<<<')
    elif is_partial:
        if profit_filt < profit_base:
            print(f'\n  >>> 部分改善: ROI向上だが収支減少。収支減{profit_filt - profit_base:+,.0f}円は許容範囲か要検討。<<<')
        else:
            print(f'\n  >>> 部分改善: 一部指標が改善。詳細検討推奨。<<<')
    else:
        print(f'\n  >>> FAIL: フィルター追加による改善効果なし、または件数不足。<<<')

conn.close()
print('\n\n比較分析完了。')
