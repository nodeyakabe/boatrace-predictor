#!/usr/bin/env python
"""
ペアワイズ順位予測モデルの学習スクリプト

使用方法:
    python scripts/train_pairwise_rank_model.py

概要:
    - ペアワイズ相対スコアリングモデルを学習
    - 艇間の直接対決確率を予測
    - LightGBMを使用
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
import pandas as pd
import numpy as np

from src.ml.pairwise_rank_model import (
    PairwiseRankModel,
    prepare_training_dataset
)


def setup_logging(verbose: bool = False):
    """ロギング設定"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def analyze_training_data(df: pd.DataFrame, logger: logging.Logger):
    """
    学習データを分析

    Args:
        df: データフレーム
        logger: ロガー
    """
    logger.info("=== 学習データ分析 ===")

    # 基本統計
    race_count = df['race_id'].nunique()
    entry_count = len(df)
    logger.info(f"総レース数: {race_count:,}")
    logger.info(f"総エントリー数: {entry_count:,}")

    # 6艇完備率
    race_sizes = df.groupby('race_id').size()
    complete_races = (race_sizes == 6).sum()
    logger.info(f"6艇完備レース: {complete_races:,} ({complete_races/race_count*100:.1f}%)")

    # 期待ペアワイズデータ数
    expected_pairs = complete_races * 30  # 6艇 * 5対戦 = 30ペア/レース
    logger.info(f"期待ペアワイズデータ数: {expected_pairs:,}")

    # 着順分布
    logger.info("\n=== 着順分布 ===")
    rank_dist = df.groupby('rank').size()
    for rank in range(1, 7):
        count = rank_dist.get(rank, 0)
        logger.info(f"  {rank}着: {count:,} ({count/entry_count*100:.1f}%)")

    # コース別勝率
    logger.info("\n=== コース別勝率（6艇完備レースのみ） ===")
    complete_race_ids = race_sizes[race_sizes == 6].index
    complete_df = df[df['race_id'].isin(complete_race_ids)]

    for course in range(1, 7):
        course_df = complete_df[complete_df['pit_number'] == course]
        if len(course_df) > 0:
            win_rate = (course_df['rank'] == 1).mean() * 100
            logger.info(f"  {course}コース: {win_rate:.1f}%")

    # 特徴量の欠損率
    logger.info("\n=== 特徴量欠損率 ===")
    important_cols = [
        'win_rate', 'second_rate', 'motor_second_rate',
        'exhibition_time', 'avg_st'
    ]
    for col in important_cols:
        if col in df.columns:
            missing_rate = df[col].isna().mean()
            logger.info(f"  {col}: {missing_rate*100:.1f}%")


def validate_pairwise_consistency(model: PairwiseRankModel, valid_df: pd.DataFrame, logger: logging.Logger):
    """
    ペアワイズ予測の一貫性を検証

    Args:
        model: 学習済みモデル
        valid_df: 検証データ
        logger: ロガー
    """
    logger.info("\n=== ペアワイズ予測一貫性検証 ===")

    # サンプルレースで検証
    race_ids = valid_df['race_id'].unique()[:10]

    consistency_scores = []

    for race_id in race_ids:
        race_df = valid_df[valid_df['race_id'] == race_id]

        if len(race_df) != 6:
            continue

        try:
            # ペアワイズ確率行列を取得
            prob_matrix = model.predict_pairwise_probs(race_df)

            # 一貫性チェック: P(i>j) + P(j>i) ≈ 1
            consistency = []
            for i in range(6):
                for j in range(i + 1, 6):
                    total = prob_matrix[i, j] + prob_matrix[j, i]
                    consistency.append(abs(total - 1.0))

            avg_consistency = np.mean(consistency)
            consistency_scores.append(avg_consistency)

        except Exception as e:
            logger.debug(f"レース {race_id} 検証エラー: {e}")
            continue

    if consistency_scores:
        logger.info(f"平均一貫性誤差: {np.mean(consistency_scores):.4f}")
        logger.info(f"最大一貫性誤差: {np.max(consistency_scores):.4f}")
    else:
        logger.warning("一貫性検証データがありません")


