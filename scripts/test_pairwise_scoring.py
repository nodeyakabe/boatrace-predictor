#!/usr/bin/env python
"""
ペアワイズ順位予測モデルのバックテストスクリプト

使用方法:
    python scripts/test_pairwise_scoring.py

概要:
    - 学習済みペアワイズモデルを使用してバックテスト
    - baseline（絶対スコアのみ）と比較
    - ROI、1着・2着・3着的中率、三連単的中率を評価
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import argparse
import sqlite3
from datetime import datetime
from collections import defaultdict
import pandas as pd
import numpy as np

from src.ml.pairwise_rank_model import (
    PairwiseRankModel,
    PairwiseScoreIntegrator
)
from src.analysis.race_predictor import RacePredictor


def setup_logging(verbose: bool = False):
    """ロギング設定"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def get_test_races(
    db_path: str,
    start_date: str,
    end_date: str
) -> pd.DataFrame:
    """
    テスト対象レースを取得

    Args:
        db_path: データベースパス
        start_date: 開始日
        end_date: 終了日

    Returns:
        レース情報DataFrame
    """
    conn = sqlite3.connect(db_path)

    query = """
    SELECT DISTINCT
        r.id AS race_id,
        r.venue_code,
        r.race_date,
        r.race_number,
        r.race_grade
    FROM races r
    INNER JOIN results res ON r.id = res.race_id
    INNER JOIN trifecta_odds o ON r.id = o.race_id
    WHERE r.race_date BETWEEN ? AND ?
        AND res.is_invalid = 0
    GROUP BY r.id
    HAVING COUNT(DISTINCT res.pit_number) = 6
    ORDER BY r.race_date, r.venue_code, r.race_number
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    return df


def get_race_results(db_path: str, race_id: int) -> dict:
    """
    レース結果を取得

    Args:
        db_path: データベースパス
        race_id: レースID

    Returns:
        {1着艇, 2着艇, 3着艇, 払戻金}
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 着順
    cursor.execute("""
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ? AND is_invalid = 0
    """, (race_id,))

    results = cursor.fetchall()
    rank_to_pit = {}
    for pit, rank in results:
        try:
            rank_int = int(rank)
            if 1 <= rank_int <= 6:
                rank_to_pit[rank_int] = pit
        except (ValueError, TypeError):
            continue

    # 三連単払戻金
    cursor.execute("""
        SELECT amount
        FROM payouts
        WHERE race_id = ? AND bet_type = 'trifecta'
    """, (race_id,))

    payout_row = cursor.fetchone()
    trifecta_payout = payout_row[0] if payout_row else 0

    cursor.close()
    conn.close()

    return {
        'first': rank_to_pit.get(1),
        'second': rank_to_pit.get(2),
        'third': rank_to_pit.get(3),
        'trifecta_payout': trifecta_payout
    }


