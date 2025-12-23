# -*- coding: utf-8 -*-
"""
展示タイム重み調整のバックテスト
分析結果に基づき、展示タイムの重みを調整
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
            e.pit_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
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


def calculate_score(entry: Dict, race_entries: List[Dict], weights: Dict) -> float:
    """スコア計算"""
    pit = entry['pit_number']
    score = 0.0

    # コース
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
    course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * weights.get('course', 20) / 100

    # 選手
    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * weights.get('racer', 31) / 100

    # モーター
    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * weights.get('motor', 14) / 100

    # 級別
    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * weights.get('rank', 10) / 100

    # 展示ST順位
    if weights.get('exhibition_st', 0) > 0:
        exhibition_st = entry.get('exhibition_st')
        if exhibition_st and exhibition_st > 0:
            valid_sts = [(e['pit_number'], e.get('exhibition_st') or 999)
                        for e in race_entries if e.get('exhibition_st') and e.get('exhibition_st') > 0]
            if valid_sts:
                sorted_sts = sorted(valid_sts, key=lambda x: x[1])
                for rank, (p, st) in enumerate(sorted_sts, 1):
                    if p == pit:
                        st_rank_score = (len(sorted_sts) + 1 - rank) / len(sorted_sts) * 100
                        score += st_rank_score * weights.get('exhibition_st', 0) / 100
                        break

    # 展示タイム順位
    if weights.get('exhibition_time', 0) > 0:
        exhibition_time = entry.get('exhibition_time')
        if exhibition_time and exhibition_time > 0:
            valid_times = [(e['pit_number'], e.get('exhibition_time') or 999)
                          for e in race_entries if e.get('exhibition_time') and e.get('exhibition_time') > 0]
            if valid_times:
                sorted_times = sorted(valid_times, key=lambda x: x[1])
                for rank, (p, t) in enumerate(sorted_times, 1):
                    if p == pit:
                        ex_rank_score = (len(sorted_times) + 1 - rank) / len(sorted_times) * 100
                        score += ex_rank_score * weights.get('exhibition_time', 0) / 100
                        break

    return score


def backtest(races: List[List[Dict]], weights: Dict, label: str) -> Dict:
    """バックテスト"""
    results = {'win_hits': 0, 'total': 0}

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        scores = []
        for entry in race_entries:
            s = calculate_score(entry, race_entries, weights)
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
        'win_rate': results['win_hits'] / results['total'] * 100 if results['total'] > 0 else 0,
        'total': results['total'],
        'hits': results['win_hits'],
    }


def main():
    print('=' * 70)
    print('展示タイム重み調整のバックテスト')
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
        # 旧設定（ベースライン）
        {
            'name': '旧設定（ベースライン）',
            'weights': {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10,
                       'exhibition_st': 0, 'exhibition_time': 0},
        },
        # 現在の新設定
        {
            'name': '現設定（ST15/ET10）',
            'weights': {'course': 20, 'racer': 31, 'motor': 14, 'rank': 10,
                       'exhibition_st': 15, 'exhibition_time': 10},
        },
        # 展示タイム削減案1
        {
            'name': '調整1（ST15/ET5）',
            'weights': {'course': 20, 'racer': 36, 'motor': 14, 'rank': 10,
                       'exhibition_st': 15, 'exhibition_time': 5},
        },
        # 展示タイム削減案2
        {
            'name': '調整2（ST18/ET5）',
            'weights': {'course': 20, 'racer': 33, 'motor': 14, 'rank': 10,
                       'exhibition_st': 18, 'exhibition_time': 5},
        },
        # 展示タイム削除
        {
            'name': '調整3（ST20/ET0）',
            'weights': {'course': 20, 'racer': 36, 'motor': 14, 'rank': 10,
                       'exhibition_st': 20, 'exhibition_time': 0},
        },
        # 展示ST強化
        {
            'name': '調整4（ST25/ET0）',
            'weights': {'course': 18, 'racer': 33, 'motor': 14, 'rank': 10,
                       'exhibition_st': 25, 'exhibition_time': 0},
        },
        # コース復活案
        {
            'name': '調整5（コース25/ST15）',
            'weights': {'course': 25, 'racer': 31, 'motor': 14, 'rank': 10,
                       'exhibition_st': 15, 'exhibition_time': 5},
        },
    ]

    print('=' * 70)
    print('バックテスト結果')
    print('=' * 70)
    print()

    baseline = None
    results = []

    for config in configs:
        result = backtest(races, config['weights'], config['name'])
        results.append(result)
        if baseline is None:
            baseline = result['win_rate']

    print(f"{'設定':<25} {'単勝的中率':>12} {'差分':>10} {'的中数':>10}")
    print('-' * 60)

    for r in results:
        diff = r['win_rate'] - baseline
        diff_str = f"+{diff:.2f}%" if diff >= 0 else f"{diff:.2f}%"
        print(f"{r['label']:<25} {r['win_rate']:>11.2f}% {diff_str:>10} {r['hits']:>10,}")

    # 最適パラメータ探索
    print()
    print('=' * 70)
    print('最適パラメータ探索')
    print('=' * 70)
    print()

    best_result = None
    best_weights = None

    # グリッドサーチ
    for course in [18, 20, 22, 25]:
        for st in [12, 15, 18, 20, 22]:
            for et in [0, 3, 5, 8]:
                remaining = 100 - course - st - et - 10 - 14  # rank=10, motor=14 固定
                if remaining < 20 or remaining > 40:
                    continue

                weights = {
                    'course': course,
                    'racer': remaining,
                    'motor': 14,
                    'rank': 10,
                    'exhibition_st': st,
                    'exhibition_time': et,
                }

                result = backtest(races, weights, '')

                if best_result is None or result['win_rate'] > best_result['win_rate']:
                    best_result = result
                    best_weights = weights.copy()

    print('最適パラメータ:')
    print(f"  単勝的中率: {best_result['win_rate']:.2f}% (+{best_result['win_rate'] - baseline:.2f}%)")
    print()
    print('重み配分:')
    for k, v in best_weights.items():
        print(f"  {k}: {v}%")

    print()
    print('完了')


if __name__ == '__main__':
    main()
