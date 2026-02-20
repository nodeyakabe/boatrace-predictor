#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
現行10条件の詳細分析スクリプト

目的:
    各条件の月別・年度別・会場別・オッズ帯別パフォーマンスを詳細分析し、
    改善ポイントを発見する

出力:
    docs/analysis/CURRENT_CONDITIONS_DETAILED_ANALYSIS_20260212.md
"""
import sqlite3
import sys
import io
import os
from datetime import datetime
from typing import Dict, List, Any, Tuple

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 現行10条件（standard_backtest.pyから転記）
CONDITIONS = [
    {
        'name': 'A×A1×10-12+会場+逃げ率',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 10,
        'odds_max': 12,
        'venue_filter': [10, 14, 21, 18, 8, 19, 12],
        'escape_rate_min': 0.70,
        'predicted_course': 1,
        'description': 'A×A1級×10-12倍+会場+逃げ率70%+（2026-01-09改善）',
        'use_pattern_h': False,
    },
    {
        'name': 'B×50-100×冬+4月除外',
        'confidence': 'B',
        'c1_rank': ['A1', 'B1'],
        'odds_min': 50,
        'odds_max': 100,
        'venue_filter': None,
        'month_exclude': [12, 1, 2, 4],
        'description': 'B×50-100倍×冬+4月除外（ROI 183.6%）',
        'use_pattern_h': True,
    },
    {
        'name': 'B×30-50×B1+4会場',
        'confidence': 'B',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        'venue_filter': [9, 10, 21, 6],
        'description': 'B×30-50倍×B1級×4会場（ROI 196.7%）',
        'use_pattern_h': True,
    },
    {
        'name': 'B×10-30×穴源×会場',
        'confidence': 'B',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 10,
        'odds_max': 30,
        'venue_filter': [6, 7, 8, 10, 15, 19],
        'bias_max': -0.3,
        'description': 'B×10-30倍×穴源(bias<-0.3)×会場',
        'use_pattern_h': False,
    },
    {
        'name': 'C×20-30×B1+会場',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],
        'description': 'C×20-30倍×B1級（会場フィルター・唐津除外）',
        'use_pattern_h': False,
    },
    {
        'name': '鳴門×C×A2×30-80',
        'confidence': 'C',
        'c1_rank': ['A2'],
        'odds_min': 30,
        'odds_max': 80,
        'venue_filter': [14],
        'description': '鳴門×C×A2級×30-80倍（直近4年連続黒字）',
        'use_pattern_h': True,
    },
    {
        'name': '唐津×C×B1×20-30',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23],
        'description': '唐津×C×B1級×20-30倍（直近4年連続黒字）',
        'use_pattern_h': False,
    },
    {
        'name': '児島×C×B1×30-50',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        'venue_filter': [16],
        'description': '児島×C×B1級×30-50倍（直近3年連続黒字）',
        'use_pattern_h': True,
    },
    {
        'name': 'D×40-50×B1×2連率20-30%',
        'confidence': 'D',
        'c1_rank': ['B1'],
        'odds_min': 40,
        'odds_max': 50,
        'venue_filter': None,
        'c1_second_rate_min': 20,
        'c1_second_rate_max': 30,
        'description': 'D×B1級×40-50倍×2連率20-30%',
        'use_pattern_h': False,
    },
    {
        'name': 'D×5コース予測×A2除外',
        'confidence': 'D',
        'c1_rank': ['A1', 'B1', 'B2'],
        'odds_min': 10,
        'odds_max': 200,
        'venue_filter': None,
        'predicted_course': 5,
        'description': 'D×5コース予測×A2除外（ROI 176.6%）',
        'use_pattern_h': True,
    },
]

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


def build_condition_query(cond: Dict, date_start: str, date_end: str,
                          group_by: str = None) -> str:
    """条件に応じたSQLクエリを構築

    Args:
        cond: 条件辞書
        date_start: 開始日
        date_end: 終了日
        group_by: グループ化指定 ('year', 'month', 'venue', 'odds')
    """
    c1_rank_str = "','".join(cond['c1_rank'])
    use_pattern_h = cond.get('use_pattern_h', True)

    # 各種フィルター条件
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

    month_exclude_clause = ""
    if cond.get('month_exclude'):
        months = ','.join(map(str, cond['month_exclude']))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    escape_rate_join = ""
    escape_rate_clause = ""
    if cond.get('escape_rate_min') is not None:
        escape_rate_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
        """
        escape_rate_clause = f"AND pes.escape_rate >= {cond['escape_rate_min']} "

    bias_join = ""
    bias_clause = ""
    if cond.get('bias_max') is not None:
        bias_join = """
        LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
        LEFT JOIN player_bias_stats pbs ON e_bias.racer_number = pbs.player_id AND pbs.stadium_id IS NULL
        """
        bias_clause = f"AND pbs.bias_index IS NOT NULL AND pbs.bias_index < {cond['bias_max']} "

    # グループ化カラム
    if group_by == 'year':
        group_col = "strftime('%Y', r.race_date) as group_key"
    elif group_by == 'month':
        group_col = "CAST(strftime('%m', r.race_date) AS INTEGER) as group_key"
    elif group_by == 'venue':
        group_col = "r.venue_code as group_key"
    elif group_by == 'odds':
        # オッズ帯は後段でCASE式として参照
        group_col = "1 as group_key_placeholder"
    else:
        group_col = "1 as group_key"

    if use_pattern_h:
        # パターンH: 3点買い
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                {group_col},
                rp.confidence,
                e1.racer_rank as c1_rank,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                rp4.pit_number as p4,
                rp5.pit_number as p5
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            {escape_rate_join}
            {bias_join}
            WHERE rp.rank_prediction = 1
            AND rp.confidence = '{cond["confidence"]}'
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
            {venue_clause}
            {motor_clause}
            {predicted_course_clause}
            {c1_second_rate_clause}
            {month_exclude_clause}
            {escape_rate_clause}
            {bias_clause}
        ),
        race_with_results AS (
            SELECT
                rb.*,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        ),
        race_payouts AS (
            SELECT
                rwr.*,
                CASE WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN 200 ELSE 0 END as bet_123,
                CASE WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_124,
                CASE WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_125,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN odds_123 * 200 ELSE 0
                END as payout_123,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                         AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']}
                    THEN odds_124 * 100 ELSE 0
                END as payout_124,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5
                         AND odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']}
                    THEN odds_125 * 100 ELSE 0
                END as payout_125,
                CASE
                    WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']})
                      OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']})
                      OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']})
                    THEN 1 ELSE 0
                END as is_hit,
                CASE
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} AND odds_123 < 20 THEN '10-20'
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} AND odds_123 < 30 THEN '20-30'
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} AND odds_123 < 50 THEN '30-50'
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} AND odds_123 < 100 THEN '50-100'
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN '100+'
                    WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} AND odds_124 < 20 THEN '10-20'
                    WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} AND odds_124 < 30 THEN '20-30'
                    WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} AND odds_124 < 50 THEN '30-50'
                    WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} AND odds_124 < 100 THEN '50-100'
                    WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN '100+'
                    WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} AND odds_125 < 20 THEN '10-20'
                    WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} AND odds_125 < 30 THEN '20-30'
                    WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} AND odds_125 < 50 THEN '30-50'
                    WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} AND odds_125 < 100 THEN '50-100'
                    WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} THEN '100+'
                    ELSE NULL
                END as odds_band
            FROM race_with_results rwr
        )
        SELECT
            {'group_key' if group_by != 'odds' else 'odds_band'} as group_key,
            COUNT(*) as races,
            SUM(CASE WHEN bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_123 + bet_124 + bet_125) as total_investment,
            SUM(payout_123 + payout_124 + payout_125) as total_payout
        FROM race_payouts
        WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
        {'GROUP BY group_key' if group_by != 'odds' else 'GROUP BY odds_band'}
        {'ORDER BY group_key' if group_by != 'odds' else 'ORDER BY odds_band'}
        '''
    else:
        # 1点買い
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                {group_col},
                rp.confidence,
                e1.racer_rank as c1_rank,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            {escape_rate_join}
            {bias_join}
            WHERE rp.rank_prediction = 1
            AND rp.confidence = '{cond["confidence"]}'
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{date_start}'
            AND r.race_date < '{date_end}'
            {venue_clause}
            {motor_clause}
            {predicted_course_clause}
            {c1_second_rate_clause}
            {month_exclude_clause}
            {escape_rate_clause}
            {bias_clause}
        ),
        race_bets AS (
            SELECT
                rb.*,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        ),
        race_payouts AS (
            SELECT
                rb.*,
                CASE WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN odds_123 * 100 ELSE 0
                END as payout,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit,
                CASE
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} AND odds_123 < 20 THEN '10-20'
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} AND odds_123 < 30 THEN '20-30'
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} AND odds_123 < 50 THEN '30-50'
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} AND odds_123 < 100 THEN '50-100'
                    WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN '100+'
                    ELSE NULL
                END as odds_band
            FROM race_bets rb
        )
        SELECT
            {'group_key' if group_by != 'odds' else 'odds_band'} as group_key,
            COUNT(*) as races,
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as total_investment,
            SUM(payout) as total_payout
        FROM race_payouts
        WHERE bet_amount > 0
        {'GROUP BY group_key' if group_by != 'odds' else 'GROUP BY odds_band'}
        {'ORDER BY group_key' if group_by != 'odds' else 'ORDER BY odds_band'}
        '''
    return query


