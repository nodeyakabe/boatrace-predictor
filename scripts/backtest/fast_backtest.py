#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
高速バックテスト（prediction_features ベース）

目的:
    prediction_features テーブルの raw スコアから、スコアリング重みや信頼度閾値を
    変更した場合の効果を即座に確認する。predict_race() の再実行が不要。

前提:
    generate_features.py で prediction_features テーブルが生成済みであること。

使用方法:
    # デフォルト（現在の scoring_weights.yaml のまま）
    python scripts/backtest/fast_backtest.py --full

    # confidence 閾値を変更してテスト（P5: score_gap 15→12）
    python scripts/backtest/fast_backtest.py --full --conf-a-gap 12

    # motor_weight を変更してテスト
    python scripts/backtest/fast_backtest.py --full --motor-weight 25

    # 複数パラメータを同時に変更
    python scripts/backtest/fast_backtest.py --full --conf-a-gap 12 --motor-weight 25

    # 特定年度のみ
    python scripts/backtest/fast_backtest.py --year 2024

速度の目安:
    - confidence 閾値変更のみ: 数秒〜1分
    - scoring_weights 変更: 1〜3分
    - 標準バックテスト（比較用）: 数分

結果の正確性:
    - predict_race() の全後処理（天候補正、潮位補正、パターンボーナス等）の結果が
      total_score_final として保存されているため、confidence 閾値変更は完全に正確。
    - scoring_weights 変更時は raw スコアから再計算するため、動的重み調整
      （会場/グレード依存の重み変更）の影響で微小な誤差が生じる可能性がある。
      バリデーション: validate_fast_backtest.py で既存バックテストとの一致率を確認。
