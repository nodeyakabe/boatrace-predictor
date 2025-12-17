"""
条件付き着順予測モデル
Phase 2.1: 1着→2着→3着の段階的予測モデル（最重要改善）
"""
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from typing import Dict, List, Tuple, Optional
import json
import os
from datetime import datetime


class ConditionalRankModel:
    """
    条件付き着順予測モデル

    従来: 1着確率から2着・3着を疑似推定
    改善: 1着確定後→2着予測、1-2着確定後→3着予測
    """

    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        self.models = {
            'first': None,   # 1着予測モデル
            'second': None,  # 2着予測モデル（1着条件付き）
            'third': None,   # 3着予測モデル（1-2着条件付き）
        }
        self.feature_names = None
        self.second_feature_names = None
        self.third_feature_names = None

    def _prepare_first_place_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """1着予測用データを準備"""
        # 非数値カラムと不要なカラムを除外
        exclude_cols = ['rank', 'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'racer_rank', 'racer_name', 'motor_number',
                       'boat_number', 'result_rank']
        X = df.drop([col for col in exclude_cols if col in df.columns], axis=1, errors='ignore')
        # object型のカラムを除外
        X = X.select_dtypes(include=[np.number])
        y = (df['rank'] == 1).astype(int)
        return X, y.values

    def _prepare_second_place_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        2着予測用データを準備（1着が確定した条件下）- ベクトル化版

        改善点（2025-12-15）:
        - 1着艇との相対特徴量を追加（差分特徴量）
        - 1着艇のコースとの位置関係を追加
        - 重要な特徴量に絞って伝達（特徴量爆発を防ぐ）

        各レースで1着艇を除いた5艇の中から2着を予測
        """
        # 6艇完備のレースのみを抽出
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df = df[df['race_id'].isin(valid_races)].copy()

        if len(df) == 0:
            return pd.DataFrame(), np.array([])

        # 1着艇の情報を取得
        first_place = df[df['rank'] == 1][['race_id', 'pit_number']].copy()
        first_place.columns = ['race_id', 'first_pit']

        # 重要な特徴量を選定（特徴量爆発を防ぐ）
        # 直接伝達する特徴量
        key_features = [c for c in df.columns if c not in ['rank', 'race_id', 'pit_number'] and
                       df[c].dtype in [np.float64, np.int64, np.float32, np.int32]]

        # 相対特徴量を計算するための主要指標
        relative_feature_cols = [c for c in key_features if any(kw in c.lower() for kw in
            ['win_rate', 'score', 'st_', 'motor', 'exhibition', 'course', 'total'])]

        # 1着艇の特徴量を取得
        first_features = df[df['rank'] == 1].copy()
        first_features = first_features[['race_id'] + key_features]
        first_features.columns = ['race_id'] + [f'first_place_{c}' for c in key_features]

        # 1着艇を除外
        df_with_first = df.merge(first_place, on='race_id')
        remaining = df_with_first[df_with_first['pit_number'] != df_with_first['first_pit']].copy()

        # 1着艇の特徴量をマージ
        remaining = remaining.merge(first_features, on='race_id')

        # === 相対特徴量の追加（2025-12-15改善） ===
        # 候補艇と1着艇の差分を計算
        for col in relative_feature_cols:
            first_col = f'first_place_{col}'
            if first_col in remaining.columns and col in remaining.columns:
                remaining[f'diff_first_{col}'] = remaining[col] - remaining[first_col]

        # 1着艇のコースとの位置関係
        if 'pit_number' in remaining.columns:
            remaining['course_diff_from_first'] = remaining['pit_number'] - remaining['first_pit']
            remaining['is_inner_than_first'] = (remaining['course_diff_from_first'] < 0).astype(int)
            remaining['is_outer_than_first'] = (remaining['course_diff_from_first'] > 0).astype(int)

        # ラベルを先に抽出（remainingから）
        y = (remaining['rank'] == 2).astype(int).values

        # 不要なカラムを削除
        remaining = remaining.drop(['first_pit', 'rank', 'race_id', 'pit_number'], axis=1, errors='ignore')

        # 特徴量のみを抽出
        X = remaining.select_dtypes(include=[np.number])

        return X, y

    def _prepare_second_place_data_v2(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        2着予測用データを準備（予想1着を条件とする）- v2改善版

        【重要な改善点（2025-12-16 S-1）】
        従来版との違い:
        - 従来: 「実際の1着」を条件として学習
        - v2: 「予想1着（スコア最高艇）」を条件として学習

        これにより、学習時と予測時のデータ分布が一致し、
        予想1着が外れた場合でも2着予測精度が向上する。

        期待効果:
        - 2着精度: 35.9% → 43-47%（+7-11pt）
        - 予想1着外れ時の2着精度: 16.93% → 22-24%（+5-7pt）
        """
        # 6艇完備のレースのみを抽出
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df = df[df['race_id'].isin(valid_races)].copy()

        if len(df) == 0:
            return pd.DataFrame(), np.array([])

        # スコアベースで予想1着を計算
        # total_scoreがあればそれを使用、なければwin_rateを使用
        score_col = 'total_score' if 'total_score' in df.columns else 'win_rate'

        if score_col not in df.columns:
            # スコアカラムがない場合は従来版にフォールバック
            print("[警告] スコアカラムが見つかりません。従来版にフォールバックします。")
            return self._prepare_second_place_data(df)

        # 各レースでスコア最高艇を予想1着とする
        idx_max = df.groupby('race_id')[score_col].idxmax()
        df['is_predicted_first'] = df.index.isin(idx_max).astype(int)

        # 予想1着艇の情報を取得
        predicted_first = df[df['is_predicted_first'] == 1][['race_id', 'pit_number']].copy()
        predicted_first.columns = ['race_id', 'predicted_first_pit']

        # 重要な特徴量を選定
        key_features = [c for c in df.columns if c not in
                       ['rank', 'race_id', 'pit_number', 'is_predicted_first'] and
                       df[c].dtype in [np.float64, np.int64, np.float32, np.int32]]

        # 相対特徴量を計算するための主要指標
        relative_feature_cols = [c for c in key_features if any(kw in c.lower() for kw in
            ['win_rate', 'score', 'st_', 'motor', 'exhibition', 'course', 'total'])]

        # 予想1着艇の特徴量を取得
        first_features = df[df['is_predicted_first'] == 1][['race_id'] + key_features].copy()
        first_features.columns = ['race_id'] + [f'pred_first_{c}' for c in key_features]

        # 予想1着艇を除外した5艇
        df_merged = df.merge(predicted_first, on='race_id')
        remaining = df_merged[df_merged['pit_number'] != df_merged['predicted_first_pit']].copy()

        # 予想1着艇の特徴量をマージ
        remaining = remaining.merge(first_features, on='race_id')

        # === 相対特徴量の追加 ===
        for col in relative_feature_cols:
            pred_col = f'pred_first_{col}'
            if pred_col in remaining.columns and col in remaining.columns:
                remaining[f'diff_pred_first_{col}'] = remaining[col] - remaining[pred_col]

        # コース位置関係
        if 'pit_number' in remaining.columns:
            remaining['course_diff_from_pred_first'] = remaining['pit_number'] - remaining['predicted_first_pit']
            remaining['is_inner_than_pred_first'] = (remaining['course_diff_from_pred_first'] < 0).astype(int)
            remaining['is_outer_than_pred_first'] = (remaining['course_diff_from_pred_first'] > 0).astype(int)

        # === 予想1着の的中フラグを追加（学習時のみ利用可能） ===
        # 実際の1着と予想1着が一致しているかどうか
        actual_first = df[df['rank'] == 1][['race_id', 'pit_number']].copy()
        actual_first.columns = ['race_id', 'actual_first_pit']
        remaining = remaining.merge(actual_first, on='race_id', how='left')

        if 'actual_first_pit' in remaining.columns and 'predicted_first_pit' in remaining.columns:
            remaining['pred_first_is_correct'] = (
                remaining['predicted_first_pit'] == remaining['actual_first_pit']
            ).astype(int)
            # 実際の1着情報は削除（予測時には使えない）
            remaining = remaining.drop(['actual_first_pit'], axis=1, errors='ignore')

        # ラベル: 実際の2着かどうか
        y = (remaining['rank'] == 2).astype(int).values

        # 不要なカラムを削除
        remaining = remaining.drop(
            ['predicted_first_pit', 'rank', 'race_id', 'pit_number', 'is_predicted_first'],
            axis=1, errors='ignore'
        )

        # 特徴量のみを抽出
        X = remaining.select_dtypes(include=[np.number])

        return X, y

    def _prepare_third_place_data_v2(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        3着予測用データを準備（予想1-2着を条件とする）- v2改善版

        【重要な改善点（2025-12-16 S-1）】
        従来版との違い:
        - 従来: 「実際の1-2着」を条件として学習
        - v2: 「予想1-2着（スコア上位2艇）」を条件として学習

        これにより、学習時と予測時のデータ分布が一致し、
        予想1-2着が外れた場合でも3着予測精度が向上する。

        期待効果:
        - 3着精度: 27.2% → 33-37%（+6-10pt）
        """
        # 6艇完備のレースのみを抽出
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df = df[df['race_id'].isin(valid_races)].copy()

        if len(df) == 0:
            return pd.DataFrame(), np.array([])

        # スコアベースで予想1-2着を計算
        score_col = 'total_score' if 'total_score' in df.columns else 'win_rate'

        if score_col not in df.columns:
            print("[警告] スコアカラムが見つかりません。従来版にフォールバックします。")
            return self._prepare_third_place_data(df)

        # 各レースでスコア順位を計算
        df['score_rank'] = df.groupby('race_id')[score_col].rank(ascending=False, method='first')
        df['is_predicted_first'] = (df['score_rank'] == 1).astype(int)
        df['is_predicted_second'] = (df['score_rank'] == 2).astype(int)

        # 予想1着・2着艇の情報を取得
        predicted_first = df[df['is_predicted_first'] == 1][['race_id', 'pit_number']].copy()
        predicted_first.columns = ['race_id', 'predicted_first_pit']

        predicted_second = df[df['is_predicted_second'] == 1][['race_id', 'pit_number']].copy()
        predicted_second.columns = ['race_id', 'predicted_second_pit']

        # 重要な特徴量を選定
        key_features = [c for c in df.columns if c not in
                       ['rank', 'race_id', 'pit_number', 'is_predicted_first',
                        'is_predicted_second', 'score_rank'] and
                       df[c].dtype in [np.float64, np.int64, np.float32, np.int32]]

        relative_feature_cols = [c for c in key_features if any(kw in c.lower() for kw in
            ['win_rate', 'score', 'st_', 'motor', 'exhibition', 'course', 'total'])]

        # 予想1着・2着艇の特徴量を取得
        first_features = df[df['is_predicted_first'] == 1][['race_id'] + key_features].copy()
        first_features.columns = ['race_id'] + [f'pred_first_{c}' for c in key_features]

        second_features = df[df['is_predicted_second'] == 1][['race_id'] + key_features].copy()
        second_features.columns = ['race_id'] + [f'pred_second_{c}' for c in key_features]

        # 予想1-2着艇を除外した4艇
        df_merged = df.merge(predicted_first, on='race_id').merge(predicted_second, on='race_id')
        remaining = df_merged[
            (df_merged['pit_number'] != df_merged['predicted_first_pit']) &
            (df_merged['pit_number'] != df_merged['predicted_second_pit'])
        ].copy()

        # 予想1-2着艇の特徴量をマージ
        remaining = remaining.merge(first_features, on='race_id')
        remaining = remaining.merge(second_features, on='race_id')

        # === 相対特徴量の追加 ===
        for col in relative_feature_cols:
            first_col = f'pred_first_{col}'
            second_col = f'pred_second_{col}'
            if first_col in remaining.columns and col in remaining.columns:
                remaining[f'diff_pred_first_{col}'] = remaining[col] - remaining[first_col]
            if second_col in remaining.columns and col in remaining.columns:
                remaining[f'diff_pred_second_{col}'] = remaining[col] - remaining[second_col]
            # 予想1-2着間の差分（レース展開情報）
            if first_col in remaining.columns and second_col in remaining.columns:
                remaining[f'gap_pred_1st_2nd_{col}'] = remaining[first_col] - remaining[second_col]

        # コース位置関係
        if 'pit_number' in remaining.columns:
            remaining['course_diff_from_pred_first'] = remaining['pit_number'] - remaining['predicted_first_pit']
            remaining['course_diff_from_pred_second'] = remaining['pit_number'] - remaining['predicted_second_pit']
            remaining['is_inner_than_pred_first'] = (remaining['course_diff_from_pred_first'] < 0).astype(int)
            remaining['is_outer_than_pred_first'] = (remaining['course_diff_from_pred_first'] > 0).astype(int)
            remaining['is_inner_than_pred_second'] = (remaining['course_diff_from_pred_second'] < 0).astype(int)
            remaining['is_between_pred_first_second'] = (
                ((remaining['pit_number'] > remaining['predicted_first_pit']) &
                 (remaining['pit_number'] < remaining['predicted_second_pit'])) |
                ((remaining['pit_number'] < remaining['predicted_first_pit']) &
                 (remaining['pit_number'] > remaining['predicted_second_pit']))
            ).astype(int)

        # ラベル: 実際の3着かどうか
        y = (remaining['rank'] == 3).astype(int).values

        # 不要なカラムを削除
        remaining = remaining.drop(
            ['predicted_first_pit', 'predicted_second_pit', 'rank', 'race_id',
             'pit_number', 'is_predicted_first', 'is_predicted_second', 'score_rank'],
            axis=1, errors='ignore'
        )

        X = remaining.select_dtypes(include=[np.number])

        return X, y

    def _prepare_third_place_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        3着予測用データを準備（1着・2着が確定した条件下）- ベクトル化版

        改善点（2025-12-15）:
        - 1着艇・2着艇との相対特徴量を追加（差分特徴量）
        - 1着艇・2着艇のコースとの位置関係を追加
        - 1-2着間の差分情報も追加（レースの展開を反映）
        - 重要な特徴量に絞って伝達（特徴量爆発を防ぐ）

        各レースで1着・2着艇を除いた4艇の中から3着を予測
        """
        # 6艇完備のレースのみを抽出
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df = df[df['race_id'].isin(valid_races)].copy()

        if len(df) == 0:
            return pd.DataFrame(), np.array([])

        # 1着・2着艇の情報を取得
        first_place = df[df['rank'] == 1][['race_id', 'pit_number']].copy()
        first_place.columns = ['race_id', 'first_pit']

        second_place = df[df['rank'] == 2][['race_id', 'pit_number']].copy()
        second_place.columns = ['race_id', 'second_pit']

        # 重要な特徴量を選定（特徴量爆発を防ぐ）
        key_features = [c for c in df.columns if c not in ['rank', 'race_id', 'pit_number'] and
                       df[c].dtype in [np.float64, np.int64, np.float32, np.int32]]

        # 相対特徴量を計算するための主要指標
        relative_feature_cols = [c for c in key_features if any(kw in c.lower() for kw in
            ['win_rate', 'score', 'st_', 'motor', 'exhibition', 'course', 'total'])]

        # 1着・2着艇の特徴量を取得
        first_features = df[df['rank'] == 1][['race_id'] + key_features].copy()
        first_features.columns = ['race_id'] + [f'first_place_{c}' for c in key_features]

        second_features = df[df['rank'] == 2][['race_id'] + key_features].copy()
        second_features.columns = ['race_id'] + [f'second_place_{c}' for c in key_features]

        # 1着・2着艇を除外
        df_with_places = df.merge(first_place, on='race_id').merge(second_place, on='race_id')
        remaining = df_with_places[
            (df_with_places['pit_number'] != df_with_places['first_pit']) &
            (df_with_places['pit_number'] != df_with_places['second_pit'])
        ].copy()

        # 1着・2着艇の特徴量をマージ
        remaining = remaining.merge(first_features, on='race_id')
        remaining = remaining.merge(second_features, on='race_id')

        # === 相対特徴量の追加（2025-12-15改善） ===
        # 候補艇と1着艇の差分を計算
        for col in relative_feature_cols:
            first_col = f'first_place_{col}'
            second_col = f'second_place_{col}'
            if first_col in remaining.columns and col in remaining.columns:
                remaining[f'diff_first_{col}'] = remaining[col] - remaining[first_col]
            if second_col in remaining.columns and col in remaining.columns:
                remaining[f'diff_second_{col}'] = remaining[col] - remaining[second_col]
            # 1-2着間の差分（レース展開情報）
            if first_col in remaining.columns and second_col in remaining.columns:
                remaining[f'gap_1st_2nd_{col}'] = remaining[first_col] - remaining[second_col]

        # 1着艇・2着艇のコースとの位置関係
        if 'pit_number' in remaining.columns:
            remaining['course_diff_from_first'] = remaining['pit_number'] - remaining['first_pit']
            remaining['course_diff_from_second'] = remaining['pit_number'] - remaining['second_pit']
            remaining['is_inner_than_first'] = (remaining['course_diff_from_first'] < 0).astype(int)
            remaining['is_outer_than_first'] = (remaining['course_diff_from_first'] > 0).astype(int)
            remaining['is_inner_than_second'] = (remaining['course_diff_from_second'] < 0).astype(int)
            remaining['is_between_first_second'] = (
                ((remaining['pit_number'] > remaining['first_pit']) & (remaining['pit_number'] < remaining['second_pit'])) |
                ((remaining['pit_number'] < remaining['first_pit']) & (remaining['pit_number'] > remaining['second_pit']))
            ).astype(int)

        # ラベルを先に抽出（remainingから）
        y = (remaining['rank'] == 3).astype(int).values

        # 不要なカラムを削除
        remaining = remaining.drop(['first_pit', 'second_pit', 'rank', 'race_id', 'pit_number'], axis=1, errors='ignore')

        # 特徴量のみを抽出
        X = remaining.select_dtypes(include=[np.number])

        return X, y

    def train(self, train_df: pd.DataFrame, valid_df: pd.DataFrame = None,
              params: Dict = None) -> Dict[str, float]:
        """全モデルを学習"""
        if params is None:
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': 6,
                'learning_rate': 0.05,
                'n_estimators': 500,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'min_child_weight': 3,
                'gamma': 0.1,
                'random_state': 42,
                'n_jobs': -1,
                'use_label_encoder': False,
            }

        results = {}

        # 1着モデルの学習
        print("=== 1着予測モデルの学習 ===")
        X_train_1st, y_train_1st = self._prepare_first_place_data(train_df)
        self.feature_names = list(X_train_1st.columns)

        if valid_df is not None:
            X_valid_1st, y_valid_1st = self._prepare_first_place_data(valid_df)
            self.models['first'] = xgb.XGBClassifier(**params)
            self.models['first'].fit(
                X_train_1st, y_train_1st,
                eval_set=[(X_valid_1st, y_valid_1st)],
                verbose=False
            )
            from sklearn.metrics import roc_auc_score
            pred_1st = self.models['first'].predict_proba(X_valid_1st)[:, 1]
            results['first_auc'] = roc_auc_score(y_valid_1st, pred_1st)
            print(f"1着モデル AUC: {results['first_auc']:.4f}")
        else:
            self.models['first'] = xgb.XGBClassifier(**params)
            self.models['first'].fit(X_train_1st, y_train_1st, verbose=False)

        # 2着モデルの学習
        print("=== 2着予測モデルの学習 ===")
        X_train_2nd, y_train_2nd = self._prepare_second_place_data(train_df)
        self.second_feature_names = list(X_train_2nd.columns)

        if len(X_train_2nd) > 0:
            if valid_df is not None:
                X_valid_2nd, y_valid_2nd = self._prepare_second_place_data(valid_df)
                self.models['second'] = xgb.XGBClassifier(**params)
                self.models['second'].fit(
                    X_train_2nd, y_train_2nd,
                    eval_set=[(X_valid_2nd, y_valid_2nd)],
                    verbose=False
                )
                pred_2nd = self.models['second'].predict_proba(X_valid_2nd)[:, 1]
                results['second_auc'] = roc_auc_score(y_valid_2nd, pred_2nd)
                print(f"2着モデル AUC: {results['second_auc']:.4f}")
            else:
                self.models['second'] = xgb.XGBClassifier(**params)
                self.models['second'].fit(X_train_2nd, y_train_2nd, verbose=False)

        # 3着モデルの学習
        print("=== 3着予測モデルの学習 ===")
        X_train_3rd, y_train_3rd = self._prepare_third_place_data(train_df)
        self.third_feature_names = list(X_train_3rd.columns)

        if len(X_train_3rd) > 0:
            if valid_df is not None:
                X_valid_3rd, y_valid_3rd = self._prepare_third_place_data(valid_df)
                self.models['third'] = xgb.XGBClassifier(**params)
                self.models['third'].fit(
                    X_train_3rd, y_train_3rd,
                    eval_set=[(X_valid_3rd, y_valid_3rd)],
                    verbose=False
                )
                pred_3rd = self.models['third'].predict_proba(X_valid_3rd)[:, 1]
                results['third_auc'] = roc_auc_score(y_valid_3rd, pred_3rd)
                print(f"3着モデル AUC: {results['third_auc']:.4f}")
            else:
                self.models['third'] = xgb.XGBClassifier(**params)
                self.models['third'].fit(X_train_3rd, y_train_3rd, verbose=False)

        return results

    def train_v2(self, train_df: pd.DataFrame, valid_df: pd.DataFrame = None,
                 params: Dict = None) -> Dict[str, float]:
        """
        v2版: 予想1着/2着を条件とした学習（S-1改善版）

        【重要】
        従来の train() との違い:
        - 2着モデル: _prepare_second_place_data_v2() を使用（予想1着を条件）
        - 3着モデル: _prepare_third_place_data_v2() を使用（予想1-2着を条件）

        これにより学習時と予測時のデータ分布が一致し、
        予測精度が大幅に向上することが期待される。
        """
        if params is None:
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': 6,
                'learning_rate': 0.05,
                'n_estimators': 500,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'min_child_weight': 3,
                'gamma': 0.1,
                'random_state': 42,
                'n_jobs': -1,
                'use_label_encoder': False,
            }

        results = {}

        # 1着モデルの学習（従来と同じ）
        print("=" * 60)
        print("=== 1着予測モデルの学習（従来方式） ===")
        print("=" * 60)
        X_train_1st, y_train_1st = self._prepare_first_place_data(train_df)
        self.feature_names = list(X_train_1st.columns)
        print(f"1着学習データ: {len(X_train_1st)}件, 特徴量数: {len(self.feature_names)}")

        from sklearn.metrics import roc_auc_score

        if valid_df is not None:
            X_valid_1st, y_valid_1st = self._prepare_first_place_data(valid_df)
            self.models['first'] = xgb.XGBClassifier(**params)
            self.models['first'].fit(
                X_train_1st, y_train_1st,
                eval_set=[(X_valid_1st, y_valid_1st)],
                verbose=False
            )
            pred_1st = self.models['first'].predict_proba(X_valid_1st)[:, 1]
            results['first_auc'] = roc_auc_score(y_valid_1st, pred_1st)
            print(f"1着モデル AUC: {results['first_auc']:.4f}")
        else:
            self.models['first'] = xgb.XGBClassifier(**params)
            self.models['first'].fit(X_train_1st, y_train_1st, verbose=False)

        # 2着モデルの学習（v2版: 予想1着を条件）
        print()
        print("=" * 60)
        print("=== 2着予測モデルの学習（v2: 予想1着を条件） ===")
        print("=" * 60)
        X_train_2nd, y_train_2nd = self._prepare_second_place_data_v2(train_df)
        self.second_feature_names = list(X_train_2nd.columns)
        print(f"2着学習データ: {len(X_train_2nd)}件, 特徴量数: {len(self.second_feature_names)}")
        print(f"2着ラベル分布: 正例={y_train_2nd.sum()}, 負例={len(y_train_2nd) - y_train_2nd.sum()}")

        if len(X_train_2nd) > 0:
            if valid_df is not None:
                X_valid_2nd, y_valid_2nd = self._prepare_second_place_data_v2(valid_df)
                print(f"2着検証データ: {len(X_valid_2nd)}件")
                self.models['second'] = xgb.XGBClassifier(**params)
                self.models['second'].fit(
                    X_train_2nd, y_train_2nd,
                    eval_set=[(X_valid_2nd, y_valid_2nd)],
                    verbose=False
                )
                pred_2nd = self.models['second'].predict_proba(X_valid_2nd)[:, 1]
                results['second_auc'] = roc_auc_score(y_valid_2nd, pred_2nd)
                print(f"2着モデル AUC: {results['second_auc']:.4f}")
            else:
                self.models['second'] = xgb.XGBClassifier(**params)
                self.models['second'].fit(X_train_2nd, y_train_2nd, verbose=False)

        # 3着モデルの学習（v2版: 予想1-2着を条件）
        print()
        print("=" * 60)
        print("=== 3着予測モデルの学習（v2: 予想1-2着を条件） ===")
        print("=" * 60)
        X_train_3rd, y_train_3rd = self._prepare_third_place_data_v2(train_df)
        self.third_feature_names = list(X_train_3rd.columns)
        print(f"3着学習データ: {len(X_train_3rd)}件, 特徴量数: {len(self.third_feature_names)}")
        print(f"3着ラベル分布: 正例={y_train_3rd.sum()}, 負例={len(y_train_3rd) - y_train_3rd.sum()}")

        if len(X_train_3rd) > 0:
            if valid_df is not None:
                X_valid_3rd, y_valid_3rd = self._prepare_third_place_data_v2(valid_df)
                print(f"3着検証データ: {len(X_valid_3rd)}件")
                self.models['third'] = xgb.XGBClassifier(**params)
                self.models['third'].fit(
                    X_train_3rd, y_train_3rd,
                    eval_set=[(X_valid_3rd, y_valid_3rd)],
                    verbose=False
                )
                pred_3rd = self.models['third'].predict_proba(X_valid_3rd)[:, 1]
                results['third_auc'] = roc_auc_score(y_valid_3rd, pred_3rd)
                print(f"3着モデル AUC: {results['third_auc']:.4f}")
            else:
                self.models['third'] = xgb.XGBClassifier(**params)
                self.models['third'].fit(X_train_3rd, y_train_3rd, verbose=False)

        print()
        print("=" * 60)
        print("=== v2学習完了 ===")
        print("=" * 60)
        for k, v in results.items():
            print(f"  {k}: {v:.4f}")

        return results

    def predict_trifecta_probabilities(self, race_features: pd.DataFrame) -> Dict[str, float]:
        """
        三連単の全組み合わせ確率を予測（ベクトル化版）

        Args:
            race_features: 6艇の特徴量 (pit_number列を含む)

        Returns:
            {'1-2-3': 0.15, '1-3-2': 0.12, ...} 120通り
        """
        if len(race_features) != 6:
            raise ValueError("レースは6艇必要です")

        # 1着確率を計算
        X_1st = race_features.drop(['pit_number'], axis=1, errors='ignore')

        # 特徴量名を揃える
        for col in self.feature_names:
            if col not in X_1st.columns:
                X_1st[col] = 0
        X_1st = X_1st[self.feature_names]

        first_probs = self.models['first'].predict_proba(X_1st)[:, 1]
        first_probs = first_probs / first_probs.sum()

        pit_numbers = race_features['pit_number'].values.astype(int)

        # 基本特徴量をnumpy配列として取得（高速アクセス用）
        base_features = X_1st.values

        # 2着予測用の全データをバッチ生成（6x5=30パターン）
        second_batch_data = []
        second_batch_meta = []  # (first_idx, second_idx)

        for i in range(6):
            remaining_indices = [j for j in range(6) if j != i]
            for j in remaining_indices:
                # 候補艇の特徴量 + 1着艇の特徴量
                row_features = np.concatenate([base_features[j], base_features[i]])
                second_batch_data.append(row_features)
                second_batch_meta.append((i, j))

        # 2着予測（一括推論）
        if self.models['second'] is not None and self.second_feature_names:
            second_batch_df = pd.DataFrame(second_batch_data, columns=self.second_feature_names)
            second_raw_probs = self.models['second'].predict_proba(second_batch_df)[:, 1]
        else:
            second_raw_probs = np.ones(30) / 5

        # 3着予測用の全データをバッチ生成（6x5x4=120パターン）
        third_batch_data = []
        third_batch_meta = []  # (first_idx, second_idx, third_idx)

        batch_idx = 0
        for i in range(6):
            remaining_after_first = [j for j in range(6) if j != i]
            for j in remaining_after_first:
                remaining_after_second = [k for k in remaining_after_first if k != j]
                for k in remaining_after_second:
                    # 候補艇の特徴量 + 1着艇の特徴量 + 2着艇の特徴量
                    row_features = np.concatenate([base_features[k], base_features[i], base_features[j]])
                    third_batch_data.append(row_features)
                    third_batch_meta.append((i, j, k))
                batch_idx += 1

        # 3着予測（一括推論）
        if self.models['third'] is not None and self.third_feature_names:
            third_batch_df = pd.DataFrame(third_batch_data, columns=self.third_feature_names)
            third_raw_probs = self.models['third'].predict_proba(third_batch_df)[:, 1]
        else:
            third_raw_probs = np.ones(120) / 4

        # 確率の正規化と三連単確率の計算
        trifecta_probs = {}

        # 2着確率を正規化（各1着候補ごとに）
        second_probs_normalized = {}
        for i in range(6):
            indices = [idx for idx, (fi, _) in enumerate(second_batch_meta) if fi == i]
            raw_probs = second_raw_probs[indices]
            normalized = raw_probs / raw_probs.sum()
            for idx, norm_prob in zip(indices, normalized):
                second_probs_normalized[idx] = norm_prob

        # 3着確率を正規化（各1着-2着ペアごとに）
        third_probs_normalized = {}
        for i in range(6):
            for j in range(6):
                if j == i:
                    continue
                indices = [idx for idx, (fi, si, _) in enumerate(third_batch_meta) if fi == i and si == j]
                if indices:
                    raw_probs = third_raw_probs[indices]
                    normalized = raw_probs / raw_probs.sum()
                    for idx, norm_prob in zip(indices, normalized):
                        third_probs_normalized[idx] = norm_prob

        # 最終的な三連単確率を計算
        for third_idx, (first_i, second_j, third_k) in enumerate(third_batch_meta):
            # 対応する2着インデックスを探す
            second_idx = next(idx for idx, (fi, si) in enumerate(second_batch_meta) if fi == first_i and si == second_j)

            p_first = first_probs[first_i]
            p_second = second_probs_normalized[second_idx]
            p_third = third_probs_normalized[third_idx]

            trifecta_prob = p_first * p_second * p_third

            combination = f"{pit_numbers[first_i]}-{pit_numbers[second_j]}-{pit_numbers[third_k]}"
            trifecta_probs[combination] = float(trifecta_prob)

        return trifecta_probs

    def predict_trifecta_probabilities_v2(self, race_features: pd.DataFrame) -> Dict[str, float]:
        """
        三連単の全組み合わせ確率を予測（v2版: 予想1着/2着を条件とする）

        【重要】
        v2版では、学習時と同じく「予想1着（スコア最高艇）」を条件として予測する。
        これにより、学習時と予測時のデータ分布が一致する。

        Args:
            race_features: 6艇の特徴量 (pit_number列, total_scoreまたはwin_rate列を含む)

        Returns:
            {'1-2-3': 0.15, '1-3-2': 0.12, ...} 120通り
        """
        if len(race_features) != 6:
            raise ValueError("レースは6艇必要です")

        # 予想1着（スコア最高艇）を特定
        score_col = 'total_score' if 'total_score' in race_features.columns else 'win_rate'
        if score_col not in race_features.columns:
            # スコアがない場合は従来版にフォールバック
            return self.predict_trifecta_probabilities(race_features)

        # スコア順位を計算
        race_features = race_features.copy()
        race_features['score_rank'] = race_features[score_col].rank(ascending=False, method='first')
        predicted_first_idx = race_features[race_features['score_rank'] == 1].index[0]
        predicted_first_pit = race_features.loc[predicted_first_idx, 'pit_number']

        # 1着確率を計算
        X_1st = race_features.drop(['pit_number', 'score_rank'], axis=1, errors='ignore')

        # 特徴量名を揃える
        for col in self.feature_names:
            if col not in X_1st.columns:
                X_1st[col] = 0
        X_1st = X_1st[self.feature_names]

        first_probs = self.models['first'].predict_proba(X_1st)[:, 1]
        first_probs = first_probs / first_probs.sum()

        pit_numbers = race_features['pit_number'].values.astype(int)

        # インデックスとpit_numberの対応
        idx_to_pos = {idx: i for i, idx in enumerate(race_features.index)}
        predicted_first_pos = idx_to_pos[predicted_first_idx]

        # 2着予測: 予想1着を条件として、残り5艇の2着確率を計算
        # v2で学習したモデルは「予想1着」を条件としているため、
        # 全ての組み合わせで「予想1着」を固定して条件として使用
        base_features = X_1st.values
        predicted_first_features = base_features[predicted_first_pos]

        # 2着候補艇（予想1着を除く5艇）の確率を計算
        second_probs_for_pred_first = np.zeros(6)
        remaining_for_second = [i for i in range(6) if i != predicted_first_pos]

        if self.models['second'] is not None and self.second_feature_names:
            second_batch_data = []
            for j in remaining_for_second:
                row_features = np.concatenate([base_features[j], predicted_first_features])
                second_batch_data.append(row_features)

            # 特徴量数が一致しない場合の調整
            expected_cols = len(self.second_feature_names)
            actual_cols = len(second_batch_data[0])
            if actual_cols != expected_cols:
                # 不足分を0で埋める
                for i in range(len(second_batch_data)):
                    if actual_cols < expected_cols:
                        second_batch_data[i] = np.concatenate([
                            second_batch_data[i],
                            np.zeros(expected_cols - actual_cols)
                        ])
                    else:
                        second_batch_data[i] = second_batch_data[i][:expected_cols]

            second_batch_df = pd.DataFrame(second_batch_data, columns=self.second_feature_names)
            second_raw_probs = self.models['second'].predict_proba(second_batch_df)[:, 1]

            # 正規化
            second_raw_probs = second_raw_probs / second_raw_probs.sum()
            for i, j in enumerate(remaining_for_second):
                second_probs_for_pred_first[j] = second_raw_probs[i]
        else:
            # モデルがない場合は均等
            for j in remaining_for_second:
                second_probs_for_pred_first[j] = 1.0 / 5

        # 3着予測: 予想1着・予想2着を条件として、残り4艇の3着確率を計算
        # 全120通りを計算
        trifecta_probs = {}

        for i in range(6):  # 1着候補
            p_first = first_probs[i]

            for j in range(6):  # 2着候補
                if j == i:
                    continue

                # 2着確率
                if i == predicted_first_pos:
                    # 予想1着が実際に1着の場合
                    p_second = second_probs_for_pred_first[j]
                else:
                    # 予想1着が1着でない場合（v2学習とは異なるが、近似として使用）
                    p_second = second_probs_for_pred_first[j] if j != predicted_first_pos else 0
                    # 正規化
                    remaining_sum = sum(second_probs_for_pred_first[k] for k in range(6) if k != i and k != predicted_first_pos)
                    if remaining_sum > 0 and j != predicted_first_pos:
                        p_second = second_probs_for_pred_first[j] / (remaining_sum + second_probs_for_pred_first[predicted_first_pos]) if i != predicted_first_pos else p_second

                # 3着確率を計算
                remaining_for_third = [k for k in range(6) if k != i and k != j]

                if self.models['third'] is not None and self.third_feature_names:
                    # 予想1着と予想2着の特徴量
                    predicted_second_pos = remaining_for_second[np.argmax([second_probs_for_pred_first[k] for k in remaining_for_second])]
                    predicted_second_features = base_features[predicted_second_pos]

                    third_batch_data = []
                    for k in remaining_for_third:
                        row_features = np.concatenate([
                            base_features[k],
                            predicted_first_features,
                            predicted_second_features
                        ])
                        third_batch_data.append(row_features)

                    # 特徴量数調整
                    expected_cols = len(self.third_feature_names)
                    actual_cols = len(third_batch_data[0]) if third_batch_data else 0
                    if actual_cols != expected_cols and third_batch_data:
                        for idx in range(len(third_batch_data)):
                            if actual_cols < expected_cols:
                                third_batch_data[idx] = np.concatenate([
                                    third_batch_data[idx],
                                    np.zeros(expected_cols - actual_cols)
                                ])
                            else:
                                third_batch_data[idx] = third_batch_data[idx][:expected_cols]

                    if third_batch_data:
                        third_batch_df = pd.DataFrame(third_batch_data, columns=self.third_feature_names)
                        third_raw_probs = self.models['third'].predict_proba(third_batch_df)[:, 1]
                        third_raw_probs = third_raw_probs / third_raw_probs.sum()
                    else:
                        third_raw_probs = np.ones(4) / 4
                else:
                    third_raw_probs = np.ones(len(remaining_for_third)) / len(remaining_for_third)

                for k_idx, k in enumerate(remaining_for_third):
                    p_third = third_raw_probs[k_idx] if k_idx < len(third_raw_probs) else 0.25

                    trifecta_prob = p_first * p_second * p_third

                    combination = f"{pit_numbers[i]}-{pit_numbers[j]}-{pit_numbers[k]}"
                    trifecta_probs[combination] = float(trifecta_prob)

        # 正規化
        total = sum(trifecta_probs.values())
        if total > 0:
            trifecta_probs = {k: v / total for k, v in trifecta_probs.items()}

        return trifecta_probs

    def save(self, name: str = 'conditional_rank'):
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        for model_type, model in self.models.items():
            if model is not None:
                model_path = os.path.join(self.model_dir, f'{name}_{model_type}.json')
                model.save_model(model_path)

        # メタ情報を保存
        meta = {
            'feature_names': self.feature_names,
            'second_feature_names': self.second_feature_names,
            'third_feature_names': self.third_feature_names,
            'created_at': datetime.now().isoformat(),
            'model_types': list(self.models.keys())
        }
        meta_path = os.path.join(self.model_dir, f'{name}.meta.json')
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

        print(f"モデルを {self.model_dir} に保存しました")

    def load(self, name: str = 'conditional_rank'):
        """モデルを読み込み"""
        # メタ情報を読み込み
        meta_path = os.path.join(self.model_dir, f'{name}.meta.json')
        with open(meta_path, 'r') as f:
            meta = json.load(f)

        self.feature_names = meta['feature_names']
        self.second_feature_names = meta.get('second_feature_names', [])
        self.third_feature_names = meta.get('third_feature_names', [])

        for model_type in meta['model_types']:
            model_path = os.path.join(self.model_dir, f'{name}_{model_type}.json')
            if os.path.exists(model_path):
                self.models[model_type] = xgb.XGBClassifier()
                self.models[model_type].load_model(model_path)

        print(f"モデルを {self.model_dir} から読み込みました")


