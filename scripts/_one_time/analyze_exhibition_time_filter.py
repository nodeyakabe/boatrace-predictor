#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
案A: 展示タイム差フィルタ分析

各購入条件に対して、展示タイム差（1位-2位）の閾値を追加した場合のROI変化を分析する。
目的: exh_time_diff >= X のフィルタが有効かどうかを検証（全条件、6年間）

使用方法:
    python scripts/_one_time/analyze_exhibition_time_filter.py
"""
import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition


def get_exh_time_diff(cursor, race_ids):
    """
    指定レースIDの展示タイム差（1位-2位）を取得
    Returns: {race_id: exh_time_diff}
    """
    if not race_ids:
        return {}

    placeholders = ','.join(['?'] * len(race_ids))
    cursor.execute(f"""
        SELECT race_id,
               MIN(exhibition_time) as best_time,
               MIN(CASE WHEN rn = 2 THEN exhibition_time END) as second_time
        FROM (
            SELECT race_id, exhibition_time,
                   ROW_NUMBER() OVER (PARTITION BY race_id ORDER BY exhibition_time ASC) as rn
            FROM race_details
            WHERE race_id IN ({placeholders})
            AND exhibition_time IS NOT NULL
        ) ranked
        GROUP BY race_id
        HAVING second_time IS NOT NULL
    """, list(race_ids))

    result = {}
    for row in cursor.fetchall():
        race_id, best, second = row
        if best is not None and second is not None:
            result[race_id] = second - best
    return result


def calculate_performance(cursor, cond, race_ids):
    """指定レースIDのみで条件成績を計算（standard_backtest_uniqueと同じロジック）"""
    if not race_ids:
        return {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}

    use_pattern_h = cond.get('use_pattern_h', True)
    placeholders = ','.join(['?'] * len(race_ids))

    if use_pattern_h:
        query = f"""
        WITH race_bets AS (
            SELECT r.id as race_id,
                rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
                rp4.pit_number as p4, rp5.pit_number as p5,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)), 0) as odds_123,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)), 0) as odds_124,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp5.pit_number AS TEXT)), 0) as odds_125,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
            JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type='before' AND rp5.rank_prediction=5
            WHERE r.id IN ({placeholders})
        )
        SELECT
            SUM(CASE WHEN (bet_123>0 OR bet_124>0 OR bet_125>0) THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_123+bet_124+bet_125) as investment,
            SUM(pay_123+pay_124+pay_125) as payout
        FROM (
            SELECT *,
                CASE WHEN odds_123>={cond['odds_min']} AND odds_123<{cond['odds_max']} THEN 200 ELSE 0 END as bet_123,
                CASE WHEN odds_124>={cond['odds_min']} AND odds_124<{cond['odds_max']} THEN 100 ELSE 0 END as bet_124,
                CASE WHEN odds_125>={cond['odds_min']} AND odds_125<{cond['odds_max']} THEN 100 ELSE 0 END as bet_125,
                CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p3 AND odds_123>={cond['odds_min']} AND odds_123<{cond['odds_max']} THEN odds_123*200 ELSE 0 END as pay_123,
                CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p4 AND odds_124>={cond['odds_min']} AND odds_124<{cond['odds_max']} THEN odds_124*100 ELSE 0 END as pay_124,
                CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p5 AND odds_125>={cond['odds_min']} AND odds_125<{cond['odds_max']} THEN odds_125*100 ELSE 0 END as pay_125,
                CASE
                    WHEN (actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p3 AND odds_123>={cond['odds_min']} AND odds_123<{cond['odds_max']})
                      OR (actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p4 AND odds_124>={cond['odds_min']} AND odds_124<{cond['odds_max']})
                      OR (actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p5 AND odds_125>={cond['odds_min']} AND odds_125<{cond['odds_max']})
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        ) WHERE bet_123>0 OR bet_124>0 OR bet_125>0
        """
    else:
        query = f"""
        WITH race_bets AS (
            SELECT r.id as race_id,
                rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)), 0) as odds_123,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
            WHERE r.id IN ({placeholders})
        )
        SELECT
            SUM(CASE WHEN odds_123>={cond['odds_min']} AND odds_123<{cond['odds_max']} THEN 1 ELSE 0 END) as bets,
            SUM(CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p3 AND odds_123>={cond['odds_min']} AND odds_123<{cond['odds_max']} THEN 1 ELSE 0 END) as hits,
            SUM(CASE WHEN odds_123>={cond['odds_min']} AND odds_123<{cond['odds_max']} THEN 100 ELSE 0 END) as investment,
            SUM(CASE WHEN actual_1st=p1 AND actual_2nd=p2 AND actual_3rd=p3 AND odds_123>={cond['odds_min']} AND odds_123<{cond['odds_max']} THEN odds_123*100 ELSE 0 END) as payout
        FROM race_bets
        WHERE odds_123>={cond['odds_min']} AND odds_123<{cond['odds_max']}
        """

    cursor.execute(query, list(race_ids))
    row = cursor.fetchone()
    if row and row[0] and row[0] > 0:
        return {'bets': row[0] or 0, 'hits': row[1] or 0, 'investment': row[2] or 0, 'payout': row[3] or 0}
    return {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}


def compute_roi(perf):
    if perf['investment'] > 0:
        return 100.0 * perf['payout'] / perf['investment']
    return 0.0


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    START_DATE = "2020-01-01"
    END_DATE = "2026-01-01"

    # 展示タイム差の閾値リスト（0=フィルタなし）
    THRESHOLDS = [0.0, 0.03, 0.05, 0.07, 0.10]

    print("=" * 100)
    print("案A: 展示タイム差フィルタ分析（exh_time_diff >= threshold）")
    print(f"期間: {START_DATE} ～ {END_DATE}")
    print("=" * 100)

    all_summary = []  # 全条件の合計

    for cond in STANDARD_BET_CONDITIONS:
        print(f"\n{'─'*80}")
        print(f"[{cond['id']}] {cond['name']}")
        print(f"{'─'*80}")

        # 条件に該当するレースIDを取得
        race_ids = get_race_ids_for_condition(cursor, cond, START_DATE, END_DATE)
        if not race_ids:
            print("  → 対象レースなし")
            continue

        # 各レースの展示タイム差を取得
        exh_diffs = get_exh_time_diff(cursor, race_ids)
        total_races = len(race_ids)
        races_with_exh = len(exh_diffs)
        print(f"  総対象レース数: {total_races:,} | 展示タイムあり: {races_with_exh:,} ({100*races_with_exh/total_races:.1f}%)")

        # 閾値ごとの分析
        results_by_threshold = []
        for threshold in THRESHOLDS:
            if threshold == 0.0:
                filtered_ids = list(race_ids)
                label = "全件(フィルタなし)"
            else:
                filtered_ids = [rid for rid, diff in exh_diffs.items() if diff >= threshold]
                # exh_dataがないレースは除外（保守的に）
                label = f">={threshold:.2f}s"

            if not filtered_ids:
                print(f"  {label:<18}: 対象なし")
                continue

            perf = calculate_performance(cursor, cond, filtered_ids)
            roi = compute_roi(perf)
            profit = perf['payout'] - perf['investment']

            results_by_threshold.append({
                'threshold': threshold,
                'label': label,
                'total_filtered': len(filtered_ids),
                'bets': perf['bets'],
                'hits': perf['hits'],
                'roi': roi,
                'profit': profit,
            })

        # 表示
        print(f"  {'閾値':<20} {'対象レース':>8} {'購入件数':>8} {'的中':>6} {'ROI':>8} {'収支':>10}")
        print(f"  {'─'*62}")
        base_roi = 0
        for r in results_by_threshold:
            diff_str = ""
            if r['threshold'] > 0 and base_roi > 0:
                diff = r['roi'] - base_roi
                diff_str = f"  ({diff:+.1f}pt)"
            elif r['threshold'] == 0:
                base_roi = r['roi']

            print(f"  {r['label']:<20} {r['total_filtered']:>8,} {r['bets']:>8,} {r['hits']:>6} {r['roi']:>8.1f}%  {r['profit']:>+10,}{diff_str}")

    # 全体の集計（exh_time_diff >= 0.05）
    print("\n" + "=" * 100)
    print("【全体集計】各閾値での全条件合計")
    print("=" * 100)

    total_base = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}

    for threshold in THRESHOLDS:
        total = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
        for cond in STANDARD_BET_CONDITIONS:
            race_ids = get_race_ids_for_condition(cursor, cond, START_DATE, END_DATE)
            if not race_ids:
                continue
            if threshold == 0.0:
                filtered_ids = list(race_ids)
            else:
                exh_diffs = get_exh_time_diff(cursor, race_ids)
                filtered_ids = [rid for rid, diff in exh_diffs.items() if diff >= threshold]
            if not filtered_ids:
                continue
            perf = calculate_performance(cursor, cond, filtered_ids)
            for k in ['bets', 'hits', 'investment', 'payout']:
                total[k] += perf[k]

        roi = 100.0 * total['payout'] / total['investment'] if total['investment'] > 0 else 0
        profit = total['payout'] - total['investment']
        if threshold == 0.0:
            total_base = total.copy()
            diff_str = ""
        else:
            diff_roi = roi - (100.0 * total_base['payout'] / total_base['investment'] if total_base['investment'] > 0 else 0)
            diff_bets = total['bets'] - total_base['bets']
            diff_profit = profit - (total_base['payout'] - total_base['investment'])
            diff_str = f"  (件数{diff_bets:+,} ROI{diff_roi:+.1f}pt 収支{diff_profit:+,}円)"

        label = "全件" if threshold == 0.0 else f">={threshold:.2f}s"
        print(f"  {label:<12}: {total['bets']:>6,}件  ROI {roi:>7.1f}%  収支 {profit:>+10,}円{diff_str}")

    conn.close()


if __name__ == '__main__':
    main()
