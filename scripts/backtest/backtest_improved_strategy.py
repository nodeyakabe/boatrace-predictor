# -*- coding: utf-8 -*-
"""
改善版パターンH戦略のバックテスト
風向き・会場補正を適用した予測精度検証

使用方法:
    python scripts/backtest_improved_strategy.py
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sys

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.venue_wind_adjustments import (
    get_wind_coefficient,
    get_venue_coefficient,
    should_exclude_race,
    BASELINE_WIN_RATES
)
from src.betting.venue_evaluator import VenueEvaluator, get_venue_strategy

# データベースパス
DB_PATH = ROOT_DIR / "data" / "boatrace.db"


def get_connection():
    return sqlite3.connect(str(DB_PATH))


def load_race_data(start_date: str = '2024-01-01', end_date: str = '2025-12-31'):
    """
    レースデータを読み込み

    Args:
        start_date: 開始日
        end_date: 終了日

    Returns:
        DataFrame: レースデータ
    """
    conn = get_connection()

    query = """
    SELECT
        r.id as race_id,
        r.venue_code,
        r.race_date,
        r.race_number,
        rc.wind_speed,
        rc.wind_direction,
        rc.wave_height,
        rd.pit_number,
        e.racer_number,
        e.win_rate as racer_win_rate,
        res.rank as result_rank,
        res.kimarite
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    JOIN race_details rd ON r.id = rd.race_id
    JOIN entries e ON r.id = e.race_id AND rd.pit_number = e.pit_number
    JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
    WHERE r.race_date >= ? AND r.race_date <= ?
    AND res.is_invalid = 0
    AND rc.wind_speed IS NOT NULL
    ORDER BY r.race_date, r.venue_code, r.race_number, rd.pit_number
    """

    df = pd.read_sql_query(query, conn, params=[start_date, end_date])
    conn.close()

    print(f"読み込みデータ: {len(df)} 行, {df['race_id'].nunique()} レース")

    return df


def calculate_base_score(row: pd.Series) -> float:
    """
    ベーススコアを計算（簡易版）

    実際のパターンHスコアリングを簡略化したもの
    """
    pit_number = row['pit_number']
    racer_win_rate = row.get('racer_win_rate', 5.0) or 5.0

    # コース別基本スコア
    course_scores = {1: 10.0, 2: 6.0, 3: 5.0, 4: 4.0, 5: 2.5, 6: 1.5}
    base = course_scores.get(pit_number, 3.0)

    # 選手勝率による加点
    racer_bonus = (racer_win_rate - 5.0) * 0.5  # 平均5点を基準

    return base + racer_bonus


def apply_wind_venue_adjustment(
    base_score: float,
    venue_code: str,
    wind_speed: float,
    pit_number: int
) -> float:
    """
    風速・会場補正を適用
    """
    wind_coef = get_wind_coefficient(wind_speed, pit_number)
    venue_coef = get_venue_coefficient(venue_code, pit_number)

    # 補正を適用（0.7-1.3の範囲に制限）
    combined_coef = wind_coef * venue_coef
    combined_coef = max(0.7, min(1.3, combined_coef))

    return base_score * combined_coef


def run_backtest(df: pd.DataFrame, use_adjustments: bool = False):
    """
    バックテストを実行

    Args:
        df: レースデータ
        use_adjustments: 風速・会場補正を適用するか

    Returns:
        結果の辞書
    """
    evaluator = VenueEvaluator()

    results = {
        'total_races': 0,
        'correct_1st': 0,
        'correct_top2': 0,
        'correct_top3': 0,
        'excluded_races': 0,
        'predictions': [],
    }

    # レースIDでグループ化
    race_groups = df.groupby('race_id')

    for race_id, race_df in race_groups:
        results['total_races'] += 1

        venue_code = race_df['venue_code'].iloc[0]
        wind_speed = race_df['wind_speed'].iloc[0]
        wave_height = race_df['wave_height'].iloc[0]

        # 除外判定
        if use_adjustments:
            exclude, reason = should_exclude_race(venue_code, wind_speed, 'C')
            if exclude:
                results['excluded_races'] += 1
                continue

        # 各艇のスコアを計算
        scores = []
        for _, row in race_df.iterrows():
            base_score = calculate_base_score(row)

            if use_adjustments:
                adjusted_score = apply_wind_venue_adjustment(
                    base_score,
                    venue_code,
                    wind_speed,
                    row['pit_number']
                )
            else:
                adjusted_score = base_score

            scores.append({
                'pit_number': row['pit_number'],
                'score': adjusted_score,
                'result_rank': row['result_rank'],
            })

        # スコア順でソート
        scores.sort(key=lambda x: x['score'], reverse=True)

        # 予測1着
        predicted_1st = scores[0]['pit_number'] if scores else None

        # 実際の1着
        actual_1st = None
        for s in scores:
            if s['result_rank'] == '1':
                actual_1st = s['pit_number']
                break

        # 結果を記録
        if predicted_1st and actual_1st:
            predicted_ranks = [s['pit_number'] for s in scores]

            if predicted_1st == actual_1st:
                results['correct_1st'] += 1
            if actual_1st in predicted_ranks[:2]:
                results['correct_top2'] += 1
            if actual_1st in predicted_ranks[:3]:
                results['correct_top3'] += 1

            results['predictions'].append({
                'race_id': race_id,
                'venue_code': venue_code,
                'wind_speed': wind_speed,
                'predicted_1st': predicted_1st,
                'actual_1st': actual_1st,
                'correct': predicted_1st == actual_1st,
            })

    return results


def analyze_results(results: dict, label: str):
    """
    結果を分析・表示
    """
    total = results['total_races'] - results['excluded_races']

    if total == 0:
        print(f"\n{label}: 有効レースなし")
        return

    accuracy_1st = results['correct_1st'] / total * 100
    accuracy_top2 = results['correct_top2'] / total * 100
    accuracy_top3 = results['correct_top3'] / total * 100

    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"総レース数: {results['total_races']}")
    print(f"除外レース: {results['excluded_races']}")
    print(f"有効レース: {total}")
    print(f"\n的中率:")
    print(f"  1着予測的中: {results['correct_1st']} / {total} = {accuracy_1st:.2f}%")
    print(f"  TOP2的中: {results['correct_top2']} / {total} = {accuracy_top2:.2f}%")
    print(f"  TOP3的中: {results['correct_top3']} / {total} = {accuracy_top3:.2f}%")


def compare_by_conditions(df: pd.DataFrame, results_with_adj: dict, results_without: dict):
    """
    条件別の比較分析
    """
    print(f"\n{'='*60}")
    print("条件別分析")
    print(f"{'='*60}")

    predictions_with = pd.DataFrame(results_with_adj['predictions'])
    predictions_without = pd.DataFrame(results_without['predictions'])

    if len(predictions_with) == 0 or len(predictions_without) == 0:
        print("十分なデータがありません")
        return

    # 風速別比較
    print("\n【風速別 1着的中率】")
    print("風速レンジ | 補正なし | 補正あり | 改善")
    print("-" * 50)

    for wind_range, (min_speed, max_speed) in [
        ('0-2m', (0, 2)),
        ('2-4m', (2, 4)),
        ('4-6m', (4, 6)),
        ('6m+', (6, 100))
    ]:
        pred_without = predictions_without[
            (predictions_without['wind_speed'] >= min_speed) &
            (predictions_without['wind_speed'] < max_speed)
        ]
        pred_with = predictions_with[
            (predictions_with['wind_speed'] >= min_speed) &
            (predictions_with['wind_speed'] < max_speed)
        ]

        if len(pred_without) > 0 and len(pred_with) > 0:
            acc_without = pred_without['correct'].mean() * 100
            acc_with = pred_with['correct'].mean() * 100
            improvement = acc_with - acc_without
            print(f"{wind_range:10s} | {acc_without:6.2f}% | {acc_with:6.2f}% | {improvement:+.2f}%")

    # 会場タイプ別比較
    print("\n【会場タイプ別 1着的中率】")

    # イン強会場
    in_strong = ['18', '24', '19', '17', '13', '12', '07', '16', '08', '09']
    # イン弱会場
    in_weak = ['02', '04', '14', '03', '01']

    for label, venues in [('イン強会場', in_strong), ('イン弱会場', in_weak)]:
        pred_without = predictions_without[predictions_without['venue_code'].isin(venues)]
        pred_with = predictions_with[predictions_with['venue_code'].isin(venues)]

        if len(pred_without) > 0 and len(pred_with) > 0:
            acc_without = pred_without['correct'].mean() * 100
            acc_with = pred_with['correct'].mean() * 100
            improvement = acc_with - acc_without
            print(f"{label}: 補正なし {acc_without:.2f}% → 補正あり {acc_with:.2f}% ({improvement:+.2f}%)")


def main():
    """メイン処理"""
    print("=" * 60)
    print("改善版パターンH戦略 バックテスト")
    print("対象期間: 2024-01-01 ~ 2025-12-31")
    print("=" * 60)

    # データ読み込み
    print("\nデータ読み込み中...")
    df = load_race_data()

    # 補正なしでバックテスト
    print("\n補正なしでバックテスト実行中...")
    results_without = run_backtest(df, use_adjustments=False)
    analyze_results(results_without, "【補正なし】")

    # 補正ありでバックテスト
    print("\n補正ありでバックテスト実行中...")
    results_with = run_backtest(df, use_adjustments=True)
    analyze_results(results_with, "【風速・会場補正あり】")

    # 条件別比較
    compare_by_conditions(df, results_with, results_without)

    # 改善効果サマリー
    print(f"\n{'='*60}")
    print("改善効果サマリー")
    print(f"{'='*60}")

    total_without = results_without['total_races'] - results_without['excluded_races']
    total_with = results_with['total_races'] - results_with['excluded_races']

    if total_without > 0 and total_with > 0:
        acc_without = results_without['correct_1st'] / total_without * 100
        acc_with = results_with['correct_1st'] / total_with * 100
        improvement = acc_with - acc_without

        print(f"1着予測的中率:")
        print(f"  補正なし: {acc_without:.2f}%")
        print(f"  補正あり: {acc_with:.2f}%")
        print(f"  改善: {improvement:+.2f}pt")

        # 除外による効果
        excluded_pct = results_with['excluded_races'] / results_with['total_races'] * 100
        print(f"\n除外レース: {results_with['excluded_races']} ({excluded_pct:.1f}%)")
        print("  → 難しいレースを除外することで精度向上")


if __name__ == "__main__":
    main()
