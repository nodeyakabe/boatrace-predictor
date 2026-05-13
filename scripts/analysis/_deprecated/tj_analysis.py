#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TJ-3/TJ-4 フィルター再検討分析スクリプト"""

import sqlite3
import sys
import os

# プロジェクトルートに移動
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

conn = sqlite3.connect('data/boatrace.db')

# ==============================================
# GLOBAL_VENUE_MONTH_EXCLUDES
# ==============================================
global_excludes = [(5, 2), (22, 2), (14, 1), (14, 2), (17, 2)]
excl_parts = []
for v, m in global_excludes:
    excl_parts.append(f"(r.venue_code = '{v:02d}' AND CAST(strftime('%m', r.race_date) AS INTEGER) = {m})")
global_excl_clause = 'AND NOT (' + ' OR '.join(excl_parts) + ')'

# ==============================================
# 条件定義
# ==============================================
conditions = [
    {
        'id': 'A_A1_10_12',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 10, 'odds_max': 12,
        'venue_filter': [10, 14, 21, 18, 8, 12],
        'predicted_course': 1,
        'escape_rate_min': 0.70,
        'use_pattern_h': False,
        'month_exclude': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
    },
    {
        'id': 'B_50_100',
        'confidence': 'B',
        'c1_rank': ['A1', 'B1'],
        'odds_min': 50, 'odds_max': 100,
        'venue_filter': [4, 7, 19, 22, 2, 17, 21, 11, 8, 1, 9],
        'predicted_course': None,
        'escape_rate_min': None,
        'use_pattern_h': True,
        'month_exclude': [12, 1, 2, 4],
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
    },
    {
        'id': 'B_30_50_B1',
        'confidence': 'B',
        'c1_rank': ['B1'],
        'odds_min': 30, 'odds_max': 50,
        'venue_filter': [9, 10, 21, 6],
        'predicted_course': None,
        'escape_rate_min': None,
        'use_pattern_h': True,
        'month_exclude': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
    },
    {
        'id': 'B_10_30_bias',
        'confidence': 'B',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 10, 'odds_max': 30,
        'venue_filter': [6, 7, 8, 10, 15, 19],
        'predicted_course': None,
        'escape_rate_min': None,
        'use_pattern_h': False,
        'month_exclude': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
        'bias_max': -0.3,
    },
    {
        'id': 'C_20_30_B1',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20, 'odds_max': 30,
        'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],
        'predicted_course': None,
        'escape_rate_min': None,
        'use_pattern_h': False,
        'month_exclude': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
    },
    {
        'id': 'C_Naruto_A2',
        'confidence': 'C',
        'c1_rank': ['A2'],
        'odds_min': 30, 'odds_max': 80,
        'venue_filter': [14],
        'predicted_course': None,
        'escape_rate_min': None,
        'use_pattern_h': True,
        'month_exclude': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
    },
    {
        'id': 'C_Karatsu_B1',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20, 'odds_max': 30,
        'venue_filter': [23],
        'predicted_course': None,
        'escape_rate_min': None,
        'use_pattern_h': False,
        'month_exclude': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
    },
    {
        'id': 'C_Kojima_B1',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 30, 'odds_max': 50,
        'venue_filter': [16],
        'predicted_course': None,
        'escape_rate_min': None,
        'use_pattern_h': True,
        'month_exclude': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
    },
    {
        'id': 'D_40_50_B1',
        'confidence': 'D',
        'c1_rank': ['B1'],
        'odds_min': 40, 'odds_max': 50,
        'venue_filter': None,
        'predicted_course': None,
        'escape_rate_min': None,
        'use_pattern_h': False,
        'month_exclude': None,
        'c1_second_rate_min': 20,
        'c1_second_rate_max': 30,
    },
    {
        'id': 'D_course5',
        'confidence': 'D',
        'c1_rank': ['A1', 'B1', 'B2'],
        'odds_min': 10, 'odds_max': 200,
        'venue_filter': [5, 6, 1, 4],
        'predicted_course': 5,
        'escape_rate_min': None,
        'use_pattern_h': True,
        'month_exclude': None,
        'c1_second_rate_min': None,
        'c1_second_rate_max': None,
    },
]


