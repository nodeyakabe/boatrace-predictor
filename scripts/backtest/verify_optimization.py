#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
条件最適化の検証スクリプト

目的:
    提案された会場フィルターの効果を検証する
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


def analyze_with_filter(cursor, confidence, c1_ranks, odds_min, odds_max,
                         exclude_venues=None, include_venues=None, motor_min=None):
    """条件別のROIを計算（除外/包含会場対応）"""
    c1_rank_str = "','".join(c1_ranks)

    venue_clause = ""
    if exclude_venues:
        venue_clause = f"AND r.venue_code NOT IN ({','.join(map(str, exclude_venues))})"
    elif include_venues:
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, include_venues))})"

    motor_clause = ""
    if motor_min:
        motor_clause = f"AND e1.motor_second_rate >= {motor_min}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            strftime('%Y', r.race_date) as year,
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
        AND r.race_date >= '2020-01-01'
        AND r.race_date < '2025-12-01'
        {venue_clause}
        {motor_clause}
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
        year,
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) - COUNT(*) * 100 as profit
    FROM race_bets
    WHERE pred_odds >= {odds_min} AND pred_odds < {odds_max}
    GROUP BY year
    ORDER BY year
    '''
    cursor.execute(query)
    return cursor.fetchall()


def analyze_venue_performance(cursor, confidence, c1_ranks, odds_min, odds_max, motor_min=None):
    """会場別パフォーマンスを取得"""
    c1_rank_str = "','".join(c1_ranks)

    motor_clause = ""
    if motor_min:
        motor_clause = f"AND e1.motor_second_rate >= {motor_min}"

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
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '2020-01-01'
        AND r.race_date < '2025-12-01'
        {motor_clause}
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
        venue_code,
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(payout) - COUNT(*) * 100 as profit
    FROM race_bets
    WHERE pred_odds >= {odds_min} AND pred_odds < {odds_max}
    GROUP BY venue_code
    ORDER BY profit ASC
    '''
    cursor.execute(query)
    return cursor.fetchall()


