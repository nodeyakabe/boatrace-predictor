"""
最適化されたモデル学習
Phase 1: ハイパーパラメータ調整 + 確率校正
"""
import xgboost as xgb
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score
import json


class OptimizedModelTrainer:
    """最適化されたモデル学習クラス"""

    # Phase 1推奨ハイパーパラメータ
    OPTIMIZED_PARAMS = {
        'objective': 'binary:logistic',
        'learning_rate': 0.03,      # 0.05 → 0.03（過学習防止）
        'max_depth': 5,             # 6 → 5（過学習防止）
        'min_child_weight': 3,      # 1 → 3（過学習防止）
        'subsample': 0.8,           # データサンプリング
        'colsample_bytree': 0.8,    # 特徴量サンプリング
        'gamma': 0.1,               # 分割の最小損失減少
        'reg_alpha': 0.1,           # L1正則化
        'reg_lambda': 1.0,          # L2正則化
        'n_estimators': 300,        # ツリー数
        'random_state': 42,
        'eval_metric': 'auc'
    }

    def __init__(self, params=None):
        """
        初期化

        Args:
            params: カスタムパラメータ（Noneの場合は最適化パラメータを使用）
        """
        self.params = params if params else self.OPTIMIZED_PARAMS.copy()
        self.model = None
        self.calibrated_model = None
        self.feature_names = None

    def train(self, X_train, y_train, X_val=None, y_val=None, early_stopping_rounds=50):
        """
        モデルを学習

        Args:
            X_train: 訓練データ
            y_train: 訓練ラベル
            X_val: 検証データ（オプション）
            y_val: 検証ラベル（オプション）
            early_stopping_rounds: 早期停止のラウンド数

        Returns:
            trained model
        """
        self.feature_names = X_train.columns.tolist()

        # XGBoostモデルの学習
        self.model = xgb.XGBClassifier(**self.params)

        if X_val is not None and y_val is not None:
            # 検証データがある場合は早期停止を使用
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                early_stopping_rounds=early_stopping_rounds,
                verbose=False
            )
        else:
            # 検証データがない場合は通常の学習
            self.model.fit(X_train, y_train)

        print(f"[OK] Model trained with {len(self.feature_names)} features")
        return self.model

    def calibrate(self, X_cal, y_cal, method='sigmoid'):
        """
        確率校正（Platt Scaling）

        Args:
            X_cal: 校正用データ
            y_cal: 校正用ラベル
            method: 校正方法（'sigmoid' or 'isotonic'）

        Returns:
            calibrated model
        """
        if self.model is None:
            raise ValueError("Model must be trained before calibration")

        print(f"[INFO] Calibrating model with {method} method...")

        # CalibratedClassifierCVで確率校正
        self.calibrated_model = CalibratedClassifierCV(
            self.model,
            method=method,
            cv='prefit'
        )

        self.calibrated_model.fit(X_cal, y_cal)

        print("[OK] Model calibrated successfully")
        return self.calibrated_model

    def evaluate(self, X_test, y_test, use_calibrated=False):
        """
        モデルを評価

        Args:
            X_test: テストデータ
            y_test: テストラベル
            use_calibrated: 校正済みモデルを使用するか

        Returns:
            dict: 評価指標
        """
        model = self.calibrated_model if use_calibrated and self.calibrated_model else self.model

        if model is None:
            raise ValueError("Model must be trained before evaluation")

        # 予測
        y_pred = model.predict(X_test)
        y_pred_proba = model.predict_proba(X_test)[:, 1]

        # 評価指標
        metrics = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred, zero_division=0),
            'recall': recall_score(y_test, y_pred, zero_division=0),
            'auc': roc_auc_score(y_test, y_pred_proba),
            'f1_score': 2 * precision_score(y_test, y_pred, zero_division=0) * recall_score(y_test, y_pred, zero_division=0) /
                       (precision_score(y_test, y_pred, zero_division=0) + recall_score(y_test, y_pred, zero_division=0) + 1e-10)
        }

        # 確信度別の精度
        confidence_metrics = self._evaluate_by_confidence(y_test, y_pred_proba)
        metrics['confidence_metrics'] = confidence_metrics

        return metrics

    def _evaluate_by_confidence(self, y_true, y_pred_proba, thresholds=[0.6, 0.7, 0.8, 0.9]):
        """
        確信度別の精度を評価

        Args:
            y_true: 真のラベル
            y_pred_proba: 予測確率
            thresholds: 確信度の閾値リスト

        Returns:
            dict: 確信度別の精度
        """
        confidence_metrics = {}

        for threshold in thresholds:
            # 確信度が閾値以上の予測のみ
            mask = y_pred_proba >= threshold
            if np.sum(mask) == 0:
                confidence_metrics[f'conf_{threshold}'] = {
                    'accuracy': 0.0,
                    'count': 0,
                    'coverage': 0.0
                }
                continue

            y_true_filtered = y_true[mask]
            y_pred_filtered = (y_pred_proba[mask] >= 0.5).astype(int)

            confidence_metrics[f'conf_{threshold}'] = {
                'accuracy': accuracy_score(y_true_filtered, y_pred_filtered),
                'count': np.sum(mask),
                'coverage': np.sum(mask) / len(y_true)
            }

        return confidence_metrics

    def cross_validate(self, X, y, cv=5):
        """
        交差検証

        Args:
            X: 特徴量データ
            y: ラベルデータ
            cv: 分割数

        Returns:
            dict: 交差検証の結果
        """
        if self.model is None:
            self.model = xgb.XGBClassifier(**self.params)

        print(f"[INFO] Running {cv}-fold cross-validation...")

        # Stratified K-Fold（クラス比率を保持）
        skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)

        # AUCスコアで交差検証
        scores = cross_val_score(
            self.model, X, y,
            cv=skf,
            scoring='roc_auc',
            n_jobs=-1
        )

        result = {
            'mean_auc': np.mean(scores),
            'std_auc': np.std(scores),
            'scores': scores.tolist()
        }

        print(f"[OK] Cross-validation AUC: {result['mean_auc']:.4f} (+/- {result['std_auc']:.4f})")

        return result

    def get_feature_importance(self, top_n=20):
        """
        特徴量重要度を取得

        Args:
            top_n: 上位何個を返すか

        Returns:
            list: (特徴量名, 重要度)のリスト
        """
        if self.model is None:
            raise ValueError("Model must be trained before getting feature importance")

        importances = self.model.feature_importances_
        feature_importance = list(zip(self.feature_names, importances))
        feature_importance.sort(key=lambda x: x[1], reverse=True)

        return feature_importance[:top_n]

    def save_model(self, filepath, include_calibration=False):
        """
        モデルを保存

        Args:
            filepath: 保存先パス
            include_calibration: 校正済みモデルも保存するか
        """
        if self.model is None:
            raise ValueError("Model must be trained before saving")

        # XGBoostモデルをJSON形式で保存
        self.model.save_model(filepath)

        # メタデータを保存
        meta_filepath = filepath.replace('.json', '.meta.json')
        metadata = {
            'params': self.params,
            'feature_names': self.feature_names,
            'n_features': len(self.feature_names),
            'is_calibrated': include_calibration and self.calibrated_model is not None
        }

        with open(meta_filepath, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"[OK] Model saved to {filepath}")
        print(f"[OK] Metadata saved to {meta_filepath}")

    def load_model(self, filepath):
        """
        モデルを読み込み

        Args:
            filepath: モデルファイルのパス
        """
        self.model = xgb.XGBClassifier()
        self.model.load_model(filepath)

        # メタデータを読み込み
        meta_filepath = filepath.replace('.json', '.meta.json')
        try:
            with open(meta_filepath, 'r') as f:
                metadata = json.load(f)
                self.params = metadata.get('params', {})
                self.feature_names = metadata.get('feature_names', [])
                print(f"[OK] Model loaded from {filepath}")
        except FileNotFoundError:
            print(f"[WARN] Metadata file not found: {meta_filepath}")