"""
import sys
import os
import io
import json
import sqlite3
import warnings
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import yaml

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS, GLOBAL_VENUE_MONTH_EXCLUDES, GLOBAL_MONTH_EXCLUDES

try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    print("ERROR: pandas/numpy が必要です。pip install pandas numpy でインストールしてください。")
    sys.exit(1)

WEIGHTS_YAML_PATH = os.path.join(PROJECT_ROOT, 'config', 'presets', 'scoring_weights.yaml')

# ============================================================
# デフォルトの confidence 閾値（_recalculate_race_confidence と同じ）
# ============================================================
DEFAULT_CONFIDENCE_THRESHOLDS = {
    'A': {'gap': 15, 'min_score': 70},
    'B': {'gap': 10, 'min_score': 60},
    'C': {'gap': 5, 'pit1_min_score': 55},
    'D': {'gap': 2},
}


def load_scoring_weights(yaml_path: str = None) -> dict:
    """scoring_weights.yaml を読み込む"""
    path = yaml_path or WEIGHTS_YAML_PATH
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_features(start_date: str, end_date: str) -> pd.DataFrame:
    """
    prediction_features テーブルを pandas DataFrame で一括ロード

    Returns:
        DataFrame（全カラム）
    """
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query("""
        SELECT
            pf.race_id, pf.pit_number,
            pf.racer_number, pf.racer_name, pf.racer_rank,
            pf.venue_code, pf.race_grade, pf.race_date,
            pf.course_score_raw, pf.racer_score_raw, pf.motor_score_raw,
            pf.kimarite_score_raw, pf.grade_score_raw,
            pf.extended_score_raw, pf.compound_buff,
            pf.ext_class_score, pf.ext_fl_penalty, pf.ext_capsizing_penalty,
            pf.ext_session_score, pf.ext_prev_race_score, pf.ext_course_entry_score,
            pf.ext_matchup_score, pf.ext_motor_score, pf.ext_start_timing_score,
            pf.ext_exhibition_score, pf.ext_tilt_score, pf.ext_chikusen_time_score,
            pf.ext_recent_form_score, pf.ext_venue_affinity_score,
            pf.ext_place_rate_score, pf.ext_motor_second_rate_score,
            pf.total_score_final,
            pf.original_confidence,
            pf.original_rank_prediction
        FROM prediction_features pf
        WHERE pf.race_date >= ? AND pf.race_date <= ?
    """, conn, params=(start_date, end_date))
    conn.close()
    return df


def recalculate_scores(
    df: pd.DataFrame,
    weights: dict,
    thresholds: dict,
    mode: str = 'confidence_only',
    use_original_confidence: bool = False
) -> pd.DataFrame:
    """
    raw スコアから total_score + rank_prediction + confidence を再計算

    Args:
        df: prediction_features DataFrame
        weights: scoring_weights.yaml の内容
        thresholds: confidence 閾値辞書
        mode:
            'confidence_only' - total_score_final をそのまま使用、confidence のみ再計算（最速）
            'full'            - raw スコアから total_score も再計算
        use_original_confidence: True の場合、prediction_features.original_confidence をそのまま使用
            （compound_buff 込みスコアからの再計算は不正確なため、デフォルト設定時に使用）

    Returns:
        total_score, rank_prediction, confidence カラムが追加された DataFrame
    """
    df = df.copy()

    if mode == 'confidence_only':
        # total_score_final をそのまま使用（confidence 閾値変更のみ）
        df['total_score'] = df['total_score_final']
    else:
        # raw スコアから total_score を再計算（scoring_weights 変更時）
        df = _recalculate_total_score(df, weights)

    # rank_prediction を再付与（レース内ソート）
    df['rank_prediction'] = df.groupby('race_id')['total_score'].rank(
        ascending=False, method='first'
    ).astype(int)

    if use_original_confidence and 'original_rank_prediction' in df.columns:
        # original_rank_prediction をそのまま使用（compound_buff の影響を受けない正確な順位）
        # NULL の場合は total_score_final からの再計算値で補完
        mask_null = df['original_rank_prediction'].isna()
        if mask_null.any():
            df.loc[~mask_null, 'rank_prediction'] = df.loc[~mask_null, 'original_rank_prediction']
        else:
            df['rank_prediction'] = df['original_rank_prediction']
        # original_confidence をそのまま使用
        df['confidence'] = df['original_confidence']
    else:
        # confidence を再計算（閾値変更テスト時）
        # NOTE: total_score_final には compound_buff が含まれるため近似値になる
        df = _recalculate_confidence(df, thresholds)

    return df


def _recalculate_total_score(df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """
    raw スコアから total_score を再計算（scoring_weights 変更時）

    NOTE: 動的重み調整（会場/グレード依存）はここでは適用しない（平均重みを使用）。
    より正確な計算は generate_features.py での再生成が必要。
    """
    base_w = weights.get('dynamic_weights', {}).get('base', {})
    racer_w  = base_w.get('racer_weight', 35)
    motor_w  = base_w.get('motor_weight', 20)
    ext_w    = weights.get('extended_scorer', {}).get('total_weight', 20.0)
    ext_max  = weights.get('extended_scorer', {}).get('max_possible', 75)
    ext_min  = weights.get('extended_scorer', {}).get('min_possible', -10)
    course_w = base_w.get('course_weight', 35)
    kimar_w  = base_w.get('kimarite_weight', 5)
    grade_w  = base_w.get('grade_weight', 5)

    # ExtendedScore: サブコンポーネントから再合算
    ext_weights = weights.get('extended_scorer', {})

    def get_ew(key, default):
        return float(ext_weights.get(key, default))

    extended_recalc = (
        df['ext_class_score'] * (get_ew('class_score', 10) / 10.0)
        + df['ext_fl_penalty']  # fl_penalty はそのまま（ペナルティ自体）
        + df['ext_capsizing_penalty']
        + df['ext_session_score']      * (get_ew('session', 5) / 5.0)
        + df['ext_prev_race_score']    * (get_ew('prev_race', 5) / 5.0)
        + df['ext_course_entry_score'] * (get_ew('course_entry', 5) / 5.0)
        + df['ext_matchup_score']      * (get_ew('matchup', 5) / 5.0)
        + df['ext_motor_score']        * (get_ew('motor', 5) / 5.0)
        + df['ext_start_timing_score'] * (get_ew('start_timing', 10) / 10.0)
        + df['ext_exhibition_score']   * (get_ew('exhibition', 8) / 8.0)
        + df['ext_tilt_score']         * (get_ew('tilt', 3) / 3.0)
        + df['ext_chikusen_time_score']  # ほぼ 0
        + df['ext_recent_form_score']  * (get_ew('recent_form', 8) / 8.0)
        + df['ext_venue_affinity_score'] * (get_ew('venue_affinity', 3) / 3.0)
        + df['ext_place_rate_score']   * (get_ew('place_rate', 5) / 5.0)
        + df['ext_motor_second_rate_score'] * (get_ew('motor_second_rate', 3) / 3.0)
    )

    # Extended 正規化: -min 〜 max → 0 〜 ext_w
    extended_normalized = ((extended_recalc - ext_min) / (ext_max - ext_min)) * ext_w
    extended_normalized = extended_normalized.clip(0, ext_w)

    # 各スコアコンポーネント
    # course_score_raw は course_weight 適用済みのため、course_weight 変更は非対応
    # （course_weight 変更が必要な場合は generate_features.py で再生成）
    racer_score  = df['racer_score_raw']  * (racer_w / 40.0)
    motor_score  = df['motor_score_raw']  * (motor_w / 20.0)

    raw_total = (
        df['course_score_raw']     # course_weight 適用済み
        + racer_score
        + motor_score
        + df['kimarite_score_raw'] # kimarite_weight 適用済み
        + df['grade_score_raw']    # grade_weight 適用済み
        + extended_normalized
    )

    max_possible = course_w + racer_w + motor_w + kimar_w + grade_w + ext_w
    total_score = (raw_total / max_possible) * 100.0 + df['compound_buff']
    df['total_score'] = total_score.clip(0, 100)

    return df


def _recalculate_confidence(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """
    _calculate_confidence() + _recalculate_race_confidence() と同じ2段階ロジックで confidence を再計算

    Step 1: total_score ベースの判定（_calculate_confidence の score 判定部分を再現）
    Step 2: score_gap ベースの判定（_recalculate_race_confidence を再現）
    最終値: min(Step1, Step2) — 安全側に倒す（低い信頼度のみ採用）

    confidence は 1位艇のみ設定（2位以下は None）
    """
    CONF_ORDER = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
    ORDER_CONF = {v: k for k, v in CONF_ORDER.items()}

    # 1位・2位のスコアを取得
    top1 = df[df['rank_prediction'] == 1][['race_id', 'pit_number', 'total_score']].copy()
    top2 = df[df['rank_prediction'] == 2][['race_id', 'total_score']].rename(
        columns={'total_score': 'score_2nd'}
    )

    top1 = top1.merge(top2, on='race_id', how='left')
    top1['score_2nd'] = top1['score_2nd'].fillna(0.0)
    top1['score_gap'] = top1['total_score'] - top1['score_2nd']
    top1['is_course1'] = top1['pit_number'] == 1

    # Step 1: total_score ベース（_calculate_confidence のスコア判定を再現）
    # race_predictor.py L1654-1663: >=75→A, >=65→B, >=55→C, >=45→D, else E
    score_conf = np.select(
        [
            top1['total_score'] >= 75,
            top1['total_score'] >= 65,
            top1['total_score'] >= 55,
            top1['total_score'] >= 45,
        ],
        ['A', 'B', 'C', 'D'],
        default='E'
    )

    # Step 2: score_gap ベース（_recalculate_race_confidence を再現）
    # race_predictor.py L1695-1704
    ct = thresholds
    a_gap   = ct['A']['gap']
    a_min   = ct['A']['min_score']
    b_gap   = ct['B']['gap']
    b_min   = ct['B']['min_score']
    c_gap   = ct['C']['gap']
    c_p1min = ct['C'].get('pit1_min_score', 55)
    d_gap   = ct['D']['gap']

    gap_conf = np.select(
        [
            (top1['score_gap'] >= a_gap) & (top1['total_score'] >= a_min),
            (top1['score_gap'] >= b_gap) & (top1['total_score'] >= b_min),
            (top1['score_gap'] >= c_gap) | (top1['is_course1'] & (top1['total_score'] >= c_p1min)),
            top1['score_gap'] >= d_gap,
        ],
        ['A', 'B', 'C', 'D'],
        default='E'
    )

    # 最終値: min(Step1, Step2) — 安全側に倒す
    # race_predictor.py L1711: gap_conf が低い場合のみ採用
    score_order = pd.Series(score_conf).map(CONF_ORDER).values
    gap_order   = pd.Series(gap_conf).map(CONF_ORDER).values
    final_order = np.minimum(score_order, gap_order)
    top1['confidence_new'] = pd.Series(final_order).map(ORDER_CONF).values

    conf_map = top1.set_index('race_id')['confidence_new'].to_dict()
    df['confidence'] = df['race_id'].map(conf_map)

    return df


def load_odds_and_results(race_ids: List[int]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    指定 race_ids の trifecta_odds と results を取得

    Returns:
        (df_odds, df_results)
    """
    if not race_ids:
        return pd.DataFrame(), pd.DataFrame()

    conn = sqlite3.connect(DATABASE_PATH)
    placeholders = ','.join('?' * len(race_ids))

    df_odds = pd.read_sql_query(f"""
        SELECT race_id, combination, odds
        FROM trifecta_odds
        WHERE race_id IN ({placeholders})
    """, conn, params=race_ids)

    df_results = pd.read_sql_query(f"""
        SELECT race_id, pit_number, CAST(rank AS INTEGER) AS finish_position
        FROM results
        WHERE race_id IN ({placeholders})
          AND CAST(rank AS INTEGER) BETWEEN 1 AND 3
    """, conn, params=race_ids)

    conn.close()
    return df_odds, df_results


