"""
確率補正モジュール

モデルの艇番バイアスを統計的に補正する
"""

from typing import Dict
import math


class ProbabilityAdjuster:
    """
    予測確率の事後補正クラス

    問題: モデルは艇番（コース位置）を特徴量に含んでいないため、
         1号艇を過小評価、5号艇・6号艇を過大評価している

    解決策: 実際の艇番別勝率で補正
    """

    # 実際のレース結果から算出した艇番別1着率（210レースの統計）
    # 出典: model_bias_analysis_20251118.md
    ACTUAL_WIN_RATES = {
        1: 0.495,  # 49.5%
        2: 0.129,  # 12.9%
        3: 0.133,  # 13.3%
        4: 0.100,  # 10.0%
        5: 0.119,  # 11.9%
        6: 0.024,  # 2.4%
    }

    # 均等分布（バイアスがない場合の期待値）
    UNIFORM_RATE = 1.0 / 6.0  # 約16.7%

    def __init__(self, adjustment_strength: float = 0.7):
        """
        初期化

        Args:
            adjustment_strength: 補正の強さ（0.0〜1.0）
                                0.0 = 補正なし
                                1.0 = 完全補正
                                0.7 = デフォルト（モデルの予測も考慮）
        """
        self.adjustment_strength = max(0.0, min(1.0, adjustment_strength))

        # 補正係数を事前計算
        self.correction_factors = {}
        for pit, actual_rate in self.ACTUAL_WIN_RATES.items():
            # 補正係数 = 実際の勝率 / 均等分布
            factor = actual_rate / self.UNIFORM_RATE

            # 補正強度を適用（1.0に近づける = 補正を弱める）
            adjusted_factor = 1.0 + (factor - 1.0) * self.adjustment_strength

            self.correction_factors[pit] = adjusted_factor

    def adjust_trifecta_probabilities(self, probabilities: Dict[str, float]) -> Dict[str, float]:
        """
        3連単確率を補正

        Args:
            probabilities: {'1-2-3': 0.08, '1-2-4': 0.06, ...}

        Returns:
            補正後の確率（合計=1.0に正規化済み）
        """
        if not probabilities:
            return probabilities

        adjusted = {}

        for combo, prob in probabilities.items():
            # 1着艇番を取得
            first_pit = int(combo.split('-')[0])

            # 補正係数を適用
            correction = self.correction_factors.get(first_pit, 1.0)
            adjusted[combo] = prob * correction

        # 正規化（合計を1.0にする）
        total = sum(adjusted.values())
        if total > 0:
            normalized = {k: v / total for k, v in adjusted.items()}
        else:
            normalized = probabilities  # フォールバック

        return normalized

    def get_adjustment_info(self) -> Dict:
        """
        補正情報を取得（デバッグ用）

        Returns:
            {
                'strength': 0.7,
                'correction_factors': {1: 2.97, 2: 0.77, ...}
            }
        """
        return {
            'strength': self.adjustment_strength,
            'correction_factors': self.correction_factors,
            'actual_win_rates': self.ACTUAL_WIN_RATES
        }

    @classmethod
    def calculate_bias(cls, predicted_freq: Dict[int, float]) -> Dict[int, float]:
        """
        予測頻度のバイアスを計算（分析用）

        Args:
            predicted_freq: {1: 0.243, 2: 0.143, ...}  # 各艇番が1着予測される頻度

        Returns:
            {1: -0.252, 2: +0.014, ...}  # バイアス（負=過小評価、正=過大評価）
        """
        bias = {}
        for pit in range(1, 7):
            actual = cls.ACTUAL_WIN_RATES.get(pit, cls.UNIFORM_RATE)
            predicted = predicted_freq.get(pit, cls.UNIFORM_RATE)
            bias[pit] = predicted - actual

        return bias
