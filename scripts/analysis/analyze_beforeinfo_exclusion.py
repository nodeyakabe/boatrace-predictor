# -*- coding: utf-8 -*-
"""
直前情報を活用した除外条件探索
==============================

展示情報・天候情報・モーター情報などの直前情報を使った
除外条件を探索する。

目的:
    - 既存条件＋直前情報で不的中レースを除外
    - 収益改善の可能性を定量化

使用例:
    python scripts/analysis/analyze_beforeinfo_exclusion.py
"""

import sqlite3
import sys
import io
import os
from datetime import datetime
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def analyze_motor_exclusion(cursor, cond, year_start=2020, year_end=2025):
    """モーター2連率による除外効果を検証"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            substr(r.race_date, 1, 4) as year,
            e1.motor_second_rate as motor_rate,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = rb.race_id
                 AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                ), 0
            ) as pred_odds,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN 1 ELSE 0
            END as is_hit,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM race_base rb
    )
    SELECT
        CASE
            WHEN motor_rate < 25 THEN '0-25'
            WHEN motor_rate < 30 THEN '25-30'
            WHEN motor_rate < 35 THEN '30-35'
            WHEN motor_rate < 40 THEN '35-40'
            WHEN motor_rate < 45 THEN '40-45'
            ELSE '45+'
        END as motor_band,
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) as total_payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    GROUP BY motor_band
    ORDER BY motor_band
    '''
    cursor.execute(query)
    return cursor.fetchall()


def analyze_wind_exclusion(cursor, cond, year_start=2020, year_end=2025):
    """風速による除外効果を検証"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            substr(r.race_date, 1, 4) as year,
            w.wind_speed,
            w.wind_direction,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
        WHERE rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = rb.race_id
                 AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                ), 0
            ) as pred_odds,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN 1 ELSE 0
            END as is_hit,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM race_base rb
    )
    SELECT
        CASE
            WHEN wind_speed IS NULL THEN 'NULL'
            WHEN wind_speed < 2 THEN '0-2m'
            WHEN wind_speed < 4 THEN '2-4m'
            WHEN wind_speed < 6 THEN '4-6m'
            ELSE '6m+'
        END as wind_band,
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) as total_payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    GROUP BY wind_band
    ORDER BY wind_band
    '''
    cursor.execute(query)
    return cursor.fetchall()


def analyze_exhibition_exclusion(cursor, cond, year_start=2020, year_end=2025):
    """展示タイム差による除外効果を検証"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            substr(r.race_date, 1, 4) as year,
            ex1.exhibition_time as ex_time_1,
            (SELECT MIN(exhibition_time) FROM exhibition_data WHERE race_id = r.id) as ex_time_min,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN exhibition_data ex1 ON r.id = ex1.race_id AND ex1.pit_number = 1
        WHERE rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            CASE WHEN ex_time_1 > 0 AND ex_time_min > 0 THEN ex_time_1 - ex_time_min ELSE NULL END as ex_diff,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = rb.race_id
                 AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                ), 0
            ) as pred_odds,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN 1 ELSE 0
            END as is_hit,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM race_base rb
    )
    SELECT
        CASE
            WHEN ex_diff IS NULL THEN 'NULL'
            WHEN ex_diff <= 0 THEN '1着最速'
            WHEN ex_diff < 0.05 THEN '0-0.05秒差'
            WHEN ex_diff < 0.10 THEN '0.05-0.10秒差'
            WHEN ex_diff < 0.15 THEN '0.10-0.15秒差'
            ELSE '0.15秒+差'
        END as ex_band,
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) as total_payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    GROUP BY ex_band
    ORDER BY ex_band
    '''
    cursor.execute(query)
    return cursor.fetchall()


