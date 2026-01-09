#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""冬季専用ロジック検証スクリプト"""
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
    print('冬季（12,1,2月）B×50-100 専用ロジック検証')
    print('=' * 70)
    print()

    # 1. 買い目点数削減検証
    print('【1. 買い目点数削減検証】')
    print('-' * 70)

    # 3点買い（現状）
    cursor.execute('''
    WITH race_base AS (
        SELECT r.id as race_id, rp1.pit_number as p1, rp2.pit_number as p2,
               rp3.pit_number as p3, rp4.pit_number as p4, rp5.pit_number as p5
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
        AND CAST(strftime('%m', r.race_date) AS INTEGER) IN (12, 1, 2)
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
    )
    SELECT
        COUNT(*) as races,
        SUM(CASE WHEN odds_123 >= 50 AND odds_123 < 100 THEN 200 ELSE 0 END +
            CASE WHEN odds_124 >= 50 AND odds_124 < 100 THEN 100 ELSE 0 END +
            CASE WHEN odds_125 >= 50 AND odds_125 < 100 THEN 100 ELSE 0 END) as investment,
        SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100
                THEN odds_123 * 200 ELSE 0 END +
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= 50 AND odds_124 < 100
                THEN odds_124 * 100 ELSE 0 END +
            CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= 50 AND odds_125 < 100
                THEN odds_125 * 100 ELSE 0 END) as payout
    FROM race_with_odds
    WHERE odds_123 >= 50 AND odds_123 < 100
    ''')
    row = cursor.fetchone()
    roi = 100.0 * row[2] / row[1] if row[1] else 0
    profit = row[2] - row[1] if row[1] else 0
    print(f'3点(現状)       件数:{row[0]:>4}  投資:{row[1]:>8,}  ROI:{roi:>6.1f}%  収支:{profit:>+10,.0f}')

    # 1点買い
    cursor.execute('''
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
        SUM(CASE WHEN odds_123 >= 50 AND odds_123 < 100 THEN 100 ELSE 0 END) as investment,
        SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100
                THEN odds_123 * 100 ELSE 0 END) as payout
    FROM race_with_odds
    WHERE odds_123 >= 50 AND odds_123 < 100
    ''')
    row = cursor.fetchone()
    roi = 100.0 * row[2] / row[1] if row[1] else 0
    profit = row[2] - row[1] if row[1] else 0
    print(f'1点(1-2-3)      件数:{row[0]:>4}  投資:{row[1]:>8,}  ROI:{roi:>6.1f}%  収支:{profit:>+10,.0f}')

    print()

    # 2. B上位（スコア差>=50）の冬専用
    print('【2. B上位（スコア差>=50）の冬専用】')
    print('-' * 70)

    cursor.execute('''
    WITH race_base AS (
        SELECT r.id as race_id, rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
               (rp1.total_score - rp2.total_score) as score_diff
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
        SUM(CASE WHEN odds_123 >= 50 AND odds_123 < 100 THEN 100 ELSE 0 END) as investment,
        SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100
                THEN odds_123 * 100 ELSE 0 END) as payout
    FROM race_with_odds
    WHERE odds_123 >= 50 AND odds_123 < 100
    ''')
    row = cursor.fetchone()
    roi = 100.0 * row[2] / row[1] if row[1] else 0
    profit = row[2] - row[1] if row[1] else 0
    print(f'B+(スコア差>=50) 1点  件数:{row[0]:>4}  投資:{row[1]:>8,}  ROI:{roi:>6.1f}%  収支:{profit:>+10,.0f}')

    print()

    # 3. 1コース勝率によるフィルター
    print('【3. 1コース勝率フィルター（逃げ率代用）】')
    print('-' * 70)

    for win_rate_min in [5.5, 6.0, 6.5, 7.0]:
        cursor.execute(f'''
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
            AND e1.win_rate >= {win_rate_min}
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
            SUM(CASE WHEN odds_123 >= 50 AND odds_123 < 100 THEN 100 ELSE 0 END) as investment,
            SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100
                    THEN odds_123 * 100 ELSE 0 END) as payout
        FROM race_with_odds
        WHERE odds_123 >= 50 AND odds_123 < 100
        ''')
        row = cursor.fetchone()
        roi = 100.0 * row[2] / row[1] if row[1] else 0
        profit = row[2] - row[1] if row[1] else 0
        print(f'win_rate>={win_rate_min}    件数:{row[0]:>4}  投資:{row[1]:>8,}  ROI:{roi:>6.1f}%  収支:{profit:>+10,.0f}')

    print()

    # 4. 複合条件（冬専用ロジック候補）
    print('【4. 複合条件（冬専用ロジック候補）】')
    print('-' * 70)

    # 案A: B+ + 1点買い + 40-70倍
    cursor.execute('''
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
    ''')
    row = cursor.fetchone()
    roi = 100.0 * row[2] / row[1] if row[1] else 0
    profit = row[2] - row[1] if row[1] else 0
    print(f'案A: B+×40-70×1点     件数:{row[0]:>4}  投資:{row[1]:>8,}  ROI:{roi:>6.1f}%  収支:{profit:>+10,.0f}')

    # 案B: win_rate>=6.5 + 1点買い + 50-100倍
    cursor.execute('''
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
        AND e1.win_rate >= 6.5
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
        SUM(CASE WHEN odds_123 >= 50 AND odds_123 < 100 THEN 100 ELSE 0 END) as investment,
        SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100
                THEN odds_123 * 100 ELSE 0 END) as payout
    FROM race_with_odds
    WHERE odds_123 >= 50 AND odds_123 < 100
    ''')
    row = cursor.fetchone()
    roi = 100.0 * row[2] / row[1] if row[1] else 0
    profit = row[2] - row[1] if row[1] else 0
    print(f'案B: win>=6.5×50-100×1点  件数:{row[0]:>4}  投資:{row[1]:>8,}  ROI:{roi:>6.1f}%  収支:{profit:>+10,.0f}')

    # 案C: B+ + win_rate>=6.0 + 1点買い
    cursor.execute('''
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
        AND e1.win_rate >= 6.0
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
        SUM(CASE WHEN odds_123 >= 50 AND odds_123 < 100 THEN 100 ELSE 0 END) as investment,
        SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100
                THEN odds_123 * 100 ELSE 0 END) as payout
    FROM race_with_odds
    WHERE odds_123 >= 50 AND odds_123 < 100
    ''')
    row = cursor.fetchone()
    if row[1] and row[1] > 0:
        roi = 100.0 * row[2] / row[1]
        profit = row[2] - row[1]
        print(f'案C: B+×win>=6.0×1点   件数:{row[0]:>4}  投資:{row[1]:>8,}  ROI:{roi:>6.1f}%  収支:{profit:>+10,.0f}')
    else:
        print(f'案C: B+×win>=6.0×1点   件数:0')

    print()

    # 5. 年度別安定性確認
    print('【5. 年度別安定性確認（案C: B+×win>=6.0×1点）】')
    print('-' * 70)

    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        cursor.execute(f'''
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
            AND e1.win_rate >= 6.0
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
            SUM(CASE WHEN odds_123 >= 50 AND odds_123 < 100 THEN 100 ELSE 0 END) as investment,
            SUM(CASE WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100
                    THEN odds_123 * 100 ELSE 0 END) as payout
        FROM race_with_odds
        WHERE odds_123 >= 50 AND odds_123 < 100
        ''')
        row = cursor.fetchone()
        if row[1] and row[1] > 0:
            roi = 100.0 * row[2] / row[1]
            profit = row[2] - row[1]
            mark = '○' if profit >= 0 else '×'
            print(f'{year}年冬: 件数={row[0]:>3}, ROI={roi:>6.1f}%, 収支={profit:>+8,.0f} {mark}')
        else:
            print(f'{year}年冬: 件数=0')

    conn.close()

    print()
    print('=' * 70)
    print('検証完了')

if __name__ == '__main__':
    main()
