#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TJ-4: 予測スコア差の条件別閾値最適化分析

目的:
    現行購入条件（10条件）ごとに、スコア差フィルター追加時の
    ROI改善効果を試算し、採用推奨閾値を提案する。

スコア差 = 1位予測と2位予測のtotal_scoreの差

使用方法:
    python scripts/analysis/tj4_score_gap_optimization.py

作成日: 2026-02-18
"""
import sqlite3
import sys
import io
import os
from typing import Dict, List, Tuple

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS, GLOBAL_VENUE_MONTH_EXCLUDES

# ============================================================
# 定数
# ============================================================
START_DATE = '2020-01-01'
END_DATE = '2025-12-31'

# スコア差の閾値区間（5pt刻み）
SCORE_GAP_BINS = [
    (0, 5, '0-5pt'),
    (5, 10, '5-10pt'),
    (10, 15, '10-15pt'),
    (15, 20, '15-20pt'),
    (20, 25, '20-25pt'),
    (25, 9999, '25pt+'),
]

# スコア差フィルターの候補閾値
SCORE_GAP_THRESHOLDS = [5, 8, 10, 12, 15, 18, 20, 25]


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_condition_base_query(cond: Dict) -> Tuple[str, List]:
    """
    条件定義からSQLのWHERE句とパラメータを構築する。
    standard_backtest.pyと同じロジックを使用。
    """
    c1_ranks_str = ','.join([f"'{r}'" for r in cond['c1_rank']])

    confidence_clause = ""
    if cond.get('confidence') is not None:
        confidence_clause = f"AND rp.confidence = '{cond['confidence']}'"

    venue_clause = ""
    if cond.get('venue_filter'):
        venue_codes = [f"'{v:02d}'" if isinstance(v, int) else f"'{v}'" for v in cond['venue_filter']]
        venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"

    month_exclude_clause = ""
    if cond.get('month_exclude'):
        months = ','.join(map(str, cond['month_exclude']))
        month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    c1_second_rate_clause = ""
    if cond.get('c1_second_rate_min') is not None:
        c1_second_rate_clause += f"AND e1.second_rate >= {cond['c1_second_rate_min']} "
    if cond.get('c1_second_rate_max') is not None:
        c1_second_rate_clause += f"AND e1.second_rate < {cond['c1_second_rate_max']} "

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    # パターンH用：5位までJOINが必要
    if cond.get('use_pattern_h', False):
        rank_joins = """
        JOIN race_predictions rp2 ON rp2.race_id = rp.race_id
            AND rp2.rank_prediction = 2 AND rp2.prediction_type = 'before'
        JOIN race_predictions rp3 ON rp3.race_id = rp.race_id
            AND rp3.rank_prediction = 3 AND rp3.prediction_type = 'before'
        JOIN race_predictions rp4 ON rp4.race_id = rp.race_id
            AND rp4.rank_prediction = 4 AND rp4.prediction_type = 'before'
        JOIN race_predictions rp5 ON rp5.race_id = rp.race_id
            AND rp5.rank_prediction = 5 AND rp5.prediction_type = 'before'
        """
    else:
        rank_joins = """
        JOIN race_predictions rp2 ON rp2.race_id = rp.race_id
            AND rp2.rank_prediction = 2 AND rp2.prediction_type = 'before'
        JOIN race_predictions rp3 ON rp3.race_id = rp.race_id
            AND rp3.rank_prediction = 3 AND rp3.prediction_type = 'before'
        """

    # バイアスフィルター（backtest_helpers.pyと同じ方式）
    bias_join = ""
    bias_clause = ""
    if cond.get('bias_max') is not None:
        bias_join = """
        LEFT JOIN entries e_bias ON r.id = e_bias.race_id AND e_bias.pit_number = rp1.pit_number
        LEFT JOIN (
            SELECT player_id, bias_index
            FROM player_bias_stats
            WHERE stadium_id IS NULL AND bias_index IS NOT NULL
            AND id IN (
                SELECT MAX(id)
                FROM player_bias_stats
                WHERE stadium_id IS NULL AND bias_index IS NOT NULL
                GROUP BY player_id
            )
        ) pbs ON e_bias.racer_number = pbs.player_id
        """
        bias_clause = f"AND pbs.bias_index IS NOT NULL AND pbs.bias_index < {cond['bias_max']} "

    # 逃げ率フィルター（backtest_helpers.pyと同じ方式）
    escape_join = ""
    escape_clause = ""
    if cond.get('escape_rate_min') is not None:
        escape_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN (
            SELECT player_id, escape_rate
            FROM player_escape_stats
            WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
            AND id IN (
                SELECT MAX(id)
                FROM player_escape_stats
                WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
                GROUP BY player_id
            )
        ) pes ON e_pred.racer_number = pes.player_id
        """
        escape_clause = f"AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= {cond['escape_rate_min']} "

    # GLOBAL_VENUE_MONTH_EXCLUDES の適用
    global_exclude_clauses = []
    for venue_code, month in GLOBAL_VENUE_MONTH_EXCLUDES:
        global_exclude_clauses.append(
            f"NOT (r.venue_code = '{venue_code:02d}' AND CAST(strftime('%m', r.race_date) AS INTEGER) = {month})"
        )
    global_exclude_str = ""
    if global_exclude_clauses:
        global_exclude_str = "AND " + " AND ".join(global_exclude_clauses)

    return (confidence_clause, venue_clause, month_exclude_clause, predicted_course_clause,
            c1_second_rate_clause, motor_clause, rank_joins, bias_join, bias_clause,
            escape_join, escape_clause, global_exclude_str, c1_ranks_str)