def get_race_features(db_path: str, race_id: int) -> pd.DataFrame:
    """
    レース特徴量を取得

    Args:
        db_path: データベースパス
        race_id: レースID

    Returns:
        特徴量DataFrame
    """
    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        e.pit_number,
        e.racer_number,
        e.racer_rank,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.motor_number,
        e.motor_second_rate,
        e.motor_third_rate,
        e.boat_second_rate,
        e.avg_st,
        e.f_count,
        e.l_count,
        rd.exhibition_time,
        rd.st_time,
        rd.tilt_angle
    FROM entries e
    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE e.race_id = ?
    ORDER BY e.pit_number
    """

    df = pd.read_sql_query(query, conn, params=(race_id,))
    conn.close()

    return df


def run_backtest(
    db_path: str,
    test_races: pd.DataFrame,
    pairwise_model: PairwiseRankModel,
    integration_weights: list,
    bet_unit: int = 100,
    logger: logging.Logger = None
):
    """
    バックテストを実行

    Args:
        db_path: データベースパス
        test_races: テストレース一覧
        pairwise_model: ペアワイズモデル
        integration_weights: テストする統合重みのリスト
        bet_unit: 1点あたりの賭け金
        logger: ロガー

    Returns:
        バックテスト結果
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    predictor = RacePredictor(db_path)

    # 各統合重みについて統計を収集
    all_stats = {}
    for weight in integration_weights:
        all_stats[weight] = {
            'total_races': 0,
            'total_bets': 0,
            'total_investment': 0,
            'total_return': 0,
            'first_correct': 0,
            'second_correct': 0,
            'second_correct_given_first': 0,
            'third_correct': 0,
            'third_correct_given_first_second': 0,
            'trifecta_correct': 0,
        }

    # baseline統計
    baseline_stats = dict(all_stats[integration_weights[0]])

    detailed_results = []

    logger.info(f"バックテスト開始: {len(test_races)}レース")
    logger.info(f"テスト統合重み: {integration_weights}")

    for idx, race_row in test_races.iterrows():
        race_id = race_row['race_id']

        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if len(predictions) != 6:
                continue

            # 実際の結果
            actual = get_race_results(db_path, race_id)

            if actual['first'] is None or actual['second'] is None:
                continue

            # レース特徴量取得
            race_features = get_race_features(db_path, race_id)

            if len(race_features) != 6:
                continue

            # 特徴量にtotal_scoreを追加
            for pred in predictions:
                pit = pred['pit_number']
                idx_match = race_features[race_features['pit_number'] == pit].index
                if len(idx_match) > 0:
                    race_features.loc[idx_match[0], 'total_score'] = pred['total_score']

            # baseline予測（ペアワイズなし）
            pred_first_baseline = predictions[0]['pit_number']
            pred_second_baseline = predictions[1]['pit_number']
            pred_third_baseline = predictions[2]['pit_number']

            baseline_stats['total_races'] += 1

            first_correct_baseline = (pred_first_baseline == actual['first'])
            second_correct_baseline = (pred_second_baseline == actual['second'])
            third_correct_baseline = (pred_third_baseline == actual['third'])

            if first_correct_baseline:
                baseline_stats['first_correct'] += 1
                if second_correct_baseline:
                    baseline_stats['second_correct_given_first'] += 1
                    if third_correct_baseline:
                        baseline_stats['third_correct_given_first_second'] += 1
                        baseline_stats['trifecta_correct'] += 1

            if second_correct_baseline:
                baseline_stats['second_correct'] += 1

            if third_correct_baseline:
                baseline_stats['third_correct'] += 1

            # 信頼度判定
            top_confidence = predictions[0].get('confidence', 'E')

            # 購入判定（信頼度B以上）
            if top_confidence in ['A', 'B']:
                baseline_stats['total_bets'] += 1
                baseline_stats['total_investment'] += bet_unit
                if first_correct_baseline and second_correct_baseline and third_correct_baseline:
                    baseline_stats['total_return'] += actual['trifecta_payout']

            # 各統合重みでテスト
            for weight in integration_weights:
                stats = all_stats[weight]
                stats['total_races'] += 1

                if pairwise_model.model is not None:
                    # ペアワイズスコアを統合
                    integrator = PairwiseScoreIntegrator(
                        pairwise_model=pairwise_model,
                        integration_weight=weight
                    )

                    # 予測をコピー
                    predictions_copy = [dict(p) for p in predictions]
                    integrated_predictions = integrator.integrate_predictions(
                        predictions_copy, race_features.copy()
                    )

                    pred_first = integrated_predictions[0]['pit_number']
                    pred_second = integrated_predictions[1]['pit_number']
                    pred_third = integrated_predictions[2]['pit_number']
                else:
                    pred_first = pred_first_baseline
                    pred_second = pred_second_baseline
                    pred_third = pred_third_baseline

                first_correct = (pred_first == actual['first'])
                second_correct = (pred_second == actual['second'])
                third_correct = (pred_third == actual['third'])

                if first_correct:
                    stats['first_correct'] += 1
                    if second_correct:
                        stats['second_correct_given_first'] += 1
                        if third_correct:
                            stats['third_correct_given_first_second'] += 1
                            stats['trifecta_correct'] += 1

                if second_correct:
                    stats['second_correct'] += 1

                if third_correct:
                    stats['third_correct'] += 1

                # 購入判定
                if top_confidence in ['A', 'B']:
                    stats['total_bets'] += 1
                    stats['total_investment'] += bet_unit
                    if first_correct and second_correct and third_correct:
                        stats['total_return'] += actual['trifecta_payout']

            # 詳細結果を記録
            detailed_results.append({
                'race_id': race_id,
                'race_date': race_row['race_date'],
                'venue_code': race_row['venue_code'],
                'pred_first_baseline': pred_first_baseline,
                'pred_second_baseline': pred_second_baseline,
                'pred_third_baseline': pred_third_baseline,
                'actual_first': actual['first'],
                'actual_second': actual['second'],
                'actual_third': actual['third'],
                'first_correct_baseline': first_correct_baseline,
                'second_correct_baseline': second_correct_baseline,
                'third_correct_baseline': third_correct_baseline,
                'trifecta_payout': actual['trifecta_payout'],
                'confidence': top_confidence
            })

        except Exception as e:
            logger.debug(f"レース {race_id} 処理エラー: {e}")
            continue

        # 進捗表示
        if (idx + 1) % 100 == 0:
            logger.info(f"  進捗: {idx + 1}/{len(test_races)}")

    return baseline_stats, all_stats, detailed_results