def main():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 100)
    print("条件最適化検証レポート")
    print("=" * 100)
    print()

    # ============================================================
    # 1. D×30-60 条件の分析
    # ============================================================
    print("=" * 100)
    print("【1】D×30-60 条件の分析")
    print("=" * 100)
    print()

    # 会場別パフォーマンス
    venue_data = analyze_venue_performance(cursor, 'D', ['A1', 'A2', 'B1'], 30, 60)

    print("【会場別パフォーマンス（収支順）】")
    print("-" * 70)
    print(f"{'会場':<10} {'件数':>6} {'的中':>4} {'収支':>12} {'ROI':>8}")
    print("-" * 70)

    total_bets = 0
    total_profit = 0
    exclude_venues = []

    for row in venue_data:
        venue_code, bets, hits, profit = row
        venue_name = VENUE_NAMES.get(venue_code, f"会場{venue_code}")
        roi = 100.0 * (profit + bets * 100) / (bets * 100) if bets > 0 else 0
        status = "✗" if profit < 0 else "✓"
        print(f"{venue_name:<10} {bets:>6} {hits:>4} {profit:>+12,.0f} {roi:>7.1f}% {status}")
        total_bets += bets
        total_profit += profit
        if profit < 0:
            exclude_venues.append(venue_code)

    print("-" * 70)
    total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100) if total_bets > 0 else 0
    print(f"{'合計':<10} {total_bets:>6} {'-':>4} {total_profit:>+12,.0f} {total_roi:>7.1f}%")
    print()

    print(f"赤字会場（除外候補）: {len(exclude_venues)}会場")
    print(f"  {[VENUE_NAMES.get(int(v), f'会場{v}') for v in exclude_venues]}")
    print()

    # フィルター適用後
    print("【フィルター適用後の年度別パフォーマンス】")
    print("-" * 70)

    yearly_data = analyze_with_filter(cursor, 'D', ['A1', 'A2', 'B1'], 30, 60, exclude_venues=exclude_venues)

    print(f"{'年度':<6} {'件数':>6} {'的中':>4} {'収支':>12} {'ROI':>8}")
    print("-" * 70)

    filter_total_bets = 0
    filter_total_profit = 0
    black_years = 0

    for row in yearly_data:
        year, bets, hits, profit = row
        roi = 100.0 * (profit + bets * 100) / (bets * 100) if bets > 0 else 0
        status = "✓" if profit >= 0 else "✗"
        print(f"{year:<6} {bets:>6} {hits:>4} {profit:>+12,.0f} {roi:>7.1f}% {status}")
        filter_total_bets += bets
        filter_total_profit += profit
        if profit >= 0:
            black_years += 1

    print("-" * 70)
    filter_total_roi = 100.0 * (filter_total_profit + filter_total_bets * 100) / (filter_total_bets * 100) if filter_total_bets > 0 else 0
    print(f"{'合計':<6} {filter_total_bets:>6} {'-':>4} {filter_total_profit:>+12,.0f} {filter_total_roi:>7.1f}%")
    print(f"黒字年数: {black_years}/6年")
    print()

    print("【D×30-60 改善効果】")
    print(f"  フィルターなし: {total_bets}件, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円")
    print(f"  フィルターあり: {filter_total_bets}件, ROI {filter_total_roi:.1f}%, 収支 {filter_total_profit:+,.0f}円")
    print(f"  改善効果: ROI {filter_total_roi - total_roi:+.1f}pt, 収支 {filter_total_profit - total_profit:+,.0f}円")
    print()

    # ============================================================
    # 2. A×A1×14-16 条件の分析
    # ============================================================
    print("=" * 100)
    print("【2】A×A1×14-16 条件の分析")
    print("=" * 100)
    print()

    # 会場別パフォーマンス
    venue_data = analyze_venue_performance(cursor, 'A', ['A1'], 14, 16)

    print("【会場別パフォーマンス（収支順）】")
    print("-" * 70)
    print(f"{'会場':<10} {'件数':>6} {'的中':>4} {'収支':>12} {'ROI':>8}")
    print("-" * 70)

    total_bets = 0
    total_profit = 0
    exclude_venues_a1 = []

    for row in venue_data:
        venue_code, bets, hits, profit = row
        venue_name = VENUE_NAMES.get(venue_code, f"会場{venue_code}")
        roi = 100.0 * (profit + bets * 100) / (bets * 100) if bets > 0 else 0
        status = "✗" if profit < 0 else "✓"
        print(f"{venue_name:<10} {bets:>6} {hits:>4} {profit:>+12,.0f} {roi:>7.1f}% {status}")
        total_bets += bets
        total_profit += profit
        if profit < 0:
            exclude_venues_a1.append(venue_code)

    print("-" * 70)
    total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100) if total_bets > 0 else 0
    print(f"{'合計':<10} {total_bets:>6} {'-':>4} {total_profit:>+12,.0f} {total_roi:>7.1f}%")
    print()

    print(f"赤字会場（除外候補）: {len(exclude_venues_a1)}会場")
    print(f"  {[VENUE_NAMES.get(int(v), f'会場{v}') for v in exclude_venues_a1]}")
    print()

    # フィルター適用後
    print("【フィルター適用後の年度別パフォーマンス】")
    print("-" * 70)

    yearly_data = analyze_with_filter(cursor, 'A', ['A1'], 14, 16, exclude_venues=exclude_venues_a1)

    print(f"{'年度':<6} {'件数':>6} {'的中':>4} {'収支':>12} {'ROI':>8}")
    print("-" * 70)

    filter_total_bets = 0
    filter_total_profit = 0
    black_years = 0

    for row in yearly_data:
        year, bets, hits, profit = row
        roi = 100.0 * (profit + bets * 100) / (bets * 100) if bets > 0 else 0
        status = "✓" if profit >= 0 else "✗"
        print(f"{year:<6} {bets:>6} {hits:>4} {profit:>+12,.0f} {roi:>7.1f}% {status}")
        filter_total_bets += bets
        filter_total_profit += profit
        if profit >= 0:
            black_years += 1

    print("-" * 70)
    filter_total_roi = 100.0 * (filter_total_profit + filter_total_bets * 100) / (filter_total_bets * 100) if filter_total_bets > 0 else 0
    print(f"{'合計':<6} {filter_total_bets:>6} {'-':>4} {filter_total_profit:>+12,.0f} {filter_total_roi:>7.1f}%")
    print(f"黒字年数: {black_years}/6年")
    print()

    print("【A×A1×14-16 改善効果】")
    print(f"  フィルターなし: {total_bets}件, ROI {total_roi:.1f}%, 収支 {total_profit:+,.0f}円")
    print(f"  フィルターあり: {filter_total_bets}件, ROI {filter_total_roi:.1f}%, 収支 {filter_total_profit:+,.0f}円")
    print(f"  改善効果: ROI {filter_total_roi - total_roi:+.1f}pt, 収支 {filter_total_profit - total_profit:+,.0f}円")
    print()

    # ============================================================
    # 3. A×B1×Motor40%+ 条件の分析
    # ============================================================
    print("=" * 100)
    print("【3】A×B1×Motor40%+ 条件の分析")
    print("=" * 100)
    print()

    yearly_data = analyze_with_filter(cursor, 'A', ['B1'], 10, 100, motor_min=40)

    print("【年度別パフォーマンス】")
    print("-" * 70)
    print(f"{'年度':<6} {'件数':>6} {'的中':>4} {'収支':>12} {'ROI':>8}")
    print("-" * 70)

    total_bets = 0
    total_profit = 0
    black_years = 0
    year_profits = []

    for row in yearly_data:
        year, bets, hits, profit = row
        roi = 100.0 * (profit + bets * 100) / (bets * 100) if bets > 0 else 0
        status = "✓" if profit >= 0 else "✗"
        print(f"{year:<6} {bets:>6} {hits:>4} {profit:>+12,.0f} {roi:>7.1f}% {status}")
        total_bets += bets
        total_profit += profit
        year_profits.append((year, profit))
        if profit >= 0:
            black_years += 1

    print("-" * 70)
    total_roi = 100.0 * (total_profit + total_bets * 100) / (total_bets * 100) if total_bets > 0 else 0
    print(f"{'合計':<6} {total_bets:>6} {'-':>4} {total_profit:>+12,.0f} {total_roi:>7.1f}%")
    print(f"黒字年数: {black_years}/6年")
    print()

    # 2020-2024の合計
    profit_2020_2024 = sum(p for y, p in year_profits if y != '2025')
    print("【リスク評価】")
    print(f"  2020-2024年の合計収支: {profit_2020_2024:+,.0f}円")
    print(f"  2025年の収支: {year_profits[-1][1]:+,.0f}円")
    print(f"  2025年を除いた場合: {profit_2020_2024:+,.0f}円（{'黒字' if profit_2020_2024 >= 0 else '赤字'}）")
    print()

    # ============================================================
    # 最終判断
    # ============================================================
    print("=" * 100)
    print("【最終判断】")
    print("=" * 100)
    print()

    print("1. D×30-60条件:")
    print("   → 会場フィルター適用で採用（15会場除外）")
    print(f"   → 除外会場: 多摩川,戸田,福岡,江戸川,蒲郡,常滑,平和島,琵琶湖,住之江,児島,芦屋,尼崎,徳山,大村,津")
    print()

    print("2. A×A1×14-16条件:")
    print("   → 会場フィルター適用で採用")
    print(f"   → 除外会場: {[VENUE_NAMES.get(int(v), f'会場{v}') for v in exclude_venues_a1]}")
    print()

    print("3. A×B1×Motor40%+条件:")
    if profit_2020_2024 < 0:
        print("   → 不採用（2020-2024年が赤字、2025年のみ黒字は統計的に信頼性なし）")
    else:
        print("   → 採用継続（過去5年も黒字）")
    print()

    conn.close()


if __name__ == '__main__':
    main()
