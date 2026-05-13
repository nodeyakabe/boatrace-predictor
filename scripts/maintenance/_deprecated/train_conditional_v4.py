"""
conditional_rank_v4 再学習スクリプト

Phase1-b: pred_first_is_correct（リーケージ）を除去した修正版モデルを学習する。

修正内容:
- pred_first_is_correct を学習特徴量から除外（事後情報のリーケージ修正）
- 予測時の差分特徴量0埋めバグ修正済みコードと整合する特徴量構成

学習データ:
- races/results/entries/race_details/race_conditions + race_predictions(total_score)
- 期間: 2020-01-01 〜 2025-12-31
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score

from src.ml.conditional_rank_model import ConditionalRankModel


def load_training_data(db_path: str = 'data/boatrace.db') -> pd.DataFrame:
    """
    学習用データをDBから読み込み。
    total_score を race_predictions テーブルから JOIN する（v3と同方式）。
    prediction_type='before' を優先し、なければ 'advance' を使用。
    """
    print("=== 学習データの読み込み ===")
    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        CAST(res.pit_number AS INTEGER) as pit_number,
        CAST(res.rank AS INTEGER) as rank,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.local_win_rate,
        e.local_second_rate,
        e.motor_second_rate,
        e.boat_second_rate,
        e.avg_st,
        rd.exhibition_time,
        rd.st_time        as exhibition_st,
        rd.exhibition_course,
        rd.tilt_angle,
        rc.wind_speed,
        rc.wave_height,
        rc.temperature,
        rc.water_temperature,
        -- total_score: before 優先、なければ advance
        COALESCE(rp_b.total_score, rp_a.total_score) as total_score
    FROM races r
    JOIN results res
        ON r.id = res.race_id
    JOIN entries e
        ON r.id = e.race_id AND res.pit_number = e.pit_number
    LEFT JOIN race_details rd
        ON r.id = rd.race_id AND res.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc
        ON r.id = rc.race_id
    LEFT JOIN race_predictions rp_b
        ON r.id = rp_b.race_id
        AND rp_b.pit_number = CAST(res.pit_number AS INTEGER)
        AND rp_b.prediction_type = 'before'
    LEFT JOIN race_predictions rp_a
        ON r.id = rp_a.race_id
        AND rp_a.pit_number = CAST(res.pit_number AS INTEGER)
        AND rp_a.prediction_type = 'advance'
    WHERE r.race_date >= '2020-01-01'
      AND r.race_date <= '2025-12-31'
      AND res.rank IS NOT NULL
      AND CAST(res.rank AS INTEGER) BETWEEN 1 AND 6
    ORDER BY r.race_date, r.id, res.pit_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"読み込みレコード数: {len(df):,}")
    print(f"ユニークレース数:   {df['race_id'].nunique():,}")
    print(f"total_score有率:    {df['total_score'].notna().mean()*100:.1f}%")

    # 欠損値補完（中央値）
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().sum() > 0:
            df[col] = df[col].fillna(df[col].median())

    return df


def train_with_cv(df: pd.DataFrame, n_splits: int = 5):
    """TimeSeriesSplit でクロスバリデーション + 最終モデル学習"""
    print(f"\n=== TimeSeriesSplit ({n_splits}分割) CV ===")

    df = df.sort_values('race_date').reset_index(drop=True)
    race_ids = df['race_id'].unique()
    tscv = TimeSeriesSplit(n_splits=n_splits)

    cv_results = {'first_auc': [], 'second_auc': [], 'third_auc': []}

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
        'early_stopping_rounds': 50,
    }

    for fold, (train_idx, test_idx) in enumerate(tscv.split(race_ids), 1):
        print(f"\n--- Fold {fold}/{n_splits} ---")
        train_df = df[df['race_id'].isin(race_ids[train_idx])].copy()
        test_df  = df[df['race_id'].isin(race_ids[test_idx])].copy()
        print(f"  学習: {len(train_df):,}件  検証: {len(test_df):,}件")

        model = ConditionalRankModel()
        try:
            results = model.train_v2(train_df, test_df, params)
            for key in cv_results:
                if key in results:
                    cv_results[key].append(results[key])
        except Exception as e:
            print(f"  [警告] Fold {fold} エラー: {e}")

    print("\n=== CV 結果 ===")
    for key, vals in cv_results.items():
        if vals:
            print(f"  {key}: {np.mean(vals):.4f} (+/- {np.std(vals):.4f})")

    # 最終モデル: 直近6ヶ月を検証用に確保
    print("\n=== 最終モデル学習（全データ） ===")
    cutoff = (pd.to_datetime(df['race_date'].max()) - pd.Timedelta(days=180)).strftime('%Y-%m-%d')
    train_final = df[df['race_date'] < cutoff].copy()
    valid_final  = df[df['race_date'] >= cutoff].copy()
    print(f"  学習: {len(train_final):,}件  検証: {len(valid_final):,}件")

    final_model = ConditionalRankModel()
    final_results = final_model.train_v2(train_final, valid_final, params)

    return final_model, cv_results, final_results


def main():
    print("=" * 70)
    print("conditional_rank_v4 学習スクリプト")
    print("修正内容: pred_first_is_correct 除去（Phase1-b リーケージ修正）")
    print("=" * 70)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    df = load_training_data()

    final_model, cv_results, final_results = train_with_cv(df, n_splits=5)

    # モデル保存
    save_name = f"conditional_rank_v4_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    final_model.save(save_name)

    print("\n" + "=" * 70)
    print("=== 学習完了 ===")
    print(f"保存先: models/{save_name}_*.json")
    print("\n【CV 結果】")
    for key, vals in cv_results.items():
        if vals:
            print(f"  {key}: {np.mean(vals):.4f} (+/- {np.std(vals):.4f})")
    print("\n【最終モデル精度】")
    for key, val in final_results.items():
        print(f"  {key}: {val:.4f}")
    print("=" * 70)


if __name__ == '__main__':
    main()
