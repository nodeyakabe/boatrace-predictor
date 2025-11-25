"""
評価指標モジュール

改善点_1118.md ⑤ 評価指標の拡充
- Brier score (既存)
- Logloss (既存)
- Rank correlation (新規)
- Top-N Accuracy (新規)
- Expected Calibration Error (新規)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from scipy.stats import spearmanr, kendalltau
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    roc_auc_score,
    accuracy_score
)


class RankingMetrics:
    """順位予測の評価指標"""

    @staticmethod
    def rank_correlation(
        y_true_ranks: np.ndarray,
        y_pred_scores: np.ndarray,
        method: str = 'spearman'
    ) -> Dict[str, float]:
        """
        順位相関係数を計算

        Args:
            y_true_ranks: 実際の着順 (1-6)
            y_pred_scores: 予測スコア (高いほど1着に近い)
            method: 'spearman' or 'kendall'

        Returns:
            相関係数と p値
        """
        # 予測スコアを逆順に変換（高スコア→1位）
        pred_ranks = pd.Series(y_pred_scores).rank(ascending=False).values

        if method == 'spearman':
            corr, pvalue = spearmanr(y_true_ranks, pred_ranks)
        elif method == 'kendall':
            corr, pvalue = kendalltau(y_true_ranks, pred_ranks)
        else:
            raise ValueError(f"Unknown method: {method}")

        return {
            'correlation': corr if not np.isnan(corr) else 0.0,
            'p_value': pvalue if not np.isnan(pvalue) else 1.0
        }

    @staticmethod
    def top_n_accuracy(
        y_true: np.ndarray,
        y_pred_probs: np.ndarray,
        n: int = 1
    ) -> float:
        """
        Top-N正解率を計算

        Args:
            y_true: 実際のラベル (1着なら1, それ以外は0)
            y_pred_probs: 予測確率
            n: 上位N件

        Returns:
            Top-N正解率
        """
        if len(y_true) == 0:
            return 0.0

        # 予測確率の高い順にソート
        sorted_indices = np.argsort(y_pred_probs)[::-1]

        # 上位N件に正解が含まれているか
        top_n_indices = sorted_indices[:n]
        hit = np.any(y_true[top_n_indices] == 1)

        return float(hit)

    @staticmethod
    def race_top_n_accuracy(
        race_results: List[Dict],
        n_values: List[int] = [1, 2, 3]
    ) -> Dict[str, float]:
        """
        レース単位でのTop-N正解率を計算

        Args:
            race_results: レースごとの結果リスト
                [{'true_rank': [1,2,3,4,5,6], 'pred_probs': [0.3,0.2,...]}, ...]
            n_values: 計算するNの値リスト

        Returns:
            各NでのTop-N正解率
        """
        results = {}

        for n in n_values:
            hits = 0
            total = 0

            for race in race_results:
                if 'true_rank' not in race or 'pred_probs' not in race:
                    continue

                true_ranks = np.array(race['true_rank'])
                pred_probs = np.array(race['pred_probs'])

                # 予測の上位N艇
                top_n_boats = np.argsort(pred_probs)[::-1][:n]

                # 実際の1着が上位Nに含まれているか
                first_place_idx = np.argmin(true_ranks)
                if first_place_idx in top_n_boats:
                    hits += 1
                total += 1

            results[f'top_{n}_accuracy'] = hits / total if total > 0 else 0.0

        return results


class CalibrationMetrics:
    """確率校正の評価指標"""

    @staticmethod
    def expected_calibration_error(
        y_true: np.ndarray,
        y_pred_prob: np.ndarray,
        n_bins: int = 10
    ) -> float:
        """
        Expected Calibration Error (ECE) を計算

        Args:
            y_true: 実際のラベル
            y_pred_prob: 予測確率
            n_bins: ビン数

        Returns:
            ECE値 (0に近いほど良い)
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

    @staticmethod
    def maximum_calibration_error(
        y_true: np.ndarray,
        y_pred_prob: np.ndarray,
        n_bins: int = 10
    ) -> float:
        """
        Maximum Calibration Error (MCE) を計算

        Args:
            y_true: 実際のラベル
            y_pred_prob: 予測確率
            n_bins: ビン数

        Returns:
            MCE値
        """
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        mce = 0.0

        for i in range(n_bins):
            in_bin = (y_pred_prob > bin_boundaries[i]) & (y_pred_prob <= bin_boundaries[i + 1])

            if in_bin.sum() > 0:
                avg_confidence = y_pred_prob[in_bin].mean()
                avg_accuracy = y_true[in_bin].mean()
                mce = max(mce, np.abs(avg_accuracy - avg_confidence))

        return mce