def analyze_start_timing_exclusion(cursor, cond, year_start=2020, year_end=2025):
    """スタートタイミングによる除外効果を検証"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            substr(r.race_date, 1, 4) as year,
            ex1.start_timing as st_1,
            (SELECT MIN(start_timing) FROM exhibition_data WHERE race_id = r.id AND start_timing > 0) as st_min,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN exhibition_data ex1 ON r.id = ex1.race_id AND ex1.pit_number = 1
        WHERE rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
    ),
    race_bets AS (
        SELECT
            rb.*,
            CASE
                WHEN st_1 IS NULL OR st_1 <= 0 THEN NULL
                WHEN st_min IS NULL OR st_min <= 0 THEN NULL
                ELSE st_1 - st_min
            END as st_diff,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = rb.race_id
                 AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                ), 0
            ) as pred_odds,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN 1 ELSE 0
            END as is_hit,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                 AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM race_base rb
    )
    SELECT
        CASE
            WHEN st_diff IS NULL THEN 'NULL'
            WHEN st_diff <= 0 THEN '1コース最速'
            WHEN st_diff < 5 THEN '0-5遅れ'
            WHEN st_diff < 10 THEN '5-10遅れ'
            WHEN st_diff < 15 THEN '10-15遅れ'
            ELSE '15+遅れ'
        END as st_band,
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) as total_payout
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    GROUP BY st_band
    ORDER BY st_band
    '''
    cursor.execute(query)
    return cursor.fetchall()


def main():
    print("=" * 80)
    print("直前情報を活用した除外条件探索")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 主要条件を分析
    conditions = [
        {'name': 'D×35-60', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'],
         'odds_min': 35, 'odds_max': 60, 'race_exclude': [9], 'venue_exclude': [10]},
        {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'],
         'odds_min': 40, 'odds_max': 50},
        {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'],
         'odds_min': 20, 'odds_max': 30,
         'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},
        {'name': 'D×5コース予測', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1', 'B2'],
         'odds_min': 10, 'odds_max': 200, 'predicted_course': 5},
    ]

    for cond in conditions:
        print(f"\n{'='*70}")
        print(f"条件: {cond['name']}")
        print("=" * 70)

        # モーター2連率分析
        print("\n--- 1コース モーター2連率別 ---")
        results = analyze_motor_exclusion(cursor, cond)
        for row in results:
            band, bets, hits, payout = row
            hits = hits or 0
            payout = payout or 0
            invest = bets * 100
            roi = payout / invest * 100 if invest > 0 else 0
            profit = payout - invest
            hit_rate = hits / bets * 100 if bets > 0 else 0
            print(f"  {band}%: {bets}件, {hits}的中 ({hit_rate:.1f}%), ROI {roi:.1f}%, {profit:+,.0f}円")

        # 風速分析
        print("\n--- 風速別 ---")
        results = analyze_wind_exclusion(cursor, cond)
        for row in results:
            band, bets, hits, payout = row
            hits = hits or 0
            payout = payout or 0
            invest = bets * 100
            roi = payout / invest * 100 if invest > 0 else 0
            profit = payout - invest
            hit_rate = hits / bets * 100 if bets > 0 else 0
            print(f"  {band}: {bets}件, {hits}的中 ({hit_rate:.1f}%), ROI {roi:.1f}%, {profit:+,.0f}円")

        # 展示タイム差分析
        print("\n--- 1コース展示タイム差（最速との差）---")
        results = analyze_exhibition_exclusion(cursor, cond)
        for row in results:
            band, bets, hits, payout = row
            hits = hits or 0
            payout = payout or 0
            invest = bets * 100
            roi = payout / invest * 100 if invest > 0 else 0
            profit = payout - invest
            hit_rate = hits / bets * 100 if bets > 0 else 0
            print(f"  {band}: {bets}件, {hits}的中 ({hit_rate:.1f}%), ROI {roi:.1f}%, {profit:+,.0f}円")

        # スタートタイミング分析
        print("\n--- 1コース スタートタイミング差（最速との差）---")
        results = analyze_start_timing_exclusion(cursor, cond)
        for row in results:
            band, bets, hits, payout = row
            hits = hits or 0
            payout = payout or 0
            invest = bets * 100
            roi = payout / invest * 100 if invest > 0 else 0
            profit = payout - invest
            hit_rate = hits / bets * 100 if bets > 0 else 0
            print(f"  {band}: {bets}件, {hits}的中 ({hit_rate:.1f}%), ROI {roi:.1f}%, {profit:+,.0f}円")

    conn.close()

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
