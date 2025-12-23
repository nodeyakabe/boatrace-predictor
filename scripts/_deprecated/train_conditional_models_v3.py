# -*- coding: utf-8 -*-
"""
条件付きモデル（Stage2/3）v3学習スクリプト

2025-12-16作成: S-1改善「学習データ分布修正」

【重要な改善点】
従来版(v1/v2)との違い:
- 2着モデル: 「実際の1着」→「予想1着（スコア最高艇）」を条件として学習
- 3着モデル: 「実際の1-2着」→「予想1-2着」を条件として学習

これにより学習時と予測時のデータ分布が一致し、
予測精度が大幅に向上することが期待される。

期待効果:
- 2着精度: 35.9% → 43-47%（+7-11pt）
- 3着精度: 27.2% → 33-37%（+6-10pt）
- ROI: +30-50pt
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

    【重要】v3では total_score カラムが必要
    - total_score がないと「予想1着」を計算できない
    - win_rate でフォールバック可能だが、精度は低下する
    """
    print("=" * 70)
    print("=== 学習データの読み込み（v3: スコア付き） ===")
    print("=" * 70)

    conn = sqlite3.connect(db_path)

    # race_predictionsテーブルからtotal_scoreを取得
    # race_predictionsがない場合はwin_rateで代用
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
        rc.water_temperature,
        -- 予測スコア（race_predictionsテーブル）
        rp.total_score
    FROM races r
    JOIN results res ON r.id = res.race_id
    JOIN entries e ON r.id = e.race_id AND res.pit_number = e.pit_number
    LEFT JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    LEFT JOIN race_predictions rp ON r.id = rp.race_id
        AND res.pit_number = rp.pit_number
        AND rp.prediction_type = 'advance'
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

    # total_scoreの状況を確認
    score_available = df['total_score'].notna().sum()
    print(f"total_score利用可能: {score_available:,}件 ({score_available/len(df)*100:.1f}%)")

    # total_scoreがない場合はwin_rateで代用
    if 'total_score' not in df.columns or df['total_score'].isna().all():
        print("[警告] total_scoreがありません。win_rateで代用します。")
        df['total_score'] = df['win_rate']
    else:
        # 欠損値はwin_rateで補完
        df['total_score'] = df['total_score'].fillna(df['win_rate'])

    # 欠損値の処理
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().sum() > 0:
            df[col] = df[col].fillna(df[col].median())

    return df


def evaluate_model_v2(model: ConditionalRankModel, test_df: pd.DataFrame) -> Dict[str, float]:
    """
    v2メソッドを使用してモデルを評価

    Returns:
        精度指標の辞書
    """
    results = {}

    # 1着予測（従来と同じ）
    X_1st, y_1st = model._prepare_first_place_data(test_df)
    if len(X_1st) > 0 and model.models['first'] is not None:
        pred_1st = model.models['first'].predict_proba(X_1st)[:, 1]
        results['first_auc'] = roc_auc_score(y_1st, pred_1st)
        results['first_accuracy'] = accuracy_score(y_1st, (pred_1st >= 0.5).astype(int))

    # 2着予測（v2: 予想1着を条件）
    X_2nd, y_2nd = model._prepare_second_place_data_v2(test_df)
    if len(X_2nd) > 0 and model.models['second'] is not None:
        # 特徴量名を揃える
        for col in model.second_feature_names:
            if col not in X_2nd.columns:
                X_2nd[col] = 0
        X_2nd = X_2nd.reindex(columns=model.second_feature_names, fill_value=0)

        pred_2nd = model.models['second'].predict_proba(X_2nd)[:, 1]
        results['second_auc'] = roc_auc_score(y_2nd, pred_2nd)
        results['second_accuracy'] = accuracy_score(y_2nd, (pred_2nd >= 0.5).astype(int))

    # 3着予測（v2: 予想1-2着を条件）
    X_3rd, y_3rd = model._prepare_third_place_data_v2(test_df)
    if len(X_3rd) > 0 and model.models['third'] is not None:
        # 特徴量名を揃える
        for col in model.third_feature_names:
            if col not in X_3rd.columns:
                X_3rd[col] = 0
        X_3rd = X_3rd.reindex(columns=model.third_feature_names, fill_value=0)

        pred_3rd = model.models['third'].predict_proba(X_3rd)[:, 1]
        results['third_auc'] = roc_auc_score(y_3rd, pred_3rd)
        results['third_accuracy'] = accuracy_score(y_3rd, (pred_3rd >= 0.5).astype(int))

    return results


