#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
信頼度×会場別 不的中パターン詳細分析

目的:
    各信頼度（A/B/C/D）と各会場の組み合わせでの
    不的中傾向を詳細に分析し、改善ポイントを特定

使用方法:
    python scripts/backtest/analyze_miss_by_confidence_venue.py
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


def analyze_confidence_venue_matrix(cursor):
    """信頼度×会場のROIマトリクスを作成"""
    print("=" * 100)
    print("信頼度×会場 ROIマトリクス（6年間: 2020-2025年、オッズ10-100倍）")
    print("=" * 100)

    results = {}

    for confidence in ['A', 'B', 'C', 'D']:
        results[confidence] = {}

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
            AND e1.racer_rank IN ('A1', 'A2', 'B1')
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
            venue_code,
            COUNT(*) as total,
            SUM(is_hit) as hits,
            SUM(is_1st_hit) as first_hits,
            ROUND(100.0 * SUM(is_hit) / COUNT(*), 2) as hit_rate,
            ROUND(100.0 * SUM(is_1st_hit) / COUNT(*), 1) as first_hit_rate,
            ROUND(100.0 * SUM(payout) / (COUNT(*) * 100), 1) as roi,
            SUM(payout) - (COUNT(*) * 100) as profit
        FROM race_with_result
        WHERE pred_odds >= 10 AND pred_odds < 100
        GROUP BY venue_code
        ORDER BY venue_code
        '''
        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            venue_code, total, hits, first_hits, hit_rate, first_hit_rate, roi, profit = row
            results[confidence][venue_code] = {
                'total': total,
                'hits': hits,
                'first_hits': first_hits,
                'hit_rate': hit_rate,
                'first_hit_rate': first_hit_rate,
                'roi': roi,
                'profit': profit
            }

    return results


def print_roi_heatmap(results):
    """ROIヒートマップ形式で表示"""
    print("\n### ROIヒートマップ（赤字=✗、黒字=✓）")
    print("-" * 100)

    # ヘッダー
    header = f"{'会場':<8}"
    for conf in ['A', 'B', 'C', 'D']:
        header += f"  {conf:>8}"
    print(header)
    print("-" * 100)

    # 全会場のデータを表示
    for venue_code in range(1, 25):
        venue_name = VENUE_NAMES.get(venue_code, f'会場{venue_code}')
        row = f"{venue_name:<8}"

        for conf in ['A', 'B', 'C', 'D']:
            data = results[conf].get(venue_code)
            if data and data['total'] >= 10:
                roi = data['roi']
                mark = "✓" if roi >= 100 else "✗"
                row += f"  {roi:>6.1f}%{mark}"
            else:
                row += f"  {'---':>8}"
        print(row)


def find_worst_combinations(results, min_count=30):
    """最悪の信頼度×会場組み合わせを特定"""
    print("\n\n" + "=" * 100)
    print("信頼度×会場 ワースト20（6年間赤字の組み合わせ）")
    print("条件: 30件以上のサンプル")
    print("=" * 100)

    combinations = []

    for conf in ['A', 'B', 'C', 'D']:
        for venue_code, data in results[conf].items():
            if data['total'] >= min_count:
                combinations.append({
                    'confidence': conf,
                    'venue_code': venue_code,
                    'venue_name': VENUE_NAMES.get(venue_code, f'会場{venue_code}'),
                    'total': data['total'],
                    'hits': data['hits'],
                    'first_hit_rate': data['first_hit_rate'],
                    'roi': data['roi'],
                    'profit': data['profit']
                })

    # 収支でソート（悪い順）
    worst = sorted(combinations, key=lambda x: x['profit'])[:20]

    print(f"\n{'信頼度':<6} {'会場':<8} {'件数':>6} {'的中':>4} {'1着率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 70)

    for c in worst:
        print(f"{c['confidence']:<6} {c['venue_name']:<8} {c['total']:>6} {c['hits']:>4} {c['first_hit_rate']:>7.1f}% {c['roi']:>7.1f}% {c['profit']:>+12,.0f}")


def find_best_combinations(results, min_count=30):
    """最良の信頼度×会場組み合わせを特定"""
    print("\n\n" + "=" * 100)
    print("信頼度×会場 ベスト20（6年間黒字の組み合わせ）")
    print("条件: 30件以上のサンプル")
    print("=" * 100)

    combinations = []

    for conf in ['A', 'B', 'C', 'D']:
        for venue_code, data in results[conf].items():
            if data['total'] >= min_count and data['roi'] >= 100:
                combinations.append({
                    'confidence': conf,
                    'venue_code': venue_code,
                    'venue_name': VENUE_NAMES.get(venue_code, f'会場{venue_code}'),
                    'total': data['total'],
                    'hits': data['hits'],
                    'first_hit_rate': data['first_hit_rate'],
                    'roi': data['roi'],
                    'profit': data['profit']
                })

    # 収支でソート（良い順）
    best = sorted(combinations, key=lambda x: -x['profit'])[:20]

    print(f"\n{'信頼度':<6} {'会場':<8} {'件数':>6} {'的中':>4} {'1着率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 70)

    for c in best:
        print(f"{c['confidence']:<6} {c['venue_name']:<8} {c['total']:>6} {c['hits']:>4} {c['first_hit_rate']:>7.1f}% {c['roi']:>7.1f}% {c['profit']:>+12,.0f}")


def analyze_miss_pattern_by_venue(cursor, confidence, venue_code):
    """特定の信頼度×会場での不的中パターン詳細"""
    venue_name = VENUE_NAMES.get(venue_code, f'会場{venue_code}')

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            substr(r.race_date, 1, 4) as year,
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
        AND r.venue_code = {venue_code}
        AND e1.racer_rank IN ('A1', 'A2', 'B1')
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
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                THEN 1 ELSE 0
            END as is_1st_hit
        FROM race_base rb
    )
    SELECT
        p1 as pred_1st,
        actual_1st,
        COUNT(*) as cnt
    FROM race_with_result
    WHERE pred_odds >= 10 AND pred_odds < 100
    AND is_1st_hit = 0
    GROUP BY p1, actual_1st
    ORDER BY cnt DESC
    LIMIT 5
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    return rows


def analyze_worst_combinations_detail(cursor, results):
    """ワースト組み合わせの詳細分析"""
    print("\n\n" + "=" * 100)
    print("ワースト組み合わせの1着ミスパターン詳細")
    print("=" * 100)

    # ワースト10を取得
    combinations = []
    for conf in ['A', 'B', 'C', 'D']:
        for venue_code, data in results[conf].items():
            if data['total'] >= 50 and data['roi'] < 80:
                combinations.append({
                    'confidence': conf,
                    'venue_code': venue_code,
                    'venue_name': VENUE_NAMES.get(venue_code, f'会場{venue_code}'),
                    'roi': data['roi'],
                    'profit': data['profit'],
                    'total': data['total']
                })

    worst = sorted(combinations, key=lambda x: x['profit'])[:10]

    for c in worst:
        print(f"\n### {c['confidence']}×{c['venue_name']} (ROI {c['roi']:.1f}%, {c['profit']:+,}円, {c['total']}件)")
        print("-" * 50)

        patterns = analyze_miss_pattern_by_venue(cursor, c['confidence'], c['venue_code'])
        if patterns:
            print("1着ミスパターン（上位5）:")
            for pred_1st, actual_1st, cnt in patterns:
                print(f"  予測{pred_1st}着 → 実際{actual_1st}着: {cnt}件")


def analyze_year_stability_by_confidence_venue(cursor):
    """信頼度×会場の年度別安定性分析"""
    print("\n\n" + "=" * 100)
    print("信頼度×会場 年度別安定性分析")
    print("条件: 6年間で50件以上、かつ赤字年が3年以上ある組み合わせ")
    print("=" * 100)

    unstable_combinations = []

    for confidence in ['A', 'B', 'C', 'D']:
        for venue_code in range(1, 25):
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
                AND r.venue_code = {venue_code}
                AND e1.racer_rank IN ('A1', 'A2', 'B1')
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
                SUM(payout) - (COUNT(*) * 100) as profit
            FROM race_with_result
            WHERE pred_odds >= 10 AND pred_odds < 100
            GROUP BY year
            ORDER BY year
            '''
            cursor.execute(query)
            rows = cursor.fetchall()

            if not rows:
                continue

            total_count = sum(r[1] for r in rows)
            if total_count < 50:
                continue

            red_years = sum(1 for r in rows if r[2] < 0)
            total_profit = sum(r[2] for r in rows)

            if red_years >= 3:
                unstable_combinations.append({
                    'confidence': confidence,
                    'venue_code': venue_code,
                    'venue_name': VENUE_NAMES.get(venue_code, f'会場{venue_code}'),
                    'total': total_count,
                    'red_years': red_years,
                    'total_profit': total_profit,
                    'years': rows
                })

    # 赤字年が多い順にソート
    unstable = sorted(unstable_combinations, key=lambda x: (-x['red_years'], x['total_profit']))[:15]

    print(f"\n{'信頼度':<6} {'会場':<8} {'件数':>6} {'赤字年':>6} {'6年収支':>12} {'年度別'}")
    print("-" * 90)

    for c in unstable:
        year_str = " ".join([f"{y[0][-2:]}:{'+' if y[2]>=0 else ''}{int(y[2]/1000)}k" for y in c['years']])
        print(f"{c['confidence']:<6} {c['venue_name']:<8} {c['total']:>6} {c['red_years']:>6}年 {c['total_profit']:>+12,.0f} {year_str}")


def main():
    print("=" * 100)
    print("信頼度×会場 不的中パターン詳細分析（上位AI分析用）")
    print("=" * 100)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 信頼度×会場マトリクス
    results = analyze_confidence_venue_matrix(cursor)
    print_roi_heatmap(results)

    # ワースト組み合わせ
    find_worst_combinations(results)

    # ベスト組み合わせ
    find_best_combinations(results)

    # ワースト組み合わせの詳細
    analyze_worst_combinations_detail(cursor, results)

    # 年度別安定性分析
    analyze_year_stability_by_confidence_venue(cursor)

    conn.close()

    print("\n")
    print("=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