def evaluate_ranking_accuracy(model: PairwiseRankModel, valid_df: pd.DataFrame, logger: logging.Logger):
    """
    順位予測精度を評価

    Args:
        model: 学習済みモデル
        valid_df: 検証データ
        logger: ロガー
    """
    logger.info("\n=== 順位予測精度評価 ===")

    # 6艇完備レースのみ
    race_sizes = valid_df.groupby('race_id').size()
    complete_races = race_sizes[race_sizes == 6].index
    valid_df = valid_df[valid_df['race_id'].isin(complete_races)]

    race_ids = valid_df['race_id'].unique()

    results = {
        'first_correct': 0,
        'second_correct': 0,
        'third_correct': 0,
        'trifecta_correct': 0,
        'total': 0
    }

    methods = ['win_count', 'score_diff', 'copeland']
    method_results = {m: dict(results) for m in methods}

    for race_id in race_ids:
        race_df = valid_df[valid_df['race_id'] == race_id]

        if len(race_df) != 6:
            continue

        # 実際の順位
        actual_ranks = race_df.set_index('pit_number')['rank'].to_dict()
        actual_first = min(actual_ranks, key=actual_ranks.get)
        actual_order = sorted(actual_ranks.keys(), key=lambda x: actual_ranks[x])

        try:
            for method in methods:
                # ペアワイズ予測
                predicted_order = model.predict_rank_order(race_df, method=method)

                method_results[method]['total'] += 1

                # 1着的中
                if predicted_order[0] == actual_order[0]:
                    method_results[method]['first_correct'] += 1

                    # 1着的中時の2着的中
                    if predicted_order[1] == actual_order[1]:
                        method_results[method]['second_correct'] += 1

                        # 1-2着的中時の3着的中
                        if predicted_order[2] == actual_order[2]:
                            method_results[method]['third_correct'] += 1
                            method_results[method]['trifecta_correct'] += 1

        except Exception as e:
            logger.debug(f"レース {race_id} 評価エラー: {e}")
            continue

    # 結果出力
    for method in methods:
        r = method_results[method]
        total = r['total']

        if total > 0:
            logger.info(f"\n--- 方法: {method} ---")
            logger.info(f"総レース数: {total:,}")
            logger.info(f"1着的中率: {r['first_correct']/total*100:.2f}%")
            logger.info(f"2着的中率(1着的中時): {r['second_correct']/max(1, r['first_correct'])*100:.2f}%")
            logger.info(f"3着的中率(1-2着的中時): {r['third_correct']/max(1, r['second_correct'])*100:.2f}%")
            logger.info(f"三連単的中率: {r['trifecta_correct']/total*100:.2f}%")


def main():
    parser = argparse.ArgumentParser(
        description='ペアワイズ順位予測モデルの学習'
    )
    parser.add_argument(
        '--db-path', type=str,
        default='data/boatrace.db',
        help='データベースパス'
    )
    parser.add_argument(
        '--model-dir', type=str,
        default='models',
        help='モデル保存ディレクトリ'
    )
    parser.add_argument(
        '--train-start', type=str,
        default='2024-01-01',
        help='学習データ開始日'
    )
    parser.add_argument(
        '--train-end', type=str,
        default='2025-10-31',
        help='学習データ終了日'
    )
    parser.add_argument(
        '--valid-start', type=str,
        default='2025-11-01',
        help='検証データ開始日'
    )
    parser.add_argument(
        '--valid-end', type=str,
        default='2025-11-27',
        help='検証データ終了日'
    )
    parser.add_argument(
        '--model-name', type=str,
        default='pairwise_rank',
        help='保存するモデル名'
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='詳細ログを出力'
    )
    parser.add_argument(
        '--skip-evaluation', action='store_true',
        help='評価をスキップ'
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("ペアワイズ順位予測モデル 学習スクリプト")
    logger.info("=" * 60)
    logger.info(f"データベース: {args.db_path}")
    logger.info(f"学習期間: {args.train_start} ~ {args.train_end}")
    logger.info(f"検証期間: {args.valid_start} ~ {args.valid_end}")

    # データベース存在確認
    if not os.path.exists(args.db_path):
        logger.error(f"データベースが見つかりません: {args.db_path}")
        sys.exit(1)

    # データ読み込み
    logger.info("\n=== データ読み込み ===")
    logger.info("学習データを読み込み中...")
    train_df = prepare_training_dataset(
        args.db_path, args.train_start, args.train_end
    )
    logger.info(f"学習データ: {len(train_df):,}件")

    logger.info("検証データを読み込み中...")
    valid_df = prepare_training_dataset(
        args.db_path, args.valid_start, args.valid_end
    )
    logger.info(f"検証データ: {len(valid_df):,}件")

    # データ分析
    analyze_training_data(train_df, logger)

    # モデル学習
    logger.info("\n=== モデル学習 ===")
    model = PairwiseRankModel(
        model_dir=args.model_dir,
        db_path=args.db_path
    )

    # LightGBMパラメータ
    params = {
        'objective': 'binary',
        'metric': 'auc',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'feature_fraction': 0.8,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'min_child_samples': 20,
        'random_state': 42,
        'verbose': -1,
        'force_col_wise': True
    }

    results = model.train(train_df, valid_df, params)

    # 結果出力
    logger.info("\n=== 学習結果 ===")
    if 'valid_auc' in results:
        logger.info(f"検証AUC: {results['valid_auc']:.4f}")

        # AUCの評価
        auc = results['valid_auc']
        if auc >= 0.70:
            logger.info("  -> 優れた識別性能")
        elif auc >= 0.65:
            logger.info("  -> 良好な識別性能")
        elif auc >= 0.60:
            logger.info("  -> まずまずの識別性能")
        else:
            logger.info("  -> 改善の余地あり")

    if 'valid_logloss' in results:
        logger.info(f"検証LogLoss: {results['valid_logloss']:.4f}")

    # 一貫性検証
    if not args.skip_evaluation:
        validate_pairwise_consistency(model, valid_df, logger)

        # 順位予測精度評価
        evaluate_ranking_accuracy(model, valid_df, logger)

    # モデル保存
    logger.info("\n=== モデル保存 ===")
    model.save(args.model_name)
    logger.info(f"モデルを保存しました: {args.model_dir}/{args.model_name}")

    # 特徴量重要度の詳細
    if 'feature_importance' in results:
        logger.info("\n=== 特徴量重要度 Top 15 ===")
        importance = results['feature_importance']
        sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)

        for i, (fname, imp) in enumerate(sorted_imp[:15], 1):
            logger.info(f"  {i:2d}. {fname}: {imp:.2f}")

    logger.info("\n" + "=" * 60)
    logger.info("学習完了")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
