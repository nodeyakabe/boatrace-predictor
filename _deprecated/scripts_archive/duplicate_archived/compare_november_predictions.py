#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
11月予測比較スクリプト

現行版（既存予測）と改善版（新規特徴量）の予測精度を比較します。

- 現行版: DBに保存済みの race_predictions テーブルのデータ
- 改善版: 新規特徴量（ボーターズ + 会場×コース）を使った予測

実行方法:
  python scripts/compare_november_predictions.py
"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score
import json
import warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def load_november_results(db_path: str, year: int = 2024) -> pd.DataFrame:
    """
    11月のレース結果を取得
    """
    conn = sqlite3.connect(db_path)

    start_date = f"{year}-11-01"
    end_date = f"{year}-11-30"

    query = """
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            e.pit_number,
            e.racer_number,
            e.racer_name,
            res.rank as result_rank
        FROM races r
        JOIN entries e ON r.id = e.race_id
        JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
            AND res.rank IS NOT NULL
            AND res.rank NOT IN ('F', 'L', 'K', '')
        ORDER BY r.race_date, r.venue_code, r.race_number, e.pit_number
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    # 1着フラグ
    df['is_win'] = (df['result_rank'] == '1').astype(int)

    return df


def load_current_predictions(db_path: str, year: int = 2024) -> pd.DataFrame:
    """
    現行版（DBに保存済み）の予測を取得
    """
    conn = sqlite3.connect(db_path)

    start_date = f"{year}-11-01"
    end_date = f"{year}-11-30"

    query = """
        SELECT
            p.race_id,
            p.pit_number,
            p.rank_prediction,
            p.total_score,
            p.confidence,
            p.prediction_type
        FROM race_predictions p
        JOIN races r ON p.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
            AND p.prediction_type = 'before'
        ORDER BY p.race_id, p.pit_number
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    return df


def run_improved_predictions(db_path: str, year: int = 2025) -> pd.DataFrame:
    """
    改善版（新規特徴量を使用）の予測を実行
    """
    from src.ml.dataset_builder import DatasetBuilder
    import xgboost as xgb

    start_date = f"{year}-11-01"
    end_date = f"{year}-11-30"

    # 訓練期間: 9月-10月（2ヶ月分）
    train_start = f"{year}-09-01"
    train_end = f"{year}-10-31"

    builder = DatasetBuilder()

    print("\n【改善版】訓練データ構築中...")
    df_train = builder.build_training_dataset(train_start, train_end)
    print(f"  基本データ: {len(df_train)}行")

    # 全特徴量を追加（ボーターズ + 会場×コース）
    df_train = builder.add_all_derived_features(
        df_train,
        include_boaters=True,
        include_venue_course=True
    )
    print(f"  特徴量追加後: {len(df_train.columns)}列")

    print("\n【改善版】テストデータ構築中...")
    df_test = builder.build_training_dataset(start_date, end_date)
    print(f"  基本データ: {len(df_test)}行")

    df_test = builder.add_all_derived_features(
        df_test,
        include_boaters=True,
        include_venue_course=True
    )
    print(f"  特徴量追加後: {len(df_test.columns)}列")

    # 特徴量選択
    exclude_cols = [
        'race_id', 'race_date', 'venue_code', 'race_number',
        'pit_number', 'racer_number', 'racer_name', 'motor_number',
        'boat_number', 'result_rank', 'is_win', 'target'
    ]

    feature_cols = [c for c in df_train.columns if c not in exclude_cols]
    feature_cols = [c for c in feature_cols if c in df_test.columns]

    print(f"\n  使用特徴量: {len(feature_cols)}個")

    # データ準備
    X_train = df_train[feature_cols].copy()
    y_train = df_train['is_win'] if 'is_win' in df_train.columns else (df_train['result_rank'] == '1').astype(int)

    X_test = df_test[feature_cols].copy()

    # 欠損値・無限値処理
    X_train = X_train.fillna(X_train.mean())
    X_train = X_train.replace([np.inf, -np.inf], 0)
    X_test = X_test.fillna(X_test.mean())
    X_test = X_test.replace([np.inf, -np.inf], 0)

    # モデル訓練
    print("\n【改善版】モデル訓練中...")
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='auc'
    )

    model.fit(X_train, y_train, verbose=False)

    # 予測
    print("【改善版】予測実行中...")
    y_prob = model.predict_proba(X_test)[:, 1]

    # 結果をDataFrameに
    result_df = df_test[['race_id', 'pit_number']].copy()
    result_df['improved_score'] = y_prob * 100  # 0-100スケール

    # レースごとに順位を付ける
    result_df['improved_rank'] = result_df.groupby('race_id')['improved_score'].rank(
        ascending=False, method='min'
    ).astype(int)

    return result_df


