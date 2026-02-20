# -*- coding: utf-8 -*-
"""
不的中パターン分析
==================

既存購入条件の不的中レースを分析し、除外すべきパターンを探索する。

目的:
    - 不的中レースの共通特徴を発見
    - 除外条件の候補を特定
    - 収益改善の可能性を定量化

使用例:
    python scripts/analysis/analyze_miss_patterns.py
"""

import sqlite3
import sys
import io
import os
from datetime import datetime
from collections import defaultdict

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


def get_condition_races(cursor, cond, year_start=2020, year_end=2025):
    """条件に該当するレースを取得"""
    c1_rank_str = "','".join(cond['c1_rank'])
    venue_clause = ""
    if cond.get('venue_filter'):
        venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"

    motor_clause = ""
    if cond.get('motor_min'):
        motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

    race_exclude_clause = ""
    if cond.get('race_exclude'):
        race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"

    venue_exclude_clause = ""
    if cond.get('venue_exclude'):
        venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    query = f'''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.race_number,
            r.venue_code,
            rp.confidence,
            e1.racer_rank as c1_rank,
            e1.motor_second_rate,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {motor_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        {predicted_course_clause}
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
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    )
    SELECT
        race_id, race_date, race_number, venue_code, confidence, c1_rank,
        motor_second_rate, p1, p2, p3, pred_odds, is_hit,
        actual_1st, actual_2nd, actual_3rd
    FROM race_bets
    WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
    '''
    cursor.execute(query)
    return cursor.fetchall()


def analyze_miss_by_venue(misses):
    """会場別の不的中分析"""
    venue_stats = defaultdict(lambda: {'count': 0, 'loss': 0})

    for race in misses:
        venue_code = race[3]
        venue_stats[venue_code]['count'] += 1
        venue_stats[venue_code]['loss'] += 100  # 1レース100円損失

    return venue_stats


def analyze_miss_by_race_number(misses):
    """レース番号別の不的中分析"""
    race_stats = defaultdict(lambda: {'count': 0, 'loss': 0})

    for race in misses:
        race_number = race[2]
        race_stats[race_number]['count'] += 1
        race_stats[race_number]['loss'] += 100

    return race_stats


def analyze_miss_by_predicted_course(misses):
    """予測1着コース別の不的中分析"""
    course_stats = defaultdict(lambda: {'count': 0, 'loss': 0})

    for race in misses:
        p1 = race[7]  # 予測1着
        course_stats[p1]['count'] += 1
        course_stats[p1]['loss'] += 100

    return course_stats


def analyze_miss_by_actual_1st(misses):
    """実際の1着コース別の不的中分析"""
    actual_stats = defaultdict(lambda: {'count': 0, 'loss': 0})

    for race in misses:
        actual_1st = race[12]
        if actual_1st:
            actual_stats[actual_1st]['count'] += 1
            actual_stats[actual_1st]['loss'] += 100

    return actual_stats


def analyze_miss_by_odds_band(misses):
    """オッズ帯別の不的中分析"""
    odds_stats = defaultdict(lambda: {'count': 0, 'loss': 0})

    for race in misses:
        odds = race[10]
        if odds < 20:
            band = '10-20'
        elif odds < 30:
            band = '20-30'
        elif odds < 40:
            band = '30-40'
        elif odds < 50:
            band = '40-50'
        elif odds < 60:
            band = '50-60'
        elif odds < 80:
            band = '60-80'
        elif odds < 100:
            band = '80-100'
        else:
            band = '100+'

        odds_stats[band]['count'] += 1
        odds_stats[band]['loss'] += 100

    return odds_stats


