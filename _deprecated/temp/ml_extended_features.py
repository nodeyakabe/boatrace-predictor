# -*- coding: utf-8 -*-
"""
拡張特徴量を含めた機械学習による重み最適化
2024年11月27日
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
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import warnings
warnings.filterwarnings('ignore')

from config.settings import DATABASE_PATH, VENUE_IN1_RATES


def get_extended_race_data(start_date: str, end_date: str) -> List[Dict]:
    """拡張特徴量を含むレースデータを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 基本データ + 展示タイム + race_details
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
            e.f_count,
            e.l_count,
            rd.exhibition_time,
            rd.tilt_angle as tilt,
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

    # レースごとにグループ化
    races = defaultdict(list)
    for row in rows:
        races[row['race_id']].append(dict(row))

    conn.close()
    return list(races.values())


def extract_features(entry: Dict, race_entries: List[Dict], venue_code: str) -> List[float]:
    """
    エントリーから特徴量を抽出

    Returns:
        [course, racer, motor, rank, st, exhibition, tilt, venue_in1, motor_venue]
    """
    pit = entry['pit_number']

    # 1. コーススコア
    course_base = {1: 100, 2: 33, 3: 22, 4: 18, 5: 11, 6: 9}
    course_score = course_base.get(pit, 10)

    # 2. 選手スコア（勝率ベース）
    win_rate = entry.get('win_rate') or 0
    local_win_rate = entry.get('local_win_rate') or 0
    racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10

    # 3. モータースコア
    motor_rate = entry.get('motor_second_rate') or 30
    motor_score = motor_rate

    # 4. 級別スコア
    rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
    rank = entry.get('racer_rank') or 'B1'
    rank_score = rank_scores.get(rank, 40)

    # 5. 平均STスコア（レース内相対順位）
    avg_st = entry.get('avg_st')
    st_score = 50  # デフォルト
    if avg_st is not None and avg_st > 0:
        valid_sts = [(e['pit_number'], e.get('avg_st') or 1.0)
                     for e in race_entries if e.get('avg_st') and e.get('avg_st') > 0]
        valid_sts.sort(key=lambda x: x[1])
        for i, (p, st) in enumerate(valid_sts, 1):
            if p == pit:
                st_score = 100 - (i - 1) * 10  # 1位=100, 6位=50
                break

    # 6. 展示タイムスコア（レース内相対順位）
    exhibition_time = entry.get('exhibition_time')
    exhibition_score = 50
    if exhibition_time is not None and exhibition_time > 0:
        valid_ex = [(e['pit_number'], e.get('exhibition_time') or 99)
                    for e in race_entries if e.get('exhibition_time') and e.get('exhibition_time') > 0]
        valid_ex.sort(key=lambda x: x[1])  # 早い順
        for i, (p, ex) in enumerate(valid_ex, 1):
            if p == pit:
                exhibition_score = 100 - (i - 1) * 10
                break

    # 7. チルト角度（-0.5〜+3.0を0〜100に正規化）
    tilt = entry.get('tilt')
    if tilt is not None:
        tilt_score = (tilt + 0.5) / 3.5 * 100
        tilt_score = max(0, min(100, tilt_score))
    else:
        tilt_score = 50

    # 8. 会場別1コース勝率（1コースのみ）
    venue_in1_score = 0
    if pit == 1:
        venue_in1 = VENUE_IN1_RATES.get(venue_code, 57)
        venue_in1_score = venue_in1  # そのまま

    # 9. F/Lペナルティ
    f_count = entry.get('f_count') or 0
    l_count = entry.get('l_count') or 0
    fl_penalty = -(f_count * 20 + l_count * 10)
    fl_score = max(0, 100 + fl_penalty)  # 0-100

    return [
        course_score,      # 0: コース
        racer_score,       # 1: 選手
        motor_score,       # 2: モーター
        rank_score,        # 3: 級別
        st_score,          # 4: ST
        exhibition_score,  # 5: 展示
        tilt_score,        # 6: チルト
        venue_in1_score,   # 7: 会場1コース勝率
        fl_score,          # 8: F/Lペナルティ
    ]


def prepare_ml_data(races: List[List[Dict]]) -> Tuple[np.ndarray, np.ndarray]:
    """
    機械学習用データを準備

    各レースで1着の艇を正例、それ以外を負例としてペアワイズ学習
    """
    X_list = []
    y_list = []

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        venue = race_entries[0]['venue_code']

        # 1着を特定
        winner = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                winner = entry
                break

        if winner is None:
            continue

        winner_features = extract_features(winner, race_entries, venue)

        # 1着 vs 他艇のペアを作成
        for entry in race_entries:
            if entry['pit_number'] == winner['pit_number']:
                continue

            loser_features = extract_features(entry, race_entries, venue)

            # 差分を特徴量として使用（winner - loser）
            diff = [w - l for w, l in zip(winner_features, loser_features)]

            X_list.append(diff)
            y_list.append(1)  # winner > loser

            # 逆も追加（loser - winner = 0）
            diff_rev = [-d for d in diff]
            X_list.append(diff_rev)
            y_list.append(0)

    return np.array(X_list), np.array(y_list)


def train_and_evaluate(X: np.ndarray, y: np.ndarray) -> Dict:
    """学習と評価"""
    # データ分割
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # 標準化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # ロジスティック回帰
    model = LogisticRegression(max_iter=1000, C=0.1)
    model.fit(X_train_scaled, y_train)

    # テスト精度
    train_acc = model.score(X_train_scaled, y_train)
    test_acc = model.score(X_test_scaled, y_test)

    # 係数（=重み）
    feature_names = [
        'course', 'racer', 'motor', 'rank', 'st',
        'exhibition', 'tilt', 'venue_in1', 'fl_penalty'
    ]
    coefficients = dict(zip(feature_names, model.coef_[0]))

    return {
        'train_accuracy': train_acc,
        'test_accuracy': test_acc,
        'coefficients': coefficients,
        'model': model,
        'scaler': scaler,
    }