def analyze_condition_by_score_gap(conn: sqlite3.Connection, cond: Dict) -> List[Dict]:
    """
    1条件について、スコア差区間別の的中率・ROI・収支を計算する。
    """
    (confidence_clause, venue_clause, month_exclude_clause, predicted_course_clause,
     c1_second_rate_clause, motor_clause, rank_joins, bias_join, bias_clause,
     escape_join, escape_clause, global_exclude_str, c1_ranks_str) = build_condition_base_query(cond)

    use_pattern_h = cond.get('use_pattern_h', False)

    if use_pattern_h:
        # パターンH: 3点買い（1-2-3, 1-3-2, 2-1-3）各100円、合計400円
        # 買い目1: rp1-rp2-rp3（100円）
        # 買い目2: rp1-rp3-rp2（100円）
        # 買い目3: rp2-rp1-rp3（100円）
        # 最大払戻し（このシミュレーションでは最初に的中した買い目のみ加算）
        bet_amount = 400
        result_columns = """
            -- 的中チェック（三連単: rp1→rp2→rp3, rp1→rp3→rp2, rp2→rp1→rp3）
            CASE
                WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                    THEN CAST(ROUND(to1.odds * 100) AS INTEGER)
                WHEN res1.rank = '1' AND res3.rank = '2' AND res2.rank = '3'
                    THEN CAST(ROUND(to2.odds * 100) AS INTEGER)
                WHEN res2.rank = '1' AND res1.rank = '2' AND res3.rank = '3'
                    THEN CAST(ROUND(to3.odds * 100) AS INTEGER)
                ELSE 0
            END as payout,
            CASE
                WHEN (res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3')
                  OR (res1.rank = '1' AND res3.rank = '2' AND res2.rank = '3')
                  OR (res2.rank = '1' AND res1.rank = '2' AND res3.rank = '3')
                    THEN 1 ELSE 0
            END as hit
        """
        odds_joins = f"""
        LEFT JOIN trifecta_odds to1 ON to1.race_id = r.id
            AND to1.combination = CAST(rp1.pit_number AS TEXT) || '-'
                || CAST(rp2.pit_number AS TEXT) || '-'
                || CAST(rp3.pit_number AS TEXT)
        LEFT JOIN trifecta_odds to2 ON to2.race_id = r.id
            AND to2.combination = CAST(rp1.pit_number AS TEXT) || '-'
                || CAST(rp3.pit_number AS TEXT) || '-'
                || CAST(rp2.pit_number AS TEXT)
        LEFT JOIN trifecta_odds to3 ON to3.race_id = r.id
            AND to3.combination = CAST(rp2.pit_number AS TEXT) || '-'
                || CAST(rp1.pit_number AS TEXT) || '-'
                || CAST(rp3.pit_number AS TEXT)
        """
        odds_clause = f"""
        AND to1.odds IS NOT NULL
        AND to1.odds BETWEEN {cond['odds_min']} AND {cond['odds_max']}
        """
    else:
        # 1点買い: rp1-rp2-rp3（100円）
        bet_amount = 100
        result_columns = """
            CASE
                WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                    THEN CAST(ROUND(to1.odds * 100) AS INTEGER)
                ELSE 0
            END as payout,
            CASE
                WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                    THEN 1 ELSE 0
            END as hit
        """
        odds_joins = f"""
        LEFT JOIN trifecta_odds to1 ON to1.race_id = r.id
            AND to1.combination = CAST(rp1.pit_number AS TEXT) || '-'
                || CAST(rp2.pit_number AS TEXT) || '-'
                || CAST(rp3.pit_number AS TEXT)
        """
        odds_clause = f"""
        AND to1.odds IS NOT NULL
        AND to1.odds BETWEEN {cond['odds_min']} AND {cond['odds_max']}
        """

    sql = f"""
    SELECT
        rp1.total_score - rp2.total_score as score_gap,
        {result_columns}
    FROM race_predictions rp
    JOIN race_predictions rp1 ON rp1.race_id = rp.race_id
        AND rp1.rank_prediction = 1 AND rp1.prediction_type = 'before'
    {rank_joins}
    JOIN races r ON r.id = rp.race_id
    LEFT JOIN entries e1 ON e1.race_id = r.id AND e1.pit_number = rp1.pit_number
    LEFT JOIN results res1 ON res1.race_id = r.id AND res1.pit_number = rp1.pit_number
    LEFT JOIN results res2 ON res2.race_id = r.id AND res2.pit_number = rp2.pit_number
    LEFT JOIN results res3 ON res3.race_id = r.id AND res3.pit_number = rp3.pit_number
    {bias_join}
    {escape_join}
    {odds_joins}
    WHERE rp.rank_prediction = 1
    AND rp.prediction_type = 'before'
    AND r.race_date BETWEEN '{START_DATE}' AND '{END_DATE}'
    AND e1.racer_rank IN ({c1_ranks_str})
    {confidence_clause}
    {venue_clause}
    {month_exclude_clause}
    {predicted_course_clause}
    {c1_second_rate_clause}
    {motor_clause}
    {bias_clause}
    {escape_clause}
    {odds_clause}
    {global_exclude_str}
    AND res1.is_invalid = 0
    """

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"  SQLエラー ({cond['id']}): {e}")
        return []

    if not rows:
        return []

    # スコア差区間別集計
    results = []
    for gap_min, gap_max, gap_label in SCORE_GAP_BINS:
        bin_rows = [r for r in rows if r['score_gap'] is not None
                    and gap_min <= r['score_gap'] < gap_max]
        if not bin_rows:
            continue
        total = len(bin_rows)
        hits = sum(r['hit'] or 0 for r in bin_rows)
        payouts = sum(r['payout'] or 0 for r in bin_rows)
        bet_total = total * bet_amount
        roi = (payouts / bet_total * 100) if bet_total > 0 else 0
        profit = payouts - bet_total
        results.append({
            'gap_label': gap_label,
            'gap_min': gap_min,
            'gap_max': gap_max,
            'count': total,
            'hits': hits,
            'hit_rate': hits / total * 100 if total > 0 else 0,
            'roi': roi,
            'profit': profit,
            'bet_total': bet_total,
        })

    return results


