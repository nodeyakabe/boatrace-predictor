#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""冬季専用ロジック検証スクリプト v2"""
import sqlite3
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print('=' * 70)
    print('案A（B+×40-70倍×1点）年度別安定性')
    print('=' * 70)
    print()

    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        cursor.execute(f"""
        WITH race_base AS (
            SELECT r.id as race_id, rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            WHERE rp.confidence = 'B' AND e1.racer_rank IN ('A1', 'B1')
            AND r.race_date >= '{year}-01-01' AND r.race_date < '{year+1}-01-01'
            AND CAST(strftime('%m', r.race_date) AS INTEGER) IN (12, 1, 2)
            AND (rp1.total_score - rp2.total_score) >= 50
        ),
        race_with_odds AS (
            SELECT rb.*,
                COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                          AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
            FROM race_base rb
        )
        SELECT
            COUNT(*) as races,
            SUM(CASE WHEN odds_123 >= 40 AND odds_123 < 70 THEN 100 ELSE 0 END) as investment,
            SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 40 AND odds_123 < 70
                    THEN odds_123 * 100 ELSE 0 END) as payout
        FROM race_with_odds
        WHERE odds_123 >= 40 AND odds_123 < 70
        """)
        row = cursor.fetchone()
        if row[1] and row[1] > 0:
            roi = 100.0 * row[2] / row[1]
            profit = row[2] - row[1]
            mark = '○' if profit >= 0 else '×'
            print(f'{year}年冬: 件数={row[0]:>3}, ROI={roi:>6.1f}%, 収支={profit:>+8,.0f} {mark}')
        else:
            print(f'{year}年冬: 件数=0')

    print()
    print('=' * 70)
    print('通年との比較')
    print('=' * 70)
    print()

    # 春夏秋（通年ロジック50-100倍×パターンH）
    cursor.execute("""
    WITH race_base AS (
        SELECT r.id as race_id, rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
               rp4.pit_number as p4, rp5.pit_number as p5
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.confidence = 'B' AND e1.racer_rank IN ('A1', 'B1')
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (12, 1, 2)
    ),
    race_with_odds AS (
        SELECT rb.*,
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
        SELECT *,
            CASE WHEN odds_123 >= 50 AND odds_123 < 100 THEN 200 ELSE 0 END as bet_123,
            CASE WHEN odds_124 >= 50 AND odds_124 < 100 THEN 100 ELSE 0 END as bet_124,
            CASE WHEN odds_125 >= 50 AND odds_125 < 100 THEN 100 ELSE 0 END as bet_125,
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100
                THEN odds_123 * 200 ELSE 0 END as payout_123,
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= 50 AND odds_124 < 100
                THEN odds_124 * 100 ELSE 0 END as payout_124,
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= 50 AND odds_125 < 100
                THEN odds_125 * 100 ELSE 0 END as payout_125
        FROM race_with_odds
    )
    SELECT
        COUNT(*) as races,
        SUM(bet_123 + bet_124 + bet_125) as investment,
        SUM(payout_123 + payout_124 + payout_125) as payout
    FROM race_payouts
    WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
    """)
    row = cursor.fetchone()
    roi = 100.0 * row[2] / row[1] if row[1] else 0
    profit = row[2] - row[1] if row[1] else 0
    print(f'春夏秋（通年ロジック）: 件数={row[0]:>4}, ROI={roi:>6.1f}%, 収支={profit:>+10,.0f}')

    # 冬専用ロジック
    cursor.execute("""
    WITH race_base AS (
        SELECT r.id as race_id, rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.confidence = 'B' AND e1.racer_rank IN ('A1', 'B1')
        AND r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
        AND CAST(strftime('%m', r.race_date) AS INTEGER) IN (12, 1, 2)
        AND (rp1.total_score - rp2.total_score) >= 50
    ),
    race_with_odds AS (
        SELECT rb.*,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    )
    SELECT
        COUNT(*) as races,
        SUM(CASE WHEN odds_123 >= 40 AND odds_123 < 70 THEN 100 ELSE 0 END) as investment,
        SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 40 AND odds_123 < 70
                THEN odds_123 * 100 ELSE 0 END) as payout
    FROM race_with_odds
    WHERE odds_123 >= 40 AND odds_123 < 70
    """)
    row = cursor.fetchone()
    roi = 100.0 * row[2] / row[1] if row[1] else 0
    profit = row[2] - row[1] if row[1] else 0
    print(f'冬（冬専用ロジック）:   件数={row[0]:>4}, ROI={roi:>6.1f}%, 収支={profit:>+10,.0f}')

    print()
    print('=' * 70)
    print('組み合わせ効果')
    print('=' * 70)
    print()

    # 春夏秋の成績
    spring_summer_fall_profit = 124610  # 前回計算結果
    winter_profit = profit

    print(f'春夏秋（通年50-100×パターンH）: +124,610円')
    print(f'冬（冬専用40-70×B+×1点）:      {winter_profit:>+,}円')
    print(f'--------------------------------------')
    print(f'合計:                          +{124610 + int(winter_profit):,}円')

    conn.close()

if __name__ == '__main__':
    main()