def filter_by_condition(df_top1: pd.DataFrame, df_all: pd.DataFrame, cond: dict) -> pd.DataFrame:
    """
    1つの購入条件に対して df_top1 をフィルタリング

    Args:
        df_top1: rank_prediction == 1 のDataFrame
                 （pit1_racer_rank カラムが必要: run_fast_backtest で付与済み）
        df_all:  全rank のDataFrame（predicted_course フィルタ用）
        cond: bet_conditions の1条件

    Returns:
        条件に合致した df_top1 の部分集合
    """
    d = df_top1.copy()

    # confidence フィルター
    if cond.get('confidence'):
        d = d[d['confidence'] == cond['confidence']]

    # 1号艇（pit_number=1）の選手ランク（c1_rank）
    # 標準バックテスト（backtest_helpers.py L183）と同じく pit_number=1 のランクを使用
    if cond.get('c1_rank'):
        d = d[d['pit1_racer_rank'].isin(cond['c1_rank'])]

    # 会場フィルター
    if cond.get('venue_filter'):
        venues = [f"{v:02d}" if isinstance(v, int) else str(v) for v in cond['venue_filter']]
        d = d[d['venue_code'].isin(venues)]

    # 会場除外
    if cond.get('venue_exclude'):
        venues_ex = [f"{v:02d}" if isinstance(v, int) else str(v) for v in cond['venue_exclude']]
        d = d[~d['venue_code'].isin(venues_ex)]

    # 月除外（条件個別 + グローバル月除外）
    combined_month_exclude = list(cond.get('month_exclude') or []) + list(GLOBAL_MONTH_EXCLUDES or [])
    if combined_month_exclude:
        d = d[~d['month'].isin(combined_month_exclude)]

    # グローバル会場×月除外
    # GLOBAL_VENUE_MONTH_EXCLUDES は (venue_int, month_int) のタプルリスト
    if GLOBAL_VENUE_MONTH_EXCLUDES:
        for excl in GLOBAL_VENUE_MONTH_EXCLUDES:
            if isinstance(excl, tuple):
                venue_int, month_int = excl
                v = f"{venue_int:02d}"
                months = [month_int]
            else:
                # 辞書形式のフォールバック
                v = f"{excl['venue']:02d}" if isinstance(excl.get('venue'), int) else str(excl.get('venue', ''))
                months = excl.get('months', [])
            if v and months:
                d = d[~(d['venue_code'].eq(v) & d['month'].isin(months))]

    # 会場×月除外（条件個別）
    if cond.get('venue_month_exclude'):
        for excl in cond['venue_month_exclude']:
            if isinstance(excl, tuple):
                venue_int, month_int = excl
                v = f"{venue_int:02d}"
                months = [month_int]
            else:
                v = f"{excl['venue']:02d}" if isinstance(excl.get('venue'), int) else str(excl.get('venue', ''))
                months = excl.get('months', [])
            if v and months:
                d = d[~(d['venue_code'].eq(v) & d['month'].isin(months))]

    # predicted_course（pit_number == N を1位予測した場合のみ）
    if cond.get('predicted_course'):
        d = d[d['pit_number'] == cond['predicted_course']]

    return d


