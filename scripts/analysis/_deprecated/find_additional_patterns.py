# -*- coding: utf-8 -*-
"""
追加採用候補パターン探索
========================

継続監視パターンおよびその他の条件から、
採用可能なパターンを探索する。

採用基準:
- 6年中4年以上黒字
- 直近2年で黒字
- サンプル数50件以上
- ROI 110%以上

使用例:
    python scripts/analysis/find_additional_patterns.py
"""

import sqlite3
import sys
import io
import os
from datetime import datetime
from itertools import product

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': '琵琶湖', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}


def analyze_pattern(cursor, confidence, c1_ranks, odds_min, odds_max,
                    venue_filter=None, predicted_course=None, race_exclude=None):
    """パターンを分析"""
    c1_rank_str = "','".join(c1_ranks)
    venue_clause = ""
    if venue_filter:
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, venue_filter))})"

    predicted_course_clause = ""
    if predicted_course:
        predicted_course_clause = f"AND rp1.pit_number = {predicted_course}"

    race_exclude_clause = ""
    if race_exclude:
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, race_exclude))})"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            substr(r.race_date, 1, 4) as year,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.confidence = '{confidence}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        {venue_clause}
        {predicted_course_clause}
        {race_exclude_clause}
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
        SUM(payout) as payout
    FROM race_bets
    WHERE pred_odds >= {odds_min} AND pred_odds < {odds_max}
    GROUP BY year
    ORDER BY year
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    results = {y: {'bets': 0, 'hits': 0, 'payout': 0} for y in years}

    for row in rows:
        year, bets, hits, payout = row
        if year in results:
            results[year] = {'bets': bets, 'hits': hits or 0, 'payout': payout or 0}

    total_bets = sum(r['bets'] for r in results.values())
    total_payout = sum(r['payout'] for r in results.values())
    total_invest = total_bets * 100
    total_roi = total_payout / total_invest * 100 if total_invest > 0 else 0
    total_profit = total_payout - total_invest

    positive_years = 0
    recent_profit = 0
    for y in years:
        r = results[y]
        invest = r['bets'] * 100
        profit = r['payout'] - invest
        if profit > 0:
            positive_years += 1
        if y in ['2024', '2025']:
            recent_profit += profit

    return {
        'total': total_bets,
        'roi': total_roi,
        'profit': total_profit,
        'positive_years': positive_years,
        'recent_profit': recent_profit,
        'yearly': results
    }


def main():
    print("=" * 80)
    print("追加採用候補パターン探索")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    candidates = []

    # D条件: 他のコース予測
    print("\n--- D × コース別予測 ---")
    for course in [2, 3, 4, 6]:
        r = analyze_pattern(cursor, 'D', ['A1', 'A2', 'B1', 'B2'], 10, 200, predicted_course=course)
        if r['total'] >= 50 and r['roi'] >= 110:
            print(f"  D×{course}コース予測: {r['total']}件, ROI {r['roi']:.1f}%, {r['positive_years']}/6年黒字, 直近2年 {r['recent_profit']:+,.0f}円")
            if r['positive_years'] >= 4 and r['recent_profit'] > 0:
                candidates.append({
                    'name': f'D×{course}コース予測',
                    **r
                })

    # C条件: 他のオッズ帯
    print("\n--- C × オッズ帯別 ---")
    for odds_min, odds_max in [(30, 50), (50, 80), (80, 100)]:
        for rank in [['A1'], ['A2'], ['B1']]:
            r = analyze_pattern(cursor, 'C', rank, odds_min, odds_max)
            rank_str = rank[0]
            if r['total'] >= 50 and r['roi'] >= 110:
                print(f"  C×{rank_str}×{odds_min}-{odds_max}: {r['total']}件, ROI {r['roi']:.1f}%, {r['positive_years']}/6年黒字")
                if r['positive_years'] >= 4 and r['recent_profit'] > 0:
                    candidates.append({
                        'name': f'C×{rank_str}×{odds_min}-{odds_max}',
                        **r
                    })

    # D条件: 会場別（主要会場）
    print("\n--- D × 会場別 ---")
    for venue in [6, 8, 9, 15, 18, 20, 21, 24]:  # 高ROI会場候補
        venue_name = VENUE_NAMES.get(f'{venue:02d}', str(venue))
        r = analyze_pattern(cursor, 'D', ['A1', 'A2', 'B1'], 30, 60, venue_filter=[venue])
        if r['total'] >= 30 and r['roi'] >= 120:
            print(f"  D×{venue_name}×30-60: {r['total']}件, ROI {r['roi']:.1f}%, {r['positive_years']}/6年黒字, 直近 {r['recent_profit']:+,.0f}円")
            if r['positive_years'] >= 4 and r['recent_profit'] > 0 and r['total'] >= 50:
                candidates.append({
                    'name': f'D×{venue_name}×30-60',
                    **r
                })

    # B条件: 20-30倍帯
    print("\n--- B × 20-30倍 ---")
    for rank in [['A1'], ['A2'], ['B1']]:
        r = analyze_pattern(cursor, 'B', rank, 20, 30)
        rank_str = rank[0]
        if r['total'] >= 50 and r['roi'] >= 110:
            print(f"  B×{rank_str}×20-30: {r['total']}件, ROI {r['roi']:.1f}%, {r['positive_years']}/6年黒字")
            if r['positive_years'] >= 4 and r['recent_profit'] > 0:
                candidates.append({
                    'name': f'B×{rank_str}×20-30',
                    **r
                })

    # D × 100倍+ の詳細分析
    print("\n--- D × 100倍+ 詳細 ---")
    for rank in [['A1'], ['A2'], ['B1']]:
        r = analyze_pattern(cursor, 'D', rank, 100, 500)
        rank_str = rank[0]
        if r['total'] >= 30:
            print(f"  D×{rank_str}×100+: {r['total']}件, ROI {r['roi']:.1f}%, {r['positive_years']}/6年黒字, 直近 {r['recent_profit']:+,.0f}円")
            if r['positive_years'] >= 4 and r['recent_profit'] > 0 and r['total'] >= 50:
                candidates.append({
                    'name': f'D×{rank_str}×100+',
                    **r
                })

    conn.close()

    # サマリー
    print("\n" + "=" * 80)
    print("採用候補パターン")
    print("=" * 80)

    if candidates:
        for c in sorted(candidates, key=lambda x: (x['positive_years'], x['roi']), reverse=True):
            print(f"\n{c['name']}:")
            print(f"  件数: {c['total']}, ROI: {c['roi']:.1f}%, 収支: {c['profit']:+,.0f}円")
            print(f"  黒字年数: {c['positive_years']}/6年, 直近2年: {c['recent_profit']:+,.0f}円")
    else:
        print("\n採用基準を満たすパターンはありませんでした。")


if __name__ == "__main__":
    main()
