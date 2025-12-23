# -*- coding: utf-8 -*-
"""
新スコアリング設定でのバックテスト
2024年11月27日 - 動的配点システム検証
"""

import sys
import os
import io

# パス設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import time
from datetime import datetime
from collections import defaultdict
from typing import Dict, List

# 設定ファイルから読み込み
from config.settings import (
    DATABASE_PATH,
    get_dynamic_weights,
    get_venue_type,
    VENUE_IN1_RATES,
    HIGH_IN_VENUES,
    LOW_IN_VENUES,
    SCORING_WEIGHTS,
    DYNAMIC_SCORING_WEIGHTS,
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


def calculate_score_old(entry: Dict, venue_code: str) -> float:
    """旧スコアリング（固定重み）"""
    score = 0.0
    weights = SCORING_WEIGHTS  # 固定重み

    # 1. コーススコア
    pit = entry['pit_number']
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
    course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * weights.get('course', 35) / 100

    # 2. 選手スコア
    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * weights.get('racer', 35) / 100

    # 3. モータースコア
    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * weights.get('motor', 20) / 100

    # 4. 級別スコア
    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * weights.get('rank', 10) / 100

    return score


def calculate_score_new(entry: Dict, venue_code: str) -> float:
    """新スコアリング（動的配点）"""
    score = 0.0

    # 会場特性に応じた動的重みを取得
    weights = get_dynamic_weights(venue_code)

    # 1. コーススコア（会場別1コース勝率を反映）
    pit = entry['pit_number']
    if pit == 1:
        venue_in1 = VENUE_IN1_RATES.get(venue_code, 57)
        course_score = venue_in1 / 67.1 * 100  # 最高勝率67.1%（徳山）を基準
    else:
        course_base = {2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * weights.get('course', 35) / 100

    # 2. 選手スコア
    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * weights.get('racer', 35) / 100

    # 3. モータースコア
    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * weights.get('motor', 20) / 100

    # 4. 級別スコア
    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * weights.get('rank', 10) / 100

    # 5. STスコア（新規追加）
    avg_st = entry.get('avg_st')
    if avg_st is not None and avg_st > 0:
        if avg_st < 0.12:
            st_score = 100  # 最速
        elif avg_st < 0.15:
            st_score = 90   # 良好
        elif avg_st < 0.18:
            st_score = 70   # 普通
        elif avg_st < 0.20:
            st_score = 50   # やや遅い
        else:
            st_score = 30   # 遅い
    else:
        st_score = 50  # データなし

    # ST重み（分析結果: 勝率に大きく影響）
    score += st_score * 10 / 100

    return score


def predict_race(race_entries: List[Dict], score_func, venue_code: str) -> List[int]:
    """レース予測"""
    scores = []
    for entry in race_entries:
        score = score_func(entry, venue_code)
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
    venue_type_stats = defaultdict(lambda: {'win_hits': 0, 'total': 0})

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

        # 会場別
        venue_stats[venue]['total'] += 1
        if eval_result['win_hit']:
            venue_stats[venue]['win_hits'] += 1

        # 会場タイプ別
        vtype = get_venue_type(venue)
        venue_type_stats[vtype]['total'] += 1
        if eval_result['win_hit']:
            venue_type_stats[vtype]['win_hits'] += 1

    return {
        'label': label,
        'results': results,
        'venue_stats': dict(venue_stats),
        'venue_type_stats': dict(venue_type_stats),
    }


def print_comparison(old_result: Dict, new_result: Dict):
    """比較結果を表示"""
    print('=' * 70)
    print('バックテスト結果比較: 旧スコアリング vs 新スコアリング（動的配点）')
    print('=' * 70)
    print()

    old_r = old_result['results']
    new_r = new_result['results']
    old_total = old_r['total']
    new_total = new_r['total']

    print(f"テスト対象: {old_total:,}レース")
    print()

    print('【的中率比較】')
    print(f"{'指標':<12} {'旧スコア':>10} {'新スコア':>10} {'差分':>10}")
    print('-' * 45)

    metrics = [
        ('単勝', 'win_hits'),
        ('複勝', 'place_hits'),
        ('2連単', 'exacta_hits'),
        ('3連単', 'trifecta_hits'),
        ('3連複', 'trio_hits'),
    ]

    for name, key in metrics:
        old_rate = old_r[key] / old_total * 100
        new_rate = new_r[key] / new_total * 100
        diff = new_rate - old_rate
        diff_str = f"+{diff:.2f}%" if diff >= 0 else f"{diff:.2f}%"
        print(f"{name:<12} {old_rate:>9.2f}% {new_rate:>9.2f}% {diff_str:>10}")

    print()
    print('【会場タイプ別 単勝的中率】')
    print(f"{'タイプ':<10} {'旧スコア':>10} {'新スコア':>10} {'差分':>10}")
    print('-' * 45)

    for vtype in ['solid', 'chaotic', 'normal']:
        type_name = {'solid': '堅い会場', 'chaotic': '荒れ会場', 'normal': '普通会場'}[vtype]
        old_stats = old_result['venue_type_stats'].get(vtype, {'win_hits': 0, 'total': 1})
        new_stats = new_result['venue_type_stats'].get(vtype, {'win_hits': 0, 'total': 1})

        old_rate = old_stats['win_hits'] / old_stats['total'] * 100 if old_stats['total'] > 0 else 0
        new_rate = new_stats['win_hits'] / new_stats['total'] * 100 if new_stats['total'] > 0 else 0
        diff = new_rate - old_rate
        diff_str = f"+{diff:.2f}%" if diff >= 0 else f"{diff:.2f}%"

        print(f"{type_name:<10} {old_rate:>9.2f}% {new_rate:>9.2f}% {diff_str:>10}")

    print()
    print('【会場別 単勝的中率 TOP/BOTTOM 5】')

    # 新スコアでの改善が大きい会場
    venue_diffs = []
    for venue in new_result['venue_stats']:
        old_stats = old_result['venue_stats'].get(venue, {'win_hits': 0, 'total': 1})
        new_stats = new_result['venue_stats'][venue]
        if old_stats['total'] > 50 and new_stats['total'] > 50:
            old_rate = old_stats['win_hits'] / old_stats['total'] * 100
            new_rate = new_stats['win_hits'] / new_stats['total'] * 100
            venue_diffs.append((venue, old_rate, new_rate, new_rate - old_rate))

    venue_diffs.sort(key=lambda x: x[3], reverse=True)

    print()
    print('改善TOP 5:')
    for venue, old_rate, new_rate, diff in venue_diffs[:5]:
        print(f"  {venue}: {old_rate:.1f}% → {new_rate:.1f}% ({'+' if diff >= 0 else ''}{diff:.1f}%)")

    print()
    print('改善BOTTOM 5:')
    for venue, old_rate, new_rate, diff in venue_diffs[-5:]:
        print(f"  {venue}: {old_rate:.1f}% → {new_rate:.1f}% ({'+' if diff >= 0 else ''}{diff:.1f}%)")


def main():
    print('新スコアリング設定 バックテスト')
    print('=' * 70)
    print()

    # テスト期間
    start_date = '2024-08-01'
    end_date = '2024-11-20'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    # データ取得
    print('データ取得中...')
    start = time.time()
    races = get_race_data(start_date, end_date)
    load_time = time.time() - start
    print(f"データ取得完了: {len(races):,}レース ({load_time:.1f}秒)")
    print()

    # 旧スコアリングでバックテスト
    print('旧スコアリング（固定重み）でテスト中...')
    start = time.time()
    old_result = run_backtest(races, calculate_score_old, '旧スコアリング')
    old_time = time.time() - start
    print(f"完了 ({old_time:.1f}秒)")

    # 新スコアリングでバックテスト
    print('新スコアリング（動的配点）でテスト中...')
    start = time.time()
    new_result = run_backtest(races, calculate_score_new, '新スコアリング')
    new_time = time.time() - start
    print(f"完了 ({new_time:.1f}秒)")
    print()

    # 比較結果表示
    print_comparison(old_result, new_result)

    print()
    print('=' * 70)
    print('動的配点システムの設定内容')
    print('=' * 70)
    print()
    print('【会場タイプ別重み設定】')
    for vtype, weights in DYNAMIC_SCORING_WEIGHTS.items():
        type_name = {'solid': '堅い会場', 'chaotic': '荒れ会場', 'normal': '普通会場'}[vtype]
        print(f"  {type_name}:")
        for key, val in weights.items():
            print(f"    {key}: {val}")

    print()
    print('完了')


if __name__ == '__main__':
    main()
