# -*- coding: utf-8 -*-
"""
積極的な改善案のバックテスト
展示STと展示タイムの重みを大幅に強化
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from collections import defaultdict
from typing import Dict, List

from config.settings import DATABASE_PATH


def get_race_data(start_date: str, end_date: str) -> List[List[Dict]]:
    """データ取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            e.avg_st,
            rd.exhibition_time,
            rd.st_time as exhibition_st,
            COALESCE(res.rank, 99) as result_rank
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
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


def calculate_score_v2(entry: Dict, race_entries: List[Dict], config: Dict) -> float:
    """
    改良版スコア計算
    展示ST・展示タイムを順位ベースで大きく反映
    """
    pit = entry['pit_number']
    weights = config['weights']

    score = 0.0

    # 1. コーススコア（基本）
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
    course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * weights['course'] / 100

    # 2. 選手スコア
    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * weights['racer'] / 100

    # 3. モータースコア
    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * weights['motor'] / 100

    # 4. 級別スコア
    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * weights['rank'] / 100

    # 5. 展示ST順位スコア（大きく反映）
    if config.get('use_exhibition_st', False):
        exhibition_st = entry.get('exhibition_st')
        if exhibition_st and exhibition_st > 0:
            valid_sts = [(e['pit_number'], e.get('exhibition_st') or 999)
                        for e in race_entries if e.get('exhibition_st') and e.get('exhibition_st') > 0]
            if valid_sts:
                sorted_sts = sorted(valid_sts, key=lambda x: x[1])
                for rank, (p, st) in enumerate(sorted_sts, 1):
                    if p == pit:
                        # 順位ベースのスコア（1位=100, 6位=0）
                        st_rank_score = (7 - rank) / 6 * 100
                        score += st_rank_score * weights.get('exhibition_st', 10) / 100
                        break

    # 6. 展示タイム順位スコア
    if config.get('use_exhibition_time', False):
        exhibition_time = entry.get('exhibition_time')
        if exhibition_time and exhibition_time > 0:
            valid_times = [(e['pit_number'], e.get('exhibition_time') or 999)
                          for e in race_entries if e.get('exhibition_time') and e.get('exhibition_time') > 0]
            if valid_times:
                sorted_times = sorted(valid_times, key=lambda x: x[1])
                for rank, (p, t) in enumerate(sorted_times, 1):
                    if p == pit:
                        ex_rank_score = (7 - rank) / 6 * 100
                        score += ex_rank_score * weights.get('exhibition_time', 10) / 100
                        break

    # 7. 過去ST順位スコア
    if config.get('use_avg_st', False):
        avg_st = entry.get('avg_st')
        if avg_st and avg_st > 0:
            valid_sts = [(e['pit_number'], e.get('avg_st') or 999)
                        for e in race_entries if e.get('avg_st') and e.get('avg_st') > 0]
            if valid_sts:
                sorted_sts = sorted(valid_sts, key=lambda x: x[1])
                for rank, (p, st) in enumerate(sorted_sts, 1):
                    if p == pit:
                        avg_st_score = (7 - rank) / 6 * 100
                        score += avg_st_score * weights.get('avg_st', 5) / 100
                        break

    return score


def backtest(races: List[List[Dict]], config: Dict, label: str) -> Dict:
    """バックテスト"""
    results = {'win_hits': 0, 'total': 0}

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        scores = []
        for entry in race_entries:
            s = calculate_score_v2(entry, race_entries, config)
            scores.append((entry['pit_number'], s, entry['result_rank']))

        scores.sort(key=lambda x: -x[1])
        predicted = scores[0][0]

        actual = None
        for pit, _, result_rank in scores:
            if str(result_rank) == '1':
                actual = pit
                break

        results['total'] += 1
        if predicted == actual:
            results['win_hits'] += 1

    return {
        'label': label,
        'win_rate': results['win_hits'] / results['total'] * 100,
        'total': results['total'],
        'hits': results['win_hits'],
    }


