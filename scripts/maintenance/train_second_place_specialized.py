#!/usr/bin/env python
"""
2着専用スコアリングモデルの学習スクリプト

使用方法:
    python scripts/train_second_place_specialized.py

概要:
    - 差し・まくり差し特化型の2着予測モデルを学習
    - 予想1着を条件として学習データを作成
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

from src.ml.second_place_specialized_model import (
    SecondPlaceSpecializedScorer,
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


def load_data_with_kimarite(
    db_path: str,
    start_date: str,
    end_date: str
) -> pd.DataFrame:
    """
    決まり手情報を含むデータを読み込み

    Args:
        db_path: データベースパス
        start_date: 開始日
        end_date: 終了日

    Returns:
        学習用DataFrame
    """
    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        r.id AS race_id,
        r.venue_code,
        r.race_date,
        r.race_grade,
        e.pit_number,
        e.racer_number,
        e.racer_name,
        e.racer_rank,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.motor_number,
        e.motor_second_rate,
        e.motor_third_rate,
        e.boat_second_rate,
        e.boat_third_rate,
        e.avg_st,
        e.f_count,
        e.l_count,
        e.local_win_rate,
        rd.exhibition_time,
        rd.st_time,
        rd.actual_course,
        rd.tilt_angle,
        res.rank,
        res.kimarite
    FROM races r
    INNER JOIN entries e ON r.id = e.race_id
    INNER JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE r.race_date BETWEEN ? AND ?
        AND res.is_invalid = 0
        AND res.rank IS NOT NULL
        AND CAST(res.rank AS INTEGER) BETWEEN 1 AND 6
    ORDER BY r.race_date, r.id, e.pit_number
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    # rankを整数に変換
    df['rank'] = df['rank'].astype(int)

    # 決まり手から差し率・まくり差し率を計算
    df = add_kimarite_features(df)

    # 総合スコアを計算
    df['total_score'] = calculate_total_score(df)

    return df


def add_kimarite_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    決まり手特徴量を追加

    Args:
        df: データフレーム

    Returns:
        決まり手特徴量が追加されたデータフレーム
    """
    # 選手ごとの決まり手集計
    kimarite_map = {
        '逃げ': 'nige',
        '差し': 'sashi',
        'まくり': 'makuri',
        'まくり差し': 'makurisashi',
        '抜き': 'nuki',
        '恵まれ': 'megumi'
    }

    # 各選手の過去の決まり手を集計
    racer_kimarite = df.groupby(['racer_number', 'kimarite']).size().unstack(fill_value=0)

    # 各決まり手の率を計算
    racer_total = racer_kimarite.sum(axis=1)
    for jp_name, en_name in kimarite_map.items():
        if jp_name in racer_kimarite.columns:
            racer_kimarite[f'{en_name}_rate'] = racer_kimarite[jp_name] / racer_total
        else:
            racer_kimarite[f'{en_name}_rate'] = 0

    # 元のデータにマージ
    rate_cols = [f'{en_name}_rate' for en_name in kimarite_map.values()]
    existing_rate_cols = [col for col in rate_cols if col in racer_kimarite.columns]

    if existing_rate_cols:
        kimarite_rates = racer_kimarite[existing_rate_cols].reset_index()
        df = df.merge(kimarite_rates, on='racer_number', how='left')

        # 欠損値を0で埋める
        for col in existing_rate_cols:
            df[col] = df[col].fillna(0)

    return df


def calculate_total_score(df: pd.DataFrame) -> pd.Series:
    """
    総合スコアを計算

    Args:
        df: データフレーム

    Returns:
        総合スコアのSeries
    """
    score = pd.Series(0.0, index=df.index)

    # 勝率ベース
    if 'win_rate' in df.columns:
        score += df['win_rate'].fillna(0) * 8

    # モーター2連対率
    if 'motor_second_rate' in df.columns:
        score += df['motor_second_rate'].fillna(0) * 0.3

    # コースボーナス
    course_bonus = df['pit_number'].map({
        1: 15, 2: 5, 3: 3, 4: 2, 5: 1, 6: 0
    }).fillna(0)
    score += course_bonus

    # ST優位性
    if 'avg_st' in df.columns:
        st_bonus = (0.20 - df['avg_st'].fillna(0.20)) * 50
        score += st_bonus.clip(-5, 5)

    return score


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

    # 着順分布
    logger.info("\n=== 着順分布 ===")
    rank_dist = df.groupby('rank').size()
    for rank in range(1, 7):
        count = rank_dist.get(rank, 0)
        logger.info(f"  {rank}着: {count:,} ({count/entry_count*100:.1f}%)")

    # 決まり手分布
    if 'kimarite' in df.columns:
        logger.info("\n=== 決まり手分布（1着のみ） ===")
        first_df = df[df['rank'] == 1]
        kimarite_dist = first_df['kimarite'].value_counts()
        for kimarite, count in kimarite_dist.head(6).items():
            logger.info(f"  {kimarite}: {count:,} ({count/len(first_df)*100:.1f}%)")

    # 特徴量の欠損率
    logger.info("\n=== 特徴量欠損率 ===")
    important_cols = [
        'win_rate', 'motor_second_rate', 'exhibition_time', 'avg_st'
    ]
    for col in important_cols:
        if col in df.columns:
            missing_rate = df[col].isna().mean()
            logger.info(f"  {col}: {missing_rate*100:.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description='2着専用スコアリングモデルの学習'
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
        default='second_place_specialized',
        help='保存するモデル名'
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='詳細ログを出力'
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("2着専用スコアリングモデル 学習スクリプト")
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
    train_df = load_data_with_kimarite(
        args.db_path, args.train_start, args.train_end
    )
    logger.info(f"学習データ: {len(train_df):,}件")

    logger.info("検証データを読み込み中...")
    valid_df = load_data_with_kimarite(
        args.db_path, args.valid_start, args.valid_end
    )
    logger.info(f"検証データ: {len(valid_df):,}件")

    # データ分析
    analyze_training_data(train_df, logger)

    # モデル学習
    logger.info("\n=== モデル学習 ===")
    scorer = SecondPlaceSpecializedScorer(
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
        'force_col_wise': True  # 警告抑制
    }

    results = scorer.train(train_df, valid_df, params)

    # 結果出力
    logger.info("\n=== 学習結果 ===")
    if 'valid_auc' in results:
        logger.info(f"検証AUC: {results['valid_auc']:.4f}")

        # AUCの評価
        auc = results['valid_auc']
        if auc >= 0.65:
            logger.info("  -> 良好な識別性能")
        elif auc >= 0.60:
            logger.info("  -> まずまずの識別性能")
        else:
            logger.info("  -> 改善の余地あり")

    # モデル保存
    logger.info("\n=== モデル保存 ===")
    scorer.save(args.model_name)
    logger.info(f"モデルを保存しました: {args.model_dir}/{args.model_name}")

    # 特徴量重要度の詳細
    if 'feature_importance' in results:
        logger.info("\n=== 特徴量重要度 ===")
        importance = results['feature_importance']
        sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)

        for i, (fname, imp) in enumerate(sorted_imp[:15], 1):
            logger.info(f"  {i:2d}. {fname}: {imp:.2f}")

    logger.info("\n" + "=" * 60)
    logger.info("学習完了")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
