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

        # 1着艇の特徴量を取得
        first_features = df[df['rank'] == 1].copy()
        feature_cols = [c for c in first_features.columns if c not in ['rank', 'race_id', 'pit_number']]
        first_features = first_features[['race_id'] + feature_cols]
        first_features.columns = ['race_id'] + [f'first_place_{c}' for c in feature_cols]

        # 1着艇を除外
        df_with_first = df.merge(first_place, on='race_id')
        remaining = df_with_first[df_with_first['pit_number'] != df_with_first['first_pit']].copy()
        remaining = remaining.drop('first_pit', axis=1)

        # 1着艇の特徴量をマージ
        remaining = remaining.merge(first_features, on='race_id')

        # ラベルと特徴量
        y = (remaining['rank'] == 2).astype(int).values
        X = remaining.drop(['rank', 'race_id', 'pit_number'], axis=1, errors='ignore')
        X = X.select_dtypes(include=[np.number])

        return X, y

    def _prepare_third_place_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        3着予測用データを準備（1着・2着が確定した条件下）- ベクトル化版

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

        # 1着・2着艇の特徴量を取得
        feature_cols = [c for c in df.columns if c not in ['rank', 'race_id', 'pit_number']]

        first_features = df[df['rank'] == 1][['race_id'] + feature_cols].copy()
        first_features.columns = ['race_id'] + [f'first_place_{c}' for c in feature_cols]

        second_features = df[df['rank'] == 2][['race_id'] + feature_cols].copy()
        second_features.columns = ['race_id'] + [f'second_place_{c}' for c in feature_cols]

        # 1着・2着艇を除外
        df_with_places = df.merge(first_place, on='race_id').merge(second_place, on='race_id')
        remaining = df_with_places[
            (df_with_places['pit_number'] != df_with_places['first_pit']) &
            (df_with_places['pit_number'] != df_with_places['second_pit'])
        ].copy()
        remaining = remaining.drop(['first_pit', 'second_pit'], axis=1)

        # 1着・2着艇の特徴量をマージ
        remaining = remaining.merge(first_features, on='race_id')
        remaining = remaining.merge(second_features, on='race_id')

        # ラベルと特徴量
        y = (remaining['rank'] == 3).astype(int).values
        X = remaining.drop(['rank', 'race_id', 'pit_number'], axis=1, errors='ignore')
        X = X.select_dtypes(include=[np.number])

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
