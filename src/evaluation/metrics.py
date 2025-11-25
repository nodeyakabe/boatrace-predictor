"""
予測精度評価指標
Brier Score, Log Loss, Calibration Curveなど
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


class PredictionMetrics:
    """予測精度評価クラス"""

    @staticmethod
    def brier_score(predicted_probs: List[float], actual_results: List[int]) -> float:
        """
        Brierスコア（確率予測の精度）

        Args:
            predicted_probs: 予測確率のリスト [0.55, 0.14, 0.12, ...]
            actual_results: 実際の結果（1着=1, それ以外=0） [1, 0, 0, ...]

        Returns:
            Brierスコア（0に近いほど良い）

        数式:
            BS = (1/N) * Σ(predicted_prob - actual_result)^2
        """
        if len(predicted_probs) != len(actual_results):
            raise ValueError("予測と実際の結果の数が一致しません")

        if len(predicted_probs) == 0:
            return 0.0

        squared_errors = [(p - a) ** 2 for p, a in zip(predicted_probs, actual_results)]
        return sum(squared_errors) / len(squared_errors)

    @staticmethod
    def log_loss(predicted_probs: List[float], actual_results: List[int], epsilon: float = 1e-15) -> float:
        """
        対数損失（Log Loss）

        Args:
            predicted_probs: 予測確率のリスト
            actual_results: 実際の結果（1着=1, それ以外=0）
            epsilon: ゼロ除算回避用の微小値

        Returns:
            Log Loss（0に近いほど良い）

        数式:
            LL = -(1/N) * Σ(y * log(p) + (1-y) * log(1-p))
        """
        if len(predicted_probs) != len(actual_results):
            raise ValueError("予測と実際の結果の数が一致しません")

        if len(predicted_probs) == 0:
            return 0.0

        # 確率をクリップ（0と1を避ける）
        clipped_probs = [max(epsilon, min(1 - epsilon, p)) for p in predicted_probs]

        log_loss_sum = 0.0
        for p, y in zip(clipped_probs, actual_results):
            log_loss_sum += y * np.log(p) + (1 - y) * np.log(1 - p)

        return -log_loss_sum / len(predicted_probs)

    @staticmethod
    def calibration_curve(
        predicted_probs: List[float],
        actual_results: List[int],
        n_bins: int = 10
    ) -> Tuple[List[float], List[float], List[int]]:
        """
        較正曲線（Calibration Curve）

        予測確率と実際の頻度の一致度を測定

        Args:
            predicted_probs: 予測確率のリスト
            actual_results: 実際の結果（1着=1, それ以外=0）
            n_bins: ビン数（区間数）

        Returns:
            (bin_means, true_frequencies, bin_counts)
            - bin_means: 各ビンの予測確率平均
            - true_frequencies: 各ビンの実際の頻度
            - bin_counts: 各ビンのサンプル数
        """
        if len(predicted_probs) != len(actual_results):
            raise ValueError("予測と実際の結果の数が一致しません")

        if len(predicted_probs) == 0:
            return [], [], []

        # ビンに分割
        bins = np.linspace(0, 1, n_bins + 1)
        bin_means = []
        true_frequencies = []
        bin_counts = []

        for i in range(n_bins):
            bin_min = bins[i]
            bin_max = bins[i + 1]

            # このビンに含まれるサンプル
            in_bin = [
                (p, y) for p, y in zip(predicted_probs, actual_results)
                if bin_min <= p < bin_max or (i == n_bins - 1 and p == bin_max)
            ]

            if len(in_bin) > 0:
                bin_probs = [p for p, _ in in_bin]
                bin_results = [y for _, y in in_bin]

                bin_means.append(np.mean(bin_probs))
                true_frequencies.append(np.mean(bin_results))
                bin_counts.append(len(in_bin))
            else:
                bin_means.append((bin_min + bin_max) / 2)
                true_frequencies.append(0.0)
                bin_counts.append(0)

        return bin_means, true_frequencies, bin_counts

    @staticmethod
    def per_confidence_accuracy(
        predictions: List[Dict],
        results: List[Dict]
    ) -> Dict[str, Dict]:
        """
        信頼度別の的中率

        Args:
            predictions: 予測結果リスト
                [
                    {'pit_number': 1, 'rank_prediction': 1, 'confidence': 'A', ...},
                    ...
                ]
            results: 実際の結果リスト
                [
                    {'pit_number': 1, 'rank': 1, ...},
                    ...
                ]

        Returns:
            {
                'A': {'total': 100, 'correct': 85, 'accuracy': 0.85},
                'B': {'total': 150, 'correct': 105, 'accuracy': 0.70},
                ...
            }
        """
        # 結果をpit_numberでマッピング
        results_map = {r['pit_number']: r['rank'] for r in results}

        # 信頼度別に集計
        confidence_stats = defaultdict(lambda: {'total': 0, 'correct': 0})

        for pred in predictions:
            confidence = pred.get('confidence', 'E')
            pit_number = pred['pit_number']
            predicted_rank = pred.get('rank_prediction', 99)

            if pit_number in results_map:
                actual_rank = results_map[pit_number]

                confidence_stats[confidence]['total'] += 1

                # 順位が一致すれば的中
                if predicted_rank == actual_rank:
                    confidence_stats[confidence]['correct'] += 1

        # 的中率を計算
        result = {}
        for confidence, stats in confidence_stats.items():
            total = stats['total']
            correct = stats['correct']
            accuracy = correct / total if total > 0 else 0.0

            result[confidence] = {
                'total': total,
                'correct': correct,
                'accuracy': accuracy
            }

        return result

    @staticmethod
    def expected_calibration_error(
        predicted_probs: List[float],
        actual_results: List[int],
        n_bins: int = 10
    ) -> float:
        """
        期待較正誤差（Expected Calibration Error: ECE）

        Args:
            predicted_probs: 予測確率のリスト
            actual_results: 実際の結果
            n_bins: ビン数

        Returns:
            ECE（0に近いほど較正されている）

        数式:
            ECE = Σ(|bin_count / total| * |bin_mean - true_freq|)
        """
        bin_means, true_frequencies, bin_counts = PredictionMetrics.calibration_curve(
            predicted_probs, actual_results, n_bins
        )

        if sum(bin_counts) == 0:
            return 0.0

        total_count = sum(bin_counts)
        ece = 0.0

        for bin_mean, true_freq, bin_count in zip(bin_means, true_frequencies, bin_counts):
            if bin_count > 0:
                ece += (bin_count / total_count) * abs(bin_mean - true_freq)

        return ece

    @staticmethod
    def generate_evaluation_report(
        predictions: List[Dict],
        results: List[Dict]
    ) -> str:
        """
        総合評価レポートを生成

        Args:
            predictions: 予測結果リスト
            results: 実際の結果リスト

        Returns:
            レポート文字列
        """
        report = []
        report.append("=" * 80)
        report.append("予測精度評価レポート")
        report.append("=" * 80)
        report.append("")

        # 信頼度別的中率
        confidence_accuracy = PredictionMetrics.per_confidence_accuracy(predictions, results)

        report.append("【信頼度別的中率】")
        report.append("-" * 80)
        report.append("信頼度 | 予測数 | 的中数 | 的中率")
        report.append("-" * 80)

        for confidence in ['A', 'B', 'C', 'D', 'E']:
            if confidence in confidence_accuracy:
                stats = confidence_accuracy[confidence]
                report.append(
                    f"  {confidence}    | {stats['total']:6} | {stats['correct']:6} | {stats['accuracy']*100:6.2f}%"
                )

        report.append("")

        # Brierスコア（1着予測のみ）
        first_place_preds = [p for p in predictions if p.get('rank_prediction') == 1]
        if len(first_place_preds) > 0:
            results_map = {r['pit_number']: r['rank'] for r in results}

            predicted_probs = []
            actual_results = []

            for pred in first_place_preds:
                pit_number = pred['pit_number']
                if pit_number in results_map:
                    # 推定勝率を使用（なければスコアから計算）
                    prob = pred.get('estimated_win_rate', pred.get('total_score', 50) / 100)
                    predicted_probs.append(prob)

                    actual = 1 if results_map[pit_number] == 1 else 0
                    actual_results.append(actual)

            if len(predicted_probs) > 0:
                brier = PredictionMetrics.brier_score(predicted_probs, actual_results)
                logloss = PredictionMetrics.log_loss(predicted_probs, actual_results)
                ece = PredictionMetrics.expected_calibration_error(predicted_probs, actual_results)

                report.append("【確率予測の精度】")
                report.append("-" * 80)
                report.append(f"Brier Score: {brier:.4f}（0に近いほど良い）")
                report.append(f"Log Loss: {logloss:.4f}（0に近いほど良い）")
                report.append(f"ECE (期待較正誤差): {ece:.4f}（0に近いほど良い）")
                report.append("")

        report.append("=" * 80)

        return '\n'.join(report)