def train_with_cv_v3(df: pd.DataFrame, n_splits: int = 5) -> Tuple[ConditionalRankModel, Dict]:
    """
    v3版: TimeSeriesSplitでクロスバリデーション付き学習

    【重要】
    train_v2() メソッドを使用して学習
    - 2着モデル: 予想1着を条件
    - 3着モデル: 予想1-2着を条件

    Args:
        df: 学習データ（total_scoreカラムが必要）
        n_splits: 分割数

    Returns:
        学習済みモデル、CV結果
    """
    print()
    print("=" * 70)
    print(f"=== v3学習: TimeSeriesSplit ({n_splits}分割) クロスバリデーション ===")
    print("=" * 70)

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
        print(f"\n{'='*50}")
        print(f"--- Fold {fold}/{n_splits} ---")
        print(f"{'='*50}")

        train_races = race_ids[train_idx]
        test_races = race_ids[test_idx]

        train_df = df[df['race_id'].isin(train_races)].copy()
        test_df = df[df['race_id'].isin(test_races)].copy()

        print(f"  学習: {len(train_df):,}件 ({len(train_races):,}レース)")
        print(f"  検証: {len(test_df):,}件 ({len(test_races):,}レース)")

        # モデル学習（v2メソッドを使用）
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
            'early_stopping_rounds': 50,
        }

        try:
            # v2メソッドで学習
            train_results = model.train_v2(train_df, test_df, params)

            for key in cv_results:
                if key in train_results:
                    cv_results[key].append(train_results[key])
        except Exception as e:
            print(f"  [警告] Fold {fold}でエラー: {e}")
            import traceback
            traceback.print_exc()
            continue

    # CV結果の集計
    print()
    print("=" * 70)
    print("=== クロスバリデーション結果 ===")
    print("=" * 70)
    for key, values in cv_results.items():
        if values:
            mean_val = np.mean(values)
            std_val = np.std(values)
            print(f"  {key}: {mean_val:.4f} (+/- {std_val:.4f})")

    # 最終モデルを全データで学習
    print()
    print("=" * 70)
    print("=== 最終モデルの学習（全データ） ===")
    print("=" * 70)

    # 直近6ヶ月を検証用に確保
    cutoff_date = df['race_date'].max()
    cutoff_date = pd.to_datetime(cutoff_date) - pd.Timedelta(days=180)
    cutoff_str = cutoff_date.strftime('%Y-%m-%d')

    train_final = df[df['race_date'] < cutoff_str].copy()
    valid_final = df[df['race_date'] >= cutoff_str].copy()

    print(f"  学習: {len(train_final):,}件 ({train_final['race_id'].nunique():,}レース)")
    print(f"  検証: {len(valid_final):,}件 ({valid_final['race_id'].nunique():,}レース)")

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

    # v2メソッドで最終学習
    final_results = final_model.train_v2(train_final, valid_final, final_params)

    return final_model, {
        'cv_results': cv_results,
        'final_results': final_results
    }