def analyze_condition(cursor, cond: Dict, date_start: str, date_end: str,
                     group_by: str = None) -> List[Dict]:
    """条件別のパフォーマンスを分析"""
    query = build_condition_query(cond, date_start, date_end, group_by)
    cursor.execute(query)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        if row and row[2] and row[2] > 0:  # bets > 0
            group_key, races, bets, hits, investment, payout = row
            hits = hits or 0
            payout = payout or 0
            roi = 100.0 * payout / investment if investment > 0 else 0
            profit = payout - investment
            hit_rate = 100.0 * hits / bets if bets > 0 else 0
            results.append({
                'group_key': group_key,
                'bets': bets,
                'hits': hits,
                'hit_rate': hit_rate,
                'investment': investment,
                'payout': payout,
                'roi': roi,
                'profit': profit,
            })
    return results


def generate_report(conn):
    """詳細レポートを生成"""
    cursor = conn.cursor()

    report_lines = []
    report_lines.append("# 現行10条件の詳細分析レポート")
    report_lines.append("")
    report_lines.append(f"**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # エグゼクティブサマリー
    report_lines.append("## エグゼクティブサマリー")
    report_lines.append("")

    # 全体パフォーマンス（6年間）
    report_lines.append("### 全体パフォーマンス（2020-2025年）")
    report_lines.append("")

    total_bets = 0
    total_hits = 0
    total_investment = 0
    total_payout = 0

    condition_summaries = []
    for cond in CONDITIONS:
        results = analyze_condition(cursor, cond, '2020-01-01', '2026-01-01')
        if results:
            result = results[0]
            total_bets += result['bets']
            total_hits += result['hits']
            total_investment += result['investment']
            total_payout += result['payout']
            condition_summaries.append({
                'name': cond['name'],
                'confidence': cond['confidence'],
                'use_pattern_h': cond.get('use_pattern_h', True),
                **result
            })

    total_roi = 100.0 * total_payout / total_investment if total_investment > 0 else 0
    total_profit = total_payout - total_investment
    total_hit_rate = 100.0 * total_hits / total_bets if total_bets > 0 else 0

    report_lines.append(f"- **購入レース数**: {total_bets:,}件")
    report_lines.append(f"- **的中数**: {total_hits:,}件")
    report_lines.append(f"- **的中率**: {total_hit_rate:.2f}%")
    report_lines.append(f"- **ROI**: {total_roi:.1f}%")
    report_lines.append(f"- **収支**: {total_profit:+,.0f}円")
    report_lines.append("")

    # 信頼度別
    report_lines.append("### 信頼度別パフォーマンス")
    report_lines.append("")
    report_lines.append("| 信頼度 | 件数 | 的中率 | ROI | 収支 |")
    report_lines.append("|:------:|-----:|-------:|----:|-----:|")

    for conf in ['A', 'B', 'C', 'D']:
        conf_bets = sum(s['bets'] for s in condition_summaries if s['confidence'] == conf)
        conf_hits = sum(s['hits'] for s in condition_summaries if s['confidence'] == conf)
        conf_investment = sum(s['investment'] for s in condition_summaries if s['confidence'] == conf)
        conf_payout = sum(s['payout'] for s in condition_summaries if s['confidence'] == conf)

        if conf_bets > 0:
            conf_roi = 100.0 * conf_payout / conf_investment
            conf_profit = conf_payout - conf_investment
            conf_hit_rate = 100.0 * conf_hits / conf_bets
            report_lines.append(f"| {conf} | {conf_bets:,} | {conf_hit_rate:.1f}% | {conf_roi:.1f}% | {conf_profit:+,.0f} |")

    report_lines.append("")

    # 1点買い vs パターンH
    report_lines.append("### 1点買い vs パターンH比較")
    report_lines.append("")

    single_bet_bets = sum(s['bets'] for s in condition_summaries if not s['use_pattern_h'])
    single_bet_hits = sum(s['hits'] for s in condition_summaries if not s['use_pattern_h'])
    single_bet_investment = sum(s['investment'] for s in condition_summaries if not s['use_pattern_h'])
    single_bet_payout = sum(s['payout'] for s in condition_summaries if not s['use_pattern_h'])

    pattern_h_bets = sum(s['bets'] for s in condition_summaries if s['use_pattern_h'])
    pattern_h_hits = sum(s['hits'] for s in condition_summaries if s['use_pattern_h'])
    pattern_h_investment = sum(s['investment'] for s in condition_summaries if s['use_pattern_h'])
    pattern_h_payout = sum(s['payout'] for s in condition_summaries if s['use_pattern_h'])

    report_lines.append("| 方式 | 条件数 | 件数 | 的中率 | ROI | 収支 |")
    report_lines.append("|:-----|-------:|-----:|-------:|----:|-----:|")

    if single_bet_bets > 0:
        single_roi = 100.0 * single_bet_payout / single_bet_investment
        single_profit = single_bet_payout - single_bet_investment
        single_hit_rate = 100.0 * single_bet_hits / single_bet_bets
        single_count = sum(1 for s in condition_summaries if not s['use_pattern_h'])
        report_lines.append(f"| 1点買い | {single_count} | {single_bet_bets:,} | {single_hit_rate:.1f}% | {single_roi:.1f}% | {single_profit:+,.0f} |")

    if pattern_h_bets > 0:
        pattern_roi = 100.0 * pattern_h_payout / pattern_h_investment
        pattern_profit = pattern_h_payout - pattern_h_investment
        pattern_hit_rate = 100.0 * pattern_h_hits / pattern_h_bets
        pattern_count = sum(1 for s in condition_summaries if s['use_pattern_h'])
        report_lines.append(f"| パターンH | {pattern_count} | {pattern_h_bets:,} | {pattern_hit_rate:.1f}% | {pattern_roi:.1f}% | {pattern_profit:+,.0f} |")

    report_lines.append("")

    # 主要な発見
    report_lines.append("### 主要な発見")
    report_lines.append("")

    # トップ3条件
    sorted_by_roi = sorted(condition_summaries, key=lambda x: x['roi'], reverse=True)
    report_lines.append("#### トップ3条件（ROI順）")
    report_lines.append("")
    for i, cond in enumerate(sorted_by_roi[:3], 1):
        report_lines.append(f"{i}. **{cond['name']}**: ROI {cond['roi']:.1f}%, 収支 {cond['profit']:+,.0f}円 ({cond['bets']}件)")
    report_lines.append("")

    # 問題のある条件（ROI 100%未満または赤字）
    problematic = [c for c in condition_summaries if c['roi'] < 100 or c['profit'] < 0]
    if problematic:
        report_lines.append("#### 改善が必要な条件")
        report_lines.append("")
        for cond in problematic:
            report_lines.append(f"- **{cond['name']}**: ROI {cond['roi']:.1f}%, 収支 {cond['profit']:+,.0f}円")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")

    # 各条件の詳細分析
    report_lines.append("## 各条件の詳細分析")
    report_lines.append("")

    for i, cond in enumerate(CONDITIONS, 1):
        report_lines.append(f"### 条件{i}: {cond['name']}")
        report_lines.append("")

        # 基本情報
        report_lines.append("#### 基本情報")
        report_lines.append("")
        report_lines.append(f"- **信頼度**: {cond['confidence']}")
        report_lines.append(f"- **オッズ帯**: {cond['odds_min']}-{cond['odds_max']}倍")
        report_lines.append(f"- **級別**: {', '.join(cond['c1_rank'])}")
        report_lines.append(f"- **買い方**: {'パターンH（3点買い400円）' if cond.get('use_pattern_h', True) else '1点買い（100円）'}")
        if cond.get('venue_filter'):
            venue_names = [VENUE_NAMES.get(v, f'#{v}') for v in cond['venue_filter']]
            report_lines.append(f"- **会場フィルター**: {', '.join(venue_names)}")
        if cond.get('predicted_course'):
            report_lines.append(f"- **コース指定**: {cond['predicted_course']}コース予測限定")
        if cond.get('month_exclude'):
            report_lines.append(f"- **月除外**: {', '.join(map(str, cond['month_exclude']))}月を除外")
        report_lines.append("")

        # 全体パフォーマンス
        overall = analyze_condition(cursor, cond, '2020-01-01', '2026-01-01')
        if overall:
            result = overall[0]
            report_lines.append("#### 6年間パフォーマンス（2020-2025）")
            report_lines.append("")
            report_lines.append(f"- **レース数**: {result['bets']:,}件")
            report_lines.append(f"- **的中数**: {result['hits']:,}件")
            report_lines.append(f"- **的中率**: {result['hit_rate']:.2f}%")
            report_lines.append(f"- **ROI**: {result['roi']:.1f}%")
            report_lines.append(f"- **収支**: {result['profit']:+,.0f}円")
            avg_odds = result['payout'] / result['hits'] if result['hits'] > 0 else 0
            report_lines.append(f"- **平均配当**: {avg_odds:,.0f}円")
            report_lines.append("")

        # 年度別成績
        yearly = analyze_condition(cursor, cond, '2020-01-01', '2026-01-01', group_by='year')
        if yearly:
            report_lines.append("#### 年度別成績")
            report_lines.append("")
            report_lines.append("| 年度 | 件数 | 的中 | 的中率 | ROI | 収支 | 判定 |")
            report_lines.append("|-----:|-----:|-----:|-------:|----:|-----:|:----:|")

            black_years = 0
            for y in yearly:
                year = int(y['group_key'])
                status = "○" if y['profit'] > 0 else "×"
                if y['profit'] > 0:
                    black_years += 1
                report_lines.append(f"| {year} | {y['bets']:,} | {y['hits']} | {y['hit_rate']:.1f}% | {y['roi']:.1f}% | {y['profit']:+,.0f} | {status} |")

            report_lines.append("")
            report_lines.append(f"**黒字年数**: {black_years}/6年")
            report_lines.append("")

        # 月別成績
        monthly = analyze_condition(cursor, cond, '2020-01-01', '2026-01-01', group_by='month')
        if monthly:
            report_lines.append("#### 月別成績（6年間累計）")
            report_lines.append("")
            report_lines.append("| 月 | 件数 | 的中 | 的中率 | ROI | 収支 | 判定 |")
            report_lines.append("|---:|-----:|-----:|-------:|----:|-----:|:----:|")

            black_months = 0
            for m in monthly:
                month = int(m['group_key'])
                status = "○" if m['profit'] > 0 else "×"
                if m['profit'] > 0:
                    black_months += 1
                report_lines.append(f"| {month} | {m['bets']:,} | {m['hits']} | {m['hit_rate']:.1f}% | {m['roi']:.1f}% | {m['profit']:+,.0f} | {status} |")

            report_lines.append("")
            report_lines.append(f"**黒字月数**: {black_months}/12月")
            report_lines.append("")

        # 会場別成績（上位10会場）
        venue_results = analyze_condition(cursor, cond, '2020-01-01', '2026-01-01', group_by='venue')
        if venue_results:
            # ROI順でソート
            venue_results_sorted = sorted(venue_results, key=lambda x: x['roi'], reverse=True)

            report_lines.append("#### 会場別成績（ROI上位10会場）")
            report_lines.append("")
            report_lines.append("| 会場 | 件数 | 的中 | 的中率 | ROI | 収支 |")
            report_lines.append("|:-----|-----:|-----:|-------:|----:|-----:|")

            for v in venue_results_sorted[:10]:
                venue_code = int(v['group_key'])
                venue_name = VENUE_NAMES.get(venue_code, f'#{venue_code}')
                report_lines.append(f"| {venue_name} | {v['bets']:,} | {v['hits']} | {v['hit_rate']:.1f}% | {v['roi']:.1f}% | {v['profit']:+,.0f} |")

            report_lines.append("")

            # 低ROI会場（ワースト3）
            if len(venue_results_sorted) > 10:
                report_lines.append("**ワースト3会場（ROI）**:")
                report_lines.append("")
                for v in venue_results_sorted[-3:]:
                    venue_code = int(v['group_key'])
                    venue_name = VENUE_NAMES.get(venue_code, f'#{venue_code}')
                    report_lines.append(f"- {venue_name}: ROI {v['roi']:.1f}%, 収支 {v['profit']:+,.0f}円 ({v['bets']}件)")
                report_lines.append("")

        # オッズ帯別成績
        odds_results = analyze_condition(cursor, cond, '2020-01-01', '2026-01-01', group_by='odds')
        if odds_results:
            report_lines.append("#### オッズ帯別成績")
            report_lines.append("")
            report_lines.append("| オッズ帯 | 件数 | 的中 | 的中率 | ROI | 収支 |")
            report_lines.append("|:---------|-----:|-----:|-------:|----:|-----:|")

            for o in odds_results:
                report_lines.append(f"| {o['group_key']}倍 | {o['bets']:,} | {o['hits']} | {o['hit_rate']:.1f}% | {o['roi']:.1f}% | {o['profit']:+,.0f} |")

            report_lines.append("")

        # 強み
        report_lines.append("#### 強み")
        report_lines.append("")

        if overall and overall[0]['roi'] >= 150:
            report_lines.append(f"- **高ROI**: {overall[0]['roi']:.1f}%で優秀")
        if yearly:
            black_years = sum(1 for y in yearly if y['profit'] > 0)
            if black_years >= 5:
                report_lines.append(f"- **高安定性**: {black_years}/6年黒字")
        if monthly:
            black_months = sum(1 for m in monthly if m['profit'] > 0)
            if black_months >= 8:
                report_lines.append(f"- **月別安定性**: {black_months}/12月黒字")
        if venue_results:
            high_roi_venues = [v for v in venue_results if v['roi'] >= 200]
            if high_roi_venues:
                report_lines.append(f"- **高ROI会場数**: {len(high_roi_venues)}会場がROI 200%以上")

        report_lines.append("")

        # 弱み
        report_lines.append("#### 弱み")
        report_lines.append("")

        if overall and overall[0]['roi'] < 100:
            report_lines.append(f"- **低ROI**: {overall[0]['roi']:.1f}%で赤字")
        if yearly:
            red_years = [y for y in yearly if y['profit'] < 0]
            if red_years:
                red_year_list = ', '.join([y['group_key'] for y in red_years])
                report_lines.append(f"- **赤字年度**: {red_year_list}年")
        if monthly:
            red_months = [m for m in monthly if m['profit'] < 0]
            if red_months:
                red_month_list = ', '.join([str(int(m['group_key'])) for m in red_months])
                report_lines.append(f"- **赤字月**: {red_month_list}月")
        if venue_results:
            low_roi_venues = [v for v in venue_results if v['roi'] < 80 and v['bets'] >= 10]
            if low_roi_venues:
                report_lines.append(f"- **低ROI会場数**: {len(low_roi_venues)}会場がROI 80%未満（10件以上）")

        report_lines.append("")

        # 改善提案
        report_lines.append("#### 改善提案")
        report_lines.append("")

        if overall and overall[0]['roi'] < 100:
            report_lines.append("- **条件見直し**: ROI 100%未満のため、フィルター追加または廃止検討")

        if yearly:
            red_years = [y for y in yearly if y['profit'] < 0]
            if len(red_years) >= 3:
                report_lines.append("- **年度別分析**: 赤字年度の特徴を分析し、フィルター追加を検討")

        if monthly:
            red_months = [m for m in monthly if m['profit'] < -5000 and m['bets'] >= 10]
            if red_months:
                red_month_list = ', '.join([f"{int(m['group_key'])}月" for m in red_months])
                report_lines.append(f"- **月除外フィルター**: {red_month_list}の除外を検討")

        if venue_results:
            low_roi_venues = [v for v in venue_results if v['roi'] < 80 and v['bets'] >= 20]
            if low_roi_venues and not cond.get('venue_filter'):
                report_lines.append("- **会場フィルター追加**: 低ROI会場を除外して安定性向上")

        if odds_results:
            low_roi_odds = [o for o in odds_results if o['roi'] < 80 and o['bets'] >= 20]
            if low_roi_odds:
                report_lines.append("- **オッズ帯最適化**: 低ROIオッズ帯の除外を検討")

        if overall and overall[0]['bets'] < 50:
            report_lines.append("- **サンプル不足**: レース数が少なく安定性評価が困難")

        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")

    # 条件間比較
    report_lines.append("## 条件間比較")
    report_lines.append("")

    # ROIランキング
    report_lines.append("### ROIランキング（上位順）")
    report_lines.append("")
    report_lines.append("| 順位 | 条件名 | 件数 | ROI | 収支 | 方式 |")
    report_lines.append("|-----:|:-------|-----:|----:|-----:|:----:|")

    sorted_by_roi = sorted(condition_summaries, key=lambda x: x['roi'], reverse=True)
    for i, cond in enumerate(sorted_by_roi, 1):
        method = 'P.H' if cond['use_pattern_h'] else '1点'
        report_lines.append(f"| {i} | {cond['name']} | {cond['bets']:,} | {cond['roi']:.1f}% | {cond['profit']:+,.0f} | {method} |")

    report_lines.append("")

    # 収支ランキング
    report_lines.append("### 収支ランキング（上位順）")
    report_lines.append("")
    report_lines.append("| 順位 | 条件名 | 件数 | ROI | 収支 | 方式 |")
    report_lines.append("|-----:|:-------|-----:|----:|-----:|:----:|")

    sorted_by_profit = sorted(condition_summaries, key=lambda x: x['profit'], reverse=True)
    for i, cond in enumerate(sorted_by_profit, 1):
        method = 'P.H' if cond['use_pattern_h'] else '1点'
        report_lines.append(f"| {i} | {cond['name']} | {cond['bets']:,} | {cond['roi']:.1f}% | {cond['profit']:+,.0f} | {method} |")

    report_lines.append("")

    # 安定性ランキング
    report_lines.append("### 安定性ランキング（黒字年数順）")
    report_lines.append("")
    report_lines.append("| 順位 | 条件名 | 黒字年数 | ROI | 収支 |")
    report_lines.append("|-----:|:-------|:--------:|----:|-----:|")

    stability_data = []
    for cond in CONDITIONS:
        yearly = analyze_condition(cursor, cond, '2020-01-01', '2026-01-01', group_by='year')
        overall = analyze_condition(cursor, cond, '2020-01-01', '2026-01-01')
        if yearly and overall:
            black_years = sum(1 for y in yearly if y['profit'] > 0)
            stability_data.append({
                'name': cond['name'],
                'black_years': black_years,
                'roi': overall[0]['roi'],
                'profit': overall[0]['profit']
            })

    sorted_by_stability = sorted(stability_data, key=lambda x: (x['black_years'], x['roi']), reverse=True)
    for i, data in enumerate(sorted_by_stability, 1):
        report_lines.append(f"| {i} | {data['name']} | {data['black_years']}/6年 | {data['roi']:.1f}% | {data['profit']:+,.0f} |")

    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # 改善機会
    report_lines.append("## 改善機会")
    report_lines.append("")

    report_lines.append("### 高優先度")
    report_lines.append("")

    # ROI 100%未満または大幅赤字の条件
    high_priority = [c for c in condition_summaries if c['roi'] < 100 or c['profit'] < -10000]
    if high_priority:
        for i, cond in enumerate(high_priority, 1):
            report_lines.append(f"{i}. **{cond['name']}**: ROI {cond['roi']:.1f}%, 収支 {cond['profit']:+,.0f}円")
            report_lines.append(f"   - **対策**: 条件見直しまたは廃止検討")
        report_lines.append("")
    else:
        report_lines.append("該当なし（全条件がROI 100%以上）")
        report_lines.append("")

    report_lines.append("### 中優先度")
    report_lines.append("")

    # ROI 100-120%の条件（改善余地あり）
    mid_priority = [c for c in condition_summaries if 100 <= c['roi'] < 120]
    if mid_priority:
        for i, cond in enumerate(mid_priority, 1):
            report_lines.append(f"{i}. **{cond['name']}**: ROI {cond['roi']:.1f}%")
            report_lines.append(f"   - **対策**: フィルター追加で120%以上を目指す")
        report_lines.append("")
    else:
        report_lines.append("該当なし")
        report_lines.append("")

    report_lines.append("### 低優先度")
    report_lines.append("")

    # ROI 150%以上だが更なる最適化余地がある条件
    low_priority = [c for c in condition_summaries if c['roi'] >= 150 and c['bets'] >= 100]
    if low_priority:
        for i, cond in enumerate(low_priority, 1):
            report_lines.append(f"{i}. **{cond['name']}**: ROI {cond['roi']:.1f}%")
            report_lines.append(f"   - **対策**: 細かい最適化（月除外、会場追加等）")
        report_lines.append("")
    else:
        report_lines.append("該当なし")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")

    # 結論
    report_lines.append("## 結論")
    report_lines.append("")

    report_lines.append("### 維持すべき条件")
    report_lines.append("")
    excellent = [c for c in condition_summaries if c['roi'] >= 150 and c['profit'] > 0]
    if excellent:
        for cond in sorted(excellent, key=lambda x: x['roi'], reverse=True):
            report_lines.append(f"- **{cond['name']}**: ROI {cond['roi']:.1f}%, 収支 {cond['profit']:+,.0f}円")
        report_lines.append("")

    report_lines.append("### 改善すべき条件")
    report_lines.append("")
    needs_improvement = [c for c in condition_summaries if 100 <= c['roi'] < 150 and c['profit'] > 0]
    if needs_improvement:
        for cond in needs_improvement:
            report_lines.append(f"- **{cond['name']}**: ROI {cond['roi']:.1f}% → 目標150%以上")
        report_lines.append("")
    else:
        report_lines.append("該当なし（全条件が優秀またはROI 100%未満）")
        report_lines.append("")

    report_lines.append("### 廃止検討すべき条件")
    report_lines.append("")
    should_remove = [c for c in condition_summaries if c['roi'] < 100 or (c['profit'] < 0 and c['bets'] >= 50)]
    if should_remove:
        for cond in should_remove:
            report_lines.append(f"- **{cond['name']}**: ROI {cond['roi']:.1f}%, 収支 {cond['profit']:+,.0f}円")
        report_lines.append("")
        report_lines.append("**注意**: 廃止は慎重に。データ補完後の再検証も検討。")
        report_lines.append("")
    else:
        report_lines.append("該当なし（全条件がROI 100%以上または黒字）")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")

    # 付録
    report_lines.append("## 付録")
    report_lines.append("")

    report_lines.append("### 分析スクリプト")
    report_lines.append("")
    report_lines.append("- `scripts/analysis/analyze_current_conditions.py`")
    report_lines.append("")

    report_lines.append("### データの制約")
    report_lines.append("")
    report_lines.append("- **分析期間**: 2020年1月1日 ～ 2025年12月31日（6年間）")
    report_lines.append("- **データソース**: `data/boatrace.db`")
    report_lines.append("- **オッズデータ**: 一部欠損あり（補完前）")
    report_lines.append("- **統計指標**: 一部欠損あり（逃げ率、バイアス指数等）")
    report_lines.append("")
    report_lines.append("**重要**: データ補完後の再分析を推奨")
    report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append(f"*レポート生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    return '\n'.join(report_lines)


def main():
    print("現行10条件の詳細分析を開始します...")
    print()

    # データベース接続
    conn = sqlite3.connect(DATABASE_PATH)

    try:
        # レポート生成
        report = generate_report(conn)

        # レポート保存
        output_dir = os.path.join(PROJECT_ROOT, 'docs', 'analysis')
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, 'CURRENT_CONDITIONS_DETAILED_ANALYSIS_20260212.md')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"レポートを生成しました: {output_path}")
        print()
        print("=" * 80)
        print("分析完了")
        print("=" * 80)

    finally:
        conn.close()


if __name__ == '__main__':
    main()
