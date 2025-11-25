"""
確率校正モジュール

機械学習モデルの出力確率を校正して、実際の確率により近づける

方法:
- Platt Scaling (Logistic Regression)
- Isotonic Regression
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import log_loss, brier_score_loss
import joblib
from pathlib import Path
from typing import Tuple, Optional
import matplotlib.pyplot as plt


class ProbabilityCalibrator:
    """
    確率校正クラス

    モデルの出力確率を校正して信頼性を向上
    """

    def __init__(self, method: str = 'platt', model_dir: str = "models"):
        """
        Args:
            method: 校正方法 ('platt' or 'isotonic')
            model_dir: モデル保存ディレクトリ
        """
        self.method = method
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True)
        self.calibrator = None

    def fit(
        self,
        y_prob: np.ndarray,
        y_true: np.ndarray
    ) -> None:
        """
        校正モデルを学習

        Args:
            y_prob: モデルの出力確率（校正前）
            y_true: 実際のラベル（0 or 1）
        """
        if self.method == 'platt':
            # Platt Scaling: ロジスティック回帰で校正
            self.calibrator = LogisticRegression()
            self.calibrator.fit(y_prob.reshape(-1, 1), y_true)

        elif self.method == 'isotonic':
            # Isotonic Regression: 単調関数で校正
            self.calibrator = IsotonicRegression(out_of_bounds='clip')
            self.calibrator.fit(y_prob, y_true)

        else:
            raise ValueError(f"Unknown method: {self.method}")

    def transform(self, y_prob: np.ndarray) -> np.ndarray:
        """
        確率を校正

        Args:
            y_prob: モデルの出力確率（校正前）

        Returns:
            np.ndarray: 校正後の確率
        """
        if self.calibrator is None:
            raise ValueError("Calibrator not fitted yet")

        if self.method == 'platt':
            return self.calibrator.predict_proba(y_prob.reshape(-1, 1))[:, 1]
        elif self.method == 'isotonic':
            return self.calibrator.transform(y_prob)

    def evaluate(
        self,
        y_prob_raw: np.ndarray,
        y_prob_cal: np.ndarray,
        y_true: np.ndarray
    ) -> dict:
        """
        校正前後の性能を評価

        Args:
            y_prob_raw: 校正前の確率
            y_prob_cal: 校正後の確率
            y_true: 実際のラベル

        Returns:
            dict: 評価指標
        """
        metrics = {
            'raw_log_loss': log_loss(y_true, y_prob_raw),
            'calibrated_log_loss': log_loss(y_true, y_prob_cal),
            'raw_brier_score': brier_score_loss(y_true, y_prob_raw),
            'calibrated_brier_score': brier_score_loss(y_true, y_prob_cal)
        }

        return metrics

    def plot_calibration_curve(
        self,
        y_prob_raw: np.ndarray,
        y_prob_cal: np.ndarray,
        y_true: np.ndarray,
        n_bins: int = 10,
        save_path: Optional[str] = None
    ) -> None:
        """
        校正曲線をプロット

        Args:
            y_prob_raw: 校正前の確率
            y_prob_cal: 校正後の確率
            y_true: 実際のラベル
            n_bins: ビン数
            save_path: 保存パス
        """
        fig, ax = plt.subplots(figsize=(10, 6))

        # 校正前
        prob_bins_raw, true_bins_raw = self._compute_calibration_curve(
            y_prob_raw, y_true, n_bins
        )
        ax.plot(prob_bins_raw, true_bins_raw, 'o-', label='Before Calibration', color='red')

        # 校正後
        prob_bins_cal, true_bins_cal = self._compute_calibration_curve(
            y_prob_cal, y_true, n_bins
        )
        ax.plot(prob_bins_cal, true_bins_cal, 's-', label='After Calibration', color='blue')

        # 理想線
        ax.plot([0, 1], [0, 1], '--', label='Perfectly Calibrated', color='gray')

        ax.set_xlabel('Mean Predicted Probability')
        ax.set_ylabel('Fraction of Positives')
        ax.set_title(f'Calibration Curve ({self.method})')
        ax.legend()
        ax.grid(True, alpha=0.3)

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        else:
            plt.show()

        plt.close()

    def _compute_calibration_curve(
        self,
        y_prob: np.ndarray,
        y_true: np.ndarray,
        n_bins: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        校正曲線のデータを計算

        Args:
            y_prob: 予測確率
            y_true: 実際のラベル
            n_bins: ビン数

        Returns:
            (mean_pred_prob, fraction_of_positives)
        """
        bins = np.linspace(0, 1, n_bins + 1)
        bin_indices = np.digitize(y_prob, bins[:-1]) - 1
        bin_indices = np.clip(bin_indices, 0, n_bins - 1)

        prob_bins = []
        true_bins = []

        for i in range(n_bins):
            mask = bin_indices == i
            if mask.sum() > 0:
                prob_bins.append(y_prob[mask].mean())
                true_bins.append(y_true[mask].mean())

        return np.array(prob_bins), np.array(true_bins)

    def save(self, filename: str = None) -> str:
        """
        校正モデルを保存

        Args:
            filename: ファイル名

        Returns:
            str: 保存パス
        """
        if self.calibrator is None:
            raise ValueError("Calibrator not fitted yet")

        if filename is None:
            filename = f"calibrator_{self.method}.pkl"

        filepath = self.model_dir / filename
        joblib.dump(self.calibrator, filepath)

        return str(filepath)

    def load(self, filename: str = None) -> None:
        """
        校正モデルを読み込み

        Args:
            filename: ファイル名
        """
        if filename is None:
            filename = f"calibrator_{self.method}.pkl"

        filepath = self.model_dir / filename
        self.calibrator = joblib.load(filepath)