def compute_payoff(race_ids, df_all, df_odds, df_results, cond) -> dict:
    """
    対象レースの収支を計算

    標準バックテスト（standard_backtest_unique.py）と同じロジック:
    - Pattern H: p1-p2-p3（200円）, p1-p2-p4（100円）, p1-p2-p5（100円）
    - 各ベットは個別にオッズチェック（オッズ外のベットはスキップ）

    Args:
        race_ids: 購入対象の race_id リスト
        df_all: 全rank DataFrame（2-5位の pit_number 取得用）
        df_odds: trifecta_odds DataFrame
        df_results: results DataFrame
        cond: 購入条件

    Returns:
        {'total_bet': int, 'total_return': int, 'hits': int, 'races': int}
    """
    use_pattern_h = cond.get('use_pattern_h', False)
    odds_min = cond.get('odds_min', 0)
    odds_max = cond.get('odds_max', 9999)

    total_bet = 0
    total_return = 0
    hits = 0
    races_bought = 0

    rid_set = set(race_ids)
    df_top  = df_all[df_all['race_id'].isin(rid_set) & (df_all['rank_prediction'] == 1)]
    df_2nd  = df_all[df_all['race_id'].isin(rid_set) & (df_all['rank_prediction'] == 2)]
    df_3rd  = df_all[df_all['race_id'].isin(rid_set) & (df_all['rank_prediction'] == 3)]
    df_4th  = df_all[df_all['race_id'].isin(rid_set) & (df_all['rank_prediction'] == 4)]
    df_5th  = df_all[df_all['race_id'].isin(rid_set) & (df_all['rank_prediction'] == 5)]

    top_map  = df_top.set_index('race_id')['pit_number'].to_dict()
    sec_map  = df_2nd.set_index('race_id')['pit_number'].to_dict()
    trd_map  = df_3rd.set_index('race_id')['pit_number'].to_dict()
    qua_map  = df_4th.set_index('race_id')['pit_number'].to_dict()
    qui_map  = df_5th.set_index('race_id')['pit_number'].to_dict()

    # trifecta_odds をインデックス化
    odds_idx = {}
    for _, row in df_odds[df_odds['race_id'].isin(rid_set)].iterrows():
        odds_idx[(row['race_id'], row['combination'])] = row['odds']

    # results をインデックス化（上位3位の pit_number を取得）
    finish_map = {}
    for _, row in df_results[df_results['race_id'].isin(rid_set)].iterrows():
        rid = row['race_id']
        pos = int(row['finish_position'])
        pit = int(row['pit_number'])
        if rid not in finish_map:
            finish_map[rid] = {}
        finish_map[rid][pos] = pit

    for race_id in race_ids:
        p1 = top_map.get(race_id)
        p2 = sec_map.get(race_id)
        p3 = trd_map.get(race_id)
        p4 = qua_map.get(race_id)
        p5 = qui_map.get(race_id)

        if p1 is None or p2 is None or p3 is None:
            continue

        # パターンH: 3点買い（200/100/100円）
        # 標準バックテスト（standard_backtest_unique.py L140-162）と同じ構成:
        #   p1-p2-p3（200円）, p1-p2-p4（100円）, p1-p2-p5（100円）
        # 各ベットは個別にオッズチェック（odds_min <= odds < odds_max を満たすもののみ購入）
        if use_pattern_h:
            raw_bets = [
                (f"{p1}-{p2}-{p3}", 200),
                (f"{p1}-{p2}-{p4}", 100) if p4 else None,
                (f"{p1}-{p2}-{p5}", 100) if p5 else None,
            ]
        else:
            # 1点買い（100円）
            raw_bets = [(f"{p1}-{p2}-{p3}", 100)]

        # 各ベットの個別オッズチェック（標準バックテストと同じ）
        bets = []
        for b in raw_bets:
            if b is None:
                continue
            comb, bet_amount = b
            b_odds = odds_idx.get((race_id, comb))
            if b_odds is None or b_odds < odds_min or b_odds >= odds_max:
                continue
            bets.append((comb, bet_amount, b_odds))

        if not bets:
            continue

        # 購入
        race_bet = sum(b[1] for b in bets)
        total_bet += race_bet
        races_bought += 1

        # 的中判定
        actual = finish_map.get(race_id, {})
        actual_1 = actual.get(1)
        actual_2 = actual.get(2)
        actual_3 = actual.get(3)
        if actual_1 is None or actual_2 is None or actual_3 is None:
            continue

        actual_comb = f"{actual_1}-{actual_2}-{actual_3}"

        for comb, bet_amount, b_odds in bets:
            if comb == actual_comb:
                total_return += int(b_odds * bet_amount)  # odds は倍率、bet_amount円分
                hits += 1
                break

    return {
        'total_bet': total_bet,
        'total_return': total_return,
        'hits': hits,
        'races': races_bought,
    }


