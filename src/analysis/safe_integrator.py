"""
安全統合ロジック（PRE × BEFORE_SAFE）

PRE_SCOREを壊さない保守的な統合
BEFORE_SAFEの重みを最大15%に制限し、PRE予測の精度を維持
"""

from typing import List, Dict
import numpy as np


class SafeIntegrator:
    """PRE × BEFORE_SAFE 安全統合クラス"""

    def __init__(self, before_safe_weight: float = 0.15):
        """
        初期化

        Args:
            before_safe_weight: BEFORE_SAFEの重み（0.0-0.25推奨、デフォルト0.15 Phase 5で引き上げ）
        """
        # 重み設定（保守的）
        self.before_safe_weight = min(max(before_safe_weight, 0.0), 0.25)
        self.pre_weight = 1.0 - self.before_safe_weight

    def integrate(
        self,
        pre_scores: List[float],
        before_safe_scores: List[float]
    ) -> List[float]:
        """
        PRE_SCOREとBEFORE_SAFEスコアを統合

        Args:
            pre_scores: PRE_SCOREリスト（各艇）
            before_safe_scores: BEFORE_SAFEスコアリスト（各艇）

        Returns:
            統合後のスコアリスト
        """
        if len(pre_scores) != len(before_safe_scores):
            raise ValueError("pre_scores and before_safe_scores must have the same length")

        # BEFORE_SAFEをPREスケール（0-100）に正規化
        before_safe_normalized = self._normalize_to_0_100(before_safe_scores)

        # 保守的統合
        final_scores = []
        for pre, before_safe_norm in zip(pre_scores, before_safe_normalized):
            final = self.pre_weight * pre + self.before_safe_weight * before_safe_norm
            final_scores.append(final)

        return final_scores

    def _normalize_to_0_100(self, scores: List[float]) -> List[float]:
        """
        スコアを0-100範囲に正規化

        Args:
            scores: 元のスコアリスト

        Returns:
            正規化されたスコアリスト
        """
        arr = np.array(scores, dtype=float)

        # 最小値・最大値を取得
        min_score = np.nanmin(arr)
        max_score = np.nanmax(arr)

        # 範囲が極小の場合は中央値50で返す
        if max_score - min_score < 1e-6:
            return [50.0] * len(scores)

        # 0-100に正規化
        normalized = 100.0 * (arr - min_score) / (max_score - min_score)

        return normalized.tolist()

    def set_weight(self, before_safe_weight: float):
        """
        BEFORE_SAFEの重みを設定

        Args:
            before_safe_weight: 新しい重み（0.0-0.25）
        """
        self.before_safe_weight = min(max(before_safe_weight, 0.0), 0.25)
        self.pre_weight = 1.0 - self.before_safe_weight

    def get_weights(self) -> Dict[str, float]:
        """
        現在の重みを取得

        Returns:
            {'pre_weight': float, 'before_safe_weight': float}
        """
        return {
            'pre_weight': self.pre_weight,
            'before_safe_weight': self.before_safe_weight
        }
