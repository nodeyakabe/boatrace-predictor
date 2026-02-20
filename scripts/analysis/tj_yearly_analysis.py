#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TJ-3/TJ-4 有望候補の年度別安定性分析"""

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
# 有望候補のリスト（分析1-3から選出）
# =====================================================
# 分析で効果が確認できた条件 x フィルター組み合わせ
candidates = [
    # --- TJ-4 (スコア差) 有望案 ---
    {
        'label': 'C_20_30_B1 + score_gap>=15',
        'desc': 'C x 20-30 x B1 + スコア差15以上',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20, 'odds_max': 30,
        'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],
        'use_pattern_h': False,
        'month_exclude': None,
        'predicted_course': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': 15,
        'p1_avg_st_max': None,
    },
    {
        'label': 'C_Kojima_B1 + score_gap>=25',
        'desc': '児島 x C x B1 x 30-50 + スコア差25以上',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 30, 'odds_max': 50,
        'venue_filter': [16],
        'use_pattern_h': True,
        'month_exclude': None,
        'predicted_course': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': 25,
        'p1_avg_st_max': None,
    },
    {
        'label': 'D_40_50_B1 + score_gap>=10',
        'desc': 'D x 40-50 x B1 x 2連率20-30% + スコア差10以上',
        'confidence': 'D',
        'c1_rank': ['B1'],
        'odds_min': 40, 'odds_max': 50,
        'venue_filter': None,
        'use_pattern_h': False,
        'month_exclude': None,
        'predicted_course': None,
        'c1_second_rate_min': 20,
        'c1_second_rate_max': 30,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': 10,
        'p1_avg_st_max': None,
    },

    # --- TJ-3 (avg_st) 有望案 ---
    {
        'label': 'A_A1_10_12 + avg_st<=0.13',
        'desc': 'A x A1 x 10-12 + avg_st<=0.13',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 10, 'odds_max': 12,
        'venue_filter': [10, 14, 21, 18, 8, 12],
        'use_pattern_h': False,
        'month_exclude': None,
        'predicted_course': 1,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': 0.70,
        'bias_max': None,
        'min_score_gap': None,
        'p1_avg_st_max': 0.13,
    },
    {
        'label': 'C_Naruto_A2 + avg_st<=0.17',
        'desc': '鳴門 x C x A2 x 30-80 + avg_st<=0.17',
        'confidence': 'C',
        'c1_rank': ['A2'],
        'odds_min': 30, 'odds_max': 80,
        'venue_filter': [14],
        'use_pattern_h': True,
        'month_exclude': None,
        'predicted_course': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': None,
        'p1_avg_st_max': 0.17,
    },
    {
        'label': 'C_Karatsu_B1 + avg_st<=0.17',
        'desc': '唐津 x C x B1 x 20-30 + avg_st<=0.17',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20, 'odds_max': 30,
        'venue_filter': [23],
        'use_pattern_h': False,
        'month_exclude': None,
        'predicted_course': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': None,
        'p1_avg_st_max': 0.17,
    },
    {
        'label': 'C_Kojima_B1 + avg_st<=0.20',
        'desc': '児島 x C x B1 x 30-50 + avg_st<=0.20',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 30, 'odds_max': 50,
        'venue_filter': [16],
        'use_pattern_h': True,
        'month_exclude': None,
        'predicted_course': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': None,
        'p1_avg_st_max': 0.20,
    },
    {
        'label': 'D_course5 + avg_st<=0.15',
        'desc': 'D x 5コース x A2除外 + avg_st<=0.15',
        'confidence': 'D',
        'c1_rank': ['A1', 'B1', 'B2'],
        'odds_min': 10, 'odds_max': 200,
        'venue_filter': [5, 6, 1, 4],
        'use_pattern_h': True,
        'month_exclude': None,
        'predicted_course': 5,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': None,
        'p1_avg_st_max': 0.15,
    },

    # --- 組み合わせ有望案 ---
    {
        'label': 'C_20_30_B1 + gap>=15 + st<=0.20',
        'desc': 'C x 20-30 x B1 + スコア差15 + avg_st<=0.20',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20, 'odds_max': 30,
        'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],
        'use_pattern_h': False,
        'month_exclude': None,
        'predicted_course': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': 15,
        'p1_avg_st_max': 0.20,
    },
    {
        'label': 'C_20_30_B1 + gap>=20 + st<=0.20',
        'desc': 'C x 20-30 x B1 + スコア差20 + avg_st<=0.20',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20, 'odds_max': 30,
        'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],
        'use_pattern_h': False,
        'month_exclude': None,
        'predicted_course': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': None,
        'bias_max': None,
        'min_score_gap': 20,
        'p1_avg_st_max': 0.20,
    },
    {
        'label': 'A_A1_10_12 + gap>=15 + st<=0.17',
        'desc': 'A x A1 x 10-12 + スコア差15 + avg_st<=0.17',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 10, 'odds_max': 12,
        'venue_filter': [10, 14, 21, 18, 8, 12],
        'use_pattern_h': False,
        'month_exclude': None,
        'predicted_course': 1,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'escape_rate_min': 0.70,
        'bias_max': None,
        'min_score_gap': 15,
        'p1_avg_st_max': 0.17,
    },
]