def main():
    print("=" * 80)
    print("不的中パターン分析")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 主要条件を分析
    conditions = [
        {'name': 'D×35-60', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'],
         'odds_min': 35, 'odds_max': 60, 'race_exclude': [9], 'venue_exclude': [10]},
        {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'],
         'odds_min': 40, 'odds_max': 50},
        {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'],
         'odds_min': 20, 'odds_max': 30,
         'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},
    ]

    for cond in conditions:
        print(f"\n{'='*60}")
        print(f"条件: {cond['name']}")
        print("=" * 60)

        races = get_condition_races(cursor, cond)
        if not races:
            print("該当レースなし")
            continue

        hits = [r for r in races if r[11] == 1]
        misses = [r for r in races if r[11] == 0]

        total = len(races)
        hit_count = len(hits)
        miss_count = len(misses)
        hit_rate = hit_count / total * 100 if total > 0 else 0

        print(f"\n全体: {total}件, 的中: {hit_count}件 ({hit_rate:.1f}%), 不的中: {miss_count}件")
        print(f"不的中による損失: -{miss_count * 100:,}円")

        # 会場別分析
        print("\n--- 会場別 不的中 ---")
        venue_stats = analyze_miss_by_venue(misses)
        sorted_venues = sorted(venue_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        for venue_code, stats in sorted_venues[:10]:
            venue_name = VENUE_NAMES.get(venue_code, str(venue_code))
            # 会場ごとの的中も計算
            venue_hits = len([r for r in hits if r[3] == venue_code])
            venue_total = stats['count'] + venue_hits
            venue_roi = (venue_hits * 50 * 100 - venue_total * 100) / (venue_total * 100) * 100 + 100 if venue_total > 0 else 0
            print(f"  {venue_name}: {stats['count']}件 (損失 -{stats['loss']:,}円)")

        # レース番号別分析
        print("\n--- レース番号別 不的中 ---")
        race_stats = analyze_miss_by_race_number(misses)
        for race_num in sorted(race_stats.keys()):
            stats = race_stats[race_num]
            # レース番号ごとの的中も計算
            race_hits = len([r for r in hits if r[2] == race_num])
            race_total = stats['count'] + race_hits
            if race_total >= 10:
                race_roi_approx = race_hits / race_total * 100 if race_total > 0 else 0
                print(f"  {race_num}R: 不的中{stats['count']}件, 的中{race_hits}件 (的中率 {race_roi_approx:.1f}%)")

        # 予測1着コース別分析
        print("\n--- 予測1着コース別 不的中 ---")
        course_stats = analyze_miss_by_predicted_course(misses)
        for course in sorted(course_stats.keys()):
            stats = course_stats[course]
            course_hits = len([r for r in hits if r[7] == course])
            course_total = stats['count'] + course_hits
            if course_total >= 10:
                course_hit_rate = course_hits / course_total * 100 if course_total > 0 else 0
                print(f"  {course}コース予測: 不的中{stats['count']}件, 的中{course_hits}件 (的中率 {course_hit_rate:.1f}%)")

        # 実際の1着コース別分析
        print("\n--- 実際の1着コース別 不的中 ---")
        actual_stats = analyze_miss_by_actual_1st(misses)
        for actual in sorted(actual_stats.keys()):
            stats = actual_stats[actual]
            if stats['count'] >= 10:
                print(f"  実際{actual}コース1着: {stats['count']}件 (損失 -{stats['loss']:,}円)")

        # オッズ帯別分析
        print("\n--- オッズ帯別 不的中 ---")
        odds_stats = analyze_miss_by_odds_band(misses)
        for band in ['10-20', '20-30', '30-40', '40-50', '50-60', '60-80', '80-100', '100+']:
            if band in odds_stats:
                stats = odds_stats[band]
                band_hits = len([r for r in hits if
                    (band == '10-20' and 10 <= r[10] < 20) or
                    (band == '20-30' and 20 <= r[10] < 30) or
                    (band == '30-40' and 30 <= r[10] < 40) or
                    (band == '40-50' and 40 <= r[10] < 50) or
                    (band == '50-60' and 50 <= r[10] < 60) or
                    (band == '60-80' and 60 <= r[10] < 80) or
                    (band == '80-100' and 80 <= r[10] < 100) or
                    (band == '100+' and r[10] >= 100)
                ])
                band_total = stats['count'] + band_hits
                band_hit_rate = band_hits / band_total * 100 if band_total > 0 else 0
                print(f"  {band}倍: 不的中{stats['count']}件, 的中{band_hits}件 (的中率 {band_hit_rate:.1f}%)")

    conn.close()

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