class ComprehensiveEvaluator:
    """包括的な評価を行うクラス"""

    def __init__(self):
        self.ranking_metrics = RankingMetrics()
        self.calibration_metrics = CalibrationMetrics()

    def evaluate_binary_classification(
        self,
        y_true: np.ndarray,
        y_pred_prob: np.ndarray
    ) -> Dict[str, float]:
        """
        2値分類の包括的評価

        Args:
            y_true: 実際のラベル
            y_pred_prob: 予測確率

        Returns:
            各種指標の辞書
        """
        y_true = np.array(y_true)
        y_pred_prob = np.array(y_pred_prob)

        # 基本指標
        metrics = {
            'brier_score': brier_score_loss(y_true, y_pred_prob),
            'log_loss': log_loss(y_true, y_pred_prob, labels=[0, 1]),
        }

        # AUC (エラーハンドリング付き)
        try:
            metrics['auc'] = roc_auc_score(y_true, y_pred_prob)
        except ValueError:
            metrics['auc'] = 0.5  # 1クラスのみの場合

        # 校正指標
        metrics['ece'] = self.calibration_metrics.expected_calibration_error(
            y_true, y_pred_prob
        )
        metrics['mce'] = self.calibration_metrics.maximum_calibration_error(
            y_true, y_pred_prob
        )

        # Top-N Accuracy
        for n in [1, 2, 3]:
            metrics[f'top_{n}_accuracy'] = self.ranking_metrics.top_n_accuracy(
                y_true, y_pred_prob, n=n
            )

        return metrics

    def evaluate_race_predictions(
        self,
        race_results: List[Dict]
    ) -> Dict[str, float]:
        """
        レース予測の包括的評価

        Args:
            race_results: レースごとの結果
                [{'true_rank': [...], 'pred_probs': [...], 'pred_scores': [...]}, ...]

        Returns:
            各種指標の辞書
        """
        metrics = {}

        # Rank correlation (全レース平均)
        spearman_corrs = []
        kendall_corrs = []

        for race in race_results:
            if 'true_rank' in race and 'pred_scores' in race:
                sp = self.ranking_metrics.rank_correlation(
                    np.array(race['true_rank']),
                    np.array(race['pred_scores']),
                    method='spearman'
                )
                kt = self.ranking_metrics.rank_correlation(
                    np.array(race['true_rank']),
                    np.array(race['pred_scores']),
                    method='kendall'
                )
                spearman_corrs.append(sp['correlation'])
                kendall_corrs.append(kt['correlation'])

        if spearman_corrs:
            metrics['spearman_correlation'] = np.mean(spearman_corrs)
            metrics['kendall_correlation'] = np.mean(kendall_corrs)

        # Top-N Accuracy
        top_n_results = self.ranking_metrics.race_top_n_accuracy(
            race_results, n_values=[1, 2, 3]
        )
        metrics.update(top_n_results)

        return metrics

    def format_report(self, metrics: Dict[str, float]) -> str:
        """
        評価結果をフォーマットして表示

        Args:
            metrics: 評価指標の辞書

        Returns:
            フォーマットされた文字列
        """
        lines = ["=" * 50, "評価指標レポート", "=" * 50, ""]

        # 基本指標
        if 'auc' in metrics:
            lines.append("【基本指標】")
            lines.append(f"  AUC:         {metrics.get('auc', 0):.4f}")
            lines.append(f"  Brier Score: {metrics.get('brier_score', 0):.4f}")
            lines.append(f"  Log Loss:    {metrics.get('log_loss', 0):.4f}")
            lines.append("")

        # 校正指標
        if 'ece' in metrics:
            lines.append("【校正指標】")
            lines.append(f"  ECE: {metrics.get('ece', 0):.4f}")
            lines.append(f"  MCE: {metrics.get('mce', 0):.4f}")
            lines.append("")

        # 順位相関
        if 'spearman_correlation' in metrics:
            lines.append("【順位相関】")
            lines.append(f"  Spearman: {metrics.get('spearman_correlation', 0):.4f}")
            lines.append(f"  Kendall:  {metrics.get('kendall_correlation', 0):.4f}")
            lines.append("")

        # Top-N Accuracy
        top_n_keys = [k for k in metrics.keys() if k.startswith('top_')]
        if top_n_keys:
            lines.append("【Top-N Accuracy】")
            for key in sorted(top_n_keys):
                n = key.split('_')[1]
                lines.append(f"  Top-{n}: {metrics.get(key, 0):.4f}")
            lines.append("")

        lines.append("=" * 50)

        return "\n".join(lines)


def evaluate_model(
    y_true: np.ndarray,
    y_pred_prob: np.ndarray,
    race_results: Optional[List[Dict]] = None
) -> Dict[str, float]:
    """
    便利関数: モデルを包括的に評価

    Args:
        y_true: 実際のラベル
        y_pred_prob: 予測確率
        race_results: レースごとの結果（オプション）

    Returns:
        全評価指標
    """
    evaluator = ComprehensiveEvaluator()

    # 2値分類評価
    metrics = evaluator.evaluate_binary_classification(y_true, y_pred_prob)

    # レース予測評価
    if race_results:
        race_metrics = evaluator.evaluate_race_predictions(race_results)
        metrics.update(race_metrics)

    return metrics


if __name__ == "__main__":
    # テスト
    np.random.seed(42)

    # 2値分類のテスト
    y_true = np.random.randint(0, 2, 100)
    y_pred_prob = np.clip(y_true + np.random.normal(0, 0.3, 100), 0, 1)

    evaluator = ComprehensiveEvaluator()
    metrics = evaluator.evaluate_binary_classification(y_true, y_pred_prob)
    print(evaluator.format_report(metrics))

    # レース予測のテスト
    race_results = []
    for _ in range(20):
        true_rank = np.random.permutation([1, 2, 3, 4, 5, 6])
        # 1着に近いほど高いスコア（ノイズ付き）
        pred_scores = 7 - true_rank + np.random.normal(0, 1, 6)
        pred_probs = np.exp(pred_scores) / np.sum(np.exp(pred_scores))

        race_results.append({
            'true_rank': true_rank.tolist(),
            'pred_scores': pred_scores.tolist(),
            'pred_probs': pred_probs.tolist()
        })

    race_metrics = evaluator.evaluate_race_predictions(race_results)
    print("\n【レース予測評価】")
    for key, value in race_metrics.items():
        print(f"  {key}: {value:.4f}")
