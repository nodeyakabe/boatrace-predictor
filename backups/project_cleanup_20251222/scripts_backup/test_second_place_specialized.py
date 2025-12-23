#!/usr/bin/env python
"""
2着専用スコアリングモデルのバックテストスクリプト

使用方法:
    python scripts/test_second_place_specialized.py

概要:
    - 学習済み2着専用モデルを使用してバックテスト
    - baseline（条件付きモデルのみ）と比較
    - ROI、2着的中率、三連単的中率を評価
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

from src.ml.second_place_specialized_model import (
    SecondPlaceSpecializedScorer,
    SecondPlaceIntegrator
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

    # 着順（rankが着順を表す）
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
    scorer: SecondPlaceSpecializedScorer,
    integration_weight: float,
    bet_unit: int = 100,
    logger: logging.Logger = None
):
    """
    バックテストを実行

    Args:
        db_path: データベースパス
        test_races: テストレース一覧
        scorer: 2着専用スコアラー
        integration_weight: 統合重み
        bet_unit: 1点あたりの賭け金
        logger: ロガー

    Returns:
        バックテスト結果
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    predictor = RacePredictor(db_path)
    integrator = SecondPlaceIntegrator(
        specialized_scorer=scorer,
        integration_weight=integration_weight
    )

    # 統計
    stats = {
        'total_races': 0,
        'total_bets': 0,
        'total_investment': 0,
        'total_return': 0,
        # 的中統計
        'first_correct': 0,
        'second_correct': 0,
        'second_correct_given_first': 0,
        'third_correct': 0,
        'trifecta_correct': 0,
        # 専用モデルの効果
        'improved_second': 0,
        'degraded_second': 0,
    }

    # 詳細結果
    detailed_results = []

    logger.info(f"バックテスト開始: {len(test_races)}レース")
    logger.info(f"統合重み: {integration_weight}")

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

            stats['total_races'] += 1

            # baseline予測（専用モデルなし）
            pred_first = predictions[0]['pit_number']
            pred_second_baseline = predictions[1]['pit_number']
            pred_third_baseline = predictions[2]['pit_number']

            # 専用モデルによる2着予測
            pred_second_specialized = pred_second_baseline
            specialized_probs = {}

            if scorer.model is not None:
                try:
                    specialized_probs = scorer.predict(race_features, pred_first)
                    if specialized_probs:
                        pred_second_specialized = max(
                            specialized_probs, key=specialized_probs.get
                        )
                except Exception as e:
                    logger.debug(f"専用モデル予測エラー: {e}")

            # 統合予測
            # baseline 2着確率（スコアベース）
            baseline_second_probs = {}
            total_score = sum(p['total_score'] for p in predictions[1:])
            if total_score > 0:
                for p in predictions[1:]:
                    baseline_second_probs[p['pit_number']] = p['total_score'] / total_score

            integrated_probs = integrator.integrate_second_place_predictions(
                predictions, baseline_second_probs, race_features
            )

            pred_second_integrated = pred_second_baseline
            if integrated_probs:
                pred_second_integrated = max(integrated_probs, key=integrated_probs.get)

            # 3着予測（簡易版: 1着・2着以外の最高スコア）
            remaining_for_third = [
                p for p in predictions
                if p['pit_number'] not in [pred_first, pred_second_integrated]
            ]
            pred_third_integrated = remaining_for_third[0]['pit_number'] if remaining_for_third else None

            # 結果判定
            first_correct = (pred_first == actual['first'])
            second_correct_baseline = (pred_second_baseline == actual['second'])
            second_correct_specialized = (pred_second_specialized == actual['second'])
            second_correct_integrated = (pred_second_integrated == actual['second'])

            if first_correct:
                stats['first_correct'] += 1
                if second_correct_integrated:
                    stats['second_correct_given_first'] += 1

            if second_correct_integrated:
                stats['second_correct'] += 1

            # 専用モデルの効果
            if second_correct_specialized and not second_correct_baseline:
                stats['improved_second'] += 1
            elif not second_correct_specialized and second_correct_baseline:
                stats['degraded_second'] += 1

            # 三連単的中判定
            trifecta_correct = (
                pred_first == actual['first'] and
                pred_second_integrated == actual['second'] and
                pred_third_integrated == actual['third']
            )

            if trifecta_correct:
                stats['trifecta_correct'] += 1
                stats['total_return'] += actual['trifecta_payout']

            # 購入（信頼度B以上のレースのみ）
            top_confidence = predictions[0].get('confidence', 'E')
            if top_confidence in ['A', 'B']:
                stats['total_bets'] += 1
                stats['total_investment'] += bet_unit

                if trifecta_correct:
                    stats['total_return'] += 0  # 既に加算済み

            # 詳細結果を記録
            detailed_results.append({
                'race_id': race_id,
                'race_date': race_row['race_date'],
                'venue_code': race_row['venue_code'],
                'pred_first': pred_first,
                'pred_second_baseline': pred_second_baseline,
                'pred_second_specialized': pred_second_specialized,
                'pred_second_integrated': pred_second_integrated,
                'actual_first': actual['first'],
                'actual_second': actual['second'],
                'actual_third': actual['third'],
                'first_correct': first_correct,
                'second_correct_baseline': second_correct_baseline,
                'second_correct_specialized': second_correct_specialized,
                'second_correct_integrated': second_correct_integrated,
                'trifecta_payout': actual['trifecta_payout'],
                'confidence': top_confidence
            })

        except Exception as e:
            logger.debug(f"レース {race_id} 処理エラー: {e}")
            continue

        # 進捗表示
        if (idx + 1) % 100 == 0:
            logger.info(f"  進捗: {idx + 1}/{len(test_races)}")

    return stats, detailed_results