def run_fast_backtest(df_features: pd.DataFrame, start_date: str, end_date: str) -> dict:
    """
    年度範囲でのバックテストを実行

    Returns:
        {cond_id: {'bet', 'return', 'hits', 'races', 'roi'}, ...}
    """
    df = df_features[
        (df_features['race_date'] >= start_date) &
        (df_features['race_date'] <= end_date)
    ].copy()

    if df.empty:
        return {}

    df['month'] = df['race_date'].str[5:7].astype(int)

    # 1号艇（pit_number=1）のランクをレースごとに取得し df_top1 に付与
    # 標準バックテスト（backtest_helpers.py L183）: c1_rank は pit_number=1 の entries で判定
    pit1_ranks = (
        df[df['pit_number'] == 1][['race_id', 'racer_rank']]
        .rename(columns={'racer_rank': 'pit1_racer_rank'})
    )

    df_top1 = df[df['rank_prediction'] == 1].copy()
    df_top1 = df_top1.merge(pit1_ranks, on='race_id', how='left')
    df_top1['pit1_racer_rank'] = df_top1['pit1_racer_rank'].fillna('B2')

    # 全条件の race_ids を先に収集してから一括取得
    assigned = {}   # {race_id: cond_id}  重複除外用
    cond_race_ids = {}  # {cond_id: [race_id, ...]}

    sorted_conds = sorted(
        STANDARD_BET_CONDITIONS,
        key=lambda x: (x.get('priority', 999), STANDARD_BET_CONDITIONS.index(x))
    )

    for cond in sorted_conds:
        filtered = filter_by_condition(df_top1, df, cond)
        new_ids = []
        for rid in filtered['race_id'].tolist():
            if rid not in assigned:
                assigned[rid] = cond['id']
                new_ids.append(rid)
        cond_race_ids[cond['id']] = new_ids

    # trifecta_odds と results を一括取得
    all_race_ids = list(assigned.keys())
    df_odds, df_results = load_odds_and_results(all_race_ids)

    # 条件ごとの収支計算
    results = {}
    for cond in STANDARD_BET_CONDITIONS:
        cid = cond['id']
        rids = cond_race_ids.get(cid, [])
        if not rids:
            results[cid] = {'bet': 0, 'return': 0, 'hits': 0, 'races': 0, 'roi': 0.0}
            continue

        payoff = compute_payoff(rids, df, df_odds, df_results, cond)
        roi = (payoff['total_return'] / payoff['total_bet'] * 100.0
               if payoff['total_bet'] > 0 else 0.0)
        results[cid] = {
            'bet': payoff['total_bet'],
            'return': payoff['total_return'],
            'hits': payoff['hits'],
            'races': payoff['races'],
            'roi': roi,
        }

    return results


