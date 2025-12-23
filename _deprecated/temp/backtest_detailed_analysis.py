# -*- coding: utf-8 -*-
"""
詳細分析: 展示STと勝率の相関確認
改善案が効いているか検証
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from collections import defaultdict
from config.settings import DATABASE_PATH


def analyze_exhibition_st_correlation():
    """展示STと勝率の相関を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print('=' * 70)
    print('展示ST（当日ST）と勝率の相関分析')
    print('=' * 70)
    print()

    # 展示STの順位別勝率
    cursor.execute("""
        WITH ranked_st AS (
            SELECT
                r.id as race_id,
                rd.pit_number,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                res.rank as result_rank
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL
              AND rd.st_time > 0
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            st_rank,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN result_rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM ranked_st
        GROUP BY st_rank
        ORDER BY st_rank
    """)

    print('展示ST順位別勝率:')
    print(f"{'順位':<6} {'レース数':>10} {'勝利数':>10} {'勝率':>10}")
    print('-' * 40)
    for row in cursor.fetchall():
        st_rank, total, wins, win_rate = row
        print(f"{st_rank:<6} {total:>10,} {wins:>10,} {win_rate:>9.2f}%")

    print()

    # 過去ST vs 展示ST の相関
    cursor.execute("""
        SELECT
            CASE
                WHEN e.avg_st < rd.st_time THEN '過去ST < 展示ST（本番で遅い）'
                WHEN e.avg_st > rd.st_time THEN '過去ST > 展示ST（本番で速い）'
                ELSE '過去ST = 展示ST'
            END as comparison,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM entries e
        JOIN races r ON e.race_id = r.id
        JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE e.avg_st IS NOT NULL
          AND e.avg_st > 0
          AND rd.st_time IS NOT NULL
          AND rd.st_time > 0
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
          AND r.race_date >= '2024-01-01'
        GROUP BY comparison
    """)

    print('過去ST vs 展示STの比較:')
    for row in cursor.fetchall():
        comparison, total, wins, win_rate = row
        print(f"  {comparison}: {win_rate:.2f}% ({total:,}件)")

    print()

    # 展示タイム順位別勝率
    cursor.execute("""
        WITH ranked_ex AS (
            SELECT
                r.id as race_id,
                rd.pit_number,
                rd.exhibition_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.exhibition_time) as ex_rank,
                res.rank as result_rank
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.exhibition_time IS NOT NULL
              AND rd.exhibition_time > 0
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            ex_rank,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN result_rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM ranked_ex
        GROUP BY ex_rank
        ORDER BY ex_rank
    """)

    print('展示タイム順位別勝率:')
    print(f"{'順位':<6} {'レース数':>10} {'勝利数':>10} {'勝率':>10}")
    print('-' * 40)
    for row in cursor.fetchall():
        ex_rank, total, wins, win_rate = row
        print(f"{ex_rank:<6} {total:>10,} {wins:>10,} {win_rate:>9.2f}%")

    print()

    # 進入崩れと勝率
    cursor.execute("""
        SELECT
            CASE
                WHEN rd.actual_course < e.pit_number THEN '前付け（内コースへ）'
                WHEN rd.actual_course > e.pit_number THEN '外コースへ流れ'
                ELSE '枠なり'
            END as entry_type,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM entries e
        JOIN races r ON e.race_id = r.id
        JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE rd.actual_course IS NOT NULL
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
          AND r.race_date >= '2024-01-01'
        GROUP BY entry_type
    """)

    print('進入パターン別勝率:')
    for row in cursor.fetchall():
        entry_type, total, wins, win_rate = row
        print(f"  {entry_type}: {win_rate:.2f}% ({total:,}件)")

    print()

    # 1コース限定で展示ST順位の影響
    cursor.execute("""
        WITH ranked_st AS (
            SELECT
                r.id as race_id,
                rd.pit_number,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                res.rank as result_rank
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL
              AND rd.st_time > 0
              AND rd.pit_number = 1
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            st_rank,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN result_rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM ranked_st
        GROUP BY st_rank
        ORDER BY st_rank
    """)

    print('【1号艇限定】展示ST順位別勝率:')
    print(f"{'順位':<6} {'レース数':>10} {'勝利数':>10} {'勝率':>10}")
    print('-' * 40)
    for row in cursor.fetchall():
        st_rank, total, wins, win_rate = row
        print(f"{st_rank:<6} {total:>10,} {wins:>10,} {win_rate:>9.2f}%")

    print()

    # 展示ST1位 + 展示タイム1位の選手の勝率
    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                rd.pit_number,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.exhibition_time) as ex_rank,
                res.rank as result_rank
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND rd.exhibition_time IS NOT NULL AND rd.exhibition_time > 0
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            CASE
                WHEN st_rank = 1 AND ex_rank = 1 THEN 'ST1位 & 展示1位'
                WHEN st_rank = 1 THEN 'ST1位のみ'
                WHEN ex_rank = 1 THEN '展示1位のみ'
                ELSE 'その他'
            END as category,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN result_rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM ranked
        GROUP BY category
        ORDER BY win_rate DESC
    """)

    print('展示ST1位 & 展示タイム1位の効果:')
    for row in cursor.fetchall():
        category, total, wins, win_rate = row
        print(f"  {category}: {win_rate:.2f}% ({total:,}件)")

    conn.close()


def analyze_why_improvement_small():
    """改善が小さい理由を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print()
    print('=' * 70)
    print('改善が小さい理由の分析')
    print('=' * 70)
    print()

    # 現在のベースライン予測の精度内訳
    cursor.execute("""
        WITH base_score AS (
            SELECT
                r.id as race_id,
                e.pit_number,
                -- 現行スコア計算
                (CASE e.pit_number
                    WHEN 1 THEN 55 WHEN 2 THEN 18 WHEN 3 THEN 12
                    WHEN 4 THEN 10 WHEN 5 THEN 6 WHEN 6 THEN 5
                END / 55.0 * 100) * 0.35 +
                ((COALESCE(e.win_rate, 0) * 0.6 + COALESCE(e.local_win_rate, 0) * 0.4) * 10) * 0.35 +
                COALESCE(e.motor_second_rate, 30) * 0.20 +
                (CASE e.racer_rank
                    WHEN 'A1' THEN 100 WHEN 'A2' THEN 70
                    WHEN 'B1' THEN 40 ELSE 10
                END) * 0.10 as score,
                res.rank as result_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE res.rank IS NOT NULL
              AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        ),
        race_predictions AS (
            SELECT
                race_id,
                pit_number,
                result_rank,
                RANK() OVER (PARTITION BY race_id ORDER BY score DESC) as predicted_rank
            FROM base_score
        )
        SELECT
            CASE
                WHEN pit_number = 1 AND result_rank = '1' THEN '1号艇的中'
                WHEN pit_number != 1 AND result_rank = '1' THEN '非1号艇的中'
                WHEN pit_number = 1 AND result_rank != '1' THEN '1号艇ハズレ'
                ELSE '非1号艇ハズレ'
            END as category,
            COUNT(*) as cnt
        FROM race_predictions
        WHERE predicted_rank = 1
        GROUP BY category
    """)

    print('現行予測の内訳（予測1位のみ）:')
    total = 0
    results = {}
    for row in cursor.fetchall():
        category, cnt = row
        results[category] = cnt
        total += cnt

    for category, cnt in results.items():
        print(f"  {category}: {cnt:,}件 ({cnt/total*100:.1f}%)")

    print()

    # 1コース勝率と予測の関係
    cursor.execute("""
        SELECT
            e.racer_rank,
            e.pit_number,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM entries e
        JOIN races r ON e.race_id = r.id
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE e.pit_number = 1
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
          AND r.race_date >= '2024-01-01'
        GROUP BY e.racer_rank
        ORDER BY win_rate DESC
    """)

    print('1コース級別勝率:')
    for row in cursor.fetchall():
        rank, pit, total, wins, win_rate = row
        print(f"  {rank or 'N/A'}: {win_rate:.1f}% ({total:,}件)")

    print()

    # 改善案が効く場面の分析
    # 展示ST1位が枠番1位以外だった場合の勝率
    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                rd.pit_number,
                e.racer_rank,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                res.rank as result_rank
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            JOIN entries e ON r.id = e.race_id AND rd.pit_number = e.pit_number
            JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            '展示ST1位が非1号艇' as scenario,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN result_rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM ranked
        WHERE st_rank = 1 AND pit_number != 1

        UNION ALL

        SELECT
            '展示ST1位が1号艇' as scenario,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            AVG(CASE WHEN result_rank = '1' THEN 1.0 ELSE 0.0 END) * 100 as win_rate
        FROM ranked
        WHERE st_rank = 1 AND pit_number = 1
    """)

    print('展示ST1位の所在と勝率:')
    for row in cursor.fetchall():
        scenario, total, wins, win_rate = row
        print(f"  {scenario}: {win_rate:.1f}% ({total:,}件)")

    conn.close()


if __name__ == '__main__':
    analyze_exhibition_st_correlation()
    analyze_why_improvement_small()