if __name__ == "__main__":
    # テスト実行
    print("=" * 60)
    print("確率校正テスト")
    print("=" * 60)

    # サンプルデータ生成
    np.random.seed(42)
    n_samples = 1000

    # 校正が必要なバイアスのある確率
    y_prob_raw = np.random.beta(2, 5, n_samples)  # 0に偏ったバイアス
    y_true = np.random.binomial(1, y_prob_raw)

    # 訓練/検証分割
    y_prob_train, y_prob_test, y_true_train, y_true_test = train_test_split(
        y_prob_raw, y_true, test_size=0.3, random_state=42
    )

    # Platt Scaling
    print("\n【Platt Scaling】")
    calibrator_platt = ProbabilityCalibrator(method='platt')
    calibrator_platt.fit(y_prob_train, y_true_train)
    y_prob_cal_platt = calibrator_platt.transform(y_prob_test)

    metrics_platt = calibrator_platt.evaluate(y_prob_test, y_prob_cal_platt, y_true_test)
    print(f"Log Loss: {metrics_platt['raw_log_loss']:.4f} → {metrics_platt['calibrated_log_loss']:.4f}")
    print(f"Brier Score: {metrics_platt['raw_brier_score']:.4f} → {metrics_platt['calibrated_brier_score']:.4f}")

    # Isotonic Regression
    print("\n【Isotonic Regression】")
    calibrator_isotonic = ProbabilityCalibrator(method='isotonic')
    calibrator_isotonic.fit(y_prob_train, y_true_train)
    y_prob_cal_isotonic = calibrator_isotonic.transform(y_prob_test)

    metrics_isotonic = calibrator_isotonic.evaluate(y_prob_test, y_prob_cal_isotonic, y_true_test)
    print(f"Log Loss: {metrics_isotonic['raw_log_loss']:.4f} → {metrics_isotonic['calibrated_log_loss']:.4f}")
    print(f"Brier Score: {metrics_isotonic['raw_brier_score']:.4f} → {metrics_isotonic['calibrated_brier_score']:.4f}")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