def save_json(yearly_results: dict, param_desc: str, path: str):
    """バックテスト結果をJSONに保存"""
    data = {
        'saved_at': datetime.now().isoformat(),
        'param_desc': param_desc,
        'yearly': {}
    }
    for year, yr in yearly_results.items():
        bet = sum(v['bet'] for v in yr.values())
        ret = sum(v['return'] for v in yr.values())
        hits = sum(v['hits'] for v in yr.values())
        races = sum(v['races'] for v in yr.values())
        roi = ret / bet * 100 if bet > 0 else 0.0
        data['yearly'][str(year)] = {
            'bet': bet, 'return': ret, 'hits': hits,
            'races': races, 'roi': round(roi, 2), 'profit': ret - bet,
            'conditions': {cid: v for cid, v in yr.items()}
        }
    # 合計
    total_bet = sum(v['bet'] for yr in yearly_results.values() for v in yr.values())
    total_ret = sum(v['return'] for yr in yearly_results.values() for v in yr.values())
    total_hits = sum(v['hits'] for yr in yearly_results.values() for v in yr.values())
    total_races = sum(v['races'] for yr in yearly_results.values() for v in yr.values())
    total_roi = total_ret / total_bet * 100 if total_bet > 0 else 0.0
    black_years = sum(1 for yr in data['yearly'].values() if yr['profit'] >= 0)
    data['total'] = {
        'bet': total_bet, 'return': total_ret, 'hits': total_hits,
        'races': total_races, 'roi': round(total_roi, 2),
        'profit': total_ret - total_bet, 'black_years': black_years
    }
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nJSON保存完了: {path}")


def compare_json(yearly_results: dict, compare_path: str, param_desc: str):
    """保存済みJSONと現在の結果を比較表示"""
    with open(compare_path, 'r', encoding='utf-8') as f:
        base = json.load(f)

    print(f"\n{'='*70}")
    print(f"ベースライン比較 [{base['param_desc']} → {param_desc}]")
    print(f"{'='*70}")

    print(f"\n【年度別比較】")
    print(f"{'年度':^6} {'旧件数':>7} {'新件数':>7} {'旧ROI':>8} {'新ROI':>8} {'ROI差':>7} {'旧収支':>10} {'新収支':>10} {'収支差':>10}")
    print('-' * 80)

    total_old_bet = total_old_ret = total_new_bet = total_new_ret = 0
    for year in sorted(yearly_results.keys()):
        yr_new = yearly_results[year]
        new_bet = sum(v['bet'] for v in yr_new.values())
        new_ret = sum(v['return'] for v in yr_new.values())
        new_races = sum(v['races'] for v in yr_new.values())
        new_roi = new_ret / new_bet * 100 if new_bet > 0 else 0.0
        new_profit = new_ret - new_bet

        yr_base = base['yearly'].get(str(year), {})
        old_races = yr_base.get('races', 0)
        old_roi = yr_base.get('roi', 0.0)
        old_profit = yr_base.get('profit', 0)

        roi_diff = new_roi - old_roi
        profit_diff = new_profit - old_profit
        roi_sign = '+' if roi_diff >= 0 else ''
        p_sign = '+' if profit_diff >= 0 else ''

        print(f"{year:^6} {old_races:>7,} {new_races:>7,} {old_roi:>7.1f}% {new_roi:>7.1f}% {roi_sign}{roi_diff:>5.1f}pt {old_profit:>+10,} {new_profit:>+10,} {p_sign}{profit_diff:>+9,}")
        total_old_bet += yr_base.get('bet', 0)
        total_old_ret += yr_base.get('return', 0)
        total_new_bet += new_bet
        total_new_ret += new_ret

    print('-' * 80)
    old_total_roi = total_old_ret / total_old_bet * 100 if total_old_bet > 0 else 0.0
    new_total_roi = total_new_ret / total_new_bet * 100 if total_new_bet > 0 else 0.0
    old_total_profit = total_old_ret - total_old_bet
    new_total_profit = total_new_ret - total_new_bet
    roi_diff = new_total_roi - old_total_roi
    profit_diff = new_total_profit - old_total_profit
    old_races_total = base['total'].get('races', 0)
    new_races_total = sum(v['races'] for yr in yearly_results.values() for v in yr.values())
    print(f"{'合計':^6} {old_races_total:>7,} {new_races_total:>7,} {old_total_roi:>7.1f}% {new_total_roi:>7.1f}% {'+' if roi_diff>=0 else ''}{roi_diff:>5.1f}pt {old_total_profit:>+10,} {new_total_profit:>+10,} {'+' if profit_diff>=0 else ''}{profit_diff:>+9,}")
    print(f"\n{'='*70}")