def analyze_score_gap_threshold_effect(conn: sqlite3.Connection, cond: Dict) -> List[Dict]:
    """
    スコア差閾値フィルターを適用した場合のROI・収支変化を試算する。
    """
    (confidence_clause, venue_clause, month_exclude_clause, predicted_course_clause,
     c1_second_rate_clause, motor_clause, rank_joins, bias_join, bias_clause,
     escape_join, escape_clause, global_exclude_str, c1_ranks_str) = build_condition_base_query(cond)

    use_pattern_h = cond.get('use_pattern_h', False)
    bet_amount = 400 if use_pattern_h else 100

    if use_pattern_h:
        result_columns = """
            CASE
                WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                    THEN CAST(ROUND(to1.odds * 100) AS INTEGER)
                WHEN res1.rank = '1' AND res3.rank = '2' AND res2.rank = '3'
                    THEN CAST(ROUND(to2.odds * 100) AS INTEGER)
                WHEN res2.rank = '1' AND res1.rank = '2' AND res3.rank = '3'
                    THEN CAST(ROUND(to3.odds * 100) AS INTEGER)
                ELSE 0
            END as payout,
            CASE
                WHEN (res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3')
                  OR (res1.rank = '1' AND res3.rank = '2' AND res2.rank = '3')
                  OR (res2.rank = '1' AND res1.rank = '2' AND res3.rank = '3')
                    THEN 1 ELSE 0
            END as hit
        """
        odds_joins = f"""
        LEFT JOIN trifecta_odds to1 ON to1.race_id = r.id
            AND to1.combination = CAST(rp1.pit_number AS TEXT) || '-'
                || CAST(rp2.pit_number AS TEXT) || '-'
                || CAST(rp3.pit_number AS TEXT)
        LEFT JOIN trifecta_odds to2 ON to2.race_id = r.id
            AND to2.combination = CAST(rp1.pit_number AS TEXT) || '-'
                || CAST(rp3.pit_number AS TEXT) || '-'
                || CAST(rp2.pit_number AS TEXT)
        LEFT JOIN trifecta_odds to3 ON to3.race_id = r.id
            AND to3.combination = CAST(rp2.pit_number AS TEXT) || '-'
                || CAST(rp1.pit_number AS TEXT) || '-'
                || CAST(rp3.pit_number AS TEXT)
        """
        odds_clause = f"""
        AND to1.odds IS NOT NULL
        AND to1.odds BETWEEN {cond['odds_min']} AND {cond['odds_max']}
        """
    else:
        result_columns = """
            CASE
                WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                    THEN CAST(ROUND(to1.odds * 100) AS INTEGER)
                ELSE 0
            END as payout,
            CASE
                WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                    THEN 1 ELSE 0
            END as hit
        """
        odds_joins = f"""
        LEFT JOIN trifecta_odds to1 ON to1.race_id = r.id
            AND to1.combination = CAST(rp1.pit_number AS TEXT) || '-'
                || CAST(rp2.pit_number AS TEXT) || '-'
                || CAST(rp3.pit_number AS TEXT)
        """
        odds_clause = f"""
        AND to1.odds IS NOT NULL
        AND to1.odds BETWEEN {cond['odds_min']} AND {cond['odds_max']}
        """

    # まず全データを取得
    sql = f"""
    SELECT
        rp1.total_score - rp2.total_score as score_gap,
        {result_columns}
    FROM race_predictions rp
    JOIN race_predictions rp1 ON rp1.race_id = rp.race_id
        AND rp1.rank_prediction = 1 AND rp1.prediction_type = 'before'
    {rank_joins}
    JOIN races r ON r.id = rp.race_id
    LEFT JOIN entries e1 ON e1.race_id = r.id AND e1.pit_number = rp1.pit_number
    LEFT JOIN results res1 ON res1.race_id = r.id AND res1.pit_number = rp1.pit_number
    LEFT JOIN results res2 ON res2.race_id = r.id AND res2.pit_number = rp2.pit_number
    LEFT JOIN results res3 ON res3.race_id = r.id AND res3.pit_number = rp3.pit_number
    {bias_join}
    {escape_join}
    {odds_joins}
    WHERE rp.rank_prediction = 1
    AND rp.prediction_type = 'before'
    AND r.race_date BETWEEN '{START_DATE}' AND '{END_DATE}'
    AND e1.racer_rank IN ({c1_ranks_str})
    {confidence_clause}
    {venue_clause}
    {month_exclude_clause}
    {predicted_course_clause}
    {c1_second_rate_clause}
    {motor_clause}
    {bias_clause}
    {escape_clause}
    {odds_clause}
    {global_exclude_str}
    AND res1.is_invalid = 0
    """

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"  SQLエラー ({cond['id']}): {e}")
        return []

    if not rows:
        return []

    # ベースライン（フィルターなし）
    all_rows = list(rows)
    threshold_results = []

    # ベースライン
    total = len(all_rows)
    hits = sum(r['hit'] or 0 for r in all_rows)
    payouts = sum(r['payout'] or 0 for r in all_rows)
    bet_total = total * bet_amount
    roi_base = (payouts / bet_total * 100) if bet_total > 0 else 0
    profit_base = payouts - bet_total

    threshold_results.append({
        'threshold': None,
        'label': 'ベースライン（フィルターなし）',
        'count': total,
        'hits': hits,
        'hit_rate': hits / total * 100 if total > 0 else 0,
        'roi': roi_base,
        'profit': profit_base,
        'count_reduction': 0,
        'roi_change': 0,
        'profit_change': 0,
    })

    # 各閾値でフィルタリング
    for threshold in SCORE_GAP_THRESHOLDS:
        filtered = [r for r in all_rows if r['score_gap'] is not None and r['score_gap'] >= threshold]
        if not filtered:
            continue
        total_f = len(filtered)
        hits_f = sum(r['hit'] or 0 for r in filtered)
        payouts_f = sum(r['payout'] or 0 for r in filtered)
        bet_total_f = total_f * bet_amount
        roi_f = (payouts_f / bet_total_f * 100) if bet_total_f > 0 else 0
        profit_f = payouts_f - bet_total_f

        threshold_results.append({
            'threshold': threshold,
            'label': f'スコア差 ≥ {threshold}pt',
            'count': total_f,
            'hits': hits_f,
            'hit_rate': hits_f / total_f * 100 if total_f > 0 else 0,
            'roi': roi_f,
            'profit': profit_f,
            'count_reduction': total - total_f,
            'roi_change': roi_f - roi_base,
            'profit_change': profit_f - profit_base,
        })

    return threshold_results