def print_results(
    baseline_stats: dict,
    all_stats: dict,
    detailed_results: list,
    logger: logging.Logger
):
    """
    結果を出力

    Args:
        baseline_stats: baselineの統計情報
        all_stats: 各統合重みの統計情報
        detailed_results: 詳細結果
        logger: ロガー
    """
    logger.info("\n" + "=" * 70)
    logger.info("バックテスト結果")
    logger.info("=" * 70)

    total = baseline_stats['total_races']
    if total == 0:
        logger.warning("有効なレースがありませんでした")
        return

    # Baseline結果
    logger.info("\n=== Baseline（ペアワイズなし） ===")
    logger.info(f"総レース数: {total:,}")
    logger.info(f"1着的中率: {baseline_stats['first_correct']}/{total} = {baseline_stats['first_correct']/total*100:.2f}%")
    logger.info(f"2着的中率: {baseline_stats['second_correct']}/{total} = {baseline_stats['second_correct']/total*100:.2f}%")
    logger.info(f"2着的中率(1着的中時): {baseline_stats['second_correct_given_first']}/{max(1, baseline_stats['first_correct'])} = "
                f"{baseline_stats['second_correct_given_first']/max(1, baseline_stats['first_correct'])*100:.2f}%")
    logger.info(f"3着的中率: {baseline_stats['third_correct']}/{total} = {baseline_stats['third_correct']/total*100:.2f}%")
    logger.info(f"3着的中率(1-2着的中時): {baseline_stats['third_correct_given_first_second']}/{max(1, baseline_stats['second_correct_given_first'])} = "
                f"{baseline_stats['third_correct_given_first_second']/max(1, baseline_stats['second_correct_given_first'])*100:.2f}%")
    logger.info(f"三連単的中率: {baseline_stats['trifecta_correct']}/{total} = {baseline_stats['trifecta_correct']/total*100:.2f}%")

    if baseline_stats['total_investment'] > 0:
        roi = baseline_stats['total_return'] / baseline_stats['total_investment'] * 100
        logger.info(f"\n購入レース数: {baseline_stats['total_bets']}")
        logger.info(f"ROI: {roi:.1f}%")
        profit = baseline_stats['total_return'] - baseline_stats['total_investment']
        logger.info(f"収支: {profit:+,}円")

    # 各統合重みの結果
    logger.info("\n=== ペアワイズ統合結果（統合重み別） ===")
    logger.info("-" * 70)
    logger.info(f"{'重み':>6} | {'1着':>6} | {'2着':>6} | {'2着|1着':>8} | {'3着':>6} | {'三連単':>6} | {'ROI':>8}")
    logger.info("-" * 70)

    for weight, stats in sorted(all_stats.items()):
        first_rate = stats['first_correct'] / max(1, stats['total_races']) * 100
        second_rate = stats['second_correct'] / max(1, stats['total_races']) * 100
        second_given_first = stats['second_correct_given_first'] / max(1, stats['first_correct']) * 100
        third_rate = stats['third_correct'] / max(1, stats['total_races']) * 100
        trifecta_rate = stats['trifecta_correct'] / max(1, stats['total_races']) * 100

        if stats['total_investment'] > 0:
            roi = stats['total_return'] / stats['total_investment'] * 100
        else:
            roi = 0

        # baselineとの差分
        first_diff = first_rate - baseline_stats['first_correct'] / max(1, total) * 100
        second_diff = second_rate - baseline_stats['second_correct'] / max(1, total) * 100
        trifecta_diff = trifecta_rate - baseline_stats['trifecta_correct'] / max(1, total) * 100

        logger.info(
            f"{weight:>6.2f} | {first_rate:>5.1f}% | {second_rate:>5.1f}% | {second_given_first:>7.1f}% | "
            f"{third_rate:>5.1f}% | {trifecta_rate:>5.1f}% | {roi:>7.1f}%"
        )

    logger.info("-" * 70)

    # 改善幅サマリー
    logger.info("\n=== 改善幅サマリー（vs Baseline） ===")
    best_weight = None
    best_improvement = -float('inf')

    for weight, stats in sorted(all_stats.items()):
        second_rate = stats['second_correct'] / max(1, stats['total_races']) * 100
        baseline_second = baseline_stats['second_correct'] / max(1, total) * 100
        improvement = second_rate - baseline_second

        if improvement > best_improvement:
            best_improvement = improvement
            best_weight = weight

        third_rate = stats['third_correct'] / max(1, stats['total_races']) * 100
        baseline_third = baseline_stats['third_correct'] / max(1, total) * 100
        third_improvement = third_rate - baseline_third

        logger.info(f"  統合重み={weight:.2f}: 2着{improvement:+.2f}pt, 3着{third_improvement:+.2f}pt")

    if best_weight is not None:
        logger.info(f"\n最適な統合重み: {best_weight:.2f} (2着改善幅: {best_improvement:+.2f}pt)")