def print_report(yearly_results: dict, param_desc: str):
    """結果をレポート出力"""
    print(f"\n{'='*70}")
    print(f"高速バックテスト結果 [{param_desc}]")
    print(f"{'='*70}")

    total_bet = 0
    total_ret = 0
    total_hits = 0
    total_races = 0
    black_years = 0

    print(f"\n【年度別サマリー】")
    print(f"{'年度':^6} {'件数':>6} {'ROI':>8} {'収支':>10} {'判定':^4}")
    print('-' * 45)

    for year in sorted(yearly_results.keys()):
        yr = yearly_results[year]
        bet = sum(v['bet'] for v in yr.values())
        ret = sum(v['return'] for v in yr.values())
        hits = sum(v['hits'] for v in yr.values())
        races = sum(v['races'] for v in yr.values())
        roi = ret / bet * 100 if bet > 0 else 0.0
        profit = ret - bet
        mark = '○' if profit >= 0 else '×'

        if profit >= 0:
            black_years += 1
        total_bet   += bet
        total_ret   += ret
        total_hits  += hits
        total_races += races

        profit_str = f"+{profit:,}" if profit >= 0 else f"{profit:,}"
        print(f"{year:^6} {races:>6,} {roi:>7.1f}% {profit_str:>10} {mark:^4}")

    print('-' * 45)
    total_roi = total_ret / total_bet * 100 if total_bet > 0 else 0.0
    total_profit = total_ret - total_bet
    profit_str = f"+{total_profit:,}" if total_profit >= 0 else f"{total_profit:,}"
    print(f"{'合計':^6} {total_races:>6,} {total_roi:>7.1f}% {profit_str:>10} {black_years}/6年黒字")

    print(f"\n【条件別成績（全期間）】")
    print(f"{'条件':^20} {'件数':>6} {'ROI':>8} {'収支':>10}")
    print('-' * 52)

    cond_totals = {}
    for year, yr in yearly_results.items():
        for cid, v in yr.items():
            if cid not in cond_totals:
                cond_totals[cid] = {'bet': 0, 'return': 0, 'races': 0}
            cond_totals[cid]['bet'] += v['bet']
            cond_totals[cid]['return'] += v['return']
            cond_totals[cid]['races'] += v['races']

    for cond in STANDARD_BET_CONDITIONS:
        cid = cond['id']
        t = cond_totals.get(cid, {'bet': 0, 'return': 0, 'races': 0})
        roi = t['return'] / t['bet'] * 100 if t['bet'] > 0 else 0.0
        profit = t['return'] - t['bet']
        profit_str = f"+{profit:,}" if profit >= 0 else f"{profit:,}"
        print(f"{cid[:20]:^20} {t['races']:>6,} {roi:>7.1f}% {profit_str:>10}")

    print(f"\n{'='*70}")