def build_query(cond, include_avg_st=False):
    """条件に基づいてクエリを構築"""
    c1_ranks_str = ','.join([f"'{r}'" for r in cond['c1_rank']])

    conf_clause = f"AND rp.confidence = '{cond['confidence']}'" if cond.get('confidence') else ''

    venue_clause = ''
    if cond.get('venue_filter'):
        vcs = ','.join([f"'{v:02d}'" for v in cond['venue_filter']])
        venue_clause = f'AND r.venue_code IN ({vcs})'

    month_clause = ''
    if cond.get('month_exclude'):
        ms = ','.join(map(str, cond['month_exclude']))
        month_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({ms})"

    pred_course_clause = ''
    if cond.get('predicted_course'):
        pred_course_clause = f'AND rp1.pit_number = {cond["predicted_course"]}'

    c1_sr_clause = ''
    if cond.get('c1_second_rate_min') is not None:
        c1_sr_clause += f'AND e1.second_rate >= {cond["c1_second_rate_min"]} '
    if cond.get('c1_second_rate_max') is not None:
        c1_sr_clause += f'AND e1.second_rate < {cond["c1_second_rate_max"]} '

    # 逃げ率
    escape_join = ''
    escape_clause = ''
    if cond.get('escape_rate_min') is not None:
        escape_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN (
            SELECT player_id, escape_rate
            FROM player_escape_stats
            WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
            AND id IN (SELECT MAX(id) FROM player_escape_stats WHERE stadium_id IS NULL AND escape_rate IS NOT NULL GROUP BY player_id)
        ) pes ON e_pred.racer_number = pes.player_id
        """
        escape_clause = f'AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= {cond["escape_rate_min"]}'

    # バイアス
    bias_join = ''
    bias_clause = ''
    if cond.get('bias_max') is not None:
        bias_join = """
        LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
        LEFT JOIN (
            SELECT player_id, bias_index
            FROM player_bias_stats
            WHERE stadium_id IS NULL AND bias_index IS NOT NULL
            AND id IN (SELECT MAX(id) FROM player_bias_stats WHERE stadium_id IS NULL AND bias_index IS NOT NULL GROUP BY player_id)
        ) pbs ON e_bias.racer_number = pbs.player_id
        """
        bias_clause = f'AND pbs.bias_index IS NOT NULL AND pbs.bias_index < {cond["bias_max"]}'

    # avg_st JOIN（分析用）
    avg_st_join = ''
    avg_st_select = ''
    if include_avg_st:
        avg_st_join = """
        LEFT JOIN entries e_avgst ON r.id = e_avgst.race_id AND e_avgst.pit_number = rp1.pit_number
        """
        avg_st_select = ', e_avgst.avg_st as p1_avg_st'

    # パターンHの場合のJOIN
    if cond.get('use_pattern_h'):
        extra_joins = """
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        """
    else:
        extra_joins = ''

    query = f"""
    SELECT
        rp1.total_score - rp2.total_score as score_gap,
        rp1.pit_number as p1_pit,
        rp2.pit_number as p2_pit,
        rp3.pit_number as p3_pit,
        CASE WHEN res1.pit_number IS NOT NULL AND res1.pit_number = rp1.pit_number THEN 1 ELSE 0 END as p1_hit,
        CASE WHEN res1.pit_number = rp1.pit_number
             AND res2.pit_number = rp2.pit_number
             AND res3.pit_number = rp3.pit_number THEN 1 ELSE 0 END as trifecta_hit,
        t.odds as trifecta_odds,
        r.id as race_id,
        r.race_date,
        r.venue_code,
        strftime('%Y', r.race_date) as year
        {avg_st_select}
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
    {global_excl_clause}
    AND t.odds IS NOT NULL
    AND t.odds >= {cond['odds_min']} AND t.odds < {cond['odds_max']}
    """

    return query


def analyze_score_gap(df, cond_id):
    """スコア差帯の分析"""
    if len(df) == 0:
        print(f'\n--- {cond_id}: データなし ---')
        return

    print(f'\n{"="*90}')
    print(f'条件: {cond_id}  (全体 {len(df)}件)')

    # 全体ROI
    total_hit = df.loc[df['trifecta_hit']==1, 'trifecta_odds'].sum()
    total_roi = total_hit / len(df) * 100
    total_profit = (total_hit - len(df)) * 100
    print(f'全体ROI: {total_roi:.1f}%, 収支: {total_profit:+,.0f}円')
    print(f'{"="*90}')

    # スコア差帯の分析
    bins = [(-999, 10), (10, 15), (15, 20), (20, 25), (25, 999)]
    labels = ['<10', '10-15', '15-20', '20-25', '>=25']

    header = f'{"スコア差帯":>10} | {"件数":>6} | {"1位的中率":>8} | {"三連単的中率":>10} | {"平均odds":>8} | {"ROI":>8} | {"収支":>12}'
    print(header)
    print('-'*90)

    for (lo, hi), label in zip(bins, labels):
        subset = df[(df['score_gap'] >= lo) & (df['score_gap'] < hi)]
        n = len(subset)
        if n == 0:
            continue
        p1_rate = subset['p1_hit'].mean() * 100
        tri_hits = subset['trifecta_hit'].sum()
        tri_rate = tri_hits / n * 100
        avg_odds = subset['trifecta_odds'].mean()
        hit_odds_sum = subset.loc[subset['trifecta_hit']==1, 'trifecta_odds'].sum()
        roi = hit_odds_sum / n * 100 if n > 0 else 0
        profit = (hit_odds_sum - n) * 100
        print(f'{label:>10} | {n:>6} | {p1_rate:>7.1f}% | {tri_rate:>9.1f}% | {avg_odds:>8.1f} | {roi:>7.1f}% | {profit:>+12,.0f}')

    # フィルター閾値ごとの累積効果
    print(f'\n  フィルター閾値ごとの効果（score_gap >= X のレースのみ残す）:')
    header2 = f'  {"閾値":>8} | {"残件数":>6} | {"除去数":>6} | {"残ROI":>8} | {"除去ROI":>8} | {"残収支":>12} | {"除去収支":>12}'
    print(header2)
    print('  ' + '-'*85)

    results = {}
    for threshold in [10, 15, 20, 25]:
        remain = df[df['score_gap'] >= threshold]
        removed = df[df['score_gap'] < threshold]
        n_r = len(remain)
        n_rm = len(removed)

        if n_r > 0:
            hit_r = remain.loc[remain['trifecta_hit']==1, 'trifecta_odds'].sum()
            roi_r = hit_r / n_r * 100
            profit_r = (hit_r - n_r) * 100
        else:
            roi_r = 0
            profit_r = 0

        if n_rm > 0:
            hit_rm = removed.loc[removed['trifecta_hit']==1, 'trifecta_odds'].sum()
            roi_rm = hit_rm / n_rm * 100
            profit_rm = (hit_rm - n_rm) * 100
        else:
            roi_rm = 0
            profit_rm = 0

        roi_diff = roi_r - total_roi
        marker = ' ***' if roi_r > total_roi and n_r >= 50 and profit_r > total_profit else ''
        print(f'  >={threshold:>5} | {n_r:>6} | {n_rm:>6} | {roi_r:>7.1f}% | {roi_rm:>7.1f}% | {profit_r:>+12,.0f} | {profit_rm:>+12,.0f}{marker}')
        results[threshold] = {'n_remain': n_r, 'roi_remain': roi_r, 'profit_remain': profit_r, 'roi_removed': roi_rm}

    return results


def analyze_avg_st(df, cond_id):
    """avg_st帯の分析"""
    if len(df) == 0 or 'p1_avg_st' not in df.columns:
        print(f'\n--- {cond_id}: avg_stデータなし ---')
        return

    df_valid = df[df['p1_avg_st'].notna()].copy()
    if len(df_valid) == 0:
        print(f'\n--- {cond_id}: avg_st有効データなし ---')
        return

    print(f'\n{"="*90}')
    print(f'条件: {cond_id}  (avg_st有効 {len(df_valid)}件 / 全体 {len(df)}件)')

    # 全体ROI
    total_hit = df_valid.loc[df_valid['trifecta_hit']==1, 'trifecta_odds'].sum()
    total_roi = total_hit / len(df_valid) * 100
    total_profit = (total_hit - len(df_valid)) * 100
    print(f'全体ROI: {total_roi:.1f}%, 収支: {total_profit:+,.0f}円')
    print(f'{"="*90}')

    # avg_st帯の分析
    bins = [(-1, 0.13), (0.13, 0.15), (0.15, 0.17), (0.17, 0.20), (0.20, 9.99)]
    labels = ['<0.13', '0.13-0.15', '0.15-0.17', '0.17-0.20', '>=0.20']

    header = f'{"avg_st帯":>12} | {"件数":>6} | {"1位的中率":>8} | {"三連単的中率":>10} | {"平均odds":>8} | {"ROI":>8} | {"収支":>12}'
    print(header)
    print('-'*90)

    for (lo, hi), label in zip(bins, labels):
        subset = df_valid[(df_valid['p1_avg_st'] >= lo) & (df_valid['p1_avg_st'] < hi)]
        n = len(subset)
        if n == 0:
            continue
        p1_rate = subset['p1_hit'].mean() * 100
        tri_hits = subset['trifecta_hit'].sum()
        tri_rate = tri_hits / n * 100
        avg_odds = subset['trifecta_odds'].mean()
        hit_odds_sum = subset.loc[subset['trifecta_hit']==1, 'trifecta_odds'].sum()
        roi = hit_odds_sum / n * 100 if n > 0 else 0
        profit = (hit_odds_sum - n) * 100
        print(f'{label:>12} | {n:>6} | {p1_rate:>7.1f}% | {tri_rate:>9.1f}% | {avg_odds:>8.1f} | {roi:>7.1f}% | {profit:>+12,.0f}')

    # フィルター閾値ごとの累積効果
    print(f'\n  avg_st上限フィルターの効果（avg_st <= X のレースのみ残す）:')
    header2 = f'  {"上限値":>8} | {"残件数":>6} | {"除去数":>6} | {"残ROI":>8} | {"除去ROI":>8} | {"残収支":>12} | {"除去収支":>12}'
    print(header2)
    print('  ' + '-'*85)

    for threshold in [0.13, 0.15, 0.17, 0.20]:
        remain = df_valid[df_valid['p1_avg_st'] <= threshold]
        removed = df_valid[df_valid['p1_avg_st'] > threshold]
        n_r = len(remain)
        n_rm = len(removed)

        if n_r > 0:
            hit_r = remain.loc[remain['trifecta_hit']==1, 'trifecta_odds'].sum()
            roi_r = hit_r / n_r * 100
            profit_r = (hit_r - n_r) * 100
        else:
            roi_r = 0
            profit_r = 0

        if n_rm > 0:
            hit_rm = removed.loc[removed['trifecta_hit']==1, 'trifecta_odds'].sum()
            roi_rm = hit_rm / n_rm * 100
            profit_rm = (hit_rm - n_rm) * 100
        else:
            roi_rm = 0
            profit_rm = 0

        marker = ' ***' if roi_r > total_roi and n_r >= 50 and profit_r > total_profit else ''
        print(f'  <={threshold:.2f} | {n_r:>6} | {n_rm:>6} | {roi_r:>7.1f}% | {roi_rm:>7.1f}% | {profit_r:>+12,.0f} | {profit_rm:>+12,.0f}{marker}')

    # 逆方向: avg_st >= X で買う
    print(f'\n  逆方向: avg_st下限フィルターの効果（avg_st >= X のレースのみ残す）:')
    for threshold in [0.17, 0.18, 0.20]:
        remain = df_valid[df_valid['p1_avg_st'] >= threshold]
        n_r = len(remain)
        if n_r > 0:
            hit_r = remain.loc[remain['trifecta_hit']==1, 'trifecta_odds'].sum()
            roi_r = hit_r / n_r * 100
            profit_r = (hit_r - n_r) * 100
            print(f'  >={threshold:.2f}: {n_r}件, ROI {roi_r:.1f}%, 収支 {profit_r:+,.0f}円')


def analyze_combined(df, cond_id):
    """スコア差 + avg_st 組み合わせ分析"""
    if len(df) == 0 or 'p1_avg_st' not in df.columns:
        return

    df_valid = df[df['p1_avg_st'].notna()].copy()
    if len(df_valid) < 20:
        return

    print(f'\n{"="*90}')
    print(f'条件: {cond_id} 組み合わせフィルター（avg_st有効 {len(df_valid)}件）')
    print(f'{"="*90}')

    combos = [
        ('gap>=15 AND st<=0.17', lambda d: (d['score_gap'] >= 15) & (d['p1_avg_st'] <= 0.17)),
        ('gap>=20 AND st<=0.17', lambda d: (d['score_gap'] >= 20) & (d['p1_avg_st'] <= 0.17)),
        ('gap>=15 AND st<=0.15', lambda d: (d['score_gap'] >= 15) & (d['p1_avg_st'] <= 0.15)),
        ('gap>=20 AND st<=0.15', lambda d: (d['score_gap'] >= 20) & (d['p1_avg_st'] <= 0.15)),
        ('gap>=10 AND st<=0.17', lambda d: (d['score_gap'] >= 10) & (d['p1_avg_st'] <= 0.17)),
        ('gap>=10 AND st<=0.20', lambda d: (d['score_gap'] >= 10) & (d['p1_avg_st'] <= 0.20)),
        ('gap>=15 AND st<=0.20', lambda d: (d['score_gap'] >= 15) & (d['p1_avg_st'] <= 0.20)),
        ('gap>=20 AND st<=0.20', lambda d: (d['score_gap'] >= 20) & (d['p1_avg_st'] <= 0.20)),
    ]

    # 全体ROI
    total_hit = df_valid.loc[df_valid['trifecta_hit']==1, 'trifecta_odds'].sum()
    total_roi = total_hit / len(df_valid) * 100

    header = f'  {"組み合わせ":>25} | {"件数":>6} | {"ROI":>8} | {"収支":>12} | {"判定"}'
    print(header)
    print('  ' + '-'*75)

    for label, filter_func in combos:
        mask = filter_func(df_valid)
        subset = df_valid[mask]
        n = len(subset)
        if n == 0:
            continue
        hit_sum = subset.loc[subset['trifecta_hit']==1, 'trifecta_odds'].sum()
        roi = hit_sum / n * 100
        profit = (hit_sum - n) * 100

        if n >= 50 and roi > total_roi:
            judge = 'OK(50件+)'
        elif n >= 30 and roi > total_roi:
            judge = '要注意(30-49件)'
        elif n < 30:
            judge = f'NG(少数{n}件)'
        else:
            judge = 'ROI悪化'

        print(f'  {label:>25} | {n:>6} | {roi:>7.1f}% | {profit:>+12,.0f} | {judge}')


# ==============================================
# メイン実行
# ==============================================
if __name__ == '__main__':
    import pandas as pd

    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'

    if mode in ['all', 'score_gap']:
        print('='*120)
        print(' 分析1: TJ-4（スコア差）条件別分析')
        print('='*120)

        for cond in conditions:
            query = build_query(cond, include_avg_st=False)
            df = pd.read_sql_query(query, conn)
            analyze_score_gap(df, cond['id'])

    if mode in ['all', 'avg_st']:
        print('\n\n')
        print('='*120)
        print(' 分析2: TJ-3（avg_st）条件別分析')
        print('='*120)

        for cond in conditions:
            query = build_query(cond, include_avg_st=True)
            df = pd.read_sql_query(query, conn)
            analyze_avg_st(df, cond['id'])

    if mode in ['all', 'combined']:
        print('\n\n')
        print('='*120)
        print(' 分析3: スコア差 + avg_st 組み合わせフィルター分析')
        print('='*120)

        for cond in conditions:
            query = build_query(cond, include_avg_st=True)
            df = pd.read_sql_query(query, conn)
            analyze_combined(df, cond['id'])

    conn.close()
    print('\n\n分析完了。')
