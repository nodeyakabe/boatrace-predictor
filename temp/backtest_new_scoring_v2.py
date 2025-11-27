# -*- coding: utf-8 -*-
"""
新スコアリング設定でのバックテスト v2
2024年11月27日 - 荒れ会場の配点調整版
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

from config.settings import (
    DATABASE_PATH,
    VENUE_IN1_RATES,
    HIGH_IN_VENUES,
    LOW_IN_VENUES,
    SCORING_WEIGHTS,
)


# 会場分類
# v1での問題: 荒れ会場でコース重みを下げすぎ → 1コースの勝率が低くても1号艇は有利
# 修正: 荒れ会場でもコース有利度は維持、選手能力の重みを相対的に強化

DYNAMIC_WEIGHTS_V2 = {
    # 堅い会場（1コース勝率60%以上）: コース重視
    'solid': {
        "course": 40,   # 35→40 (+5)
        "racer": 30,    # 35→30 (-5)
        "motor": 18,    # 20→18 (-2)
        "rank": 12,     # 10→12 (+2)
    },
    # 荒れ会場（1コース勝率50%以下）: コースは維持、選手・モーター強化
    'chaotic': {
        "course": 32,   # 35→32 (微減だけ)
        "racer": 38,    # 35→38 (+3)
        "motor": 22,    # 20→22 (+2)
        "rank": 8,      # 10→8 (-2)
    },
    # 普通の会場: 標準配点
    'normal': {
        "course": 35,
        "racer": 35,
        "motor": 20,
        "rank": 10,
    },
}


def get_venue_type_v2(venue_code: str) -> str:
    """会場タイプを取得"""
    if venue_code in HIGH_IN_VENUES:
        return 'solid'
    elif venue_code in LOW_IN_VENUES:
        return 'chaotic'
    else:
        return 'normal'


def get_dynamic_weights_v2(venue_code: str) -> dict:
    """v2動的配点を取得"""
    vtype = get_venue_type_v2(venue_code)
    return DYNAMIC_WEIGHTS_V2[vtype]


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


def calculate_score_baseline(entry: Dict, venue_code: str) -> float:
    """ベースライン: 固定重み"""
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


def calculate_score_v2(entry: Dict, venue_code: str) -> float:
    """v2: 動的配点 + 会場別1コース勝率 + ST"""
    score = 0.0
    weights = get_dynamic_weights_v2(venue_code)

    # コーススコア（会場別1コース勝率を反映）
    pit = entry['pit_number']
    if pit == 1:
        venue_in1 = VENUE_IN1_RATES.get(venue_code, 57)
        course_score = venue_in1 / 67.1 * 100
    else:
        course_base = {2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * weights.get('course', 35) / 100

    # 選手スコア
    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * weights.get('racer', 35) / 100

    # モータースコア
    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * weights.get('motor', 20) / 100

    # 級別スコア
    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * weights.get('rank', 10) / 100

    # STスコア（追加）
    avg_st = entry.get('avg_st')
    if avg_st is not None and avg_st > 0:
        if avg_st < 0.12:
            st_score = 100
        elif avg_st < 0.15:
            st_score = 85
        elif avg_st < 0.18:
            st_score = 65
        elif avg_st < 0.20:
            st_score = 45
        else:
            st_score = 25
    else:
        st_score = 50

    score += st_score * 8 / 100  # ST重み8点

    return score


def calculate_score_v3(entry: Dict, venue_code: str) -> float:
    """v3: v2 + 1コース級別補正"""
    score = calculate_score_v2(entry, venue_code)

    # 1コース×級別のボーナス/ペナルティ
    pit = entry['pit_number']
    rank = entry.get('racer_rank') or 'B1'

    if pit == 1:
        # 1コースでのA1は大幅有利（勝率71.1%）
        if rank == 'A1':
            score += 3.0
        elif rank == 'B2':
            # 1コースB2は不利（勝率33.2%）
            score -= 2.0

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

        venue_stats[venue]['total'] += 1
        if eval_result['win_hit']:
            venue_stats[venue]['win_hits'] += 1

        vtype = get_venue_type_v2(venue)
        venue_type_stats[vtype]['total'] += 1
        if eval_result['win_hit']:
            venue_type_stats[vtype]['win_hits'] += 1

    return {
        'label': label,
        'results': results,
        'venue_stats': dict(venue_stats),
        'venue_type_stats': dict(venue_type_stats),
    }


def print_comparison(results_list: List[Dict]):
    """複数結果の比較表示"""
    print('=' * 80)
    print('バックテスト結果比較')
    print('=' * 80)
    print()

    total = results_list[0]['results']['total']
    print(f"テスト対象: {total:,}レース")
    print()

    # 的中率比較
    print('【的中率比較】')
    header = f"{'指標':<10}"
    for r in results_list:
        header += f" {r['label'][:10]:>12}"
    print(header)
    print('-' * (10 + 13 * len(results_list)))

    metrics = [
        ('単勝', 'win_hits'),
        ('複勝', 'place_hits'),
        ('2連単', 'exacta_hits'),
        ('3連単', 'trifecta_hits'),
        ('3連複', 'trio_hits'),
    ]

    for name, key in metrics:
        line = f"{name:<10}"
        for r in results_list:
            rate = r['results'][key] / r['results']['total'] * 100
            line += f" {rate:>11.2f}%"
        print(line)

    # 会場タイプ別
    print()
    print('【会場タイプ別 単勝的中率】')
    header = f"{'タイプ':<10}"
    for r in results_list:
        header += f" {r['label'][:10]:>12}"
    print(header)
    print('-' * (10 + 13 * len(results_list)))

    for vtype in ['solid', 'chaotic', 'normal']:
        type_name = {'solid': '堅い会場', 'chaotic': '荒れ会場', 'normal': '普通会場'}[vtype]
        line = f"{type_name:<10}"
        for r in results_list:
            stats = r['venue_type_stats'].get(vtype, {'win_hits': 0, 'total': 1})
            rate = stats['win_hits'] / stats['total'] * 100 if stats['total'] > 0 else 0
            line += f" {rate:>11.2f}%"
        print(line)

    # 荒れ会場詳細
    print()
    print('【荒れ会場(02,03,04,14) 単勝的中率】')
    header = f"{'会場':<10}"
    for r in results_list:
        header += f" {r['label'][:10]:>12}"
    print(header)
    print('-' * (10 + 13 * len(results_list)))

    venue_names = {'02': '戸田', '03': '江戸川', '04': '平和島', '14': '鳴門'}
    for venue in ['02', '03', '04', '14']:
        line = f"{venue_names[venue]}({venue})"
        line = f"{line:<10}"
        for r in results_list:
            stats = r['venue_stats'].get(venue, {'win_hits': 0, 'total': 1})
            rate = stats['win_hits'] / stats['total'] * 100 if stats['total'] > 0 else 0
            line += f" {rate:>11.2f}%"
        print(line)


def main():
    print('新スコアリング設定 バックテスト v2')
    print('=' * 80)
    print()

    start_date = '2024-08-01'
    end_date = '2024-11-20'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    print('データ取得中...')
    start = time.time()
    races = get_race_data(start_date, end_date)
    print(f"データ取得完了: {len(races):,}レース ({time.time()-start:.1f}秒)")
    print()

    results_list = []

    # ベースライン
    print('ベースライン（固定重み）でテスト中...')
    result = run_backtest(races, calculate_score_baseline, 'ベースライン')
    results_list.append(result)

    # v2
    print('v2（動的配点調整版）でテスト中...')
    result = run_backtest(races, calculate_score_v2, 'v2動的配点')
    results_list.append(result)

    # v3
    print('v3（+1コース級別補正）でテスト中...')
    result = run_backtest(races, calculate_score_v3, 'v3級別補正')
    results_list.append(result)

    print()
    print_comparison(results_list)

    print()
    print('=' * 80)
    print('v2配点設定')
    print('=' * 80)
    for vtype, weights in DYNAMIC_WEIGHTS_V2.items():
        type_name = {'solid': '堅い会場', 'chaotic': '荒れ会場', 'normal': '普通会場'}[vtype]
        print(f"  {type_name}: course={weights['course']}, racer={weights['racer']}, motor={weights['motor']}, rank={weights['rank']}")

    print()
    print('完了')


if __name__ == '__main__':
    main()