def main():
    parser = argparse.ArgumentParser(
        description='高速バックテスト（prediction_features ベース）'
    )

    # 期間指定
    parser.add_argument('--full', action='store_true', help='6年間（2020-2025）')
    parser.add_argument('--year', type=int, help='特定年度（例: 2024）')
    parser.add_argument('--start', type=str, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end',   type=str, help='終了日（YYYY-MM-DD）')

    # confidence 閾値変更
    parser.add_argument('--conf-a-gap',  type=float, default=15, help='A の score_gap 閾値（デフォルト: 15）')
    parser.add_argument('--conf-a-min',  type=float, default=70, help='A の min_score（デフォルト: 70）')
    parser.add_argument('--conf-b-gap',  type=float, default=10, help='B の score_gap 閾値（デフォルト: 10）')
    parser.add_argument('--conf-b-min',  type=float, default=60, help='B の min_score（デフォルト: 60）')
    parser.add_argument('--conf-c-gap',  type=float, default=5,  help='C の score_gap 閾値（デフォルト: 5）')
    parser.add_argument('--conf-c-p1',   type=float, default=55, help='C の pit1_min_score（デフォルト: 55）')
    parser.add_argument('--conf-d-gap',  type=float, default=2,  help='D の score_gap 閾値（デフォルト: 2）')

    # scoring_weights 変更
    parser.add_argument('--racer-weight', type=float, help='racer_weight 上書き（デフォルト: 35）')
    parser.add_argument('--motor-weight', type=float, help='motor_weight 上書き（デフォルト: 20）')
    parser.add_argument('--course-weight', type=float, help='course_weight 上書き（デフォルト: 35）')
    parser.add_argument('--weights-yaml',  type=str,   help='別の scoring_weights.yaml を指定')

    # ベースライン保存・比較
    parser.add_argument('--save-json', type=str, help='結果をJSONに保存（例: data/baselines/v2.44.0.json）')
    parser.add_argument('--compare-json', type=str, help='保存済みJSONと比較（例: data/baselines/v2.44.0.json）')

    args = parser.parse_args()

    # 期間決定
    if args.full:
        start_date = '2020-01-01'
        end_date   = '2025-12-31'
        years = list(range(2020, 2026))
    elif args.year:
        start_date = f'{args.year}-01-01'
        end_date   = f'{args.year}-12-31'
        years = [args.year]
    elif args.start:
        start_date = args.start
        end_date   = args.end or '2099-12-31'
        y_s = int(start_date[:4])
        y_e = int(end_date[:4])
        years = list(range(y_s, y_e + 1))
    else:
        parser.error('--full, --year, または --start を指定してください')

    # confidence 閾値
    thresholds = {
        'A': {'gap': args.conf_a_gap, 'min_score': args.conf_a_min},
        'B': {'gap': args.conf_b_gap, 'min_score': args.conf_b_min},
        'C': {'gap': args.conf_c_gap, 'pit1_min_score': args.conf_c_p1},
        'D': {'gap': args.conf_d_gap},
    }

    # scoring_weights
    weights = load_scoring_weights(args.weights_yaml)
    if args.racer_weight is not None:
        weights.setdefault('dynamic_weights', {}).setdefault('base', {})['racer_weight'] = args.racer_weight
    if args.motor_weight is not None:
        weights.setdefault('dynamic_weights', {}).setdefault('base', {})['motor_weight'] = args.motor_weight

    # 変更内容の説明
    changes = []
    if args.conf_a_gap != 15:
        changes.append(f"A-gap={args.conf_a_gap}")
    if args.conf_b_gap != 10:
        changes.append(f"B-gap={args.conf_b_gap}")
    if args.racer_weight is not None:
        changes.append(f"racer_w={args.racer_weight}")
    if args.motor_weight is not None:
        changes.append(f"motor_w={args.motor_weight}")
    param_desc = ', '.join(changes) if changes else 'デフォルト設定'

    # 再計算モードを決定
    has_weight_change = (args.racer_weight is not None or args.motor_weight is not None
                         or args.course_weight is not None or args.weights_yaml is not None)
    mode = 'full' if has_weight_change else 'confidence_only'

    print(f"=== 高速バックテスト [{param_desc}] ===")
    print(f"期間: {start_date} 〜 {end_date}")
    print(f"モード: {'スコア再計算' if mode == 'full' else 'confidence閾値のみ変更'}（{mode}）")

    # prediction_features を一括ロード
    print(f"\nprediction_features をロード中...", end='', flush=True)
    t0 = datetime.now()
    df_features = load_features(start_date, end_date)
    print(f" {len(df_features):,}行 ({(datetime.now()-t0).total_seconds():.1f}s)")

    if df_features.empty:
        print("ERROR: prediction_features が空です。generate_features.py を先に実行してください。")
        sys.exit(1)

    # スコア・信頼度を再計算
    # use_original_confidence: 閾値変更なし（confidence_only）の場合は original_confidence をそのまま使用
    # → compound_buff 込み total_score_final からの再計算は信頼度が高くなりすぎるため
    has_threshold_change = (
        args.conf_a_gap != 15 or args.conf_a_min != 70
        or args.conf_b_gap != 10 or args.conf_b_min != 60
        or args.conf_c_gap != 5  or args.conf_c_p1 != 55
        or args.conf_d_gap != 2
    )
    use_original_confidence = (mode == 'confidence_only') and not has_threshold_change

    if use_original_confidence:
        print(f"信頼度: original_confidence を使用（標準バックテストと同一）")
    elif mode == 'confidence_only':
        print(f"信頼度: 閾値変更あり → total_score_final から再計算（近似）")

    print(f"スコア・信頼度を再計算中...", end='', flush=True)
    t0 = datetime.now()
    df_features = recalculate_scores(
        df_features, weights, thresholds, mode=mode,
        use_original_confidence=use_original_confidence
    )
    print(f" ({(datetime.now()-t0).total_seconds():.1f}s)")

    # 年度別バックテスト
    yearly_results = {}
    for year in years:
        print(f"{year}年 バックテスト中...", end='', flush=True)
        t0 = datetime.now()
        results = run_fast_backtest(df_features, f'{year}-01-01', f'{year}-12-31')
        yearly_results[year] = results
        total_races = sum(v['races'] for v in results.values())
        print(f" {total_races}件 ({(datetime.now()-t0).total_seconds():.1f}s)")

    # レポート出力
    print_report(yearly_results, param_desc)

    # JSON保存
    if args.save_json:
        save_json(yearly_results, param_desc, args.save_json)

    # ベースライン比較
    if args.compare_json:
        compare_json(yearly_results, args.compare_json, param_desc)

    print(f"完了")


if __name__ == '__main__':
    main()
