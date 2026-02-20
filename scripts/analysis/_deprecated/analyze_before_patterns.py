# -*- coding: utf-8 -*-
"""
直前情報（beforeinfo）パターン分析スクリプト
2020-2024年のbefore予測データを使用
"""

import sqlite3
from scipy import stats

def main():
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    print('=== TOP3パターン探索 (2020-2024) ===')
    cursor.execute('''
        WITH ranked_data AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) as ex_rank,
                ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY ABS(rd.st_time) ASC) as st_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE rd.exhibition_time IS NOT NULL
            AND rd.st_time IS NOT NULL
            AND r.race_date >= '2020-01-01' AND r.race_date <= '2024-12-31'
        ),
        race_count AS (
            SELECT race_id
            FROM ranked_data
            GROUP BY race_id
            HAVING COUNT(*) = 6
        )
        SELECT
            'PRE1_3_ST1' as pattern,
            SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank = 1 THEN 1 ELSE 0 END) as samples,
            SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank = 1 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) as wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank = 1 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank = 1 THEN 1 ELSE 0 END), 0), 2) as hit_rate,
            SUM(CASE WHEN p.rank_prediction <= 3 THEN 1 ELSE 0 END) as base_samples,
            SUM(CASE WHEN p.rank_prediction <= 3 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) as base_wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction <= 3 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction <= 3 THEN 1 ELSE 0 END), 0), 2) as base_rate
        FROM race_predictions p
        JOIN ranked_data rd ON p.race_id = rd.race_id AND p.pit_number = rd.pit_number
        JOIN race_count rc ON rd.race_id = rc.race_id
        JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number AND res.is_invalid = 0
        WHERE p.prediction_type = 'before'

        UNION ALL

        SELECT
            'PRE1_3_ST1_2' as pattern,
            SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank <= 2 THEN 1 ELSE 0 END) as samples,
            SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank <= 2 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) as wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank <= 2 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank <= 2 THEN 1 ELSE 0 END), 0), 2) as hit_rate,
            SUM(CASE WHEN p.rank_prediction <= 3 THEN 1 ELSE 0 END) as base_samples,
            SUM(CASE WHEN p.rank_prediction <= 3 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) as base_wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction <= 3 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction <= 3 THEN 1 ELSE 0 END), 0), 2) as base_rate
        FROM race_predictions p
        JOIN ranked_data rd ON p.race_id = rd.race_id AND p.pit_number = rd.pit_number
        JOIN race_count rc ON rd.race_id = rc.race_id
        JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number AND res.is_invalid = 0
        WHERE p.prediction_type = 'before'

        UNION ALL

        SELECT
            'PRE1_3_ST1_3' as pattern,
            SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank <= 3 THEN 1 ELSE 0 END) as samples,
            SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank <= 3 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) as wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank <= 3 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction <= 3 AND rd.st_rank <= 3 THEN 1 ELSE 0 END), 0), 2) as hit_rate,
            SUM(CASE WHEN p.rank_prediction <= 3 THEN 1 ELSE 0 END) as base_samples,
            SUM(CASE WHEN p.rank_prediction <= 3 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) as base_wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction <= 3 AND res.rank IN ('1','2','3') THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction <= 3 THEN 1 ELSE 0 END), 0), 2) as base_rate
        FROM race_predictions p
        JOIN ranked_data rd ON p.race_id = rd.race_id AND p.pit_number = rd.pit_number
        JOIN race_count rc ON rd.race_id = rc.race_id
        JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number AND res.is_invalid = 0
        WHERE p.prediction_type = 'before'
    ''')

    print('pattern      | samples | wins  | hit_rate | base_rate | diff')
    print('-' * 65)
    for row in cursor.fetchall():
        diff = row[3] - row[6] if row[3] and row[6] else 0
        diff_str = f'+{diff:.2f}%' if diff > 0 else f'{diff:.2f}%'
        print(f'{row[0]:<12} | {row[1]:>7} | {row[2]:>5} | {row[3]:>7.2f}% | {row[6]:>8.2f}% | {diff_str:>7}')

    print()
    print('=== ST順位の悪い場合のネガティブパターン ===')
    cursor.execute('''
        WITH ranked_data AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY ABS(rd.st_time) ASC) as st_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE rd.st_time IS NOT NULL
            AND r.race_date >= '2020-01-01' AND r.race_date <= '2024-12-31'
        ),
        race_count AS (
            SELECT race_id
            FROM ranked_data
            GROUP BY race_id
            HAVING COUNT(*) = 6
        )
        SELECT
            'PRE1_ST4_6' as pattern,
            SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank >= 4 THEN 1 ELSE 0 END) as samples,
            SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank >= 4 AND res.rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank >= 4 AND res.rank = '1' THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank >= 4 THEN 1 ELSE 0 END), 0), 2) as hit_rate,
            53.2 as base_rate
        FROM race_predictions p
        JOIN ranked_data rd ON p.race_id = rd.race_id AND p.pit_number = rd.pit_number
        JOIN race_count rc ON rd.race_id = rc.race_id
        JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number AND res.is_invalid = 0
        WHERE p.prediction_type = 'before'

        UNION ALL

        SELECT
            'PRE1_ST5_6' as pattern,
            SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank >= 5 THEN 1 ELSE 0 END) as samples,
            SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank >= 5 AND res.rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank >= 5 AND res.rank = '1' THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank >= 5 THEN 1 ELSE 0 END), 0), 2) as hit_rate,
            53.2 as base_rate
        FROM race_predictions p
        JOIN ranked_data rd ON p.race_id = rd.race_id AND p.pit_number = rd.pit_number
        JOIN race_count rc ON rd.race_id = rc.race_id
        JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number AND res.is_invalid = 0
        WHERE p.prediction_type = 'before'

        UNION ALL

        SELECT
            'PRE1_ST6' as pattern,
            SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank = 6 THEN 1 ELSE 0 END) as samples,
            SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank = 6 AND res.rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(100.0 * SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank = 6 AND res.rank = '1' THEN 1 ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN p.rank_prediction = 1 AND rd.st_rank = 6 THEN 1 ELSE 0 END), 0), 2) as hit_rate,
            53.2 as base_rate
        FROM race_predictions p
        JOIN ranked_data rd ON p.race_id = rd.race_id AND p.pit_number = rd.pit_number
        JOIN race_count rc ON rd.race_id = rc.race_id
        JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number AND res.is_invalid = 0
        WHERE p.prediction_type = 'before'
    ''')

    print('pattern     | samples | wins | hit_rate | base | diff (negative)')
    print('-' * 65)
    for row in cursor.fetchall():
        diff = row[3] - row[4] if row[3] else 0
        diff_str = f'{diff:.2f}%'
        print(f'{row[0]:<11} | {row[1]:>7} | {row[2]:>4} | {row[3]:>7.2f}% | {row[4]:.1f}% | {diff_str:>12}')

    conn.close()

if __name__ == '__main__':
    main()
