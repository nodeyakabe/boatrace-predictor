"""
高度なアンサンブル学習モジュール
Phase 2.4: XGBoost + LightGBM + CatBoost の統合
"""
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict
from typing import Dict, List, Optional, Tuple
import json
import os


class AdvancedEnsemble:
    """高度なアンサンブルモデル"""

    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        self.base_models = {}
        self.meta_model = None
        self.feature_names = None
        self.model_weights = {}

    def train(self, X_train: pd.DataFrame, y_train: np.ndarray,
              X_valid: pd.DataFrame = None, y_valid: np.ndarray = None) -> Dict:
        """アンサンブルモデルを学習"""
        self.feature_names = list(X_train.columns)
        results = {}

        # XGBoost
        print("=== XGBoost学習 ===")
        xgb_params = {
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
            'use_label_encoder': False,
        }
        self.base_models['xgboost'] = xgb.XGBClassifier(**xgb_params)

        if X_valid is not None:
            self.base_models['xgboost'].fit(
                X_train, y_train,
                eval_set=[(X_valid, y_valid)],
                verbose=False
            )
        else:
            self.base_models['xgboost'].fit(X_train, y_train, verbose=False)

        # LightGBM
        print("=== LightGBM学習 ===")
        lgb_params = {
            'objective': 'binary',
            'metric': 'auc',
            'max_depth': 6,
            'learning_rate': 0.05,
            'n_estimators': 500,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'min_child_weight': 3,
            'random_state': 42,
            'verbose': -1,
        }
        self.base_models['lightgbm'] = lgb.LGBMClassifier(**lgb_params)

        if X_valid is not None:
            self.base_models['lightgbm'].fit(
                X_train, y_train,
                eval_set=[(X_valid, y_valid)],
            )
        else:
            self.base_models['lightgbm'].fit(X_train, y_train)

        # CatBoostは依存関係の問題でスキップ（代わりにLogisticRegression）
        print("=== LogisticRegression（メタモデル用）学習 ===")
        from sklearn.preprocessing import StandardScaler
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)

        self.base_models['logistic'] = LogisticRegression(
            C=1.0, max_iter=1000, random_state=42
        )
        self.base_models['logistic'].fit(X_train_scaled, y_train)

        # 各モデルの性能評価
        if X_valid is not None:
            from sklearn.metrics import roc_auc_score
            X_valid_scaled = self.scaler.transform(X_valid)

            for name, model in self.base_models.items():
                if name == 'logistic':
                    pred = model.predict_proba(X_valid_scaled)[:, 1]
                else:
                    pred = model.predict_proba(X_valid)[:, 1]
                auc = roc_auc_score(y_valid, pred)
                results[f'{name}_auc'] = auc
                print(f"{name} AUC: {auc:.4f}")

        # メタモデル（スタッキング）の学習
        print("=== メタモデル学習 ===")
        self._train_meta_model(X_train, y_train, X_valid, y_valid)

        # 動的重み付けの計算
        if X_valid is not None:
            self._calculate_model_weights(X_valid, y_valid)
            results['ensemble_auc'] = self._evaluate_ensemble(X_valid, y_valid)
            print(f"アンサンブル AUC: {results['ensemble_auc']:.4f}")

        return results

    def _train_meta_model(self, X_train, y_train, X_valid=None, y_valid=None):
        """メタモデルを学習（スタッキング）"""
        # 基本モデルの予測をメタ特徴量として使用
        meta_features_train = self._get_meta_features(X_train)

        self.meta_model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        self.meta_model.fit(meta_features_train, y_train)

    def _get_meta_features(self, X: pd.DataFrame) -> np.ndarray:
        """基本モデルの予測値をメタ特徴量として取得"""
        meta_features = []

        for name, model in self.base_models.items():
            if name == 'logistic':
                X_scaled = self.scaler.transform(X)
                pred = model.predict_proba(X_scaled)[:, 1]
            else:
                pred = model.predict_proba(X)[:, 1]
            meta_features.append(pred)

        return np.column_stack(meta_features)

    def _calculate_model_weights(self, X_valid, y_valid):
        """各モデルの重みを性能に基づいて計算"""
        from sklearn.metrics import roc_auc_score

        aucs = {}
        for name, model in self.base_models.items():
            if name == 'logistic':
                X_valid_scaled = self.scaler.transform(X_valid)
                pred = model.predict_proba(X_valid_scaled)[:, 1]
            else:
                pred = model.predict_proba(X_valid)[:, 1]
            aucs[name] = roc_auc_score(y_valid, pred)

        # AUCに基づく重み付け
        total_auc = sum(aucs.values())
        self.model_weights = {name: auc / total_auc for name, auc in aucs.items()}

    def _evaluate_ensemble(self, X_valid, y_valid) -> float:
        """アンサンブルの性能を評価"""
        from sklearn.metrics import roc_auc_score
        pred = self.predict_proba(X_valid)
        return roc_auc_score(y_valid, pred)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """確率を予測（アンサンブル）"""
        # 方法1: 重み付け平均
        if self.model_weights:
            weighted_pred = np.zeros(len(X))
            for name, model in self.base_models.items():
                if name == 'logistic':
                    X_scaled = self.scaler.transform(X)
                    pred = model.predict_proba(X_scaled)[:, 1]
                else:
                    pred = model.predict_proba(X)[:, 1]
                weighted_pred += pred * self.model_weights[name]
            return weighted_pred

        # 方法2: メタモデル
        if self.meta_model is not None:
            meta_features = self._get_meta_features(X)
            return self.meta_model.predict_proba(meta_features)[:, 1]

        # フォールバック: 単純平均
        preds = []
        for name, model in self.base_models.items():
            if name == 'logistic':
                X_scaled = self.scaler.transform(X)
                pred = model.predict_proba(X_scaled)[:, 1]
            else:
                pred = model.predict_proba(X)[:, 1]
            preds.append(pred)
        return np.mean(preds, axis=0)

    def save(self, name: str = 'advanced_ensemble'):
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        # XGBoost
        if 'xgboost' in self.base_models:
            self.base_models['xgboost'].save_model(
                os.path.join(self.model_dir, f'{name}_xgb.json')
            )

        # LightGBM
        if 'lightgbm' in self.base_models:
            self.base_models['lightgbm'].booster_.save_model(
                os.path.join(self.model_dir, f'{name}_lgb.txt')
            )

        # メタ情報
        meta = {
            'feature_names': self.feature_names,
            'model_weights': self.model_weights,
        }
        with open(os.path.join(self.model_dir, f'{name}.meta.json'), 'w') as f:
            json.dump(meta, f)

        print(f"アンサンブルモデルを保存しました")

    def load(self, name: str = 'advanced_ensemble'):
        """モデルを読み込み"""
        # XGBoost
        xgb_path = os.path.join(self.model_dir, f'{name}_xgb.json')
        if os.path.exists(xgb_path):
            self.base_models['xgboost'] = xgb.XGBClassifier()
            self.base_models['xgboost'].load_model(xgb_path)

        # LightGBM
        lgb_path = os.path.join(self.model_dir, f'{name}_lgb.txt')
        if os.path.exists(lgb_path):
            self.base_models['lightgbm'] = lgb.Booster(model_file=lgb_path)

        # メタ情報
        meta_path = os.path.join(self.model_dir, f'{name}.meta.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                meta = json.load(f)
            self.feature_names = meta.get('feature_names', [])
            self.model_weights = meta.get('model_weights', {})