def analyze_overall_score_gap_distribution(conn: sqlite3.Connection) -> None:
    """
    全体のスコア差分布（信頼度別・スコア差区間別）を表示する。
    """
    print("=" * 70)
    print("【Part 1】スコア差の全体分布（before予測 2020-2025年）")
    print("=" * 70)

    sql = """
    SELECT
        rp1.confidence,
        rp1.total_score - rp2.total_score as score_gap,
        COUNT(*) as cnt
    FROM race_predictions rp1
    JOIN race_predictions rp2 ON rp2.race_id = rp1.race_id
        AND rp2.rank_prediction = 2 AND rp2.prediction_type = 'before'
    JOIN races r ON r.id = rp1.race_id
    WHERE rp1.rank_prediction = 1
    AND rp1.prediction_type = 'before'
    AND r.race_date BETWEEN ? AND ?
    GROUP BY rp1.confidence, CAST(rp1.total_score - rp2.total_score AS INTEGER)
    """

    cursor = conn.cursor()
    cursor.execute(sql, (START_DATE, END_DATE))
    rows = cursor.fetchall()

    # 信頼度別・区間別集計
    dist = {}
    for row in rows:
        conf = row['confidence']
        gap = row['score_gap']
        cnt = row['cnt']
        if conf not in dist:
            dist[conf] = {}
        for gap_min, gap_max, gap_label in SCORE_GAP_BINS:
            if gap is not None and gap_min <= gap < gap_max:
                if gap_label not in dist[conf]:
                    dist[conf][gap_label] = 0
                dist[conf][gap_label] += cnt
                break

    # 全体集計
    total_dist = {}
    for conf_data in dist.values():
        for label, cnt in conf_data.items():
            total_dist[label] = total_dist.get(label, 0) + cnt

    grand_total = sum(total_dist.values())

    print(f"\n信頼度別・スコア差区間別 レース分布（合計: {grand_total:,}件）")
    print()

    # ヘッダー
    confidences = ['A', 'B', 'C', 'D', 'E']
    headers = ['スコア差区間', '全体'] + [f'信頼度{c}' for c in confidences] + ['割合%']
    print(f"{'スコア差区間':<12}", end='')
    print(f"{'全体':>8}", end='')
    for c in confidences:
        print(f"  {f'信頼度{c}':>8}", end='')
    print(f"  {'割合%':>6}")
    print("-" * 70)

    for _, _, gap_label in SCORE_GAP_BINS:
        total_cnt = total_dist.get(gap_label, 0)
        pct = total_cnt / grand_total * 100 if grand_total > 0 else 0
        print(f"{gap_label:<12}", end='')
        print(f"{total_cnt:>8,}", end='')
        for c in confidences:
            cnt = dist.get(c, {}).get(gap_label, 0)
            print(f"  {cnt:>8,}", end='')
        print(f"  {pct:>5.1f}%")

    print()

    # 信頼度別の的中率・ROIもスコア差区間別に分析
    print("\n【スコア差区間別 的中率・ROI（三連単・1点買い換算ベース）】")
    print("※注意: 実際の買い目条件（オッズ範囲等）は考慮していない全データの傾向分析")
    print()

    sql2 = """
    SELECT
        rp1.total_score - rp2.total_score as score_gap,
        rp1.confidence,
        CASE
            WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                THEN CAST(ROUND(t.odds * 100) AS INTEGER)
            ELSE 0
        END as payout,
        CASE
            WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
                THEN 1 ELSE 0
        END as hit
    FROM race_predictions rp1
    JOIN race_predictions rp2 ON rp2.race_id = rp1.race_id
        AND rp2.rank_prediction = 2 AND rp2.prediction_type = 'before'
    JOIN race_predictions rp3 ON rp3.race_id = rp1.race_id
        AND rp3.rank_prediction = 3 AND rp3.prediction_type = 'before'
    JOIN races r ON r.id = rp1.race_id
    LEFT JOIN results res1 ON res1.race_id = r.id AND res1.pit_number = rp1.pit_number
    LEFT JOIN results res2 ON res2.race_id = r.id AND res2.pit_number = rp2.pit_number
    LEFT JOIN results res3 ON res3.race_id = r.id AND res3.pit_number = rp3.pit_number
    LEFT JOIN trifecta_odds t ON t.race_id = r.id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
            || CAST(rp2.pit_number AS TEXT) || '-'
            || CAST(rp3.pit_number AS TEXT)
    WHERE rp1.rank_prediction = 1
    AND rp1.prediction_type = 'before'
    AND r.race_date BETWEEN ? AND ?
    AND res1.is_invalid = 0
    AND t.odds IS NOT NULL
    """

    cursor.execute(sql2, (START_DATE, END_DATE))
    rows2 = cursor.fetchall()

    # 区間別集計
    bin_data = {label: {'count': 0, 'hits': 0, 'payouts': 0} for _, _, label in SCORE_GAP_BINS}
    conf_bin_data = {}

    for row in rows2:
        gap = row['score_gap']
        conf = row['confidence']
        hit = row['hit']
        payout = row['payout']

        for gap_min, gap_max, gap_label in SCORE_GAP_BINS:
            if gap is not None and gap_min <= gap < gap_max:
                bin_data[gap_label]['count'] += 1
                bin_data[gap_label]['hits'] += hit
                bin_data[gap_label]['payouts'] += payout
                # 信頼度別
                if conf not in conf_bin_data:
                    conf_bin_data[conf] = {}
                if gap_label not in conf_bin_data[conf]:
                    conf_bin_data[conf][gap_label] = {'count': 0, 'hits': 0, 'payouts': 0}
                conf_bin_data[conf][gap_label]['count'] += 1
                conf_bin_data[conf][gap_label]['hits'] += hit
                conf_bin_data[conf][gap_label]['payouts'] += payout
                break

    print(f"{'スコア差区間':<12} {'件数':>7} {'的中':>5} {'的中率':>7} {'ROI':>8} {'収支':>10}")
    print("-" * 55)

    for _, _, gap_label in SCORE_GAP_BINS:
        d = bin_data[gap_label]
        if d['count'] == 0:
            continue
        hit_rate = d['hits'] / d['count'] * 100
        bet_total = d['count'] * 100  # 1点買い換算
        roi = d['payouts'] / bet_total * 100 if bet_total > 0 else 0
        profit = d['payouts'] - bet_total
        print(f"{gap_label:<12} {d['count']:>7,} {d['hits']:>5} {hit_rate:>6.2f}% {roi:>7.1f}% {profit:>+10,}")

    print()
    print("【信頼度別・スコア差区間別 的中率・ROI】")
    print()

    for conf in ['A', 'B', 'C', 'D']:
        if conf not in conf_bin_data:
            continue
        print(f"  信頼度 {conf}:")
        print(f"  {'スコア差区間':<12} {'件数':>7} {'的中率':>7} {'ROI':>8}")
        print(f"  {'-'*38}")
        for _, _, gap_label in SCORE_GAP_BINS:
            if gap_label not in conf_bin_data[conf]:
                continue
            d = conf_bin_data[conf][gap_label]
            if d['count'] == 0:
                continue
            hit_rate = d['hits'] / d['count'] * 100
            bet_total = d['count'] * 100
            roi = d['payouts'] / bet_total * 100 if bet_total > 0 else 0
            print(f"  {gap_label:<12} {d['count']:>7,} {hit_rate:>6.2f}% {roi:>7.1f}%")
        print()


