# -*- coding: utf-8 -*-
"""
的中率改善テスト
1. レース番号別の加点減点
2. 気象条件データの分析
4. 深層学習モデル
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

from config.settings import DATABASE_PATH, VENUE_IN1_RATES, HIGH_IN_VENUES, LOW_IN_VENUES


# =============================================================================
# データ取得
# =============================================================================

def get_race_data_with_details(start_date: str, end_date: str) -> List[Dict]:
    """レースデータを気象条件含めて取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            rc.wind_speed,
            rc.wind_direction,
            rc.wave_height,
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            e.avg_st,
            rd.exhibition_time,
            rd.st_time as day_st,
            COALESCE(res.rank, 99) as result_rank
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
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


# =============================================================================
# 1. レース番号別分析
# =============================================================================

def analyze_race_number_effect(races: List[List[Dict]]) -> Dict:
    """レース番号別の1コース勝率を分析"""
    stats = defaultdict(lambda: {'wins': 0, 'total': 0})

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        race_num = race_entries[0]['race_number']

        # 1コースが勝ったか
        winner = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                winner = entry['pit_number']
                break

        stats[race_num]['total'] += 1
        if winner == 1:
            stats[race_num]['wins'] += 1

    return dict(stats)


def calculate_score_with_race_number(
    entry: Dict,
    race_entries: List[Dict],
    venue_code: str,
    race_number: int,
    adjustments: Dict
) -> float:
    """レース番号を考慮したスコア計算"""
    score = 0.0
    pit = entry['pit_number']

    # 基本スコア
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
    course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * 35 / 100

    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * 35 / 100

    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * 20 / 100

    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * 10 / 100

    # レース番号による調整
    if pit == 1:
        # 1R-3R: 新人戦で荒れやすい → 1コース減点
        if race_number <= 3:
            score -= adjustments.get('early_race_penalty', 0)
        # 10R-12R: メインレースで堅い → 1コース加点
        elif race_number >= 10:
            score += adjustments.get('main_race_bonus', 0)

    # 級別×レース番号
    if race_number >= 10 and rank == 'A1' and pit == 1:
        score += adjustments.get('main_a1_bonus', 0)

    return score


# =============================================================================
# 2. 気象条件分析
# =============================================================================

def analyze_weather_effect(races: List[List[Dict]]) -> Dict:
    """気象条件別の1コース勝率を分析"""
    wind_stats = defaultdict(lambda: {'wins': 0, 'total': 0})
    wave_stats = defaultdict(lambda: {'wins': 0, 'total': 0})

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        wind_speed = race_entries[0].get('wind_speed')
        wave_height = race_entries[0].get('wave_height')

        winner = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                winner = entry['pit_number']
                break

        # 風速カテゴリ
        if wind_speed is not None:
            if wind_speed <= 2:
                wind_cat = '弱風(0-2m)'
            elif wind_speed <= 5:
                wind_cat = '中風(3-5m)'
            else:
                wind_cat = '強風(6m+)'

            wind_stats[wind_cat]['total'] += 1
            if winner == 1:
                wind_stats[wind_cat]['wins'] += 1

        # 波高カテゴリ
        if wave_height is not None:
            if wave_height <= 3:
                wave_cat = '静水(0-3cm)'
            elif wave_height <= 7:
                wave_cat = '中波(4-7cm)'
            else:
                wave_cat = '高波(8cm+)'

            wave_stats[wave_cat]['total'] += 1
            if winner == 1:
                wave_stats[wave_cat]['wins'] += 1

    return {'wind': dict(wind_stats), 'wave': dict(wave_stats)}


def calculate_score_with_weather(
    entry: Dict,
    race_entries: List[Dict],
    venue_code: str,
    adjustments: Dict
) -> float:
    """気象条件を考慮したスコア計算"""
    score = 0.0
    pit = entry['pit_number']

    # 基本スコア
    course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
    course_score = course_base.get(pit, 10) / 55 * 100
    score += course_score * 35 / 100

    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
    score += racer_score * 35 / 100

    motor_rate = entry.get('motor_second_rate') or 30
    score += motor_rate * 20 / 100

    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)
    score += rank_score * 10 / 100

    # 気象条件による調整
    wind_speed = race_entries[0].get('wind_speed') or 0
    wave_height = race_entries[0].get('wave_height') or 0

    if pit == 1:
        # 強風時は1コース不利
        if wind_speed >= 5:
            score -= adjustments.get('strong_wind_penalty', 0)
        # 高波時も1コース不利
        if wave_height >= 5:
            score -= adjustments.get('high_wave_penalty', 0)

    # 外コースは荒天時に有利（まくりやすい）
    if pit >= 4:
        if wind_speed >= 5 or wave_height >= 5:
            score += adjustments.get('outer_rough_bonus', 0)

    return score


