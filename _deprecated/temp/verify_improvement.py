# -*- coding: utf-8 -*-
"""
改善効果の最終検証
旧設定 vs 新設定の比較
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from collections import defaultdict
from typing import Dict, List

from config.settings import DATABASE_PATH, SCORING_WEIGHTS, SCORING_WEIGHTS_LEGACY


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
    score += course_score * weights.get('course', 35) / 100

    # 選手
    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * weights.get('racer', 35) / 100

    # モーター
    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * weights.get('motor', 20) / 100

    # 級別
    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * weights.get('rank', 10) / 100

    # 展示ST順位（新設定のみ）
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

    # 展示タイム順位（新設定のみ）
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
    print('改善効果の最終検証')
    print('=' * 70)
    print()

    print('設定ファイルの重み:')
    print(f"  新設定: {SCORING_WEIGHTS}")
    print(f"  旧設定: {SCORING_WEIGHTS_LEGACY}")
    print()

    start_date = '2024-01-01'
    end_date = '2024-11-20'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    print('データ取得中...')
    races = get_race_data(start_date, end_date)
    print(f"取得完了: {len(races):,}レース")
    print()

    # 旧設定でテスト
    result_old = backtest(races, SCORING_WEIGHTS_LEGACY, '旧設定')

    # 新設定でテスト
    result_new = backtest(races, SCORING_WEIGHTS, '新設定')

    print('=' * 70)
    print('結果')
    print('=' * 70)
    print()
    print(f"{'設定':<15} {'単勝的中率':>12} {'レース数':>12} {'的中数':>10}")
    print('-' * 50)
    print(f"{'旧設定':<15} {result_old['win_rate']:>11.2f}% {result_old['total']:>12,} {result_old['hits']:>10,}")
    print(f"{'新設定':<15} {result_new['win_rate']:>11.2f}% {result_new['total']:>12,} {result_new['hits']:>10,}")
    print()

    diff = result_new['win_rate'] - result_old['win_rate']
    diff_str = f"+{diff:.2f}%" if diff >= 0 else f"{diff:.2f}%"
    print(f"改善効果: {diff_str}")
    print()
    print('完了')


if __name__ == '__main__':
    main()
