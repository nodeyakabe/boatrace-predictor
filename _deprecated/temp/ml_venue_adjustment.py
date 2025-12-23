# -*- coding: utf-8 -*-
"""
会場別加点・減点システムの最適化
基本重みは固定、会場特性は加点・減点で対応
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import numpy as np
from collections import defaultdict
from typing import Dict, List

from config.settings import (
    DATABASE_PATH, VENUE_IN1_RATES, HIGH_IN_VENUES, LOW_IN_VENUES,
    VENUE_UPSET_RATES, VENUE_MOTOR_IMPACT
)


def get_race_data(start_date: str, end_date: str) -> List[List[Dict]]:
    """レースデータを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            e.avg_st,
            COALESCE(res.rank, 99) as result_rank
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
        ORDER BY r.id, e.pit_number
    """

    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()
    conn.close()

    races = defaultdict(list)
    for row in rows:
        races[row['race_id']].append(dict(row))

    return list(races.values())


def calculate_score(
    entry: Dict,
    race_entries: List[Dict],
    venue_code: str,
    base_weights: Dict,
    adjustments: Dict
) -> float:
    """
    スコア計算（基本重み + 加点減点）

    Args:
        entry: エントリーデータ
        race_entries: レース全体のエントリー
        venue_code: 会場コード
        base_weights: 基本重み {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10}
        adjustments: 加点減点設定
    """
    score = 0.0
    pit = entry['pit_number']

    # === 基本スコア ===
    # コース
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
    course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * base_weights.get('course', 35) / 100

    # 選手
    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * base_weights.get('racer', 35) / 100

    # モーター
    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * base_weights.get('motor', 20) / 100

    # 級別
    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * base_weights.get('rank', 10) / 100

    # === ST加点（レース内相対評価） ===
    st_weight = adjustments.get('st_weight', 5)
    if st_weight > 0:
        avg_st = entry.get('avg_st')
        if avg_st is not None and avg_st > 0:
            valid_sts = [(e['pit_number'], e.get('avg_st') or 1.0)
                         for e in race_entries if e.get('avg_st') and e.get('avg_st') > 0]
            valid_sts.sort(key=lambda x: x[1])
            for i, (p, st) in enumerate(valid_sts, 1):
                if p == pit:
                    st_score = 100 - (i - 1) * 10
                    score += st_score * st_weight / 100
                    break

    # === 会場別加点・減点 ===

    # 1. 1コース × A1 ボーナス（堅い会場）
    if adjustments.get('solid_a1_bonus', 0) > 0:
        if pit == 1 and rank == 'A1' and venue_code in HIGH_IN_VENUES:
            score += adjustments['solid_a1_bonus']

    # 2. 1コース × B2 ペナルティ（堅い会場以外）
    if adjustments.get('chaotic_b2_penalty', 0) > 0:
        if pit == 1 and rank == 'B2' and venue_code in LOW_IN_VENUES:
            score -= adjustments['chaotic_b2_penalty']

    # 3. 荒れ会場での外コースA1ボーナス
    if adjustments.get('chaotic_outer_a1_bonus', 0) > 0:
        if pit >= 4 and rank == 'A1' and venue_code in LOW_IN_VENUES:
            score += adjustments['chaotic_outer_a1_bonus']

    # 4. モーター影響度の高い会場でのモーターボーナス
    if adjustments.get('motor_venue_bonus', 0) > 0:
        motor_impact = VENUE_MOTOR_IMPACT.get(venue_code, 1.5)
        if motor_impact >= 2.5:  # 高影響会場
            high_motor = (motor_rate or 30) >= 40
            if high_motor:
                score += adjustments['motor_venue_bonus']

    return score


def backtest(
    races: List[List[Dict]],
    base_weights: Dict,
    adjustments: Dict,
    label: str
) -> Dict:
    """バックテスト実行"""
    results = {'win_hits': 0, 'total': 0}
    venue_stats = defaultdict(lambda: {'win_hits': 0, 'total': 0})

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        venue = race_entries[0]['venue_code']

        scores = []
        for entry in race_entries:
            s = calculate_score(entry, race_entries, venue, base_weights, adjustments)
            scores.append((entry['pit_number'], s))

        scores.sort(key=lambda x: -x[1])
        predicted = scores[0][0]

        actual = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                actual = entry['pit_number']
                break

        results['total'] += 1
        venue_stats[venue]['total'] += 1

        if predicted == actual:
            results['win_hits'] += 1
            venue_stats[venue]['win_hits'] += 1

    return {
        'label': label,
        'win_rate': results['win_hits'] / results['total'] * 100,
        'results': results,
        'venue_stats': dict(venue_stats),
    }


def grid_search(races: List[List[Dict]], base_weights: Dict) -> List[Dict]:
    """加点・減点パラメータのグリッドサーチ"""
    results = []

    # パラメータ候補
    st_weights = [0, 3, 5, 8]
    solid_bonuses = [0, 1, 2, 3]
    chaotic_penalties = [0, 1, 2, 3]
    chaotic_bonuses = [0, 1, 2]
    motor_bonuses = [0, 1, 2]

    total = len(st_weights) * len(solid_bonuses) * len(chaotic_penalties) * len(chaotic_bonuses) * len(motor_bonuses)
    count = 0

    for st_w in st_weights:
        for solid_b in solid_bonuses:
            for chaotic_p in chaotic_penalties:
                for chaotic_b in chaotic_bonuses:
                    for motor_b in motor_bonuses:
                        count += 1
                        if count % 100 == 0:
                            print(f"  {count}/{total}...")

                        adjustments = {
                            'st_weight': st_w,
                            'solid_a1_bonus': solid_b,
                            'chaotic_b2_penalty': chaotic_p,
                            'chaotic_outer_a1_bonus': chaotic_b,
                            'motor_venue_bonus': motor_b,
                        }

                        result = backtest(races, base_weights, adjustments, '')
                        result['adjustments'] = adjustments
                        results.append(result)

    return results


def main():
    print('会場別加点・減点システムの最適化')
    print('=' * 70)
    print()

    start_date = '2024-01-01'
    end_date = '2024-11-20'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    print('データ取得中...')
    races = get_race_data(start_date, end_date)
    print(f"取得完了: {len(races):,}レース")
    print()

    # 基本重み（固定）
    base_weights = {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10}

    # ベースライン
    print('ベースライン計算中...')
    baseline = backtest(races, base_weights, {}, 'ベースライン')
    print(f"ベースライン単勝的中率: {baseline['win_rate']:.2f}%")
    print()

    # グリッドサーチ
    print('グリッドサーチ実行中...')
    results = grid_search(races, base_weights)
    print(f"完了: {len(results)}パターン")
    print()

    # 上位10件
    results.sort(key=lambda x: -x['win_rate'])

    print('=' * 70)
    print('上位10設定')
    print('=' * 70)
    print()

    for i, r in enumerate(results[:10], 1):
        adj = r['adjustments']
        print(f"【{i}位】 単勝的中率: {r['win_rate']:.2f}% (+{r['win_rate']-baseline['win_rate']:.2f}%)")
        print(f"  ST重み: {adj['st_weight']}")
        print(f"  堅い会場1コースA1ボーナス: +{adj['solid_a1_bonus']}")
        print(f"  荒れ会場1コースB2ペナルティ: -{adj['chaotic_b2_penalty']}")
        print(f"  荒れ会場外コースA1ボーナス: +{adj['chaotic_outer_a1_bonus']}")
        print(f"  高モーター会場ボーナス: +{adj['motor_venue_bonus']}")
        print()

    # 最良設定で会場別結果
    best = results[0]
    print('=' * 70)
    print(f"最良設定での会場別単勝的中率")
    print('=' * 70)
    print()

    # 比較
    best_venues = best['venue_stats']
    baseline_venues = baseline['venue_stats']

    venue_comparison = []
    for venue in best_venues:
        b_rate = baseline_venues[venue]['win_hits'] / baseline_venues[venue]['total'] * 100
        new_rate = best_venues[venue]['win_hits'] / best_venues[venue]['total'] * 100
        venue_comparison.append((venue, b_rate, new_rate, new_rate - b_rate))

    venue_comparison.sort(key=lambda x: -x[3])

    print(f"{'会場':<6} {'ベース':>10} {'最良':>10} {'差分':>10}")
    print('-' * 40)
    for venue, base_r, new_r, diff in venue_comparison:
        diff_str = f"+{diff:.1f}%" if diff >= 0 else f"{diff:.1f}%"
        print(f"{venue:<6} {base_r:>9.1f}% {new_r:>9.1f}% {diff_str:>10}")

    print()
    print('完了')


if __name__ == '__main__':
    main()
