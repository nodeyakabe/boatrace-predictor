"""
予測結果の可視化ツール

モデルの予測結果を多角的に可視化
- 予測確率の分布
- 予測確率 vs 実際の結果
- 校正曲線（Calibration Curve）
- 特徴量重要度
- SHAP値による解釈
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from sklearn.calibration import calibration_curve
from sklearn.metrics import roc_curve, auc, confusion_matrix


class PredictionVisualizer:
    """予測結果可視化クラス"""

    def __init__(self):
        """初期化"""
        # 日本語フォント設定（Matplotlibで日本語を表示）
        plt.rcParams['font.sans-serif'] = ['MS Gothic', 'Yu Gothic', 'Meiryo']
        plt.rcParams['axes.unicode_minus'] = False

    def plot_prediction_distribution(
        self,
        y_pred: np.ndarray,
        y_true: Optional[np.ndarray] = None,
        output_path: Optional[str] = None
    ):
        """
        予測確率の分布をプロット

        Args:
            y_pred: 予測確率
            y_true: 実際のラベル（オプション）
            output_path: 保存先パス
        """
        fig, axes = plt.subplots(1, 2 if y_true is not None else 1, figsize=(14 if y_true is not None else 8, 6))

        if y_true is None:
            axes = [axes]

        # 全体の予測確率分布
        axes[0].hist(y_pred, bins=50, alpha=0.7, edgecolor='black')
        axes[0].set_title('予測確率の分布', fontsize=14)
        axes[0].set_xlabel('予測確率', fontsize=12)
        axes[0].set_ylabel('頻度', fontsize=12)
        axes[0].grid(True, alpha=0.3)

        # クラス別の予測確率分布
        if y_true is not None:
            axes[1].hist(y_pred[y_true == 0], bins=50, alpha=0.5, label='不的中', edgecolor='black')
            axes[1].hist(y_pred[y_true == 1], bins=50, alpha=0.5, label='的中', edgecolor='black')
            axes[1].set_title('クラス別予測確率の分布', fontsize=14)
            axes[1].set_xlabel('予測確率', fontsize=12)
            axes[1].set_ylabel('頻度', fontsize=12)
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"[OK] グラフを保存: {output_path}")
        else:
            plt.show()

        plt.close()

    def plot_calibration_curve(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        n_bins: int = 10,
        output_path: Optional[str] = None
    ):
        """
        校正曲線（Calibration Curve）をプロット

        予測確率が実際の的中率とどれだけ一致しているかを可視化

        Args:
            y_true: 実際のラベル
            y_pred: 予測確率
            n_bins: ビン数
            output_path: 保存先パス
        """
        # 校正曲線を計算
        fraction_of_positives, mean_predicted_value = calibration_curve(
            y_true, y_pred, n_bins=n_bins, strategy='uniform'
        )

        plt.figure(figsize=(10, 8))

        # 校正曲線
        plt.plot(mean_predicted_value, fraction_of_positives, 's-', label='モデル', linewidth=2)

        # 完全に校正された線（対角線）
        plt.plot([0, 1], [0, 1], 'k--', label='完全な校正', linewidth=2)

        plt.title('校正曲線（Calibration Curve）', fontsize=14)
        plt.xlabel('予測確率', fontsize=12)
        plt.ylabel('実際の的中率', fontsize=12)
        plt.legend(fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"[OK] グラフを保存: {output_path}")
        else:
            plt.show()

        plt.close()

    def plot_roc_curve(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        output_path: Optional[str] = None
    ):
        """
        ROC曲線をプロット

        Args:
            y_true: 実際のラベル
            y_pred: 予測確率
            output_path: 保存先パス
        """
        fpr, tpr, thresholds = roc_curve(y_true, y_pred)
        roc_auc = auc(fpr, tpr)

        plt.figure(figsize=(10, 8))
        plt.plot(fpr, tpr, label=f'ROC curve (AUC = {roc_auc:.3f})', linewidth=2)
        plt.plot([0, 1], [0, 1], 'k--', label='Random', linewidth=2)

        plt.title('ROC曲線', fontsize=14)
        plt.xlabel('偽陽性率（False Positive Rate）', fontsize=12)
        plt.ylabel('真陽性率（True Positive Rate）', fontsize=12)
        plt.legend(fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"[OK] グラフを保存: {output_path}")
        else:
            plt.show()

        plt.close()

    def plot_confusion_matrix(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        threshold: float = 0.5,
        output_path: Optional[str] = None
    ):
        """
        混同行列をプロット

        Args:
            y_true: 実際のラベル
            y_pred: 予測確率
            threshold: 分類閾値
            output_path: 保存先パス
        """
        y_pred_binary = (y_pred >= threshold).astype(int)
        cm = confusion_matrix(y_true, y_pred_binary)

        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', cbar=False)

        plt.title(f'混同行列（閾値: {threshold}）', fontsize=14)
        plt.xlabel('予測ラベル', fontsize=12)
        plt.ylabel('実際のラベル', fontsize=12)
        plt.xticks([0.5, 1.5], ['不的中', '的中'])
        plt.yticks([0.5, 1.5], ['不的中', '的中'])
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"[OK] グラフを保存: {output_path}")
        else:
            plt.show()

        plt.close()

    def plot_feature_importance(
        self,
        feature_names: List[str],
        importances: np.ndarray,
        top_n: int = 20,
        output_path: Optional[str] = None
    ):
        """
        特徴量重要度をプロット

        Args:
            feature_names: 特徴量名リスト
            importances: 特徴量重要度
            top_n: 表示する特徴量数（上位N個）
            output_path: 保存先パス
        """
        # 重要度でソート
        indices = np.argsort(importances)[::-1][:top_n]
        top_features = [feature_names[i] for i in indices]
        top_importances = importances[indices]

        plt.figure(figsize=(12, 8))
        plt.barh(range(len(top_features)), top_importances, align='center')
        plt.yticks(range(len(top_features)), top_features)
        plt.xlabel('重要度', fontsize=12)
        plt.title(f'特徴量重要度（上位{top_n}個）', fontsize=14)
        plt.gca().invert_yaxis()
        plt.grid(True, alpha=0.3, axis='x')
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"[OK] グラフを保存: {output_path}")
        else:
            plt.show()

        plt.close()

    def plot_prediction_vs_actual(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        bins: int = 10,
        output_path: Optional[str] = None
    ):
        """
        予測確率別の実際の的中率をプロット

        Args:
            y_true: 実際のラベル
            y_pred: 予測確率
            bins: ビン数
            output_path: 保存先パス
        """
        # 予測確率をビンに分割
        bin_edges = np.linspace(0, 1, bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        actual_rates = []
        pred_rates = []
        counts = []

        for i in range(bins):
            mask = (y_pred >= bin_edges[i]) & (y_pred < bin_edges[i + 1])
            if mask.sum() > 0:
                actual_rates.append(y_true[mask].mean())
                pred_rates.append(y_pred[mask].mean())
                counts.append(mask.sum())
            else:
                actual_rates.append(0)
                pred_rates.append(bin_centers[i])
                counts.append(0)

        # プロット
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

        # 予測確率 vs 実際の的中率
        ax1.scatter(pred_rates, actual_rates, s=[c * 10 for c in counts], alpha=0.6)
        ax1.plot([0, 1], [0, 1], 'r--', label='理想的な予測', linewidth=2)
        ax1.set_xlabel('平均予測確率', fontsize=12)
        ax1.set_ylabel('実際の的中率', fontsize=12)
        ax1.set_title('予測確率 vs 実際の的中率', fontsize=14)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # ビン別のサンプル数
        ax2.bar(bin_centers, counts, width=(bin_edges[1] - bin_edges[0]) * 0.8)
        ax2.set_xlabel('予測確率', fontsize=12)
        ax2.set_ylabel('サンプル数', fontsize=12)
        ax2.set_title('予測確率別サンプル数', fontsize=14)
        ax2.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"[OK] グラフを保存: {output_path}")
        else:
            plt.show()

        plt.close()

    def generate_comprehensive_report(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        feature_names: Optional[List[str]] = None,
        importances: Optional[np.ndarray] = None,
        output_dir: str = "prediction_report"
    ):
        """
        包括的な可視化レポートを生成

        Args:
            y_true: 実際のラベル
            y_pred: 予測確率
            feature_names: 特徴量名リスト
            importances: 特徴量重要度
            output_dir: 出力ディレクトリ
        """
        # 出力ディレクトリを作成
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        print("=" * 70)
        print("予測結果可視化レポート生成")
        print("=" * 70)

        # 1. 予測確率の分布
        print("\n[1/6] 予測確率の分布")
        self.plot_prediction_distribution(
            y_pred, y_true,
            output_path=str(output_path / "01_prediction_distribution.png")
        )

        # 2. 校正曲線
        print("[2/6] 校正曲線")
        self.plot_calibration_curve(
            y_true, y_pred,
            output_path=str(output_path / "02_calibration_curve.png")
        )

        # 3. ROC曲線
        print("[3/6] ROC曲線")
        self.plot_roc_curve(
            y_true, y_pred,
            output_path=str(output_path / "03_roc_curve.png")
        )

        # 4. 混同行列
        print("[4/6] 混同行列")
        self.plot_confusion_matrix(
            y_true, y_pred, threshold=0.5,
            output_path=str(output_path / "04_confusion_matrix.png")
        )

        # 5. 予測確率 vs 実際の的中率
        print("[5/6] 予測確率 vs 実際の的中率")
        self.plot_prediction_vs_actual(
            y_true, y_pred,
            output_path=str(output_path / "05_prediction_vs_actual.png")
        )

        # 6. 特徴量重要度（あれば）
        if feature_names is not None and importances is not None:
            print("[6/6] 特徴量重要度")
            self.plot_feature_importance(
                feature_names, importances,
                output_path=str(output_path / "06_feature_importance.png")
            )

        print("\n" + "=" * 70)
        print(f"レポート生成完了: {output_path}")
        print("=" * 70)


if __name__ == "__main__":
    # テスト実行
    print("=" * 70)
    print("PredictionVisualizer テスト")
    print("=" * 70)

    # ダミーデータ作成
    np.random.seed(42)
    n_samples = 1000

    # 実際のラベル（不均衡）
    y_true = np.random.choice([0, 1], n_samples, p=[0.85, 0.15])

    # 予測確率（的中の場合は高め、不的中の場合は低めに設定）
    y_pred = np.where(
        y_true == 1,
        np.random.beta(5, 2, n_samples),  # 的中の場合は高い確率
        np.random.beta(2, 5, n_samples)   # 不的中の場合は低い確率
    )

    # ダミー特徴量重要度
    feature_names = [f'feature_{i}' for i in range(20)]
    importances = np.random.exponential(scale=100, size=20)

    # 可視化
    visualizer = PredictionVisualizer()

    # 包括的レポート生成
    visualizer.generate_comprehensive_report(
        y_true, y_pred,
        feature_names=feature_names,
        importances=importances,
        output_dir="test_prediction_report"
    )

    print("\n" + "=" * 70)
    print("テスト完了")
    print("=" * 70)