class TrifectaProbabilityCalculator:
    """三連単確率を計算するユーティリティクラス"""

    @staticmethod
    def from_win_probs_naive(win_probs: List[float]) -> Dict[str, float]:
        """
        従来方式: 1着確率から疑似推定（比較用）
        """
        trifecta_probs = {}

        for i in range(6):
            p1 = win_probs[i]

            # 2着候補
            remaining_2nd = [win_probs[j] for j in range(6) if j != i]
            total_2nd = sum(remaining_2nd)

            for j in range(6):
                if j == i:
                    continue

                p2 = win_probs[j] / total_2nd

                # 3着候補
                remaining_3rd = [win_probs[k] for k in range(6) if k != i and k != j]
                total_3rd = sum(remaining_3rd)

                for k in range(6):
                    if k == i or k == j:
                        continue

                    p3 = win_probs[k] / total_3rd

                    prob = p1 * p2 * p3
                    combination = f"{i+1}-{j+1}-{k+1}"
                    trifecta_probs[combination] = prob

        return trifecta_probs

    @staticmethod
    def get_top_combinations(probs: Dict[str, float], top_n: int = 10) -> List[Tuple[str, float]]:
        """上位N件の組み合わせを取得"""
        sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        return sorted_probs[:top_n]

    @staticmethod
    def normalize_probabilities(probs: Dict[str, float]) -> Dict[str, float]:
        """確率を正規化（合計を1にする）"""
        total = sum(probs.values())
        if total == 0:
            return probs
        return {k: v / total for k, v in probs.items()}
