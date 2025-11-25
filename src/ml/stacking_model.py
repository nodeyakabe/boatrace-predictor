"""
スタッキングモデル
Phase 3.2: 多層モデル構造による精度向上
"""
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
from typing import Dict, List, Optional
import json
import os


class StackingModel:
    """
    スタッキングモデル

    Layer 1: 基本モデル群（XGBoost, LightGBM, RandomForest）
    Layer 2: メタ学習器（Logistic Regression）
    """

    def __init__(self, model_dir: str = 'models', n_folds: int = 5):
        self.model_dir = model_dir
        self.n_folds = n_folds
        self.layer1_models = []
        self.layer2_model = None
        self.feature_names = None

    def train(self, X_train: pd.DataFrame, y_train: np.ndarray,
              X_valid: pd.DataFrame = None, y_valid: np.ndarray = None) -> Dict:
        """スタッキングモデルを学習"""
        self.feature_names = list(X_train.columns)
        results = {}

        print("=== Layer 1: 基本モデル群の学習 ===")

        # 交差検証によるOOF (Out-of-Fold) 予測の生成
        oof_predictions = np.zeros((len(X_train), 3))  # 3モデル
        test_predictions = []

        kfold = StratifiedKFold(n_splits=self.n_folds, shuffle=True, random_state=42)

        # モデル定義
        model_configs = [
            {
                'name': 'xgboost',
                'model': xgb.XGBClassifier(
                    objective='binary:logistic',
                    max_depth=6,
                    learning_rate=0.05,
                    n_estimators=300,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                    use_label_encoder=False,
                    eval_metric='auc',
                )
            },
            {
                'name': 'lightgbm',
                'model': lgb.LGBMClassifier(
                    objective='binary',
                    max_depth=6,
                    learning_rate=0.05,
                    n_estimators=300,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                    verbose=-1,
                )
            },
            {
                'name': 'random_forest',
                'model': RandomForestClassifier(
                    n_estimators=200,
                    max_depth=10,
                    min_samples_split=5,
                    random_state=42,
                    n_jobs=-1,
                )
            }
        ]

        # 各モデルについてOOF予測を生成
        for model_idx, config in enumerate(model_configs):
            print(f"\n--- {config['name']}の学習 ---")
            fold_models = []

            for fold_idx, (train_idx, val_idx) in enumerate(kfold.split(X_train, y_train)):
                X_fold_train = X_train.iloc[train_idx]
                y_fold_train = y_train[train_idx]
                X_fold_val = X_train.iloc[val_idx]
                y_fold_val = y_train[val_idx]

                # モデルをコピーして学習
                model = config['model'].__class__(**config['model'].get_params())

                if config['name'] in ['xgboost', 'lightgbm']:
                    model.fit(X_fold_train, y_fold_train)
                else:
                    model.fit(X_fold_train, y_fold_train)

                # OOF予測
                oof_pred = model.predict_proba(X_fold_val)[:, 1]
                oof_predictions[val_idx, model_idx] = oof_pred

                fold_models.append(model)

            # 全foldのモデルを保存
            self.layer1_models.append({
                'name': config['name'],
                'models': fold_models
            })

            # OOF AUC
            oof_auc = roc_auc_score(y_train, oof_predictions[:, model_idx])
            print(f"{config['name']} OOF AUC: {oof_auc:.4f}")
            results[f'{config["name"]}_oof_auc'] = oof_auc

        print("\n=== Layer 2: メタ学習器の学習 ===")

        # Layer 2: メタモデルの学習
        self.layer2_model = LogisticRegression(
            C=1.0,
            max_iter=1000,
            random_state=42
        )
        self.layer2_model.fit(oof_predictions, y_train)

        # OOFでのメタモデル予測
        meta_oof_pred = self.layer2_model.predict_proba(oof_predictions)[:, 1]
        meta_oof_auc = roc_auc_score(y_train, meta_oof_pred)
        print(f"メタモデル OOF AUC: {meta_oof_auc:.4f}")
        results['meta_oof_auc'] = meta_oof_auc

        # 検証セットでの評価
        if X_valid is not None and y_valid is not None:
            valid_pred = self.predict_proba(X_valid)
            valid_auc = roc_auc_score(y_valid, valid_pred)
            print(f"\n検証セット AUC: {valid_auc:.4f}")
            results['valid_auc'] = valid_auc

        return results

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """確率を予測"""
        if not self.layer1_models or self.layer2_model is None:
            raise ValueError("モデルが学習されていません")

        # Layer 1: 各基本モデルの予測
        layer1_predictions = np.zeros((len(X), len(self.layer1_models)))

        for model_idx, model_info in enumerate(self.layer1_models):
            # 全foldの平均予測
            fold_predictions = []
            for fold_model in model_info['models']:
                pred = fold_model.predict_proba(X)[:, 1]
                fold_predictions.append(pred)

            layer1_predictions[:, model_idx] = np.mean(fold_predictions, axis=0)

        # Layer 2: メタモデルの予測
        final_predictions = self.layer2_model.predict_proba(layer1_predictions)[:, 1]

        return final_predictions

    def get_layer1_predictions(self, X: pd.DataFrame) -> Dict[str, np.ndarray]:
        """Layer 1の各モデル予測を取得（デバッグ用）"""
        predictions = {}

        for model_info in self.layer1_models:
            fold_predictions = []
            for fold_model in model_info['models']:
                pred = fold_model.predict_proba(X)[:, 1]
                fold_predictions.append(pred)

            predictions[model_info['name']] = np.mean(fold_predictions, axis=0)

        return predictions

    def save(self, name: str = 'stacking'):
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        # Layer 1モデル
        for model_idx, model_info in enumerate(self.layer1_models):
            model_name = model_info['name']

            for fold_idx, fold_model in enumerate(model_info['models']):
                if model_name == 'xgboost':
                    path = os.path.join(self.model_dir, f'{name}_l1_{model_name}_f{fold_idx}.json')
                    fold_model.save_model(path)
                elif model_name == 'lightgbm':
                    path = os.path.join(self.model_dir, f'{name}_l1_{model_name}_f{fold_idx}.txt')
                    fold_model.booster_.save_model(path)
                # RandomForestはpickleで保存（省略）

        # メタ情報
        meta = {
            'feature_names': self.feature_names,
            'n_folds': self.n_folds,
            'layer1_model_names': [m['name'] for m in self.layer1_models],
        }
        with open(os.path.join(self.model_dir, f'{name}.meta.json'), 'w') as f:
            json.dump(meta, f)

        print(f"スタッキングモデルを {self.model_dir} に保存しました")

    def get_feature_importance(self) -> Dict[str, float]:
        """特徴量重要度を取得（Layer 1モデルの平均）"""
        importance_sum = defaultdict(float)
        model_count = 0

        for model_info in self.layer1_models:
            for fold_model in model_info['models']:
                if hasattr(fold_model, 'feature_importances_'):
                    for i, imp in enumerate(fold_model.feature_importances_):
                        importance_sum[self.feature_names[i]] += imp
                    model_count += 1

        if model_count == 0:
            return {}

        # 平均
        importance_avg = {k: v / model_count for k, v in importance_sum.items()}

        # ソート
        sorted_importance = dict(sorted(importance_avg.items(), key=lambda x: x[1], reverse=True))

        return sorted_importance


from collections import defaultdict