def evaluate_predictions(results_df: pd.DataFrame, pred_df: pd.DataFrame,
                        score_col: str, rank_col: str, version_name: str) -> dict:
    """
    予測精度を評価
    """
    # マージ
    merged = results_df.merge(
        pred_df,
        on=['race_id', 'pit_number'],
        how='inner'
    )

    if len(merged) == 0:
        return {'error': 'No matching data'}

    # 1着的中率
    merged['predicted_1st'] = (merged[rank_col] == 1).astype(int)
    accuracy_1st = (merged['is_win'] == merged['predicted_1st']).mean()

    # 1着予測が実際に1着だった率
    top1_predictions = merged[merged[rank_col] == 1]
    if len(top1_predictions) > 0:
        hit_rate_1st = top1_predictions['is_win'].mean()
    else:
        hit_rate_1st = 0

    # 3着以内的中率（上位3位予測が3着以内に入った率）
    merged['predicted_top3'] = (merged[rank_col] <= 3).astype(int)
    merged['actual_top3'] = (merged['result_rank'].astype(str).isin(['1', '2', '3'])).astype(int)
    top3_match = (merged['predicted_top3'] == 1) & (merged['actual_top3'] == 1)
    hit_rate_top3 = top3_match.sum() / merged['predicted_top3'].sum() if merged['predicted_top3'].sum() > 0 else 0

    # AUC
    try:
        auc = roc_auc_score(merged['is_win'], merged[score_col])
    except:
        auc = 0

    metrics = {
        'version': version_name,
        'total_predictions': len(merged),
        'races': merged['race_id'].nunique(),
        'hit_rate_1st': round(hit_rate_1st * 100, 2),
        'hit_rate_top3': round(hit_rate_top3 * 100, 2),
        'auc': round(auc, 4)
    }

    return metrics


def main():
    print("=" * 70)
    print("11月予測 比較分析")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db_path = DATABASE_PATH
    year = 2025  # 2025年11月を分析（DBにある予測データ）

    # 結果データ取得
    print("\n【Step 1】11月レース結果を取得")
    results_df = load_november_results(db_path, year)
    print(f"  レース数: {results_df['race_id'].nunique()}")
    print(f"  エントリー数: {len(results_df)}")

    # 現行版予測を取得
    print("\n【Step 2】現行版予測を取得")
    current_pred = load_current_predictions(db_path, year)
    if len(current_pred) == 0:
        print("  [!] 現行版予測がDBに見つかりません")
        print("  => 先に scripts/generate_november_predictions.py を実行してください")
        return
    print(f"  予測数: {len(current_pred)}")
    print(f"  対象レース: {current_pred['race_id'].nunique()}")

    # 改善版予測を実行
    print("\n【Step 3】改善版予測を実行")
    improved_pred = run_improved_predictions(db_path, year)
    print(f"  予測数: {len(improved_pred)}")

    # 評価
    print("\n【Step 4】予測精度を評価")

    current_metrics = evaluate_predictions(
        results_df, current_pred,
        score_col='total_score', rank_col='rank_prediction',
        version_name='現行版'
    )

    improved_metrics = evaluate_predictions(
        results_df, improved_pred,
        score_col='improved_score', rank_col='improved_rank',
        version_name='改善版'
    )

    # 結果表示
    print("\n" + "=" * 70)
    print("【比較結果】")
    print("=" * 70)

    print(f"\n{'指標':<20} {'現行版':>15} {'改善版':>15} {'差分':>15}")
    print("-" * 70)

    if 'error' not in current_metrics and 'error' not in improved_metrics:
        # 1着的中率
        diff_1st = improved_metrics['hit_rate_1st'] - current_metrics['hit_rate_1st']
        print(f"{'1着的中率 (%)':<20} {current_metrics['hit_rate_1st']:>15.2f} {improved_metrics['hit_rate_1st']:>15.2f} {diff_1st:>+15.2f}")

        # 3着以内的中率
        diff_top3 = improved_metrics['hit_rate_top3'] - current_metrics['hit_rate_top3']
        print(f"{'3着内的中率 (%)':<20} {current_metrics['hit_rate_top3']:>15.2f} {improved_metrics['hit_rate_top3']:>15.2f} {diff_top3:>+15.2f}")

        # AUC
        diff_auc = improved_metrics['auc'] - current_metrics['auc']
        print(f"{'AUC':<20} {current_metrics['auc']:>15.4f} {improved_metrics['auc']:>15.4f} {diff_auc:>+15.4f}")

        print("-" * 70)
        print(f"{'対象レース数':<20} {current_metrics['races']:>15} {improved_metrics['races']:>15}")
        print(f"{'予測エントリー数':<20} {current_metrics['total_predictions']:>15} {improved_metrics['total_predictions']:>15}")
    else:
        if 'error' in current_metrics:
            print(f"現行版エラー: {current_metrics['error']}")
        if 'error' in improved_metrics:
            print(f"改善版エラー: {improved_metrics['error']}")

    # 結果保存
    result = {
        'timestamp': datetime.now().isoformat(),
        'year': year,
        'month': 11,
        'current_version': current_metrics,
        'improved_version': improved_metrics
    }

    output_path = 'temp/november_prediction_comparison.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n結果を {output_path} に保存しました")
    print(f"\n完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == '__main__':
    main()