def main():
    print('=' * 70)
    print('積極的な改善案のバックテスト')
    print('展示ST・展示タイムの重みを大幅強化')
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

    # テスト設定
    configs = [
        # ベースライン
        {
            'name': 'ベースライン',
            'weights': {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10},
            'use_exhibition_st': False,
            'use_exhibition_time': False,
            'use_avg_st': False,
        },
        # 展示ST強化（10%）
        {
            'name': '展示ST +10%',
            'weights': {'course': 30, 'racer': 30, 'motor': 15, 'rank': 10, 'exhibition_st': 15},
            'use_exhibition_st': True,
            'use_exhibition_time': False,
            'use_avg_st': False,
        },
        # 展示ST強化（20%）
        {
            'name': '展示ST +20%',
            'weights': {'course': 25, 'racer': 25, 'motor': 15, 'rank': 10, 'exhibition_st': 25},
            'use_exhibition_st': True,
            'use_exhibition_time': False,
            'use_avg_st': False,
        },
        # 展示タイム強化（15%）
        {
            'name': '展示タイム +15%',
            'weights': {'course': 28, 'racer': 28, 'motor': 15, 'rank': 10, 'exhibition_time': 19},
            'use_exhibition_st': False,
            'use_exhibition_time': True,
            'use_avg_st': False,
        },
        # 展示ST + 展示タイム（各10%）
        {
            'name': '展示ST+タイム各10%',
            'weights': {'course': 25, 'racer': 25, 'motor': 12, 'rank': 8, 'exhibition_st': 15, 'exhibition_time': 15},
            'use_exhibition_st': True,
            'use_exhibition_time': True,
            'use_avg_st': False,
        },
        # コース重視を下げる（25%）
        {
            'name': 'コース25% + 展示系30%',
            'weights': {'course': 25, 'racer': 25, 'motor': 10, 'rank': 10, 'exhibition_st': 15, 'exhibition_time': 15},
            'use_exhibition_st': True,
            'use_exhibition_time': True,
            'use_avg_st': False,
        },
        # 極端: コース15%
        {
            'name': '【極端】コース15%',
            'weights': {'course': 15, 'racer': 25, 'motor': 10, 'rank': 10, 'exhibition_st': 20, 'exhibition_time': 20},
            'use_exhibition_st': True,
            'use_exhibition_time': True,
            'use_avg_st': False,
        },
        # モーター軽減のみ
        {
            'name': 'モーター12点のみ',
            'weights': {'course': 39, 'racer': 39, 'motor': 12, 'rank': 10},
            'use_exhibition_st': False,
            'use_exhibition_time': False,
            'use_avg_st': False,
        },
        # 過去ST追加
        {
            'name': '過去ST +8%',
            'weights': {'course': 32, 'racer': 32, 'motor': 15, 'rank': 8, 'avg_st': 13},
            'use_exhibition_st': False,
            'use_exhibition_time': False,
            'use_avg_st': True,
        },
        # 最適化候補: バランス型
        {
            'name': '★バランス最適化',
            'weights': {'course': 30, 'racer': 28, 'motor': 10, 'rank': 8, 'exhibition_st': 12, 'exhibition_time': 12},
            'use_exhibition_st': True,
            'use_exhibition_time': True,
            'use_avg_st': False,
        },
    ]

    print('=' * 70)
    print('バックテスト結果')
    print('=' * 70)
    print()

    baseline = None
    results = []

    for config in configs:
        result = backtest(races, config, config['name'])
        results.append(result)
        if baseline is None:
            baseline = result['win_rate']

    print(f"{'設定':<30} {'単勝的中率':>12} {'差分':>10}")
    print('-' * 55)

    for r in results:
        diff = r['win_rate'] - baseline
        diff_str = f"+{diff:.2f}%" if diff >= 0 else f"{diff:.2f}%"
        print(f"{r['label']:<30} {r['win_rate']:>11.2f}% {diff_str:>10}")

    # グリッドサーチ
    print()
    print('=' * 70)
    print('パラメータグリッドサーチ')
    print('=' * 70)
    print()

    best_result = None
    best_config = None

    course_weights = [20, 25, 30, 35]
    ex_st_weights = [10, 15, 20]
    ex_time_weights = [10, 15, 20]

    total = len(course_weights) * len(ex_st_weights) * len(ex_time_weights)
    count = 0

    for c in course_weights:
        for st in ex_st_weights:
            for ex in ex_time_weights:
                count += 1
                if count % 10 == 0:
                    print(f"  {count}/{total}...")

                remaining = 100 - c - st - ex - 10  # rank=10固定
                racer = remaining * 0.7
                motor = remaining * 0.3

                config = {
                    'weights': {
                        'course': c,
                        'racer': racer,
                        'motor': motor,
                        'rank': 10,
                        'exhibition_st': st,
                        'exhibition_time': ex
                    },
                    'use_exhibition_st': True,
                    'use_exhibition_time': True,
                    'use_avg_st': False,
                }

                result = backtest(races, config, '')

                if best_result is None or result['win_rate'] > best_result['win_rate']:
                    best_result = result
                    best_config = config['weights'].copy()

    print()
    print('=' * 70)
    print('最適パラメータ')
    print('=' * 70)
    print()
    print(f"単勝的中率: {best_result['win_rate']:.2f}% (+{best_result['win_rate'] - baseline:.2f}%)")
    print()
    print('重み配分:')
    for k, v in best_config.items():
        print(f"  {k}: {v:.1f}%")

    print()
    print('完了')


if __name__ == '__main__':
    main()