def main():
    print("TJ-4: 予測スコア差の条件別閾値最適化分析")
    print(f"期間: {START_DATE} ～ {END_DATE}")
    print()

    conn = get_db_connection()

    # Part 1: 全体のスコア差分布
    analyze_overall_score_gap_distribution(conn)

    # Part 2: 各条件のスコア差区間別パフォーマンス
    print("\n" + "=" * 70)
    print("【Part 2】各条件のスコア差区間別パフォーマンス")
    print("=" * 70)

    for cond in STANDARD_BET_CONDITIONS:
        print(f"\n--- {cond['name']} ({cond['id']}) ---")
        method = "パターンH（400円）" if cond.get('use_pattern_h') else "1点買い（100円）"
        print(f"    買い方: {method}")
        print(f"    信頼度: {cond.get('confidence', '全体')}, "
              f"オッズ: {cond['odds_min']}-{cond['odds_max']}")

        results = analyze_condition_by_score_gap(conn, cond)
        if not results:
            print("    データなし")
            continue

        print(f"    {'区間':<12} {'件数':>6} {'的中':>5} {'的中率':>7} {'ROI':>8} {'収支':>10}")
        print(f"    {'-'*50}")
        for r in results:
            marker = ""
            if r['roi'] >= 150:
                marker = " ★"
            elif r['roi'] >= 120:
                marker = " ◎"
            print(f"    {r['gap_label']:<12} {r['count']:>6} {r['hits']:>5} "
                  f"{r['hit_rate']:>6.2f}% {r['roi']:>7.1f}% {r['profit']:>+10,}{marker}")

    # Part 3: スコア差閾値フィルターの効果試算
    print("\n" + "=" * 70)
    print("【Part 3】スコア差閾値フィルター追加時のROI改善試算")
    print("=" * 70)

    # 各条件で最適な閾値を探す
    best_thresholds = {}

    for cond in STANDARD_BET_CONDITIONS:
        print(f"\n--- {cond['name']} ({cond['id']}) ---")
        method = "パターンH（400円）" if cond.get('use_pattern_h') else "1点買い（100円）"
        print(f"    買い方: {method}")

        results = analyze_score_gap_threshold_effect(conn, cond)
        if not results or len(results) <= 1:
            print("    データなし / 分析不可")
            continue

        # ベースライン
        baseline = results[0]
        print(f"    ベースライン: 件数={baseline['count']:,}, "
              f"ROI={baseline['roi']:.1f}%, 収支={baseline['profit']:+,}円")
        print()
        print(f"    {'閾値':<20} {'件数':>6} {'削減':>6} {'的中率':>7} "
              f"{'ROI':>8} {'ROI変化':>8} {'収支変化':>10}")
        print(f"    {'-'*70}")

        best_roi = baseline['roi']
        best_threshold = None
        best_profit = baseline['profit']

        for r in results[1:]:  # ベースラインをスキップ
            # 最低サンプル数チェック（20件以上）
            if r['count'] < 20:
                continue

            roi_marker = ""
            if r['roi_change'] > 0:
                roi_marker = " +"
            if r['roi'] > best_roi and r['count'] >= 20:
                best_roi = r['roi']
                best_threshold = r['threshold']
                best_profit = r['profit']
                roi_marker = " ★"

            print(f"    {r['label']:<20} {r['count']:>6} {r['count_reduction']:>+6} "
                  f"{r['hit_rate']:>6.2f}% {r['roi']:>7.1f}% "
                  f"{r['roi_change']:>+7.1f}pt {r['profit_change']:>+10,}{roi_marker}")

        if best_threshold is not None:
            print(f"\n    推奨閾値: スコア差 ≥ {best_threshold}pt "
                  f"(ROI {best_roi:.1f}%, 件数 {results[0]['count']}→削減後, "
                  f"収支 {best_profit:+,}円)")
            best_thresholds[cond['id']] = {
                'cond_name': cond['name'],
                'threshold': best_threshold,
                'roi_base': baseline['roi'],
                'roi_best': best_roi,
                'roi_change': best_roi - baseline['roi'],
            }
        else:
            print("\n    推奨閾値: なし（フィルターなしが最適）")
            best_thresholds[cond['id']] = {
                'cond_name': cond['name'],
                'threshold': None,
                'roi_base': baseline['roi'],
                'roi_best': baseline['roi'],
                'roi_change': 0,
            }

    # Part 4: 総合推奨
    print("\n" + "=" * 70)
    print("【Part 4】採用推奨閾値 サマリー")
    print("=" * 70)
    print()
    print(f"{'条件':<30} {'現行ROI':>8} {'推奨閾値':>10} {'改善ROI':>8} {'改善幅':>8}")
    print("-" * 70)

    for cond_id, info in best_thresholds.items():
        threshold_str = f"≥{info['threshold']}pt" if info['threshold'] else "なし"
        change_str = f"{info['roi_change']:+.1f}pt" if info['roi_change'] != 0 else "  -"
        marker = " ★" if info['roi_change'] >= 5 else ""
        print(f"{info['cond_name'][:30]:<30} {info['roi_base']:>7.1f}% "
              f"{threshold_str:>10} {info['roi_best']:>7.1f}% {change_str:>8}{marker}")

    print()
    print("★ = ROI改善幅 5pt以上の有望な閾値")
    print()
    print("【採用基準】")
    print("  - ROI改善幅 ≥ 5pt")
    print("  - フィルター後のサンプル数 ≥ 20件")
    print("  - 収支がプラス方向に改善")
    print()
    print("【注意】")
    print("  - スコア差フィルター追加は過去データへの過学習リスクあり")
    print("  - Tier 1（2年間）→ Tier 2（6年間）の順で検証を推奨")
    print("  - サンプル数が少ない場合は統計的信頼性が低い")

    conn.close()
    print("\n分析完了")


if __name__ == '__main__':
    main()
