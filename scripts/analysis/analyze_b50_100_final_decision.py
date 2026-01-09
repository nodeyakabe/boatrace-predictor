#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B×50-100条件 最終判定レポート

前回分析結果との整合性確認と最終判定
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
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: 'びわこ', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


def analyze_filter(cursor, venue_exclude=None, course_exclude=None):
    """フィルター条件で年度別分析"""
    confidence = 'B'
    c1_rank = ['A1', 'B1']
    odds_min = 50
    odds_max = 100
    c1_rank_str = "','".join(c1_rank)

    venue_clause = ""
    if venue_exclude:
        venue_clause = f"AND r.venue_code NOT IN ({','.join(map(str, venue_exclude))})"

    course_clause = ""
    if course_exclude:
        course_clause = f"AND rp1.pit_number NOT IN ({','.join(map(str, course_exclude))})"

    results = []
    for year in range(2020, 2026):
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
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{year}-01-01'
            AND r.race_date < '{year}-12-01'
            {venue_clause}
            {course_clause}
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
            COUNT(*) as bets,
            SUM(payout) as payout
        FROM race_bets
        WHERE pred_odds >= {odds_min} AND pred_odds < {odds_max}
        '''
        cursor.execute(query)
        row = cursor.fetchone()
        bets, payout = row
        cost = (bets or 0) * 100
        payout = payout or 0
        roi = 100.0 * payout / cost if cost > 0 else 0
        profit = payout - cost
        results.append({'year': year, 'bets': bets or 0, 'roi': roi, 'profit': profit})

    return results


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 100)
    print("B×50-100条件 最終判定レポート")
    print("=" * 100)
    print()
    print("採用基準: 直近4年（2022-2025）で3年以上黒字")
    print()

    # 案の定義
    cases = [
        {
            'name': '現状（フィルターなし）',
            'venue_exclude': None,
            'course_exclude': None,
        },
        {
            'name': '案A: 赤字5会場除外（前回分析ベース）',
            'venue_exclude': [21, 10, 14, 18, 20],  # 芦屋,三国,鳴門,徳山,若松
            'course_exclude': None,
        },
        {
            'name': '案A2: ROI 0%会場除外（10会場）',
            'venue_exclude': [10, 12, 13, 14, 15, 18, 20, 21, 23, 24],
            'course_exclude': None,
        },
        {
            'name': '案C: 2・5コース予測除外',
            'venue_exclude': None,
            'course_exclude': [2, 5],
        },
        {
            'name': '案E1: 赤字5会場除外 + 2・5コース除外',
            'venue_exclude': [21, 10, 14, 18, 20],
            'course_exclude': [2, 5],
        },
        {
            'name': '案E3: ROI 0%会場除外 + 2コース除外',
            'venue_exclude': [10, 12, 13, 14, 15, 18, 20, 21, 23, 24],
            'course_exclude': [2],
        },
    ]

    print("[案別 年度別詳細]")
    print("-" * 100)

    all_results = []

    for case in cases:
        results = analyze_filter(cursor, case['venue_exclude'], case['course_exclude'])
        total_bets = sum(r['bets'] for r in results)
        total_profit = sum(r['profit'] for r in results)
        total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100) if total_bets > 0 else 0
        profitable_6 = sum(1 for r in results if r['profit'] > 0)
        recent_4 = [r for r in results if r['year'] >= 2022]
        profitable_4 = sum(1 for r in recent_4 if r['profit'] > 0)

        all_results.append({
            'name': case['name'],
            'results': results,
            'total_bets': total_bets,
            'total_roi': total_roi,
            'total_profit': total_profit,
            'profitable_6': profitable_6,
            'profitable_4': profitable_4,
            'venue_exclude': case['venue_exclude'],
            'course_exclude': case['course_exclude'],
        })

        print(f"\n{case['name']}")
        if case['venue_exclude']:
            venue_names = [VENUE_NAMES[v] for v in case['venue_exclude']]
            print(f"  除外会場: {', '.join(venue_names)}")
        if case['course_exclude']:
            print(f"  除外コース: {case['course_exclude']}")
        print(f"  {'年度':<6} {'件数':>6} {'ROI':>8} {'収支':>12}")
        print("  " + "-" * 40)
        for r in results:
            status = "+" if r['profit'] > 0 else ""
            print(f"  {r['year']:<6} {r['bets']:>6} {r['roi']:>7.1f}% {r['profit']:>+12,.0f}")
        print("  " + "-" * 40)
        print(f"  {'合計':<6} {total_bets:>6} {total_roi:>7.1f}% {total_profit:>+12,.0f}")
        print(f"  黒字年: {profitable_6}/6年、直近4年: {profitable_4}/4年")

    print()
    print("=" * 100)
    print("採用判定サマリー")
    print("=" * 100)
    print()
    print(f"{'案':<45} {'件数':>6} {'ROI':>8} {'収支':>12} {'6年':>6} {'直近4年':>8} {'判定':<10}")
    print("-" * 100)

    for r in all_results:
        meets = r['profitable_4'] >= 3
        has_volume = r['total_bets'] >= 100
        if meets and has_volume:
            judgment = "採用推奨"
        elif meets:
            judgment = "保留"
        else:
            judgment = "不採用"

        print(f"{r['name']:<45} {r['total_bets']:>6} {r['total_roi']:>7.1f}% {r['total_profit']:>+12,.0f} {r['profitable_6']}/6年 {r['profitable_4']}/4年   {judgment}")

    print()
    print("-" * 100)
    print()
    print("=" * 100)
    print("最終結論")
    print("=" * 100)
    print()

    # 最良案の特定
    adoptable = [r for r in all_results if r['profitable_4'] >= 3 and r['total_bets'] >= 100]
    if adoptable:
        best = max(adoptable, key=lambda x: x['total_roi'])
        print(f"【採用推奨】{best['name']}")
        print(f"  - 6年間件数: {best['total_bets']}件")
        print(f"  - 6年間ROI: {best['total_roi']:.1f}%")
        print(f"  - 6年間収支: {best['total_profit']:+,.0f}円")
        print(f"  - 黒字年数: {best['profitable_6']}/6年、直近4年: {best['profitable_4']}/4年")
        print()

        if best['venue_exclude']:
            venue_names = [VENUE_NAMES[v] for v in best['venue_exclude']]
            print(f"  【実装】venue_filter除外: {best['venue_exclude']}")
            print(f"         ({', '.join(venue_names)})")
        if best['course_exclude']:
            print(f"  【実装】predicted_course除外: {best['course_exclude']}")
        if not best['venue_exclude'] and not best['course_exclude']:
            print("  【実装】フィルター変更なし（現状維持）")

    print()
    print("=" * 100)
    print("比較分析")
    print("=" * 100)
    print()

    baseline = all_results[0]  # 現状
    print(f"{'案':<45} {'ROI改善':>10} {'収支改善':>12} {'件数変化':>10}")
    print("-" * 100)
    for r in all_results[1:]:
        roi_diff = r['total_roi'] - baseline['total_roi']
        profit_diff = r['total_profit'] - baseline['total_profit']
        bets_diff = r['total_bets'] - baseline['total_bets']
        print(f"{r['name']:<45} {roi_diff:>+9.1f}pt {profit_diff:>+12,.0f} {bets_diff:>+10}")

    print()
    print("-" * 100)
    print()
    print("【注記】")
    print("  - 会場フィルター適用はROI大幅改善だが件数減少のトレードオフあり")
    print("  - 件数が減少すると統計的信頼性が低下し、将来の変動リスク増")
    print("  - 実運用では件数とROIのバランスを考慮")
    print()

    conn.close()


if __name__ == '__main__':
    main()
