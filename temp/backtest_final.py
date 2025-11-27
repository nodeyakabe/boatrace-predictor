# -*- coding: utf-8 -*-
"""
最終バックテスト - 推奨設定の検証
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import time
from collections import defaultdict
from typing import Dict, List

from config.settings import (
    DATABASE_PATH,
    VENUE_IN1_RATES,
    HIGH_IN_VENUES,
    SCORING_WEIGHTS,
)


def get_race_data(start_date: str, end_date: str) -> List[List[Dict]]:
    """レースデータを一括取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.win_rate,
            e.second_rate,
            e.local_win_rate,
            e.local_second_rate,
            e.motor_number,
            e.motor_second_rate,
            e.boat_second_rate,
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


def calculate_score_baseline(entry: Dict, race_entries: List[Dict], venue_code: str) -> float:
    """ベースライン: 現行設定"""
    score = 0.0
    weights = SCORING_WEIGHTS

    pit = entry['pit_number']
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
    course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * weights.get('course', 35) / 100

    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * weights.get('racer', 35) / 100

    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * weights.get('motor', 20) / 100

    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * weights.get('rank', 10) / 100

    return score


def calculate_score_recommended(entry: Dict, race_entries: List[Dict], venue_code: str) -> float:
    """推奨設定: 会場別1コース勝率 + ST相対評価（軽量）"""
    score = 0.0
    weights = SCORING_WEIGHTS  # 基本重みは固定

    pit = entry['pit_number']

    # 1コースのみ会場別勝率を反映（それ以外は従来通り）
    if pit == 1:
        venue_in1 = VENUE_IN1_RATES.get(venue_code, 57)
        # 従来の55を基準に、会場別勝率で調整
        course_score = (venue_in1 / 57.0) * 55 / 55 * 100
    else:
        course_base = {2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * weights.get('course', 35) / 100

    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * weights.get('racer', 35) / 100

    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * weights.get('motor', 20) / 100

    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * weights.get('rank', 10) / 100

    # ST相対評価（軽量: 5点）
    avg_st = entry.get('avg_st')
    if avg_st is not None and avg_st > 0:
        valid_sts = [(e['pit_number'], e.get('avg_st') or 1.0)
                     for e in race_entries if e.get('avg_st') and e.get('avg_st') > 0]
        valid_sts.sort(key=lambda x: x[1])

        st_rank = 6
        for i, (p, st) in enumerate(valid_sts, 1):
            if p == pit:
                st_rank = i
                break

        st_score = 100 - (st_rank - 1) * 10
        score += st_score * 5 / 100  # 5点

    return score


def calculate_score_solid_enhanced(entry: Dict, race_entries: List[Dict], venue_code: str) -> float:
    """堅い会場強化版: 堅い会場のみ1コースボーナス"""
    score = calculate_score_recommended(entry, race_entries, venue_code)

    pit = entry['pit_number']
    rank = entry.get('racer_rank') or 'B1'

    # 堅い会場での1コースA1にボーナス
    if venue_code in HIGH_IN_VENUES and pit == 1 and rank == 'A1':
        score += 2.0

    return score


def predict_race(race_entries: List[Dict], score_func, venue_code: str) -> List[int]:
    """レース予測"""
    scores = []
    for entry in race_entries:
        score = score_func(entry, race_entries, venue_code)
        scores.append((entry['pit_number'], score))

    scores.sort(key=lambda x: -x[1])
    return [s[0] for s in scores]


def evaluate_prediction(predicted: List[int], race_entries: List[Dict]) -> Dict:
    """予測評価"""
    actual = sorted(race_entries, key=lambda x: x['result_rank'])
    actual_order = [e['pit_number'] for e in actual]

    if len(actual_order) < 3:
        return None

    return {
        'win_hit': predicted[0] == actual_order[0],
        'place_hit': predicted[0] in actual_order[:3],
        'exacta_hit': predicted[:2] == actual_order[:2],
        'trifecta_hit': predicted[:3] == actual_order[:3],
        'trio_hit': set(predicted[:3]) == set(actual_order[:3]),
    }


def run_backtest(races: List[List[Dict]], score_func, label: str) -> Dict:
    """バックテスト実行"""
    results = {
        'win_hits': 0,
        'place_hits': 0,
        'exacta_hits': 0,
        'trifecta_hits': 0,
        'trio_hits': 0,
        'total': 0
    }

    venue_stats = defaultdict(lambda: {'win_hits': 0, 'total': 0})

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        venue = race_entries[0]['venue_code']
        predicted = predict_race(race_entries, score_func, venue)
        eval_result = evaluate_prediction(predicted, race_entries)

        if eval_result is None:
            continue

        results['total'] += 1
        if eval_result['win_hit']:
            results['win_hits'] += 1
        if eval_result['place_hit']:
            results['place_hits'] += 1
        if eval_result['exacta_hit']:
            results['exacta_hits'] += 1
        if eval_result['trifecta_hit']:
            results['trifecta_hits'] += 1
        if eval_result['trio_hit']:
            results['trio_hits'] += 1

        venue_stats[venue]['total'] += 1
        if eval_result['win_hit']:
            venue_stats[venue]['win_hits'] += 1

    return {
        'label': label,
        'results': results,
        'venue_stats': dict(venue_stats),
    }


def print_results(results_list: List[Dict]):
    """結果表示"""
    print('=' * 80)
    print('バックテスト結果 - 推奨設定検証')
    print('=' * 80)
    print()

    total = results_list[0]['results']['total']
    print(f"テスト対象: {total:,}レース")
    print()

    print('【的中率比較】')
    header = f"{'指標':<10}"
    for r in results_list:
        header += f" {r['label'][:12]:>14}"
    print(header)
    print('-' * (10 + 15 * len(results_list)))

    metrics = [
        ('単勝', 'win_hits'),
        ('複勝', 'place_hits'),
        ('2連単', 'exacta_hits'),
        ('3連単', 'trifecta_hits'),
        ('3連複', 'trio_hits'),
    ]

    baseline_results = results_list[0]['results']
    for name, key in metrics:
        line = f"{name:<10}"
        for i, r in enumerate(results_list):
            rate = r['results'][key] / r['results']['total'] * 100
            if i == 0:
                line += f" {rate:>13.2f}%"
            else:
                base_rate = baseline_results[key] / baseline_results['total'] * 100
                diff = rate - base_rate
                diff_str = f"({'+' if diff >= 0 else ''}{diff:.2f})"
                line += f" {rate:>6.2f}%{diff_str:>7}"
        print(line)

    print()
    print('【会場別単勝的中率（50レース以上）】')
    venues_all = set()
    for r in results_list:
        venues_all.update(r['venue_stats'].keys())

    venue_data = []
    for venue in venues_all:
        baseline_stats = results_list[0]['venue_stats'].get(venue, {'win_hits': 0, 'total': 0})
        if baseline_stats['total'] >= 50:
            venue_data.append((venue, baseline_stats))

    venue_data.sort(key=lambda x: x[1]['win_hits']/x[1]['total'] if x[1]['total'] > 0 else 0, reverse=True)

    header = f"{'会場':<8}"
    for r in results_list:
        header += f" {r['label'][:12]:>14}"
    print(header)
    print('-' * (8 + 15 * len(results_list)))

    for venue, _ in venue_data:
        line = f"{venue:<8}"
        baseline_stats = results_list[0]['venue_stats'].get(venue, {'win_hits': 0, 'total': 1})
        for i, r in enumerate(results_list):
            stats = r['venue_stats'].get(venue, {'win_hits': 0, 'total': 1})
            rate = stats['win_hits'] / stats['total'] * 100 if stats['total'] > 0 else 0
            if i == 0:
                line += f" {rate:>13.1f}%"
            else:
                base_rate = baseline_stats['win_hits'] / baseline_stats['total'] * 100 if baseline_stats['total'] > 0 else 0
                diff = rate - base_rate
                diff_str = f"({'+' if diff >= 0 else ''}{diff:.1f})"
                line += f" {rate:>6.1f}%{diff_str:>7}"
        print(line)


def main():
    print('最終バックテスト - 推奨設定検証')
    print('=' * 80)
    print()

    # より長期間でテスト
    start_date = '2024-01-01'
    end_date = '2024-11-20'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    print('データ取得中...')
    start = time.time()
    races = get_race_data(start_date, end_date)
    print(f"データ取得完了: {len(races):,}レース ({time.time()-start:.1f}秒)")
    print()

    results_list = []

    print('テスト実行中...')

    print('  1. ベースライン（現行設定）')
    result = run_backtest(races, calculate_score_baseline, '現行設定')
    results_list.append(result)

    print('  2. 推奨設定（会場別+ST軽量）')
    result = run_backtest(races, calculate_score_recommended, '推奨設定')
    results_list.append(result)

    print('  3. 堅い会場強化版')
    result = run_backtest(races, calculate_score_solid_enhanced, '堅い会場強化')
    results_list.append(result)

    print()
    print_results(results_list)

    # サマリー
    print()
    print('=' * 80)
    print('結論')
    print('=' * 80)
    print()

    baseline = results_list[0]['results']
    recommended = results_list[1]['results']
    enhanced = results_list[2]['results']

    b_win = baseline['win_hits'] / baseline['total'] * 100
    r_win = recommended['win_hits'] / recommended['total'] * 100
    e_win = enhanced['win_hits'] / enhanced['total'] * 100

    b_place = baseline['place_hits'] / baseline['total'] * 100
    r_place = recommended['place_hits'] / recommended['total'] * 100
    e_place = enhanced['place_hits'] / enhanced['total'] * 100

    print(f"単勝的中率: 現行 {b_win:.2f}% → 推奨 {r_win:.2f}% ({r_win-b_win:+.2f}%)")
    print(f"複勝的中率: 現行 {b_place:.2f}% → 推奨 {r_place:.2f}% ({r_place-b_place:+.2f}%)")
    print()

    if r_win >= b_win and r_place >= b_place:
        print('✓ 推奨設定は現行設定と同等以上の性能')
    elif r_place > b_place:
        print('△ 推奨設定は複勝率で改善、単勝率で若干低下')
    else:
        print('△ 推奨設定は現行設定とほぼ同等')

    print()
    print('完了')


if __name__ == '__main__':
    main()