for cand in candidates:
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
    if cand.get('bias_max') is not None:
        bias_join = """
        LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
        LEFT JOIN (
            SELECT player_id, bias_index
            FROM player_bias_stats
            WHERE stadium_id IS NULL AND bias_index IS NOT NULL
            AND id IN (SELECT MAX(id) FROM player_bias_stats WHERE stadium_id IS NULL AND bias_index IS NOT NULL GROUP BY player_id)
        ) pbs ON e_bias.racer_number = pbs.player_id
        """
        bias_clause = f'AND pbs.bias_index IS NOT NULL AND pbs.bias_index < {cand["bias_max"]}'

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

    df = pd.read_sql_query(query, conn)

    if len(df) == 0:
        print(f'\n{cand["label"]}: データなし')
        continue

    print(f'\n{"="*90}')
    print(f'{cand["label"]}')
    print(f'{cand["desc"]}')
    print(f'{"="*90}')

    # 全体
    total_n = len(df)
    total_hit_sum = df.loc[df['trifecta_hit']==1, 'trifecta_odds'].sum()
    total_roi = total_hit_sum / total_n * 100 if total_n > 0 else 0
    total_profit = (total_hit_sum - total_n) * 100
    print(f'全体: {total_n}件, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円')

    # 年度別
    print(f'\n  {"年度":>6} | {"件数":>5} | {"的中":>4} | {"ROI":>8} | {"収支":>12} | {"判定"}')
    print('  ' + '-'*60)

    black_years = 0
    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        ydf = df[df['year'] == year]
        n = len(ydf)
        if n == 0:
            print(f'  {year:>6} | {0:>5} | {0:>4} | {"N/A":>8} | {"N/A":>12} | -')
            continue
        hits = ydf['trifecta_hit'].sum()
        hit_sum = ydf.loc[ydf['trifecta_hit']==1, 'trifecta_odds'].sum()
        roi = hit_sum / n * 100
        profit = (hit_sum - n) * 100
        is_black = profit > 0
        if is_black:
            black_years += 1
        judge = 'O' if is_black else 'X'
        print(f'  {year:>6} | {n:>5} | {hits:>4} | {roi:>7.1f}% | {profit:>+12,.0f} | {judge}')

    print(f'\n  黒字年数: {black_years}/6年')

    # 判定
    if total_n >= 50 and total_roi > 100 and black_years >= 4:
        print(f'  >>> 有望: Tier 2テスト候補 <<<')
    elif total_n >= 50 and total_roi > 100 and black_years >= 3:
        print(f'  >>> 要検討: 黒字年数が足りない（{black_years}/6年） <<<')
    elif total_n < 50:
        print(f'  >>> サンプル不足: {total_n}件 <<<')
    else:
        print(f'  >>> 不採用: ROI {total_roi:.1f}%, 黒字{black_years}/6年 <<<')

conn.close()
print('\n\n年度別分析完了。')
