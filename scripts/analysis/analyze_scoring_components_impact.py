#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スコアリング要素別影響度分析

目的:
- 各スコアリング要素（展示、ST、コース、級別など）の的中率への寄与度を測定
- 展示タイム条件別加点の適切な比重を決定
- データ駆動で最適なバフ値を算出

分析手法:
1. 各要素単独での的中率を測定
2. 複合条件での的中率上昇を測定
3. 既存バフシステムとの比較
4. 最適バフ値の推定
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime
from collections import defaultdict
import statistics

DB_PATH = "data/boatrace.db"

def analyze_single_factor_impact(cursor, start_date='2025-01-01', end_date='2025-12-31'):
    """単一要素の的中率への影響を分析"""

    print("=" * 80)
    print("【1】単一要素別的中率分析")
    print("=" * 80)
    print()

    # コース別的中率
    print("■ コース別的中率")
    cursor.execute("""
        SELECT
            rd.actual_course,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.actual_course IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY rd.actual_course
        ORDER BY rd.actual_course
    """, (start_date, end_date))

    course_stats = {}
    for row in cursor.fetchall():
        course, total, first_count = row
        rate = first_count / total * 100
        course_stats[course] = {'total': total, 'rate': rate}
        print(f"  コース{course}: {rate:>5.2f}% ({first_count:>5}/{total:>6})")

    print()

    # 級別的中率
    print("■ 級別別的中率")
    cursor.execute("""
        SELECT
            e.racer_rank,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM entries e
        JOIN races r ON e.race_id = r.id
        LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND res.rank IS NOT NULL
        GROUP BY e.racer_rank
        ORDER BY e.racer_rank
    """, (start_date, end_date))

    rank_stats = {}
    for row in cursor.fetchall():
        racer_rank, total, first_count = row
        rate = first_count / total * 100
        rank_stats[racer_rank] = {'total': total, 'rate': rate}
        print(f"  {racer_rank}級: {rate:>5.2f}% ({first_count:>5}/{total:>6})")

    print()

    # 展示順位別的中率
    print("■ 展示順位別的中率")
    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            exh_rank,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        GROUP BY exh_rank
        ORDER BY exh_rank
    """, (start_date, end_date))

    exh_stats = {}
    for row in cursor.fetchall():
        exh_rank, total, first_count = row
        rate = first_count / total * 100
        exh_stats[exh_rank] = {'total': total, 'rate': rate}
        print(f"  展示{exh_rank}位: {rate:>5.2f}% ({first_count:>5}/{total:>6})")

    print()

    # ST評価別的中率
    print("■ ST評価別的中率")
    cursor.execute("""
        SELECT
            CASE
                WHEN rd.st_time <= 0.15 THEN 'good'
                WHEN rd.st_time <= 0.20 THEN 'normal'
                ELSE 'poor'
            END as st_status,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.st_time IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY st_status
        ORDER BY st_status
    """, (start_date, end_date))

    st_stats = {}
    for row in cursor.fetchall():
        st_status, total, first_count = row
        rate = first_count / total * 100
        st_stats[st_status] = {'total': total, 'rate': rate}
        print(f"  ST {st_status}: {rate:>5.2f}% ({first_count:>5}/{total:>6})")

    print()

    return {
        'course': course_stats,
        'rank': rank_stats,
        'exhibition': exh_stats,
        'st': st_stats
    }

def analyze_compound_conditions(cursor, start_date='2025-01-01', end_date='2025-12-31'):
    """複合条件の的中率上昇を分析"""

    print("=" * 80)
    print("【2】複合条件での的中率上昇分析")
    print("=" * 80)
    print()

    results = {}

    # 展示1位 × コース1
    print("■ 展示1位 × コース1")
    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.actual_course,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND rd.actual_course IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        WHERE exh_rank = 1 AND actual_course = 1
    """, (start_date, end_date))

    row = cursor.fetchone()
    if row and row[0] > 0:
        total, first_count = row
        rate = first_count / total * 100
        results['exh1_course1'] = rate
        print(f"  的中率: {rate:.2f}% ({first_count}/{total})")
        print(f"  期待値比: {rate / 16.67:.2f}x (基準: 16.67%)")
    print()

    # 展示1位 × A1級
    print("■ 展示1位 × A1級")
    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                e.racer_rank,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        WHERE exh_rank = 1 AND racer_rank = 'A1'
    """, (start_date, end_date))

    row = cursor.fetchone()
    if row and row[0] > 0:
        total, first_count = row
        rate = first_count / total * 100
        results['exh1_a1'] = rate
        print(f"  的中率: {rate:.2f}% ({first_count}/{total})")
        print(f"  期待値比: {rate / 16.67:.2f}x")
    print()

    # コース1 × A1級
    print("■ コース1 × A1級（展示なし）")
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.actual_course = 1
        AND e.racer_rank = 'A1'
        AND res.rank IS NOT NULL
    """, (start_date, end_date))

    row = cursor.fetchone()
    if row and row[0] > 0:
        total, first_count = row
        rate = first_count / total * 100
        results['course1_a1'] = rate
        print(f"  的中率: {rate:.2f}% ({first_count}/{total})")
        print(f"  期待値比: {rate / 16.67:.2f}x")
    print()

    # 展示1位 × コース1 × A1級（三重複合）
    print("■ 展示1位 × コース1 × A1級（三重複合）")
    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.actual_course,
                e.racer_rank,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND rd.actual_course IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        WHERE exh_rank = 1 AND actual_course = 1 AND racer_rank = 'A1'
    """, (start_date, end_date))

    row = cursor.fetchone()
    if row and row[0] > 0:
        total, first_count = row
        rate = first_count / total * 100
        results['exh1_course1_a1'] = rate
        print(f"  的中率: {rate:.2f}% ({first_count}/{total})")
        print(f"  期待値比: {rate / 16.67:.2f}x")
    print()

    return results

def calculate_optimal_buff_values(single_stats, compound_stats):
    """最適なバフ値を計算"""

    print("=" * 80)
    print("【3】最適バフ値の算出")
    print("=" * 80)
    print()

    # 基準: 期待値16.67%（1/6）からの乖離をバフ値に変換
    # 変換式: buff_value = (actual_rate - expected_rate) * multiplier
    # multiplierは総合スコアへの影響を考慮して調整

    EXPECTED_RATE = 16.67
    MULTIPLIER = 2.0  # 1%の的中率差 = 2点のバフ

    recommendations = {}

    print("■ 推奨バフ値（期待値からの乖離ベース）")
    print()

    # 展示1位 × コース1
    if 'exh1_course1' in compound_stats:
        rate = compound_stats['exh1_course1']
        diff = rate - EXPECTED_RATE
        buff = diff * MULTIPLIER
        recommendations['exh1_course1'] = buff
        print(f"展示1位 × コース1:")
        print(f"  的中率: {rate:.2f}% (期待値比: +{diff:.2f}pt)")
        print(f"  推奨バフ: {buff:.1f}点")
        print()

    # 展示1位 × A1級
    if 'exh1_a1' in compound_stats:
        rate = compound_stats['exh1_a1']
        diff = rate - EXPECTED_RATE
        buff = diff * MULTIPLIER
        recommendations['exh1_a1'] = buff
        print(f"展示1位 × A1級:")
        print(f"  的中率: {rate:.2f}% (期待値比: +{diff:.2f}pt)")
        print(f"  推奨バフ: {buff:.1f}点")
        print()

    # 三重複合
    if 'exh1_course1_a1' in compound_stats:
        rate = compound_stats['exh1_course1_a1']
        diff = rate - EXPECTED_RATE
        buff = diff * MULTIPLIER
        recommendations['exh1_course1_a1'] = buff
        print(f"展示1位 × コース1 × A1級:")
        print(f"  的中率: {rate:.2f}% (期待値比: +{diff:.2f}pt)")
        print(f"  推奨バフ: {buff:.1f}点")
        print()

    # 展示順位別の基本バフ
    if 'exhibition' in single_stats:
        print("■ 展示順位別基本バフ（単独効果）")
        print()
        for rank, stats in single_stats['exhibition'].items():
            rate = stats['rate']
            diff = rate - EXPECTED_RATE
            buff = diff * MULTIPLIER
            recommendations[f'exh_rank{rank}'] = buff
            print(f"展示{rank}位: {rate:.2f}% → 推奨バフ {buff:+.1f}点")
        print()

    return recommendations

def main():
    # UTF-8出力設定
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 80)
    print("スコアリング要素別影響度分析")
    print("=" * 80)
    print()
    print("目的: 展示タイム条件別加点の適切なバフ値を決定")
    print("対象期間: 2025年1月1日～12月31日")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 単一要素分析
    single_stats = analyze_single_factor_impact(cursor)

    # 複合条件分析
    compound_stats = analyze_compound_conditions(cursor)

    # 最適バフ値算出
    recommendations = calculate_optimal_buff_values(single_stats, compound_stats)

    print("=" * 80)
    print("【4】現在のバフ値との比較")
    print("=" * 80)
    print()

    current_buffs = {
        'exh1_course1': 15.0,
        'exh1_a1': 10.0,
    }

    print(f"{'条件':<30} {'現在のバフ':>12} {'推奨バフ':>12} {'差分':>10}")
    print("-" * 70)

    for key in ['exh1_course1', 'exh1_a1']:
        if key in recommendations:
            current = current_buffs.get(key, 0)
            recommended = recommendations[key]
            diff = recommended - current
            print(f"{key:<30} {current:>11.1f}点 {recommended:>11.1f}点 {diff:>9.1f}点")

    print()
    print("=" * 80)
    print("結論")
    print("=" * 80)
    print()
    print("展示タイム条件別加点は、データ駆動で適切なバフ値を設定することで")
    print("予測精度の向上が期待できます。")
    print()
    print("推奨アクション:")
    print("1. バフ値を推奨値に調整")
    print("2. 再度バックテストを実行")
    print("3. 改善効果を検証")
    print()

    conn.close()

if __name__ == '__main__':
    main()
