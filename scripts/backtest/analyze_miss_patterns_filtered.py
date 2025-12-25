#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不的中パターン傾向分析スクリプト（フィルターC適用後）

目的:
    現行の購入条件（bet_target_evaluator.py）に基づいて
    実際に購入対象となるレースの不的中パターンを分析

使用方法:
    python scripts/backtest/analyze_miss_patterns_filtered.py
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

# 現行購入条件（bet_target_evaluator.pyと同期）
CONDITIONS = [
    # A条件
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None, 'motor_min': None},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'venue_filter': None, 'motor_min': None},
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40},

    # B条件
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None, 'motor_min': None},
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
     'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8], 'motor_min': None},

    # C条件
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
     'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17], 'motor_min': None},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
     'venue_filter': [14], 'motor_min': None},

    # D条件
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None, 'motor_min': None},
    {'name': 'D×30-60', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 30, 'odds_max': 60, 'venue_filter': None, 'motor_min': None},
]


def analyze_condition_detail(cursor, cond, year_start, year_end):
    """条件別の詳細分析"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
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
        AND rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date <= '{year_end}-12-31'
        {venue_clause}
        {motor_clause}
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
                THEN 1 ELSE 0
            END as is_12_hit,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd,
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
    SELECT * FROM race_with_result
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    '''
    cursor.execute(query)
    return cursor.fetchall()


def analyze_miss_breakdown(rows, cond_name):
    """不的中の内訳を分析"""
    total = len(rows)
    if total == 0:
        return

    hits = sum(1 for r in rows if r[10] == 1)  # is_hit
    first_hits = sum(1 for r in rows if r[11] == 1)  # is_1st_hit
    first_second_hits = sum(1 for r in rows if r[12] == 1)  # is_12_hit

    misses = total - hits
    first_miss = total - first_hits
    first_hit_second_miss = first_hits - first_second_hits
    first_second_hit_third_miss = first_second_hits - hits

    print(f"\n### {cond_name} 不的中内訳")
    print("-" * 60)
    print(f"総購入数: {total}件")
    print(f"的中: {hits}件 ({100*hits/total:.1f}%)")
    print(f"不的中: {misses}件 ({100*misses/total:.1f}%)")
    print()
    print("【不的中の内訳】")
    print(f"  1着外し: {first_miss}件 ({100*first_miss/total:.1f}%)")
    print(f"  1着○2着×: {first_hit_second_miss}件 ({100*first_hit_second_miss/total:.1f}%)")
    print(f"  1-2着○3着×: {first_second_hit_third_miss}件 ({100*first_second_hit_third_miss/total:.1f}%)")

    # ROI計算
    total_payout = sum(r[16] for r in rows)  # payout
    roi = 100 * total_payout / (total * 100) if total > 0 else 0
    profit = total_payout - (total * 100)
    print(f"\nROI: {roi:.1f}%, 収支: {profit:+,.0f}円")


def analyze_1st_miss_pattern(rows, cond_name):
    """1着ミスのパターン分析"""
    # 1着ミスのケースのみ抽出
    first_misses = [r for r in rows if r[11] == 0]  # is_1st_hit == 0
    if not first_misses:
        return

    # 予測1着 vs 実際1着のパターン集計
    pattern_counts = {}
    for r in first_misses:
        p1 = r[6]  # 予測1着
        actual_1st = r[13]  # 実際1着
        key = f"{p1}→{actual_1st}"
        pattern_counts[key] = pattern_counts.get(key, 0) + 1

    print(f"\n### {cond_name} 1着ミスパターン")
    print("-" * 60)
    sorted_patterns = sorted(pattern_counts.items(), key=lambda x: -x[1])[:10]
    print(f"{'パターン':<15} {'件数':>8} {'割合':>8}")
    print("-" * 40)
    total_miss = len(first_misses)
    for pattern, cnt in sorted_patterns:
        print(f"予測{pattern:<10} {cnt:>8,} {100*cnt/total_miss:>7.1f}%")


def analyze_venue_performance(rows, cond_name):
    """会場別パフォーマンス"""
    if not rows:
        return

    venue_stats = {}
    for r in rows:
        venue = r[1]  # venue_code
        if venue not in venue_stats:
            venue_stats[venue] = {'total': 0, 'hits': 0, 'payout': 0}
        venue_stats[venue]['total'] += 1
        venue_stats[venue]['hits'] += r[10]  # is_hit
        venue_stats[venue]['payout'] += r[16]  # payout

    print(f"\n### {cond_name} 会場別パフォーマンス")
    print("-" * 70)
    print(f"{'会場':<8} {'件数':>6} {'的中':>4} {'的中率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 70)

    # ROI順でソート
    sorted_venues = sorted(venue_stats.items(),
                          key=lambda x: x[1]['payout'] / (x[1]['total'] * 100) if x[1]['total'] > 0 else 0)

    for venue, stats in sorted_venues:
        if stats['total'] < 3:  # 3件未満は除外
            continue
        venue_name = VENUE_NAMES.get(venue, f'会場{venue}')
        hit_rate = 100 * stats['hits'] / stats['total']
        roi = 100 * stats['payout'] / (stats['total'] * 100)
        profit = stats['payout'] - (stats['total'] * 100)
        mark = "✓" if roi >= 100 else "✗"
        print(f"{venue_name:<8} {stats['total']:>6} {stats['hits']:>4} {hit_rate:>7.1f}% {roi:>7.1f}% {profit:>+12,.0f} {mark}")


def analyze_year_performance(rows, cond_name):
    """年度別パフォーマンス"""
    if not rows:
        return

    year_stats = {}
    for r in rows:
        year = r[2]  # year
        if year not in year_stats:
            year_stats[year] = {'total': 0, 'hits': 0, 'payout': 0}
        year_stats[year]['total'] += 1
        year_stats[year]['hits'] += r[10]  # is_hit
        year_stats[year]['payout'] += r[16]  # payout

    print(f"\n### {cond_name} 年度別パフォーマンス")
    print("-" * 60)
    print(f"{'年度':<6} {'件数':>6} {'的中':>4} {'的中率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 60)

    black_years = 0
    for year in sorted(year_stats.keys()):
        stats = year_stats[year]
        hit_rate = 100 * stats['hits'] / stats['total'] if stats['total'] > 0 else 0
        roi = 100 * stats['payout'] / (stats['total'] * 100) if stats['total'] > 0 else 0
        profit = stats['payout'] - (stats['total'] * 100)
        mark = "✓" if roi >= 100 else "✗"
        if roi >= 100:
            black_years += 1
        print(f"{year:<6} {stats['total']:>6} {stats['hits']:>4} {hit_rate:>7.1f}% {roi:>7.1f}% {profit:>+12,.0f} {mark}")

    total_years = len(year_stats)
    print(f"\n黒字年数: {black_years}/{total_years}年")


def analyze_12_miss_when_1st_hit(rows, cond_name):
    """1着的中時の2着ミスパターン"""
    # 1着的中、2着ミスのケース
    cases = [r for r in rows if r[11] == 1 and r[12] == 0]  # is_1st_hit=1, is_12_hit=0
    if not cases:
        return

    pattern_counts = {}
    for r in cases:
        p2 = r[7]  # 予測2着
        actual_2nd = r[14]  # 実際2着
        key = f"{p2}→{actual_2nd}"
        pattern_counts[key] = pattern_counts.get(key, 0) + 1

    print(f"\n### {cond_name} 1着○時の2着ミスパターン")
    print("-" * 60)
    sorted_patterns = sorted(pattern_counts.items(), key=lambda x: -x[1])[:10]
    print(f"{'パターン':<15} {'件数':>8} {'割合':>8}")
    print("-" * 40)
    total = len(cases)
    for pattern, cnt in sorted_patterns:
        print(f"予測{pattern:<10} {cnt:>8,} {100*cnt/total:>7.1f}%")


def main():
    print("=" * 80)
    print("不的中パターン傾向分析（フィルターC適用後・6年間）")
    print("=" * 80)
    print("対象: 現行購入条件に合致するレースのみ")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 全条件の合計
    all_rows = []

    for cond in CONDITIONS:
        print("\n")
        print("=" * 80)
        print(f"【{cond['name']}】")
        print("=" * 80)

        rows = analyze_condition_detail(cursor, cond, 2020, 2025)
        if not rows:
            print("該当データなし")
            continue

        all_rows.extend(rows)

        # 各分析を実行
        analyze_miss_breakdown(rows, cond['name'])
        analyze_year_performance(rows, cond['name'])
        analyze_1st_miss_pattern(rows, cond['name'])
        analyze_12_miss_when_1st_hit(rows, cond['name'])
        analyze_venue_performance(rows, cond['name'])

    # 全体サマリー
    print("\n")
    print("=" * 80)
    print("【全条件合計】")
    print("=" * 80)

    if all_rows:
        total = len(all_rows)
        hits = sum(1 for r in all_rows if r[10] == 1)
        first_hits = sum(1 for r in all_rows if r[11] == 1)
        first_second_hits = sum(1 for r in all_rows if r[12] == 1)
        total_payout = sum(r[16] for r in all_rows)

        misses = total - hits
        first_miss = total - first_hits
        first_hit_second_miss = first_hits - first_second_hits
        first_second_hit_third_miss = first_second_hits - hits

        print(f"\n総購入数: {total}件")
        print(f"的中: {hits}件 ({100*hits/total:.1f}%)")
        print(f"不的中: {misses}件 ({100*misses/total:.1f}%)")
        print()
        print("【不的中の内訳（全体）】")
        print(f"  1着外し: {first_miss}件 ({100*first_miss/total:.1f}%)")
        print(f"  1着○2着×: {first_hit_second_miss}件 ({100*first_hit_second_miss/total:.1f}%)")
        print(f"  1-2着○3着×: {first_second_hit_third_miss}件 ({100*first_second_hit_third_miss/total:.1f}%)")

        roi = 100 * total_payout / (total * 100)
        profit = total_payout - (total * 100)
        print(f"\n6年間合計 ROI: {roi:.1f}%, 収支: {profit:+,.0f}円")

    conn.close()

    print("\n")
    print("=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == '__main__':
    main()
