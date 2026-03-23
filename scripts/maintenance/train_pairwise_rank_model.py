#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ペアワイズ相対スコアリングモデルの学習スクリプト

アプローチ3: 艇間の直接対決確率をモデル化して順位を予測

使用法:
    python scripts/train_pairwise_rank_model.py

出力:
    - models/pairwise_rank.txt: 学習済みモデル
    - models/pairwise_rank_meta.json: メタ情報
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

import logging
from datetime import datetime
import sqlite3
import pandas as pd
import numpy as np

from src.ml.pairwise_rank_model import (
    PairwiseRankModel,
    prepare_training_dataset
)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    print("=" * 70)
    print("ペアワイズ相対スコアリングモデル学習")
    print("アプローチ3: 艇間の直接対決確率によるランキング")
    print("=" * 70)
    print()

    db_path = 'data/boatrace.db'

    # データベース存在確認
    if not os.path.exists(db_path):
        logger.error(f"データベースが見つかりません: {db_path}")
        return

    # 学習期間と検証期間を設定（2026-03-18更新: 2021-2024の4年分）
    # 2020年はrace_predictionsカバー率51.2%のためスケール混在→除外
    train_start = '2021-01-01'
    train_end = '2024-10-31'
    valid_start = '2024-11-01'
    valid_end = '2024-12-31'

    print(f"学習期間: {train_start} ~ {train_end}")
    print(f"検証期間: {valid_start} ~ {valid_end}")
    print()

    # データ準備
    print("データを準備中...")
    train_df = prepare_training_dataset(db_path, train_start, train_end)
    valid_df = prepare_training_dataset(db_path, valid_start, valid_end)

    train_races = train_df['race_id'].nunique()
    valid_races = valid_df['race_id'].nunique()

    print(f"  学習データ: {len(train_df):,}行, {train_races:,}レース")
    print(f"  検証データ: {len(valid_df):,}行, {valid_races:,}レース")
    print()

    if len(train_df) == 0:
        logger.error("学習データが空です")
        return

    # モデル学習
    print("モデルを学習中...")
    print("-" * 70)

    model = PairwiseRankModel(
        model_dir='models',
        db_path=db_path
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
        'verbose': -1
    }

    results = model.train(train_df, valid_df, params=params)

    print("-" * 70)
    print()

    # 結果表示
    if 'error' in results:
        logger.error(f"学習エラー: {results['error']}")
        return

    print("=== 学習結果 ===")
    print(f"  検証AUC: {results.get('valid_auc', 0):.4f}")
    print(f"  検証精度: {results.get('valid_accuracy', 0):.4f}")
    print()

    # 成功条件チェック
    auc = results.get('valid_auc', 0)
    if auc >= 0.65:
        print(f"  [OK] AUC {auc:.4f} >= 0.65 (成功条件達成)")
    else:
        print(f"  [WARNING] AUC {auc:.4f} < 0.65 (目標未達)")
    print()

    # 特徴量重要度
    if 'feature_importance' in results:
        print("=== 特徴量重要度 Top 10 ===")
        fi = results['feature_importance']
        sorted_fi = sorted(fi.items(), key=lambda x: x[1], reverse=True)
        for i, (fname, imp) in enumerate(sorted_fi[:10], 1):
            print(f"  {i:2d}. {fname}: {imp:.2f}")
        print()

    # モデル保存
    print("モデルを保存中...")
    model.save('pairwise_rank')
    print(f"  保存先: models/pairwise_rank.txt")
    print(f"  メタ情報: models/pairwise_rank_meta.json")
    print()

    # サンプル予測
    print("=== サンプル予測 ===")
    sample_race_id = valid_df['race_id'].iloc[0]
    sample_race = valid_df[valid_df['race_id'] == sample_race_id]

    if len(sample_race) == 6:
        try:
            pairwise_probs = model.predict_pairwise_probs(sample_race)
            rank_scores = model.reconstruct_rankings(pairwise_probs, method='win_count')

            print(f"レースID: {sample_race_id}")
            print()

            # 実際の順位とペアワイズスコアを比較
            comparison = []
            for _, row in sample_race.iterrows():
                pit = int(row['pit_number'])
                actual_rank = int(row['rank'])
                pw_score = rank_scores.get(pit, 0)
                comparison.append({
                    'pit': pit,
                    'actual_rank': actual_rank,
                    'pairwise_score': pw_score,
                    'racer_rank': row.get('racer_rank', 'B1'),
                    'win_rate': row.get('win_rate', 0)
                })

            # ペアワイズスコア順にソート
            comparison.sort(key=lambda x: x['pairwise_score'], reverse=True)

            print("  艇番  級別  勝率   PW Score  予測  実際")
            print("  " + "-" * 45)
            for i, c in enumerate(comparison, 1):
                print(f"  {c['pit']:4d}   {c['racer_rank']}  {c['win_rate']:5.1f}%  "
                      f"{c['pairwise_score']:6.2f}   {i}着   {c['actual_rank']}着")
            print()

            # 的中判定
            predicted = [c['pit'] for c in comparison[:3]]
            actual = sorted(comparison, key=lambda x: x['actual_rank'])[:3]
            actual = [c['pit'] for c in actual]

            print(f"  予測Top3: {predicted}")
            print(f"  実際Top3: {actual}")
            hit_count = sum(1 for p in predicted if p in actual)
            print(f"  Top3一致: {hit_count}/3")

        except Exception as e:
            print(f"  サンプル予測エラー: {e}")
    print()

    print("=" * 70)
    print("学習完了")
    print("=" * 70)


if __name__ == '__main__':
    main()