# =============================================================================
# 4. 深層学習モデル
# =============================================================================

def prepare_nn_features(entry: Dict, race_entries: List[Dict], venue_code: str) -> List[float]:
    """ニューラルネット用の特徴量を準備"""
    pit = entry['pit_number']

    # コースのone-hot
    course_onehot = [1 if pit == i else 0 for i in range(1, 7)]

    # 選手スコア
    win_rate = (entry.get('win_rate') or 0) / 10
    local_win_rate = (entry.get('local_win_rate') or 0) / 10

    # モーター
    motor_rate = (entry.get('motor_second_rate') or 30) / 100

    # 級別one-hot
    rank = entry.get('racer_rank') or 'B1'
    rank_onehot = [
        1 if rank == 'A1' else 0,
        1 if rank == 'A2' else 0,
        1 if rank == 'B1' else 0,
        1 if rank == 'B2' else 0,
    ]

    # ST相対順位
    avg_st = entry.get('avg_st')
    st_rank = 0.5
    if avg_st and avg_st > 0:
        valid_sts = [(e['pit_number'], e.get('avg_st') or 1.0)
                     for e in race_entries if e.get('avg_st') and e.get('avg_st') > 0]
        valid_sts.sort(key=lambda x: x[1])
        for i, (p, st) in enumerate(valid_sts, 1):
            if p == pit:
                st_rank = (7 - i) / 6  # 1位=1.0, 6位=0.17
                break

    # 展示タイム相対順位
    ex_time = entry.get('exhibition_time')
    ex_rank = 0.5
    if ex_time and ex_time > 0:
        valid_ex = [(e['pit_number'], e.get('exhibition_time') or 99)
                    for e in race_entries if e.get('exhibition_time') and e.get('exhibition_time') > 0]
        valid_ex.sort(key=lambda x: x[1])
        for i, (p, ex) in enumerate(valid_ex, 1):
            if p == pit:
                ex_rank = (7 - i) / 6
                break

    # 気象条件
    wind_speed = (race_entries[0].get('wind_speed') or 3) / 10
    wave_height = (race_entries[0].get('wave_height') or 3) / 20

    # レース番号
    race_num = race_entries[0].get('race_number') or 6
    race_num_norm = race_num / 12

    features = (
        course_onehot +           # 6
        [win_rate, local_win_rate] +  # 2
        [motor_rate] +            # 1
        rank_onehot +             # 4
        [st_rank, ex_rank] +      # 2
        [wind_speed, wave_height] +   # 2
        [race_num_norm]           # 1
    )

    return features  # 18次元


def train_nn_model(races: List[List[Dict]]):
    """ニューラルネットワークを学習"""
    try:
        from sklearn.neural_network import MLPClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
    except ImportError:
        print("scikit-learn が必要です")
        return None, None

    X_list = []
    y_list = []

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        venue = race_entries[0]['venue_code']

        # 勝者を特定
        winner_pit = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                winner_pit = entry['pit_number']
                break

        if winner_pit is None:
            continue

        # 各艇の特徴量
        for entry in race_entries:
            features = prepare_nn_features(entry, race_entries, venue)
            X_list.append(features)
            y_list.append(1 if entry['pit_number'] == winner_pit else 0)

    X = np.array(X_list)
    y = np.array(y_list)

    # 分割
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 標準化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # モデル学習
    model = MLPClassifier(
        hidden_layer_sizes=(64, 32),
        activation='relu',
        max_iter=500,
        random_state=42,
        early_stopping=True,
        validation_fraction=0.1
    )
    model.fit(X_train_scaled, y_train)

    train_acc = model.score(X_train_scaled, y_train)
    test_acc = model.score(X_test_scaled, y_test)

    print(f"NN訓練精度: {train_acc:.4f}")
    print(f"NNテスト精度: {test_acc:.4f}")

    return model, scaler