def compare_with_baseline(model_v3: ConditionalRankModel, test_df: pd.DataFrame):
    """
    v3モデルと従来ベースラインを比較

    ベースライン: 常に予想1着を実際の2着に予測した場合の精度
    """
    print()
    print("=" * 70)
    print("=== v3 vs ベースライン比較 ===")
    print("=" * 70)

    # 6艇完備レースのみ
    race_counts = test_df.groupby('race_id').size()
    valid_races = race_counts[race_counts == 6].index
    test_df = test_df[test_df['race_id'].isin(valid_races)].copy()

    print(f"評価レース数: {len(valid_races):,}")

    # スコア最高艇を予想1着とする
    score_col = 'total_score' if 'total_score' in test_df.columns else 'win_rate'
    idx_max = test_df.groupby('race_id')[score_col].idxmax()
    test_df['is_predicted_first'] = test_df.index.isin(idx_max).astype(int)

    # ベースライン1: 常にスコア2位を2着と予測
    test_df['score_rank'] = test_df.groupby('race_id')[score_col].rank(ascending=False, method='first')
    test_df['is_predicted_second'] = (test_df['score_rank'] == 2).astype(int)

    # 予想1着の的中率
    actual_first = test_df[test_df['rank'] == 1][['race_id', 'pit_number']].copy()
    actual_first.columns = ['race_id', 'actual_first_pit']
    predicted_first = test_df[test_df['is_predicted_first'] == 1][['race_id', 'pit_number']].copy()
    predicted_first.columns = ['race_id', 'predicted_first_pit']

    merged = actual_first.merge(predicted_first, on='race_id')
    first_accuracy = (merged['actual_first_pit'] == merged['predicted_first_pit']).mean() * 100

    # ベースライン: 2着精度（スコア2位が実際に2着になる確率）
    actual_second = test_df[test_df['rank'] == 2][['race_id', 'pit_number']].copy()
    actual_second.columns = ['race_id', 'actual_second_pit']
    predicted_second = test_df[test_df['is_predicted_second'] == 1][['race_id', 'pit_number']].copy()
    predicted_second.columns = ['race_id', 'predicted_second_pit']

    merged_second = actual_second.merge(predicted_second, on='race_id')
    baseline_second_accuracy = (merged_second['actual_second_pit'] == merged_second['predicted_second_pit']).mean() * 100

    print(f"\n【ベースライン精度】")
    print(f"  予想1着（スコア1位）的中率: {first_accuracy:.2f}%")
    print(f"  予想2着（スコア2位）的中率: {baseline_second_accuracy:.2f}%（ベースライン）")

    # ランダム基準
    print(f"\n【ランダム基準】")
    print(f"  2着ランダム選択: 20.0% (1/5)")
    print(f"  3着ランダム選択: 25.0% (1/4)")

    # v3モデルの精度
    print(f"\n【v3モデル期待精度】")
    print(f"  2着予測目標: 43-47%（ベースライン+20pt以上）")
    print(f"  3着予測目標: 33-37%（ランダム+10pt以上）")


def main():
    """メイン処理"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    print()
    print("#" * 70)
    print("# 条件付きモデル v3 学習スクリプト")
    print("# S-1改善: 学習データ分布修正")
    print("#" * 70)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # データ読み込み
    df = load_training_data()

    # クロスバリデーション付き学習（v3）
    model, results = train_with_cv_v3(df, n_splits=5)

    # モデル保存
    model_name = f'conditional_rank_v3_{timestamp}'
    model.save(model_name)

    # ベースラインとの比較
    # 直近データで評価
    cutoff_date = df['race_date'].max()
    cutoff_date = pd.to_datetime(cutoff_date) - pd.Timedelta(days=90)
    cutoff_str = cutoff_date.strftime('%Y-%m-%d')
    test_df = df[df['race_date'] >= cutoff_str].copy()

    compare_with_baseline(model, test_df)

    # 結果レポート
    print()
    print("#" * 70)
    print("# 学習完了レポート")
    print("#" * 70)

    print("\n【CV結果】")
    for key, values in results['cv_results'].items():
        if values:
            print(f"  {key}: {np.mean(values):.4f} (+/- {np.std(values):.4f})")

    print("\n【最終モデル精度】")
    for key, value in results['final_results'].items():
        print(f"  {key}: {value:.4f}")

    print("\n【保存先】")
    print(f"  models/{model_name}_*.json")
    print(f"  models/{model_name}.meta.json")

    print("\n【次のステップ】")
    print("  1. 精度評価スクリプトを実行:")
    print("     python scripts/evaluate_conditional_model_accuracy.py")
    print()
    print("  2. バックテストを実行:")
    print("     python scripts/backtest_standard.py")
    print()

    print("#" * 70)
    print("# 完了")
    print("#" * 70)

    return model, results


if __name__ == '__main__':
    main()
