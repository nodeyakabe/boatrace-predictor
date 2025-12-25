#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不的中パターン傾向分析スクリプト

目的:
    6年間（2020-2025年）のデータを使用して、各信頼度別の不的中パターンを調査
    - どのような条件で不的中が多いか
    - 避けるべきパターンの特定
    - ROI改善のための除外条件の発見

使用方法:
    python scripts/backtest/analyze_miss_patterns.py
"""
import sqlite3
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


def get_base_data(cursor, confidence):
    """信頼度別の基本データを取得（的中/不的中含む）"""
    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            substr(r.race_date, 1, 4) as year,
            e1.racer_rank as c1_rank,
            e1.motor_second_rate,
            rp.confidence,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_with_result AS (
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
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    )
    SELECT * FROM race_with_result WHERE pred_odds > 0
    '''
    cursor.execute(query)
    return cursor.fetchall()


def analyze_by_c1_rank(cursor, confidence):
    """1コース選手の級別で分析"""
    print(f"\n### 1コース選手の級別別 不的中率（信頼度{confidence}）")
    print("-" * 70)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
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
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_with_result AS (
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
        c1_rank,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        SUM(CASE WHEN is_hit = 0 THEN 1 ELSE 0 END) as misses,
        ROUND(100.0 * SUM(CASE WHEN is_hit = 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as miss_rate,
        ROUND(100.0 * SUM(payout) / (COUNT(*) * 100), 1) as roi
    FROM race_with_result
    WHERE pred_odds >= 10 AND pred_odds < 100
    GROUP BY c1_rank
    ORDER BY miss_rate DESC
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'級別':<6} {'総数':>8} {'的中':>6} {'不的中':>6} {'不的中率':>8} {'ROI':>8}")
    print("-" * 70)
    for row in rows:
        c1_rank, total, hits, misses, miss_rate, roi = row
        print(f"{c1_rank:<6} {total:>8,} {hits:>6} {misses:>6,} {miss_rate:>7.1f}% {roi:>7.1f}%")


def analyze_by_venue(cursor, confidence):
    """会場別で分析"""
    print(f"\n### 会場別 不的中率（信頼度{confidence}）- ワースト10")
    print("-" * 70)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_with_result AS (
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
        venue_code,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        SUM(CASE WHEN is_hit = 0 THEN 1 ELSE 0 END) as misses,
        ROUND(100.0 * SUM(CASE WHEN is_hit = 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as miss_rate,
        ROUND(100.0 * SUM(payout) / (COUNT(*) * 100), 1) as roi
    FROM race_with_result
    WHERE pred_odds >= 10 AND pred_odds < 100
    GROUP BY venue_code
    HAVING COUNT(*) >= 50
    ORDER BY roi ASC
    LIMIT 10
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'会場':<8} {'総数':>8} {'的中':>6} {'不的中':>6} {'不的中率':>8} {'ROI':>8}")
    print("-" * 70)
    for row in rows:
        venue_code, total, hits, misses, miss_rate, roi = row
        venue_name = VENUE_NAMES.get(venue_code, f'会場{venue_code}')
        print(f"{venue_name:<8} {total:>8,} {hits:>6} {misses:>6,} {miss_rate:>7.1f}% {roi:>7.1f}%")


def analyze_by_odds_range(cursor, confidence):
    """オッズ帯別で分析"""
    print(f"\n### オッズ帯別 不的中率と収支（信頼度{confidence}）")
    print("-" * 70)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_with_result AS (
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
            WHEN pred_odds >= 5 AND pred_odds < 10 THEN '05-10'
            WHEN pred_odds >= 10 AND pred_odds < 15 THEN '10-15'
            WHEN pred_odds >= 15 AND pred_odds < 20 THEN '15-20'
            WHEN pred_odds >= 20 AND pred_odds < 30 THEN '20-30'
            WHEN pred_odds >= 30 AND pred_odds < 40 THEN '30-40'
            WHEN pred_odds >= 40 AND pred_odds < 50 THEN '40-50'
            WHEN pred_odds >= 50 AND pred_odds < 70 THEN '50-70'
            WHEN pred_odds >= 70 AND pred_odds < 100 THEN '70-100'
            WHEN pred_odds >= 100 THEN '100+'
            ELSE 'その他'
        END as odds_range,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(payout) / (COUNT(*) * 100), 1) as roi,
        SUM(payout) - (COUNT(*) * 100) as profit
    FROM race_with_result
    WHERE pred_odds >= 5
    GROUP BY odds_range
    ORDER BY
        CASE odds_range
            WHEN '05-10' THEN 1
            WHEN '10-15' THEN 2
            WHEN '15-20' THEN 3
            WHEN '20-30' THEN 4
            WHEN '30-40' THEN 5
            WHEN '40-50' THEN 6
            WHEN '50-70' THEN 7
            WHEN '70-100' THEN 8
            WHEN '100+' THEN 9
            ELSE 10
        END
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'オッズ帯':<10} {'総数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 70)
    for row in rows:
        odds_range, total, hits, hit_rate, roi, profit = row
        roi_mark = "✓" if roi >= 100 else "✗"
        print(f"{odds_range:<10} {total:>8,} {hits:>6} {hit_rate:>7.2f}% {roi:>7.1f}% {profit:>+12,.0f} {roi_mark}")


def analyze_miss_pattern_1st(cursor, confidence):
    """1着予測が外れた場合のパターン分析"""
    print(f"\n### 1着予測ミスのパターン（信頼度{confidence}）")
    print("-" * 70)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_with_result AS (
        SELECT
            rb.*,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st
        FROM race_base rb
    )
    SELECT
        '予測1着=' || p1 || ' → 実際1着=' || actual_1st as pattern,
        p1 as pred_1st,
        actual_1st,
        COUNT(*) as cnt
    FROM race_with_result
    WHERE p1 != actual_1st
    GROUP BY p1, actual_1st
    ORDER BY cnt DESC
    LIMIT 15
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'パターン':<25} {'予測1着':>8} {'実際1着':>8} {'件数':>8}")
    print("-" * 70)
    for row in rows:
        pattern, pred_1st, actual_1st, cnt = row
        print(f"{pattern:<25} {pred_1st:>8} {actual_1st:>8} {cnt:>8,}")


def analyze_miss_by_pred_course(cursor, confidence):
    """予測コース（1着予測が何コースか）別の分析"""
    print(f"\n### 1着予測コース別 不的中率（信頼度{confidence}）")
    print("-" * 70)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_with_result AS (
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
                THEN 1 ELSE 0
            END as is_1st_hit,
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
        p1 as pred_course,
        COUNT(*) as total,
        SUM(is_1st_hit) as first_hits,
        ROUND(100.0 * SUM(is_1st_hit) / COUNT(*), 1) as first_hit_rate,
        SUM(is_hit) as trifecta_hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as trifecta_hit_rate,
        ROUND(100.0 * SUM(payout) / (COUNT(*) * 100), 1) as roi,
        SUM(payout) - (COUNT(*) * 100) as profit
    FROM race_with_result
    WHERE pred_odds >= 10 AND pred_odds < 100
    GROUP BY p1
    ORDER BY p1
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'予測1着':>8} {'総数':>8} {'1着的中':>8} {'1着率':>8} {'3連単的中':>8} {'3連率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 100)
    for row in rows:
        pred_course, total, first_hits, first_hit_rate, trifecta_hits, trifecta_hit_rate, roi, profit = row
        roi_mark = "✓" if roi >= 100 else "✗"
        print(f"{pred_course:>8} {total:>8,} {first_hits:>8,} {first_hit_rate:>7.1f}% {trifecta_hits:>8,} {trifecta_hit_rate:>7.2f}% {roi:>7.1f}% {profit:>+12,.0f} {roi_mark}")


def analyze_combined_miss_factors(cursor, confidence):
    """複合条件での不的中・低ROI分析"""
    print(f"\n### 複合条件 低ROIワースト（信頼度{confidence}）")
    print("条件: 10-100倍、50件以上")
    print("-" * 80)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
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
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_with_result AS (
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
        venue_code,
        c1_rank,
        CASE
            WHEN pred_odds >= 10 AND pred_odds < 20 THEN '10-20'
            WHEN pred_odds >= 20 AND pred_odds < 30 THEN '20-30'
            WHEN pred_odds >= 30 AND pred_odds < 50 THEN '30-50'
            WHEN pred_odds >= 50 AND pred_odds < 100 THEN '50-100'
            ELSE 'other'
        END as odds_range,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(payout) / (COUNT(*) * 100), 1) as roi,
        SUM(payout) - (COUNT(*) * 100) as profit
    FROM race_with_result
    WHERE pred_odds >= 10 AND pred_odds < 100
    GROUP BY venue_code, c1_rank, odds_range
    HAVING COUNT(*) >= 50 AND (SUM(payout) - (COUNT(*) * 100)) < 0
    ORDER BY profit ASC
    LIMIT 20
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'会場':<8} {'級別':<6} {'オッズ帯':<10} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12}")
    print("-" * 80)
    for row in rows:
        venue_code, c1_rank, odds_range, total, hits, roi, profit = row
        venue_name = VENUE_NAMES.get(venue_code, f'会場{venue_code}')
        print(f"{venue_name:<8} {c1_rank:<6} {odds_range:<10} {total:>6,} {hits:>4} {roi:>7.1f}% {profit:>+12,.0f}")


def analyze_year_stability(cursor, confidence):
    """年度別安定性分析"""
    print(f"\n### 年度別パフォーマンス推移（信頼度{confidence}）")
    print("-" * 70)

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            substr(r.race_date, 1, 4) as year,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{confidence}'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_with_result AS (
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
        year,
        COUNT(*) as total,
        SUM(is_hit) as hits,
        ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
        ROUND(100.0 * SUM(payout) / (COUNT(*) * 100), 1) as roi,
        SUM(payout) - (COUNT(*) * 100) as profit
    FROM race_with_result
    WHERE pred_odds >= 10 AND pred_odds < 100
    GROUP BY year
    ORDER BY year
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'年度':<6} {'総数':>8} {'的中':>6} {'的中率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 70)
    for row in rows:
        year, total, hits, hit_rate, roi, profit = row
        roi_mark = "✓" if roi >= 100 else "✗"
        print(f"{year:<6} {total:>8,} {hits:>6} {hit_rate:>7.2f}% {roi:>7.1f}% {profit:>+12,.0f} {roi_mark}")


def main():
    print("=" * 80)
    print("不的中パターン傾向分析（6年間: 2020-2025年）")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    for confidence in ['A', 'B', 'C', 'D']:
        print("\n")
        print("=" * 80)
        print(f"【信頼度 {confidence}】")
        print("=" * 80)

        # 各分析を実行
        analyze_year_stability(cursor, confidence)
        analyze_by_odds_range(cursor, confidence)
        analyze_by_c1_rank(cursor, confidence)
        analyze_by_venue(cursor, confidence)
        analyze_miss_by_pred_course(cursor, confidence)
        analyze_miss_pattern_1st(cursor, confidence)
        analyze_combined_miss_factors(cursor, confidence)

    conn.close()

    print("\n")
    print("=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == '__main__':
    main()