def predict_with_nn(race_entries: List[Dict], model, scaler) -> int:
    """NNで勝者を予測"""
    venue = race_entries[0]['venue_code']

    features_list = []
    pits = []
    for entry in race_entries:
        features = prepare_nn_features(entry, race_entries, venue)
        features_list.append(features)
        pits.append(entry['pit_number'])

    X = np.array(features_list)
    X_scaled = scaler.transform(X)

    # 各艇の勝利確率
    probs = model.predict_proba(X_scaled)[:, 1]

    # 最大確率の艇
    best_idx = np.argmax(probs)
    return pits[best_idx]


# =============================================================================
# バックテスト
# =============================================================================

def backtest_baseline(races: List[List[Dict]]) -> Dict:
    """ベースラインバックテスト"""
    results = {'win_hits': 0, 'total': 0}

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        # スコア計算（基本重み）
        scores = []
        for entry in race_entries:
            pit = entry['pit_number']
            course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
            score = course_base.get(pit, 10) / 55 * 100 * 35 / 100

            win_rate = entry.get('win_rate') or 0
            local_win_rate = entry.get('local_win_rate') or 0
            score += (win_rate * 0.6 + local_win_rate * 0.4) * 10 * 35 / 100

            motor_rate = entry.get('motor_second_rate') or 30
            score += motor_rate * 20 / 100

            rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
            rank = entry.get('racer_rank') or 'B1'
            score += rank_scores.get(rank, 40) * 10 / 100

            scores.append((pit, score))

        scores.sort(key=lambda x: -x[1])
        predicted = scores[0][0]

        actual = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                actual = entry['pit_number']
                break

        results['total'] += 1
        if predicted == actual:
            results['win_hits'] += 1

    return results


def backtest_with_adjustments(
    races: List[List[Dict]],
    score_func,
    adjustments: Dict,
    label: str
) -> Dict:
    """調整付きバックテスト"""
    results = {'win_hits': 0, 'total': 0}

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        venue = race_entries[0]['venue_code']
        race_number = race_entries[0].get('race_number') or 6

        scores = []
        for entry in race_entries:
            if score_func == calculate_score_with_race_number:
                score = score_func(entry, race_entries, venue, race_number, adjustments)
            else:
                score = score_func(entry, race_entries, venue, adjustments)
            scores.append((entry['pit_number'], score))

        scores.sort(key=lambda x: -x[1])
        predicted = scores[0][0]

        actual = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                actual = entry['pit_number']
                break

        results['total'] += 1
        if predicted == actual:
            results['win_hits'] += 1

    return {'label': label, 'results': results}


def backtest_nn(races: List[List[Dict]], model, scaler) -> Dict:
    """NNバックテスト"""
    results = {'win_hits': 0, 'total': 0}

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        predicted = predict_with_nn(race_entries, model, scaler)

        actual = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                actual = entry['pit_number']
                break

        results['total'] += 1
        if predicted == actual:
            results['win_hits'] += 1

    return results


# =============================================================================
# メイン
# =============================================================================