def print_results(
    stats: dict,
    detailed_results: list,
    logger: logging.Logger
):
    """
    結果を出力

    Args:
        stats: 統計情報
        detailed_results: 詳細結果
        logger: ロガー
    """
    logger.info("\n" + "=" * 60)
    logger.info("バックテスト結果")
    logger.info("=" * 60)

    total = stats['total_races']
    if total == 0:
        logger.warning("有効なレースがありませんでした")
        return

    # 的中率
    logger.info("\n=== 的中率 ===")
    logger.info(f"総レース数: {total:,}")
    logger.info(f"1着的中率: {stats['first_correct']}/{total} = {stats['first_correct']/total*100:.2f}%")
    logger.info(f"2着的中率: {stats['second_correct']}/{total} = {stats['second_correct']/total*100:.2f}%")
    logger.info(f"2着的中率(1着的中時): {stats['second_correct_given_first']}/{stats['first_correct']} = "
                f"{stats['second_correct_given_first']/max(1, stats['first_correct'])*100:.2f}%")
    logger.info(f"三連単的中率: {stats['trifecta_correct']}/{total} = {stats['trifecta_correct']/total*100:.2f}%")

    # 専用モデルの効果
    logger.info("\n=== 専用モデルの効果 ===")
    logger.info(f"2着予測改善: {stats['improved_second']}件")
    logger.info(f"2着予測悪化: {stats['degraded_second']}件")
    net_effect = stats['improved_second'] - stats['degraded_second']
    logger.info(f"純効果: {net_effect:+d}件")

    # ROI
    logger.info("\n=== 収支 ===")
    logger.info(f"購入レース数: {stats['total_bets']}")
    logger.info(f"総投資額: {stats['total_investment']:,}円")
    logger.info(f"総回収額: {stats['total_return']:,}円")
    if stats['total_investment'] > 0:
        roi = stats['total_return'] / stats['total_investment'] * 100
        logger.info(f"ROI: {roi:.1f}%")
        profit = stats['total_return'] - stats['total_investment']
        logger.info(f"収支: {profit:+,}円")

    # 詳細分析
    if detailed_results:
        df = pd.DataFrame(detailed_results)

        # 信頼度別の分析
        logger.info("\n=== 信頼度別分析 ===")
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_df = df[df['confidence'] == conf]
            if len(conf_df) == 0:
                continue

            first_acc = conf_df['first_correct'].mean() * 100
            second_acc = conf_df['second_correct_integrated'].mean() * 100
            second_base = conf_df['second_correct_baseline'].mean() * 100
            second_spec = conf_df['second_correct_specialized'].mean() * 100

            logger.info(f"  信頼度{conf} ({len(conf_df)}件):")
            logger.info(f"    1着的中率: {first_acc:.1f}%")
            logger.info(f"    2着的中率(baseline): {second_base:.1f}%")
            logger.info(f"    2着的中率(specialized): {second_spec:.1f}%")
            logger.info(f"    2着的中率(integrated): {second_acc:.1f}%")
            improvement = second_acc - second_base
            logger.info(f"    改善幅: {improvement:+.1f}pt")


def main():
    parser = argparse.ArgumentParser(
        description='2着専用スコアリングモデルのバックテスト'
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
        default='second_place_specialized',
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
        '--integration-weight', type=float,
        default=0.5,
        help='統合重み（0.0-1.0、専用モデルの重み）'
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

    logger.info("=" * 60)
    logger.info("2着専用スコアリングモデル バックテスト")
    logger.info("=" * 60)
    logger.info(f"テスト期間: {args.start_date} ~ {args.end_date}")
    logger.info(f"統合重み: {args.integration_weight}")

    # データベース存在確認
    if not os.path.exists(args.db_path):
        logger.error(f"データベースが見つかりません: {args.db_path}")
        sys.exit(1)

    # モデル読み込み
    logger.info("\n=== モデル読み込み ===")
    scorer = SecondPlaceSpecializedScorer(
        model_dir=args.model_dir,
        db_path=args.db_path
    )

    model_path = os.path.join(args.model_dir, f'{args.model_name}.txt')
    if os.path.exists(model_path):
        scorer.load(args.model_name)
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
    stats, detailed_results = run_backtest(
        db_path=args.db_path,
        test_races=test_races,
        scorer=scorer,
        integration_weight=args.integration_weight,
        bet_unit=args.bet_unit,
        logger=logger
    )

    # 結果出力
    print_results(stats, detailed_results, logger)

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
