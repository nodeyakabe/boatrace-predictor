"""
条件付きモデル（Stage2/3）再学習スクリプト

2025-12-15作成
- TimeSeriesSplit(5)でクロスバリデーション
- early_stopping使用
- モデル保存: models/stage2_conditional.joblib, models/stage3_conditional.joblib

改善内容:
- Stage2: 1着艇との相対特徴量追加、コース位置関係追加
- Stage3: 1着・2着艇との相対特徴量追加、レース展開情報追加
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, accuracy_score
import xgboost as xgb
import joblib
from datetime import datetime
from typing import Tuple, Dict

from src.ml.conditional_rank_model import ConditionalRankModel


def load_training_data(db_path: str = 'data/boatrace.db') -> pd.DataFrame:
    """
    学習用データをDBから読み込み

    2020-2025年のレースデータを使用
    """
    print("=== 学習データの読み込み ===")

    conn = sqlite3.connect(db_path)

    # レース結果と特徴量を結合
    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        CAST(res.pit_number AS INTEGER) as pit_number,
        CAST(res.rank AS INTEGER) as rank,
        -- 選手特徴量（entriesテーブル）
        e.racer_number,
        e.racer_rank,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.local_win_rate,
        e.local_second_rate,
        e.motor_second_rate,
        e.boat_second_rate,
        e.avg_st,
        -- 展示情報（race_detailsテーブル）
        rd.exhibition_time,
        rd.st_time as exhibition_st,
        rd.exhibition_course,
        rd.tilt_angle,
        -- 気象情報
        rc.wind_speed,
        rc.wave_height,
        rc.temperature,
        rc.water_temperature
    FROM races r
    JOIN results res ON r.id = res.race_id
    JOIN entries e ON r.id = e.race_id AND res.pit_number = e.pit_number
    LEFT JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date <= '2025-12-31'
      AND res.rank IS NOT NULL
      AND CAST(res.rank AS INTEGER) <= 6
    ORDER BY r.race_date, r.id, res.pit_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"読み込みレコード数: {len(df):,}")
    print(f"ユニークレース数: {df['race_id'].nunique():,}")

    # 欠損値の処理
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().sum() > 0:
            df[col] = df[col].fillna(df[col].median())

    return df


def evaluate_model(model: ConditionalRankModel, test_df: pd.DataFrame) -> Dict[str, float]:
    """
    モデルの評価

    Returns:
        精度指標の辞書
    """
    results = {}

    # 1着予測
    X_1st, y_1st = model._prepare_first_place_data(test_df)
    if len(X_1st) > 0 and model.models['first'] is not None:
        pred_1st = model.models['first'].predict_proba(X_1st)[:, 1]
        results['first_auc'] = roc_auc_score(y_1st, pred_1st)
        results['first_accuracy'] = accuracy_score(y_1st, (pred_1st >= 0.5).astype(int))

    # 2着予測
    X_2nd, y_2nd = model._prepare_second_place_data(test_df)
    if len(X_2nd) > 0 and model.models['second'] is not None:
        # 特徴量名を揃える
        for col in model.second_feature_names:
            if col not in X_2nd.columns:
                X_2nd[col] = 0
        X_2nd = X_2nd[model.second_feature_names]

        pred_2nd = model.models['second'].predict_proba(X_2nd)[:, 1]
        results['second_auc'] = roc_auc_score(y_2nd, pred_2nd)
        results['second_accuracy'] = accuracy_score(y_2nd, (pred_2nd >= 0.5).astype(int))

    # 3着予測
    X_3rd, y_3rd = model._prepare_third_place_data(test_df)
    if len(X_3rd) > 0 and model.models['third'] is not None:
        # 特徴量名を揃える
        for col in model.third_feature_names:
            if col not in X_3rd.columns:
                X_3rd[col] = 0
        X_3rd = X_3rd[model.third_feature_names]

        pred_3rd = model.models['third'].predict_proba(X_3rd)[:, 1]
        results['third_auc'] = roc_auc_score(y_3rd, pred_3rd)
        results['third_accuracy'] = accuracy_score(y_3rd, (pred_3rd >= 0.5).astype(int))

    return results


def train_with_cv(df: pd.DataFrame, n_splits: int = 5) -> Tuple[ConditionalRankModel, Dict]:
    """
    TimeSeriesSplitでクロスバリデーション付き学習

    Args:
        df: 学習データ
        n_splits: 分割数

    Returns:
        学習済みモデル、CV結果
    """
    print(f"\n=== TimeSeriesSplit ({n_splits}分割) でクロスバリデーション ===")

    # race_dateでソート
    df = df.sort_values('race_date').reset_index(drop=True)

    # レース単位でグループ化（レースを分割しない）
    race_ids = df['race_id'].unique()
    tscv = TimeSeriesSplit(n_splits=n_splits)

    cv_results = {
        'first_auc': [],
        'second_auc': [],
        'third_auc': []
    }

    for fold, (train_idx, test_idx) in enumerate(tscv.split(race_ids), 1):
        print(f"\n--- Fold {fold}/{n_splits} ---")

        train_races = race_ids[train_idx]
        test_races = race_ids[test_idx]

        train_df = df[df['race_id'].isin(train_races)].copy()
        test_df = df[df['race_id'].isin(test_races)].copy()

        print(f"  学習: {len(train_df):,}件 ({len(train_races):,}レース)")
        print(f"  検証: {len(test_df):,}件 ({len(test_races):,}レース)")

        # モデル学習
        model = ConditionalRankModel()

        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'max_depth': 6,
            'learning_rate': 0.03,
            'n_estimators': 1000,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'min_child_weight': 3,
            'gamma': 0.1,
            'random_state': 42,
            'n_jobs': -1,
            'early_stopping_rounds': 50,  # early stopping追加
        }

        try:
            train_results = model.train(train_df, test_df, params)

            for key in cv_results:
                if key in train_results:
                    cv_results[key].append(train_results[key])
        except Exception as e:
            print(f"  [警告] Fold {fold}でエラー: {e}")
            continue

    # CV結果の集計
    print("\n=== クロスバリデーション結果 ===")
    for key, values in cv_results.items():
        if values:
            mean_val = np.mean(values)
            std_val = np.std(values)
            print(f"  {key}: {mean_val:.4f} (+/- {std_val:.4f})")

    # 最終モデルを全データで学習
    print("\n=== 最終モデルの学習（全データ） ===")

    # 直近1年を検証用に確保
    cutoff_date = df['race_date'].max()
    cutoff_date = pd.to_datetime(cutoff_date) - pd.Timedelta(days=180)
    cutoff_str = cutoff_date.strftime('%Y-%m-%d')

    train_final = df[df['race_date'] < cutoff_str].copy()
    valid_final = df[df['race_date'] >= cutoff_str].copy()

    print(f"  学習: {len(train_final):,}件")
    print(f"  検証: {len(valid_final):,}件")

    final_model = ConditionalRankModel()
    final_params = {
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        'max_depth': 6,
        'learning_rate': 0.03,
        'n_estimators': 1000,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'min_child_weight': 3,
        'gamma': 0.1,
        'random_state': 42,
        'n_jobs': -1,
        'early_stopping_rounds': 50,
    }

    final_results = final_model.train(train_final, valid_final, final_params)

    return final_model, {
        'cv_results': cv_results,
        'final_results': final_results
    }


def main():
    """メイン処理"""
    print("=" * 70)
    print("条件付きモデル（Stage2/3）再学習スクリプト")
    print("=" * 70)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # データ読み込み
    df = load_training_data()

    # クロスバリデーション付き学習
    model, results = train_with_cv(df, n_splits=5)

    # モデル保存
    model.save('conditional_rank_v2_20251215')

    # 結果レポート
    print("\n" + "=" * 70)
    print("=== 学習完了レポート ===")
    print("=" * 70)

    print("\n【CV結果】")
    for key, values in results['cv_results'].items():
        if values:
            print(f"  {key}: {np.mean(values):.4f} (+/- {np.std(values):.4f})")

    print("\n【最終モデル精度】")
    for key, value in results['final_results'].items():
        print(f"  {key}: {value:.4f}")

    print("\n【保存先】")
    print("  models/conditional_rank_v2_20251215_*.json")
    print("  models/conditional_rank_v2_20251215.meta.json")

    print("\n" + "=" * 70)
    print("完了")


if __name__ == '__main__':
    main()
