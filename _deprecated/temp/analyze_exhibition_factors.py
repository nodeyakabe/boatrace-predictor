# -*- coding: utf-8 -*-
"""
展示ST・展示タイムの詳細分析
コース、天候、潮位などの交絡因子を考慮
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from collections import defaultdict
from config.settings import DATABASE_PATH


def analyze_exhibition_by_course():
    """コース別に展示ST・展示タイムの効果を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print('=' * 80)
    print('1. コース別・展示ST順位別の勝率')
    print('=' * 80)
    print()

    # コース別に展示ST順位の効果を見る
    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                e.pit_number as course,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                res.rank as result_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND res.rank IS NOT NULL AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            course,
            st_rank,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(CASE WHEN result_rank = '1' THEN 100.0 ELSE 0.0 END), 2) as win_rate
        FROM ranked
        GROUP BY course, st_rank
        ORDER BY course, st_rank
    """)

    results = cursor.fetchall()

    # コースごとにまとめて表示
    current_course = None
    for course, st_rank, total, wins, win_rate in results:
        if current_course != course:
            if current_course is not None:
                print()
            print(f"【{course}コース】")
            print(f"  {'ST順位':<8} {'レース数':>10} {'勝率':>10}")
            print(f"  {'-'*30}")
            current_course = course
        print(f"  {st_rank}位       {total:>10,} {win_rate:>9.2f}%")

    print()
    print('=' * 80)
    print('2. コース別・展示タイム順位別の勝率')
    print('=' * 80)
    print()

    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                e.pit_number as course,
                rd.exhibition_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.exhibition_time) as ex_rank,
                res.rank as result_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE rd.exhibition_time IS NOT NULL AND rd.exhibition_time > 0
              AND res.rank IS NOT NULL AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            course,
            ex_rank,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(CASE WHEN result_rank = '1' THEN 100.0 ELSE 0.0 END), 2) as win_rate
        FROM ranked
        GROUP BY course, ex_rank
        ORDER BY course, ex_rank
    """)

    results = cursor.fetchall()

    current_course = None
    for course, ex_rank, total, wins, win_rate in results:
        if current_course != course:
            if current_course is not None:
                print()
            print(f"【{course}コース】")
            print(f"  {'展示順位':<8} {'レース数':>10} {'勝率':>10}")
            print(f"  {'-'*30}")
            current_course = course
        print(f"  {ex_rank}位       {total:>10,} {win_rate:>9.2f}%")

    conn.close()


