# -*- coding: utf-8 -*-
"""
全改善案のバックテスト
2024年11月27日

改善案:
1. 会場別1コース勝率の除外（venue_in1を使わない）
2. モーター配点を20→12に軽減
3. 展示ST混合（過去ST:展示ST = 6:4）
4. 展示タイム順位評価（絶対値→順位ベース）
5. 進入コース予測（前付け傾向の反映）
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

from config.settings import DATABASE_PATH


def get_race_data(start_date: str, end_date: str) -> List[List[Dict]]:
    """全改善案に必要なデータを取得"""
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
            e.local_win_rate,
            e.motor_second_rate,
            e.avg_st,
            e.f_count,
            e.l_count,
            rd.exhibition_time,
            rd.st_time as exhibition_st,
            rd.actual_course,
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


def get_racer_front_entry_rates(conn) -> Dict[str, float]:
    """選手ごとの前付け率を事前計算"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            e.racer_number,
            COUNT(*) as total,
            SUM(CASE WHEN rd.actual_course < e.pit_number THEN 1 ELSE 0 END) as front_count
        FROM entries e
        JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
        WHERE rd.actual_course IS NOT NULL
          AND e.pit_number >= 2
        GROUP BY e.racer_number
        HAVING total >= 10
    """)

    rates = {}
    for row in cursor.fetchall():
        racer_number, total, front_count = row
        rates[racer_number] = (front_count / total) * 100

    return rates


def calculate_base_score(entry: Dict, weights: Dict) -> float:
    """基本スコア計算"""
    score = 0.0
    pit = entry['pit_number']

    # コーススコア
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
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

    return score


def calculate_st_hybrid_score(
    entry: Dict,
    race_entries: List[Dict],
    config: Dict
) -> float:
    """
    改善案3: 展示ST混合スコア
    過去ST:展示ST = 6:4（設定可能）
    """
    avg_st = entry.get('avg_st')
    exhibition_st = entry.get('exhibition_st')
    pit = entry['pit_number']

    past_ratio = config.get('past_st_ratio', 0.6)
    exhibition_ratio = config.get('exhibition_st_ratio', 0.4)
    max_score = config.get('st_max_score', 10)

    # 有効なSTを収集してランキング
    def get_st_rank(st_values: List[Tuple[int, float]], pit: int) -> int:
        """STの順位を取得（早い=良い）"""
        sorted_sts = sorted(st_values, key=lambda x: x[1])
        for rank, (p, st) in enumerate(sorted_sts, 1):
            if p == pit:
                return rank
        return 4  # デフォルト中間

    # 過去STの順位
    past_st_score = 0
    if avg_st and avg_st > 0:
        valid_past = [(e['pit_number'], e.get('avg_st') or 1.0)
                      for e in race_entries if e.get('avg_st') and e.get('avg_st') > 0]
        if valid_past:
            rank = get_st_rank(valid_past, pit)
            past_st_score = max_score * (7 - rank) / 6  # 1位=max, 6位≈0

    # 展示STの順位
    exhibition_st_score = 0
    if exhibition_st and exhibition_st > 0:
        valid_exhibition = [(e['pit_number'], e.get('exhibition_st') or 1.0)
                           for e in race_entries if e.get('exhibition_st') and e.get('exhibition_st') > 0]
        if valid_exhibition:
            rank = get_st_rank(valid_exhibition, pit)
            exhibition_st_score = max_score * (7 - rank) / 6

    # 混合スコア
    if exhibition_st and exhibition_st > 0:
        score = past_st_score * past_ratio + exhibition_st_score * exhibition_ratio
    else:
        score = past_st_score  # 展示STがない場合は過去STのみ

    return score


def calculate_exhibition_rank_score(
    entry: Dict,
    race_entries: List[Dict],
    config: Dict
) -> float:
    """
    改善案4: 展示タイム順位評価
    絶対値ではなく順位でスコア化
    1位=+20, 2位=+10, 3位=+5, 4位=0, 5位=-5, 6位=-10
    """
    exhibition_time = entry.get('exhibition_time')
    pit = entry['pit_number']

    rank_scores = config.get('exhibition_rank_scores', {
        1: 20, 2: 10, 3: 5, 4: 0, 5: -5, 6: -10
    })
    default_score = config.get('exhibition_default_score', 0)

    if not exhibition_time or exhibition_time <= 0:
        return default_score

    # 展示タイムでランキング（早い順）
    valid_times = [(e['pit_number'], e.get('exhibition_time') or 999)
                   for e in race_entries if e.get('exhibition_time') and e.get('exhibition_time') > 0]

    if not valid_times:
        return default_score

    sorted_times = sorted(valid_times, key=lambda x: x[1])

    for rank, (p, t) in enumerate(sorted_times, 1):
        if p == pit:
            return rank_scores.get(rank, default_score)

    return default_score


def predict_course_entry(
    entry: Dict,
    racer_front_rates: Dict[str, float],
    config: Dict
) -> Tuple[int, float]:
    """
    改善案5: 進入コース予測
    前付け率が高い選手は内コースを取ると予測

    Returns:
        (predicted_course, confidence)
    """
    pit = entry['pit_number']
    racer_number = entry.get('racer_number')

    front_threshold = config.get('front_entry_threshold', 40)  # 40%以上で前付け常習

    # 1号艇はほぼ1コース
    if pit == 1:
        return 1, 0.99

    # 前付け率を確認
    front_rate = racer_front_rates.get(racer_number, 0)

    if front_rate >= front_threshold:
        # 前付け常習: 1つ内のコースを予測
        predicted = max(1, pit - 1)
        confidence = min(0.8, front_rate / 100)
        return predicted, confidence
    elif front_rate >= 20:
        # 前付け傾向あり: 確率的に内コース
        # 20-40%の範囲で徐々に内コースの可能性
        if front_rate >= 30:
            predicted = max(1, pit - 1)
            confidence = 0.5
        else:
            predicted = pit
            confidence = 0.7
        return predicted, confidence
    else:
        # 枠なり進入
        return pit, 0.9


def calculate_course_adjusted_score(
    pit: int,
    predicted_course: int,
    confidence: float,
    config: Dict
) -> float:
    """
    進入コース予測に基づくコーススコア調整
    """
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}

    # 予測コースのスコア
    predicted_score = course_base.get(predicted_course, 10) / 55 * 100
    # 枠番のスコア
    pit_score = course_base.get(pit, 10) / 55 * 100

    # 信頼度で加重平均
    adjusted_score = predicted_score * confidence + pit_score * (1 - confidence)

    return adjusted_score


def backtest(
    races: List[List[Dict]],
    config: Dict,
    racer_front_rates: Dict[str, float],
    label: str
) -> Dict:
    """バックテスト実行"""
    results = {
        'win_hits': 0,
        'place_hits': 0,  # 複勝（3着以内）
        'exacta_hits': 0,  # 2連単
        'total': 0
    }

    weights = config.get('weights', {
        'course': 35, 'racer': 35, 'motor': 20, 'rank': 10
    })

    use_st_hybrid = config.get('use_st_hybrid', False)
    use_exhibition_rank = config.get('use_exhibition_rank', False)
    use_course_prediction = config.get('use_course_prediction', False)

    st_config = config.get('st_config', {})
    exhibition_config = config.get('exhibition_config', {})
    course_config = config.get('course_config', {})

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        scores = []
        for entry in race_entries:
            # 基本スコア
            score = calculate_base_score(entry, weights)

            # 改善案3: ST混合スコア
            if use_st_hybrid:
                st_score = calculate_st_hybrid_score(entry, race_entries, st_config)
                score += st_score * st_config.get('weight', 0.1)

            # 改善案4: 展示タイム順位評価
            if use_exhibition_rank:
                ex_score = calculate_exhibition_rank_score(entry, race_entries, exhibition_config)
                score += ex_score * exhibition_config.get('weight', 0.1)

            # 改善案5: 進入コース予測
            if use_course_prediction:
                predicted_course, confidence = predict_course_entry(
                    entry, racer_front_rates, course_config
                )
                # コーススコアを予測コースで再計算
                course_adj = calculate_course_adjusted_score(
                    entry['pit_number'], predicted_course, confidence, course_config
                )
                # 元のコーススコアとの差分を加算
                original_course = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
                original_score = original_course.get(entry['pit_number'], 10) / 55 * 100
                score += (course_adj - original_score) * weights.get('course', 35) / 100 * course_config.get('weight', 0.5)

            scores.append((entry['pit_number'], score, entry['result_rank']))

        # スコア順にソート
        scores.sort(key=lambda x: -x[1])

        predicted_1st = scores[0][0]
        predicted_2nd = scores[1][0]

        # 実際の結果を取得
        actual_results = {}
        for pit, _, result_rank in scores:
            try:
                rank = int(result_rank)
                actual_results[rank] = pit
            except:
                pass

        actual_1st = actual_results.get(1)
        actual_2nd = actual_results.get(2)

        results['total'] += 1

        # 単勝的中
        if predicted_1st == actual_1st:
            results['win_hits'] += 1

        # 複勝（予想1着が3着以内）
        if predicted_1st in [actual_results.get(1), actual_results.get(2), actual_results.get(3)]:
            results['place_hits'] += 1

        # 2連単的中
        if predicted_1st == actual_1st and predicted_2nd == actual_2nd:
            results['exacta_hits'] += 1

    return {
        'label': label,
        'total': results['total'],
        'win_rate': results['win_hits'] / results['total'] * 100 if results['total'] > 0 else 0,
        'place_rate': results['place_hits'] / results['total'] * 100 if results['total'] > 0 else 0,
        'exacta_rate': results['exacta_hits'] / results['total'] * 100 if results['total'] > 0 else 0,
        'win_hits': results['win_hits'],
    }


def main():
    print('=' * 70)
    print('全改善案のバックテスト')
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

    # 前付け率を事前計算
    print('選手別前付け率を計算中...')
    conn = sqlite3.connect(DATABASE_PATH)
    racer_front_rates = get_racer_front_entry_rates(conn)
    conn.close()
    print(f"前付け傾向のある選手: {sum(1 for r in racer_front_rates.values() if r >= 40):,}名")
    print()

    # テスト設定
    configs = [
        # ベースライン（現行設定）
        {
            'name': 'ベースライン（現行）',
            'weights': {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10},
            'use_st_hybrid': False,
            'use_exhibition_rank': False,
            'use_course_prediction': False,
        },

        # 改善案1+2: 会場別除外 + モーター軽減
        {
            'name': '改善1+2: モーター12点',
            'weights': {'course': 39, 'racer': 39, 'motor': 12, 'rank': 10},
            'use_st_hybrid': False,
            'use_exhibition_rank': False,
            'use_course_prediction': False,
        },

        # 改善案3: 展示ST混合
        {
            'name': '改善3: 展示ST混合',
            'weights': {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10},
            'use_st_hybrid': True,
            'st_config': {
                'past_st_ratio': 0.6,
                'exhibition_st_ratio': 0.4,
                'st_max_score': 10,
                'weight': 0.08,
            },
            'use_exhibition_rank': False,
            'use_course_prediction': False,
        },

        # 改善案4: 展示タイム順位評価
        {
            'name': '改善4: 展示タイム順位',
            'weights': {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10},
            'use_st_hybrid': False,
            'use_exhibition_rank': True,
            'exhibition_config': {
                'exhibition_rank_scores': {1: 20, 2: 10, 3: 5, 4: 0, 5: -5, 6: -10},
                'weight': 0.08,
            },
            'use_course_prediction': False,
        },

        # 改善案5: 進入コース予測
        {
            'name': '改善5: 進入コース予測',
            'weights': {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10},
            'use_st_hybrid': False,
            'use_exhibition_rank': False,
            'use_course_prediction': True,
            'course_config': {
                'front_entry_threshold': 40,
                'weight': 0.5,
            },
        },

        # 全改善案統合
        {
            'name': '★全改善案統合',
            'weights': {'course': 39, 'racer': 39, 'motor': 12, 'rank': 10},
            'use_st_hybrid': True,
            'st_config': {
                'past_st_ratio': 0.6,
                'exhibition_st_ratio': 0.4,
                'st_max_score': 10,
                'weight': 0.08,
            },
            'use_exhibition_rank': True,
            'exhibition_config': {
                'exhibition_rank_scores': {1: 20, 2: 10, 3: 5, 4: 0, 5: -5, 6: -10},
                'weight': 0.08,
            },
            'use_course_prediction': True,
            'course_config': {
                'front_entry_threshold': 40,
                'weight': 0.5,
            },
        },
    ]

    print('=' * 70)
    print('バックテスト結果')
    print('=' * 70)
    print()

    results = []
    baseline_win_rate = None

    for config in configs:
        result = backtest(races, config, racer_front_rates, config['name'])
        results.append(result)

        if baseline_win_rate is None:
            baseline_win_rate = result['win_rate']

    # 結果表示
    print(f"{'設定':<25} {'単勝':>8} {'差分':>8} {'複勝':>8} {'2連単':>8}")
    print('-' * 65)

    for r in results:
        diff = r['win_rate'] - baseline_win_rate
        diff_str = f"+{diff:.2f}%" if diff >= 0 else f"{diff:.2f}%"
        print(f"{r['label']:<25} {r['win_rate']:>7.2f}% {diff_str:>8} {r['place_rate']:>7.2f}% {r['exacta_rate']:>7.2f}%")

    print()
    print('=' * 70)
    print('パラメータチューニング（全改善案統合）')
    print('=' * 70)
    print()

    # ST混合比率のチューニング
    best_result = None
    best_config = None

    st_ratios = [(0.5, 0.5), (0.6, 0.4), (0.7, 0.3), (0.4, 0.6)]
    ex_weights = [0.05, 0.08, 0.10, 0.12]
    motor_weights = [10, 12, 14]

    print('パラメータ探索中...')
    total_combos = len(st_ratios) * len(ex_weights) * len(motor_weights)
    count = 0

    for past_ratio, ex_ratio in st_ratios:
        for ex_weight in ex_weights:
            for motor in motor_weights:
                count += 1
                if count % 10 == 0:
                    print(f"  {count}/{total_combos}...")

                config = {
                    'weights': {'course': (100 - motor - 10) // 2, 'racer': (100 - motor - 10) // 2, 'motor': motor, 'rank': 10},
                    'use_st_hybrid': True,
                    'st_config': {
                        'past_st_ratio': past_ratio,
                        'exhibition_st_ratio': ex_ratio,
                        'st_max_score': 10,
                        'weight': 0.08,
                    },
                    'use_exhibition_rank': True,
                    'exhibition_config': {
                        'exhibition_rank_scores': {1: 20, 2: 10, 3: 5, 4: 0, 5: -5, 6: -10},
                        'weight': ex_weight,
                    },
                    'use_course_prediction': True,
                    'course_config': {
                        'front_entry_threshold': 40,
                        'weight': 0.5,
                    },
                }

                result = backtest(races, config, racer_front_rates, '')

                if best_result is None or result['win_rate'] > best_result['win_rate']:
                    best_result = result
                    best_config = {
                        'past_ratio': past_ratio,
                        'ex_ratio': ex_ratio,
                        'ex_weight': ex_weight,
                        'motor': motor,
                    }

    print()
    print('=' * 70)
    print('最適パラメータ')
    print('=' * 70)
    print()
    print(f"単勝的中率: {best_result['win_rate']:.2f}% (+{best_result['win_rate'] - baseline_win_rate:.2f}%)")
    print(f"複勝的中率: {best_result['place_rate']:.2f}%")
    print(f"2連単的中率: {best_result['exacta_rate']:.2f}%")
    print()
    print('パラメータ:')
    print(f"  ST混合比率 = 過去{best_config['past_ratio']*100:.0f}% : 展示{best_config['ex_ratio']*100:.0f}%")
    print(f"  展示タイム重み = {best_config['ex_weight']}")
    print(f"  モーター配点 = {best_config['motor']}点")
    print(f"  コース配点 = {(100 - best_config['motor'] - 10) // 2}点")
    print(f"  選手配点 = {(100 - best_config['motor'] - 10) // 2}点")
    print()
    print('完了')


if __name__ == '__main__':
    main()