def main():
    print('的中率改善テスト')
    print('=' * 70)
    print()

    start_date = '2024-01-01'
    end_date = '2024-11-20'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    print('データ取得中...')
    races = get_race_data_with_details(start_date, end_date)
    print(f"取得完了: {len(races):,}レース")
    print()

    # ベースライン
    print('=' * 70)
    print('ベースライン')
    print('=' * 70)
    baseline = backtest_baseline(races)
    baseline_rate = baseline['win_hits'] / baseline['total'] * 100
    print(f"単勝的中率: {baseline_rate:.2f}%")
    print()

    # =================================
    # 1. レース番号別分析
    # =================================
    print('=' * 70)
    print('1. レース番号別分析')
    print('=' * 70)

    race_num_stats = analyze_race_number_effect(races)
    print()
    print('【レース番号別 1コース勝率】')
    for rn in sorted(race_num_stats.keys()):
        stats = race_num_stats[rn]
        rate = stats['wins'] / stats['total'] * 100 if stats['total'] > 0 else 0
        bar = '*' * int(rate / 5)
        print(f"  {rn:2d}R: {rate:5.1f}% ({stats['wins']:>4}/{stats['total']:>4}) {bar}")

    print()
    print('【レース番号による調整テスト】')

    # グリッドサーチ
    best_result = None
    best_rate = 0

    for early_penalty in [0, 1, 2, 3]:
        for main_bonus in [0, 1, 2, 3]:
            for main_a1 in [0, 1, 2]:
                adjustments = {
                    'early_race_penalty': early_penalty,
                    'main_race_bonus': main_bonus,
                    'main_a1_bonus': main_a1,
                }
                result = backtest_with_adjustments(
                    races, calculate_score_with_race_number, adjustments, ''
                )
                rate = result['results']['win_hits'] / result['results']['total'] * 100
                if rate > best_rate:
                    best_rate = rate
                    best_result = adjustments.copy()

    print(f"最良設定: {best_result}")
    print(f"単勝的中率: {best_rate:.2f}% (+{best_rate - baseline_rate:.2f}%)")
    print()

    # =================================
    # 2. 気象条件分析
    # =================================
    print('=' * 70)
    print('2. 気象条件分析')
    print('=' * 70)

    weather_stats = analyze_weather_effect(races)

    print()
    print('【風速別 1コース勝率】')
    for cat, stats in sorted(weather_stats['wind'].items()):
        rate = stats['wins'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {cat}: {rate:5.1f}% ({stats['wins']:>4}/{stats['total']:>4})")

    print()
    print('【波高別 1コース勝率】')
    for cat, stats in sorted(weather_stats['wave'].items()):
        rate = stats['wins'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {cat}: {rate:5.1f}% ({stats['wins']:>4}/{stats['total']:>4})")

    print()
    print('【気象条件による調整テスト】')

    best_weather_result = None
    best_weather_rate = 0

    for wind_penalty in [0, 1, 2, 3]:
        for wave_penalty in [0, 1, 2, 3]:
            for outer_bonus in [0, 1, 2]:
                adjustments = {
                    'strong_wind_penalty': wind_penalty,
                    'high_wave_penalty': wave_penalty,
                    'outer_rough_bonus': outer_bonus,
                }
                result = backtest_with_adjustments(
                    races, calculate_score_with_weather, adjustments, ''
                )
                rate = result['results']['win_hits'] / result['results']['total'] * 100
                if rate > best_weather_rate:
                    best_weather_rate = rate
                    best_weather_result = adjustments.copy()

    print(f"最良設定: {best_weather_result}")
    print(f"単勝的中率: {best_weather_rate:.2f}% (+{best_weather_rate - baseline_rate:.2f}%)")
    print()

    # =================================
    # 4. 深層学習モデル
    # =================================
    print('=' * 70)
    print('4. 深層学習モデル（ニューラルネットワーク）')
    print('=' * 70)
    print()

    # 訓練データとテストデータを分割
    split_idx = int(len(races) * 0.8)
    train_races = races[:split_idx]
    test_races = races[split_idx:]

    print(f"訓練データ: {len(train_races):,}レース")
    print(f"テストデータ: {len(test_races):,}レース")
    print()

    print('NNモデル学習中...')
    model, scaler = train_nn_model(train_races)

    if model is not None:
        print()
        print('【NNモデルでバックテスト】')

        # テストデータで評価
        nn_result = backtest_nn(test_races, model, scaler)
        nn_rate = nn_result['win_hits'] / nn_result['total'] * 100

        # ベースラインもテストデータで再評価
        baseline_test = backtest_baseline(test_races)
        baseline_test_rate = baseline_test['win_hits'] / baseline_test['total'] * 100

        print(f"ベースライン(テスト): {baseline_test_rate:.2f}%")
        print(f"NNモデル(テスト): {nn_rate:.2f}% ({nn_rate - baseline_test_rate:+.2f}%)")

    print()
    print('=' * 70)
    print('結果サマリー')
    print('=' * 70)
    print()
    print(f"ベースライン:        {baseline_rate:.2f}%")
    print(f"レース番号調整:      {best_rate:.2f}% ({best_rate - baseline_rate:+.2f}%)")
    print(f"気象条件調整:        {best_weather_rate:.2f}% ({best_weather_rate - baseline_rate:+.2f}%)")
    if model is not None:
        print(f"NNモデル(テスト):    {nn_rate:.2f}% ({nn_rate - baseline_test_rate:+.2f}%)")

    print()
    print('完了')


if __name__ == '__main__':
    main()