def analyze_exhibition_by_weather():
    """天候条件別に展示ST・展示タイムの効果を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print()
    print('=' * 80)
    print('3. 風速別・展示ST順位別の勝率（1コース限定）')
    print('=' * 80)
    print()

    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                e.pit_number,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                res.rank as result_rank,
                CASE
                    WHEN rc.wind_speed IS NULL THEN 'データなし'
                    WHEN rc.wind_speed <= 2 THEN '弱風(0-2m)'
                    WHEN rc.wind_speed <= 5 THEN '中風(3-5m)'
                    ELSE '強風(6m+)'
                END as wind_category
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            LEFT JOIN race_conditions rc ON r.id = rc.race_id
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND e.pit_number = 1
              AND res.rank IS NOT NULL AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            wind_category,
            st_rank,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(CASE WHEN result_rank = '1' THEN 100.0 ELSE 0.0 END), 2) as win_rate
        FROM ranked
        GROUP BY wind_category, st_rank
        ORDER BY wind_category, st_rank
    """)

    results = cursor.fetchall()

    current_cat = None
    for wind_cat, st_rank, total, wins, win_rate in results:
        if current_cat != wind_cat:
            if current_cat is not None:
                print()
            print(f"【{wind_cat}】1コース")
            print(f"  {'ST順位':<8} {'レース数':>10} {'勝率':>10}")
            print(f"  {'-'*30}")
            current_cat = wind_cat
        print(f"  {st_rank}位       {total:>10,} {win_rate:>9.2f}%")

    print()
    print('=' * 80)
    print('4. 波高別・展示ST順位別の勝率（1コース限定）')
    print('=' * 80)
    print()

    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                e.pit_number,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                res.rank as result_rank,
                CASE
                    WHEN rc.wave_height IS NULL THEN 'データなし'
                    WHEN rc.wave_height <= 3 THEN '静水(0-3cm)'
                    WHEN rc.wave_height <= 7 THEN '中波(4-7cm)'
                    ELSE '高波(8cm+)'
                END as wave_category
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            LEFT JOIN race_conditions rc ON r.id = rc.race_id
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND e.pit_number = 1
              AND res.rank IS NOT NULL AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            wave_category,
            st_rank,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(CASE WHEN result_rank = '1' THEN 100.0 ELSE 0.0 END), 2) as win_rate
        FROM ranked
        GROUP BY wave_category, st_rank
        ORDER BY wave_category, st_rank
    """)

    results = cursor.fetchall()

    current_cat = None
    for wave_cat, st_rank, total, wins, win_rate in results:
        if current_cat != wave_cat:
            if current_cat is not None:
                print()
            print(f"【{wave_cat}】1コース")
            print(f"  {'ST順位':<8} {'レース数':>10} {'勝率':>10}")
            print(f"  {'-'*30}")
            current_cat = wave_cat
        print(f"  {st_rank}位       {total:>10,} {win_rate:>9.2f}%")

    conn.close()


def analyze_exhibition_by_rank():
    """級別ごとに展示ST・展示タイムの効果を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print()
    print('=' * 80)
    print('5. 級別・展示ST順位別の勝率（1コース限定）')
    print('=' * 80)
    print()

    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                e.pit_number,
                e.racer_rank,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                res.rank as result_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND e.pit_number = 1
              AND res.rank IS NOT NULL AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            racer_rank,
            st_rank,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(CASE WHEN result_rank = '1' THEN 100.0 ELSE 0.0 END), 2) as win_rate
        FROM ranked
        WHERE racer_rank IN ('A1', 'A2', 'B1', 'B2')
        GROUP BY racer_rank, st_rank
        ORDER BY
            CASE racer_rank WHEN 'A1' THEN 1 WHEN 'A2' THEN 2 WHEN 'B1' THEN 3 WHEN 'B2' THEN 4 END,
            st_rank
    """)

    results = cursor.fetchall()

    current_rank = None
    for racer_rank, st_rank, total, wins, win_rate in results:
        if current_rank != racer_rank:
            if current_rank is not None:
                print()
            print(f"【{racer_rank}選手】1コース")
            print(f"  {'ST順位':<8} {'レース数':>10} {'勝率':>10}")
            print(f"  {'-'*30}")
            current_rank = racer_rank
        print(f"  {st_rank}位       {total:>10,} {win_rate:>9.2f}%")

    conn.close()


def analyze_exhibition_pure_effect():
    """同一コース内での展示ST・展示タイムの純粋な効果を分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print()
    print('=' * 80)
    print('6. 同一コース内での展示ST差と勝率の関係')
    print('=' * 80)
    print()
    print('※同じコースの選手同士で、展示STが速い方が勝つ確率')
    print()

    # 1コースの選手が展示ST1位かどうかで勝率がどう変わるか
    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                e.pit_number,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank,
                res.rank as result_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND res.rank IS NOT NULL AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            pit_number as course,
            CASE WHEN st_rank = 1 THEN 'ST1位' ELSE 'ST2位以下' END as st_category,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(CASE WHEN result_rank = '1' THEN 100.0 ELSE 0.0 END), 2) as win_rate
        FROM ranked
        GROUP BY course, st_category
        ORDER BY course, st_category DESC
    """)

    results = cursor.fetchall()

    print(f"{'コース':<8} {'ST順位':<12} {'レース数':>10} {'勝率':>10}")
    print('-' * 45)
    for course, st_cat, total, wins, win_rate in results:
        print(f"{course}コース   {st_cat:<12} {total:>10,} {win_rate:>9.2f}%")

    print()
    print('=' * 80)
    print('7. 展示ST差（秒）と勝率の関係（1コース限定）')
    print('=' * 80)
    print()

    # 1コースの展示STと他艇の平均展示STの差で勝率がどう変わるか
    cursor.execute("""
        WITH race_avg AS (
            SELECT
                r.id as race_id,
                e.pit_number,
                rd.st_time,
                AVG(rd.st_time) OVER (PARTITION BY r.id) as avg_st,
                res.rank as result_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND e.pit_number = 1
              AND res.rank IS NOT NULL AND res.is_invalid = 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            CASE
                WHEN st_time - avg_st <= -0.05 THEN '平均より0.05秒以上速い'
                WHEN st_time - avg_st <= -0.02 THEN '平均より0.02-0.05秒速い'
                WHEN st_time - avg_st <= 0.02 THEN '平均と同程度'
                WHEN st_time - avg_st <= 0.05 THEN '平均より0.02-0.05秒遅い'
                ELSE '平均より0.05秒以上遅い'
            END as st_diff_category,
            COUNT(*) as total,
            SUM(CASE WHEN result_rank = '1' THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(CASE WHEN result_rank = '1' THEN 100.0 ELSE 0.0 END), 2) as win_rate
        FROM race_avg
        GROUP BY st_diff_category
        ORDER BY win_rate DESC
    """)

    results = cursor.fetchall()

    print(f"{'ST差カテゴリ':<30} {'レース数':>10} {'勝率':>10}")
    print('-' * 55)
    for st_diff_cat, total, wins, win_rate in results:
        print(f"{st_diff_cat:<30} {total:>10,} {win_rate:>9.2f}%")

    conn.close()


def analyze_correlation_with_course():
    """展示ST順位とコースの相関を分析（交絡の確認）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print()
    print('=' * 80)
    print('8. 展示ST1位になる確率（コース別）')
    print('   ※1コースの選手が展示ST1位になりやすいなら、交絡の可能性')
    print('=' * 80)
    print()

    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                e.pit_number as course,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            course,
            COUNT(*) as total,
            SUM(CASE WHEN st_rank = 1 THEN 1 ELSE 0 END) as st1_count,
            ROUND(AVG(CASE WHEN st_rank = 1 THEN 100.0 ELSE 0.0 END), 2) as st1_rate,
            ROUND(AVG(st_rank), 2) as avg_st_rank
        FROM ranked
        GROUP BY course
        ORDER BY course
    """)

    results = cursor.fetchall()

    print(f"{'コース':<8} {'レース数':>10} {'ST1位回数':>12} {'ST1位率':>10} {'平均ST順位':>12}")
    print('-' * 60)
    for course, total, st1_count, st1_rate, avg_rank in results:
        print(f"{course}コース   {total:>10,} {st1_count:>12,} {st1_rate:>9.2f}% {avg_rank:>11.2f}")

    print()
    print('=' * 80)
    print('9. 級別と展示ST順位の関係')
    print('   ※A1選手が展示ST1位になりやすいなら、級別との交絡の可能性')
    print('=' * 80)
    print()

    cursor.execute("""
        WITH ranked AS (
            SELECT
                r.id as race_id,
                e.racer_rank,
                rd.st_time,
                RANK() OVER (PARTITION BY r.id ORDER BY rd.st_time) as st_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE rd.st_time IS NOT NULL AND rd.st_time > 0
              AND e.racer_rank IN ('A1', 'A2', 'B1', 'B2')
              AND r.race_date >= '2024-01-01'
        )
        SELECT
            racer_rank,
            COUNT(*) as total,
            SUM(CASE WHEN st_rank = 1 THEN 1 ELSE 0 END) as st1_count,
            ROUND(AVG(CASE WHEN st_rank = 1 THEN 100.0 ELSE 0.0 END), 2) as st1_rate,
            ROUND(AVG(st_rank), 2) as avg_st_rank
        FROM ranked
        GROUP BY racer_rank
        ORDER BY
            CASE racer_rank WHEN 'A1' THEN 1 WHEN 'A2' THEN 2 WHEN 'B1' THEN 3 WHEN 'B2' THEN 4 END
    """)

    results = cursor.fetchall()

    print(f"{'級別':<8} {'レース数':>10} {'ST1位回数':>12} {'ST1位率':>10} {'平均ST順位':>12}")
    print('-' * 60)
    for racer_rank, total, st1_count, st1_rate, avg_rank in results:
        print(f"{racer_rank:<8} {total:>10,} {st1_count:>12,} {st1_rate:>9.2f}% {avg_rank:>11.2f}")

    conn.close()


def main():
    analyze_exhibition_by_course()
    analyze_exhibition_by_weather()
    analyze_exhibition_by_rank()
    analyze_exhibition_pure_effect()
    analyze_correlation_with_course()

    print()
    print('=' * 80)
    print('分析完了')
    print('=' * 80)


if __name__ == '__main__':
    main()
