"""
conditional_rank_v4b 再学習スクリプト

v4b の変更点（v4との差分）:
- total_score を特徴量から除外
  （ルールベース出力が汚染している問題を解消、独立した信号を確保）
- 学習期間: 2020-01-01 〜 2024-12-31
- 検証期間: 2025-01-01 〜 2025-12-31 (OOS)
  （2025年を完全 hold-out にして out-of-sample 評価を可能にする）
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


def load_training_data(db_path: str = 'data/boatrace.db',
                       start: str = '2020-01-01',
                       end:   str = '2024-12-31') -> pd.DataFrame:
    """
    学習用データをDBから読み込み。
    v4b: total_score を除外（ルールベース出力の汚染を排除）
    """
    print(f"=== 学習データの読み込み ({start} 〜 {end}) ===")
    conn = sqlite3.connect(db_path)

    query = f"""
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
        rc.water_temperature
        -- total_score は除外（v4b: ルールベース出力の汚染排除）
    FROM races r
    JOIN results res
        ON r.id = res.race_id
    JOIN entries e
        ON r.id = e.race_id AND res.pit_number = e.pit_number
    LEFT JOIN race_details rd
        ON r.id = rd.race_id AND res.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc
        ON r.id = rc.race_id
    WHERE r.race_date >= '{start}'
      AND r.race_date <= '{end}'
      AND res.rank IS NOT NULL
      AND CAST(res.rank AS INTEGER) BETWEEN 1 AND 6
    ORDER BY r.race_date, r.id, res.pit_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"読み込みレコード数: {len(df):,}")
    print(f"ユニークレース数:   {df['race_id'].nunique():,}")

    # 欠損値補完（中央値）
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().sum() > 0:
            df[col] = df[col].fillna(df[col].median())

    return df


def train_model(df: pd.DataFrame, valid_df: pd.DataFrame) -> tuple:
    """モデル学習（Early Stopping + AUC返却）"""
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
    model = ConditionalRankModel()
    results = model.train_v2(df, valid_df, params)
    return model, results


def main():
    TRAIN_START = '2020-01-01'
    TRAIN_END   = '2024-12-31'
    VALID_START = '2025-01-01'   # 1年間完全 hold-out
    VALID_END   = '2025-12-31'

    print("=" * 70)
    print("conditional_rank_v4b 学習スクリプト")
    print("変更点: total_score除外（ルールベース汚染の排除）")
    print(f"学習: {TRAIN_START} 〜 {TRAIN_END}")
    print(f"検証: {VALID_START} 〜 {VALID_END}  ← 完全OOS (2025年)")
    print("=" * 70)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    train_df = load_training_data(start=TRAIN_START, end=TRAIN_END)
    valid_df = load_training_data(start=VALID_START, end=VALID_END)

    print(f"\n=== モデル学習 ===")
    print(f"  学習: {len(train_df):,}件  検証: {len(valid_df):,}件")

    model, results = train_model(train_df, valid_df)

    # モデル保存
    save_name = f"conditional_rank_v4b_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    model.save(save_name)

    print("\n" + "=" * 70)
    print("=== 学習完了 ===")
    print(f"保存先: models/{save_name}_*.json")
    print("\n【最終モデル精度（2025年OOS）】")
    for key, val in results.items():
        print(f"  {key}: {val:.4f}")
    print("=" * 70)


if __name__ == '__main__':
    main()
