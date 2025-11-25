"""
XGBoost モデル学習・評価モジュール
"""
import xgboost as xgb
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import json
import joblib
from pathlib import Path
from sklearn.metrics import (
    roc_auc_score,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    log_loss,
    brier_score_loss
)
from scipy.stats import spearmanr, kendalltau


class ModelTrainer:
    """XGBoost モデル学習・評価クラス"""

    def __init__(self, model_dir: str = "models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True)
        self.model = None
        self.calibrator = None
        self.feature_names = None
        self.training_history = []
        self.use_calibration = False

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_valid: Optional[pd.DataFrame] = None,
        y_valid: Optional[pd.Series] = None,
        params: Optional[Dict] = None,
        num_boost_round: int = 1000,
        early_stopping_rounds: int = 50
    ) -> Dict:
        """
        XGBoost モデルを学習

        Args:
            X_train: 訓練データ特徴量
            y_train: 訓練データ目的変数
            X_valid: 検証データ特徴量
            y_valid: 検証データ目的変数
            params: XGBoost パラメータ
            num_boost_round: ブースティング回数
            early_stopping_rounds: Early stopping ラウンド数

        Returns:
            Dict: 学習結果サマリー
        """
        self.feature_names = list(X_train.columns)

        # デフォルトパラメータ
        if params is None:
            # クラス不均衡を考慮した重み計算
            scale_pos_weight = (len(y_train) - y_train.sum()) / y_train.sum()

            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': 6,
                'learning_rate': 0.05,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'scale_pos_weight': scale_pos_weight,
                'random_state': 42
            }

        # DMatrix 作成
        dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=self.feature_names)
        evals = [(dtrain, 'train')]

        if X_valid is not None and y_valid is not None:
            dvalid = xgb.DMatrix(X_valid, label=y_valid, feature_names=self.feature_names)
            evals.append((dvalid, 'valid'))

        # 学習履歴を保存するコールバック
        evals_result = {}

        # 学習
        self.model = xgb.train(
            params,
            dtrain,
            num_boost_round=num_boost_round,
            evals=evals,
            evals_result=evals_result,
            early_stopping_rounds=early_stopping_rounds if X_valid is not None else None,
            verbose_eval=False
        )

        # 学習履歴を保存
        self.training_history = evals_result

        # 学習結果サマリー
        summary = {
            'best_iteration': self.model.best_iteration if X_valid is not None else num_boost_round,
            'num_features': len(self.feature_names),
            'params': params,
            'training_samples': len(X_train),
            'validation_samples': len(X_valid) if X_valid is not None else 0
        }

        # 訓練データでの評価
        train_pred = self.model.predict(dtrain)
        summary['train_auc'] = roc_auc_score(y_train, train_pred)
        summary['train_logloss'] = log_loss(y_train, train_pred)

        # 検証データでの評価
        if X_valid is not None and y_valid is not None:
            valid_pred = self.model.predict(dvalid)
            summary['valid_auc'] = roc_auc_score(y_valid, valid_pred)
            summary['valid_logloss'] = log_loss(y_valid, valid_pred)

        return summary

    def train_calibrator(
        self,
        X_calib: pd.DataFrame,
        y_calib: pd.Series,
        method: str = 'platt'
    ) -> Dict:
        """
        確率校正モデルを学習

        Args:
            X_calib: キャリブレーション用特徴量
            y_calib: キャリブレーション用正解ラベル
            method: 校正方法 ('platt' or 'isotonic')

        Returns:
            Dict: 校正結果サマリー
        """
        if self.model is None:
            raise ValueError("先にXGBoostモデルを学習してください")

        try:
            from .probability_calibration import ProbabilityCalibrator
        except ImportError:
            raise ImportError("probability_calibrationモジュールが見つかりません")

        # 生の予測確率を取得
        y_prob_raw = self.predict(X_calib, use_calibration=False)

        # 校正モデルを学習
        self.calibrator = ProbabilityCalibrator(method=method, model_dir=str(self.model_dir))
        self.calibrator.fit(y_prob_raw, y_calib.values)

        # 校正後の確率
        y_prob_cal = self.calibrator.transform(y_prob_raw)

        # 評価
        calibration_metrics = self.calibrator.evaluate(y_prob_raw, y_prob_cal, y_calib.values)

        self.use_calibration = True

        return calibration_metrics

    def predict(self, X: pd.DataFrame, use_calibration: Optional[bool] = None) -> np.ndarray:
        """
        予測実行

        Args:
            X: 特徴量データ
            use_calibration: 校正を使用するか（Noneならself.use_calibrationを使用）

        Returns:
            np.ndarray: 予測確率（校正済みまたは生の確率）
        """
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        # 生の予測確率を取得
        dmatrix = xgb.DMatrix(X, feature_names=self.feature_names)
        y_prob_raw = self.model.predict(dmatrix)

        # 校正を適用
        if use_calibration is None:
            use_calibration = self.use_calibration

        if use_calibration and self.calibrator is not None:
            y_prob = self.calibrator.transform(y_prob_raw)
            return y_prob
        else:
            return y_prob_raw

    def evaluate(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        threshold: float = 0.5
    ) -> Dict:
        """
        モデルを評価

        Args:
            X: 特徴量データ
            y: 正解ラベル
            threshold: 予測閾値

        Returns:
            Dict: 評価指標
        """
        y_pred_proba = self.predict(X)
        y_pred = (y_pred_proba >= threshold).astype(int)

        metrics = {
            'auc': roc_auc_score(y, y_pred_proba),
            'logloss': log_loss(y, y_pred_proba),
            'brier_score': brier_score_loss(y, y_pred_proba),
            'accuracy': accuracy_score(y, y_pred),
            'precision': precision_score(y, y_pred, zero_division=0),
            'recall': recall_score(y, y_pred, zero_division=0),
            'f1': f1_score(y, y_pred, zero_division=0)
        }

        # 混同行列
        cm = confusion_matrix(y, y_pred)
        metrics['confusion_matrix'] = {
            'tn': int(cm[0, 0]),
            'fp': int(cm[0, 1]),
            'fn': int(cm[1, 0]),
            'tp': int(cm[1, 1])
        }

        # Top-N Accuracy (上位N件に正解が含まれる割合)
        sorted_indices = np.argsort(y_pred_proba)[::-1]
        y_array = y.values if hasattr(y, 'values') else np.array(y)
        for n in [1, 2, 3]:
            if len(y_array) >= n:
                top_n_correct = y_array[sorted_indices[:n]].sum()
                metrics[f'top_{n}_accuracy'] = float(top_n_correct > 0)
            else:
                metrics[f'top_{n}_accuracy'] = 0.0

        # Expected Calibration Error (ECE)
        metrics['ece'] = self._calculate_ece(y_array, y_pred_proba)

        return metrics

    def _calculate_ece(self, y_true: np.ndarray, y_pred_prob: np.ndarray, n_bins: int = 10) -> float:
        """
        Expected Calibration Error (ECE) を計算

        Args:
            y_true: 実際のラベル
            y_pred_prob: 予測確率
            n_bins: ビン数

        Returns:
            ECE値
        """
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0

        for i in range(n_bins):
            in_bin = (y_pred_prob > bin_boundaries[i]) & (y_pred_prob <= bin_boundaries[i + 1])
            prop_in_bin = in_bin.mean()

            if prop_in_bin > 0:
                avg_confidence = y_pred_prob[in_bin].mean()
                avg_accuracy = y_true[in_bin].mean()
                ece += np.abs(avg_accuracy - avg_confidence) * prop_in_bin

        return ece

    def evaluate_ranking(
        self,
        X: pd.DataFrame,
        y_ranks: np.ndarray
    ) -> Dict:
        """
        順位予測の評価

        Args:
            X: 特徴量データ
            y_ranks: 実際の着順 (1-6)

        Returns:
            Dict: 順位相関指標
        """
        y_pred_proba = self.predict(X)

        # 予測確率から順位を計算（高確率ほど上位）
        pred_ranks = pd.Series(y_pred_proba).rank(ascending=False).values

        # Spearman順位相関
        spearman_corr, spearman_p = spearmanr(y_ranks, pred_ranks)

        # Kendall順位相関
        kendall_corr, kendall_p = kendalltau(y_ranks, pred_ranks)

        return {
            'spearman_correlation': spearman_corr if not np.isnan(spearman_corr) else 0.0,
            'spearman_p_value': spearman_p if not np.isnan(spearman_p) else 1.0,
            'kendall_correlation': kendall_corr if not np.isnan(kendall_corr) else 0.0,
            'kendall_p_value': kendall_p if not np.isnan(kendall_p) else 1.0
        }

    def get_feature_importance(
        self,
        importance_type: str = 'gain'
    ) -> pd.DataFrame:
        """
        特徴量重要度を取得

        Args:
            importance_type: 重要度タイプ ('gain', 'weight', 'cover')

        Returns:
            pd.DataFrame: 特徴量重要度（降順）
        """
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        importance = self.model.get_score(importance_type=importance_type)

        df_importance = pd.DataFrame([
            {'feature': k, 'importance': v}
            for k, v in importance.items()
        ])

        df_importance = df_importance.sort_values('importance', ascending=False)

        return df_importance

    def save_model(self, filename: str) -> str:
        """
        モデルを保存（校正モデルも含む）

        Args:
            filename: ファイル名

        Returns:
            str: 保存パス
        """
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        filepath = self.model_dir / filename

        # XGBoost モデル保存
        self.model.save_model(str(filepath))

        # メタデータ保存（別ファイルに）
        meta_path = filepath.with_suffix('.meta.json')
        metadata = {
            'feature_names': self.feature_names,
            'num_features': len(self.feature_names),
            'best_iteration': self.model.best_iteration,
            'use_calibration': self.use_calibration
        }

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        # 校正モデルを保存
        if self.calibrator is not None:
            calibrator_filename = filepath.stem + '_calibrator.pkl'
            self.calibrator.save(calibrator_filename)

        return str(filepath)

    def load_model(self, filename: str) -> None:
        """
        モデルを読み込み（校正モデルも含む）

        Args:
            filename: ファイル名
        """
        filepath = self.model_dir / filename

        # XGBoost モデル読み込み
        self.model = xgb.Booster()
        self.model.load_model(str(filepath))

        # メタデータ読み込み
        meta_path = filepath.with_suffix('.meta.json')
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                self.feature_names = metadata.get('feature_names', [])
                self.use_calibration = metadata.get('use_calibration', False)

        # 校正モデルを読み込み
        if self.use_calibration:
            try:
                from .probability_calibration import ProbabilityCalibrator
                calibrator_filename = filepath.stem + '_calibrator.pkl'
                calibrator_path = self.model_dir / calibrator_filename

                if calibrator_path.exists():
                    self.calibrator = ProbabilityCalibrator(model_dir=str(self.model_dir))
                    self.calibrator.load(calibrator_filename)
                else:
                    # 校正モデルが見つからない場合は校正を無効化
                    self.use_calibration = False
                    self.calibrator = None
            except Exception:
                # エラー時は校正を無効化
                self.use_calibration = False
                self.calibrator = None

    def get_training_history(self) -> Dict:
        """
        学習履歴を取得

        Returns:
            Dict: 学習履歴
        """
        return self.training_history

    def calculate_expected_value(
        self,
        X: pd.DataFrame,
        odds: pd.Series,
        threshold: float = 0.0
    ) -> pd.DataFrame:
        """
        期待値を計算

        Args:
            X: 特徴量データ
            odds: オッズ
            threshold: 購入判定閾値

        Returns:
            pd.DataFrame: 期待値データ
        """
        pred_proba = self.predict(X)

        df_ev = pd.DataFrame({
            'pred_proba': pred_proba,
            'odds': odds,
            'expected_value': pred_proba * odds - 1.0
        })

        df_ev['should_bet'] = df_ev['expected_value'] > threshold

        return df_ev