def main():
    parser = argparse.ArgumentParser(
        description='ペアワイズ順位予測モデルのバックテスト'
    )
    parser.add_argument(
        '--db-path', type=str,
        default='data/boatrace.db',
        help='データベースパス'
    )
    parser.add_argument(
        '--model-dir', type=str,
        default='models',
        help='モデルディレクトリ'
    )
    parser.add_argument(
        '--model-name', type=str,
        default='pairwise_rank',
        help='モデル名'
    )
    parser.add_argument(
        '--start-date', type=str,
        default='2025-11-28',
        help='テスト開始日'
    )
    parser.add_argument(
        '--end-date', type=str,
        default='2025-12-10',
        help='テスト終了日'
    )
    parser.add_argument(
        '--weights', type=str,
        default='0.3,0.4,0.5,0.6,0.7',
        help='テストする統合重みのリスト（カンマ区切り）'
    )
    parser.add_argument(
        '--bet-unit', type=int,
        default=100,
        help='1点あたりの賭け金'
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='詳細ログを出力'
    )
    parser.add_argument(
        '--output', type=str,
        default=None,
        help='結果CSVの出力パス'
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # 統合重みをパース
    integration_weights = [float(w.strip()) for w in args.weights.split(',')]

    logger.info("=" * 60)
    logger.info("ペアワイズ順位予測モデル バックテスト")
    logger.info("=" * 60)
    logger.info(f"テスト期間: {args.start_date} ~ {args.end_date}")
    logger.info(f"統合重みリスト: {integration_weights}")

    # データベース存在確認
    if not os.path.exists(args.db_path):
        logger.error(f"データベースが見つかりません: {args.db_path}")
        sys.exit(1)

    # モデル読み込み
    logger.info("\n=== モデル読み込み ===")
    pairwise_model = PairwiseRankModel(
        model_dir=args.model_dir,
        db_path=args.db_path
    )

    model_path = os.path.join(args.model_dir, f'{args.model_name}.txt')
    if os.path.exists(model_path):
        pairwise_model.load(args.model_name)
        logger.info(f"モデルを読み込みました: {model_path}")
    else:
        logger.warning(f"モデルが見つかりません: {model_path}")
        logger.info("baselineのみでバックテストを実行します")

    # テストレース取得
    logger.info("\n=== テストレース取得 ===")
    test_races = get_test_races(args.db_path, args.start_date, args.end_date)
    logger.info(f"テスト対象レース: {len(test_races)}件")

    if len(test_races) == 0:
        logger.error("テスト対象レースがありません")
        sys.exit(1)

    # バックテスト実行
    baseline_stats, all_stats, detailed_results = run_backtest(
        db_path=args.db_path,
        test_races=test_races,
        pairwise_model=pairwise_model,
        integration_weights=integration_weights,
        bet_unit=args.bet_unit,
        logger=logger
    )

    # 結果出力
    print_results(baseline_stats, all_stats, detailed_results, logger)

    # CSV出力
    if args.output and detailed_results:
        df = pd.DataFrame(detailed_results)
        df.to_csv(args.output, index=False)
        logger.info(f"\n詳細結果をCSVに保存しました: {args.output}")

    logger.info("\n" + "=" * 60)
    logger.info("バックテスト完了")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