def coefficients_to_weights(coefficients: Dict) -> Dict:
    """係数を0-100の重みに変換"""
    # 絶対値の合計で正規化
    abs_total = sum(abs(v) for v in coefficients.values())
    if abs_total == 0:
        return {k: 100/len(coefficients) for k in coefficients}

    weights = {}
    for k, v in coefficients.items():
        # 正の係数のみ考慮（負は無視または別処理）
        weights[k] = max(0, v) / abs_total * 100

    # 再正規化
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total * 100 for k, v in weights.items()}

    return weights


def backtest_with_weights(races: List[List[Dict]], weights: Dict, label: str) -> Dict:
    """重みでバックテスト"""
    results = {'win_hits': 0, 'total': 0}

    for race_entries in races:
        if len(race_entries) < 6:
            continue

        venue = race_entries[0]['venue_code']

        # スコア計算
        scores = []
        for entry in race_entries:
            features = extract_features(entry, race_entries, venue)
            feature_names = [
                'course', 'racer', 'motor', 'rank', 'st',
                'exhibition', 'tilt', 'venue_in1', 'fl_penalty'
            ]
            score = sum(features[i] * weights.get(feature_names[i], 0) / 100
                        for i in range(len(features)))
            scores.append((entry['pit_number'], score))

        scores.sort(key=lambda x: -x[1])
        predicted_winner = scores[0][0]

        # 実際の勝者
        actual_winner = None
        for entry in race_entries:
            if str(entry['result_rank']) == '1':
                actual_winner = entry['pit_number']
                break

        results['total'] += 1
        if predicted_winner == actual_winner:
            results['win_hits'] += 1

    return {
        'label': label,
        'win_rate': results['win_hits'] / results['total'] * 100 if results['total'] > 0 else 0,
        'results': results,
    }


def main():
    print('拡張特徴量を含めた機械学習による重み最適化')
    print('=' * 70)
    print()

    # データ取得
    start_date = '2024-01-01'
    end_date = '2024-11-20'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    print('データ取得中...')
    races = get_extended_race_data(start_date, end_date)
    print(f"取得完了: {len(races):,}レース")
    print()

    # ML用データ準備
    print('ML用データ準備中...')
    X, y = prepare_ml_data(races)
    print(f"サンプル数: {len(X):,}")
    print()

    # 学習
    print('学習中...')
    result = train_and_evaluate(X, y)
    print(f"訓練精度: {result['train_accuracy']:.4f}")
    print(f"テスト精度: {result['test_accuracy']:.4f}")
    print()

    # 係数表示
    print('【ML係数（生値）】')
    for name, coef in sorted(result['coefficients'].items(), key=lambda x: -abs(x[1])):
        print(f"  {name:<12}: {coef:>8.4f}")
    print()

    # 重みに変換
    ml_weights = coefficients_to_weights(result['coefficients'])
    print('【ML推奨重み（正規化後）】')
    for name, weight in sorted(ml_weights.items(), key=lambda x: -x[1]):
        print(f"  {name:<12}: {weight:>6.2f}%")
    print()

    # バックテスト比較
    print('=' * 70)
    print('バックテスト比較')
    print('=' * 70)
    print()

    # ベースライン（現行設定）
    baseline_weights = {
        'course': 35, 'racer': 35, 'motor': 20, 'rank': 10,
        'st': 0, 'exhibition': 0, 'tilt': 0, 'venue_in1': 0, 'fl_penalty': 0
    }
    result_baseline = backtest_with_weights(races, baseline_weights, 'ベースライン')

    # ベースライン + ST
    st_weights = {
        'course': 32, 'racer': 32, 'motor': 18, 'rank': 10,
        'st': 8, 'exhibition': 0, 'tilt': 0, 'venue_in1': 0, 'fl_penalty': 0
    }
    result_st = backtest_with_weights(races, st_weights, 'ベース+ST')

    # ベースライン + ST + 展示
    st_ex_weights = {
        'course': 30, 'racer': 30, 'motor': 16, 'rank': 8,
        'st': 8, 'exhibition': 8, 'tilt': 0, 'venue_in1': 0, 'fl_penalty': 0
    }
    result_st_ex = backtest_with_weights(races, st_ex_weights, 'ベース+ST+展示')

    # ML推奨
    result_ml = backtest_with_weights(races, ml_weights, 'ML推奨')

    # 結果表示
    print(f"{'設定':<20} {'単勝的中率':>12}")
    print('-' * 35)
    for r in [result_baseline, result_st, result_st_ex, result_ml]:
        print(f"{r['label']:<20} {r['win_rate']:>11.2f}%")

    print()
    print('=' * 70)
    print('分析結果')
    print('=' * 70)
    print()

    # 特徴量の重要度分析
    print('【特徴量の影響度分析】')
    coefs = result['coefficients']
    total_impact = sum(abs(v) for v in coefs.values())
    for name, coef in sorted(coefs.items(), key=lambda x: -abs(x[1])):
        impact = abs(coef) / total_impact * 100
        direction = '↑勝率上昇' if coef > 0 else '↓勝率低下'
        print(f"  {name:<12}: {impact:>5.1f}% 影響度 ({direction})")

    print()
    print('完了')


if __name__ == '__main__':
    main()
