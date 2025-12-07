# -*- coding: utf-8 -*-
"""
Kelly基準計算エンジン

Phase C-②: 簡易Kelly導入
0.25 Kelly + キャップで資金変動リスクを抑制しつつ期待値最大化
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .config import FEATURES, KELLY_CONFIG, BET_UNIT


@dataclass
class KellyBetResult:
    """Kelly計算結果"""
    bet_amount: int              # 推奨賭け金（円、100円単位）
    kelly_fraction: float        # Kelly分数（0.0 ~ 1.0）
    edge: float                  # Edge
    is_bet: bool                 # 購入判定
    reason: str                  # 判定理由


class KellyCalculator:
    """
    簡易Kelly基準計算

    Kelly公式: f* = (bp - q) / b
    - b = オッズ - 1（純利益倍率）
    - p = 勝率（モデル予測確率）
    - q = 1 - p（負率）

    リスク抑制策:
    - フラクショナルKelly（0.25 Kelly）
    - 資金の5%を上限
    - Edge 5%未満は購入しない
    """

    def __init__(
        self,
        bankroll: int = 100000,
        fraction: float = None,
        max_bet_ratio: float = None,
        min_edge: float = None
    ):
        """
        初期化

        Args:
            bankroll: 資金（円）
            fraction: Kelly分数（デフォルト: config値）
            max_bet_ratio: 最大賭け金比率（デフォルト: config値）
            min_edge: 最小Edge（デフォルト: config値）
        """
        self.bankroll = bankroll
        self.fraction = fraction or KELLY_CONFIG['fraction']
        self.max_bet_ratio = max_bet_ratio or KELLY_CONFIG['max_bet_ratio']
        self.min_edge = min_edge or KELLY_CONFIG['min_edge']

    def update_bankroll(self, new_bankroll: int):
        """資金を更新"""
        self.bankroll = new_bankroll

    def calc_kelly_fraction(self, prob: float, odds: float) -> float:
        """
        Kelly分数を計算

        Args:
            prob: 予測確率（0.0 ~ 1.0）
            odds: オッズ

        Returns:
            Kelly分数（0.0 ~ 1.0）
        """
        if odds <= 1 or prob <= 0 or prob >= 1:
            return 0.0

        b = odds - 1.0  # 純利益倍率
        p = prob
        q = 1.0 - p

        # Kelly公式
        kelly = (b * p - q) / b

        return max(0.0, kelly)

    def calc_edge(self, prob: float, odds: float) -> float:
        """
        Edgeを計算

        Edge = (モデル確率 × オッズ) - 1
        = 期待値 - 1

        Args:
            prob: 予測確率
            odds: オッズ

        Returns:
            Edge（-1.0 ~ ∞）
        """
        return prob * odds - 1.0

    def calc_bet_amount(
        self,
        prob: float,
        odds: float
    ) -> KellyBetResult:
        """
        Kelly基準で賭け金を計算

        Args:
            prob: 予測確率（0.0 ~ 1.0）
            odds: オッズ

        Returns:
            KellyBetResult
        """
        # Kelly機能がOFFの場合は固定金額
        if not FEATURES.get('use_kelly', False):
            return KellyBetResult(
                bet_amount=BET_UNIT,
                kelly_fraction=0.0,
                edge=self.calc_edge(prob, odds),
                is_bet=True,
                reason='Kelly機能OFF（固定金額）'
            )

        # Edge計算
        edge = self.calc_edge(prob, odds)

        # Edge不足
        if edge < self.min_edge:
            return KellyBetResult(
                bet_amount=0,
                kelly_fraction=0.0,
                edge=edge,
                is_bet=False,
                reason=f'Edge {edge:.1%} < 最小Edge {self.min_edge:.1%}'
            )

        # Kelly分数計算
        kelly_full = self.calc_kelly_fraction(prob, odds)

        if kelly_full <= 0:
            return KellyBetResult(
                bet_amount=0,
                kelly_fraction=0.0,
                edge=edge,
                is_bet=False,
                reason='Kelly分数が0以下'
            )

        # フラクショナルKelly
        kelly_adjusted = kelly_full * self.fraction

        # 最大賭け金制限
        kelly_capped = min(kelly_adjusted, self.max_bet_ratio)

        # 賭け金計算（100円単位に丸め）
        bet_amount = int(self.bankroll * kelly_capped)
        bet_amount = max(BET_UNIT, (bet_amount // 100) * 100)

        return KellyBetResult(
            bet_amount=bet_amount,
            kelly_fraction=kelly_capped,
            edge=edge,
            is_bet=True,
            reason=f'Kelly {kelly_full:.2%} → {self.fraction}Kelly → {kelly_capped:.2%}'
        )

    def calc_optimal_bet(
        self,
        confidence: str,
        odds: float
    ) -> KellyBetResult:
        """
        信頼度とオッズから最適賭け金を計算

        Args:
            confidence: 信頼度 (B/C/D)
            odds: オッズ

        Returns:
            KellyBetResult
        """
        from .config import CONFIDENCE_HIT_RATES

        hit_rates = CONFIDENCE_HIT_RATES.get(confidence, {})
        prob = hit_rates.get('trifecta', 0.01)

        return self.calc_bet_amount(prob, odds)

    def simulate_growth(
        self,
        bet_history: list
    ) -> Dict[str, Any]:
        """
        資金成長をシミュレーション

        Args:
            bet_history: [
                {'bet': 500, 'odds': 30.0, 'hit': True},
                {'bet': 300, 'odds': 45.0, 'hit': False},
                ...
            ]

        Returns:
            {
                'final_bankroll': ...,
                'max_drawdown': ...,
                'total_bets': ...,
                'total_hits': ...,
                'roi': ...,
            }
        """
        bankroll = self.bankroll
        peak = bankroll
        max_drawdown = 0
        total_bets = 0
        total_hits = 0
        total_invested = 0
        total_returned = 0

        history = []

        for bet in bet_history:
            bet_amount = bet['bet']
            odds = bet['odds']
            hit = bet['hit']

            total_bets += 1
            total_invested += bet_amount

            if hit:
                total_hits += 1
                payout = int(bet_amount * odds)
                total_returned += payout
                bankroll += payout - bet_amount
            else:
                bankroll -= bet_amount

            # ドローダウン計算
            if bankroll > peak:
                peak = bankroll
            drawdown = (peak - bankroll) / peak if peak > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)

            history.append({
                'bankroll': bankroll,
                'drawdown': drawdown,
            })

        roi = (total_returned / total_invested * 100) if total_invested > 0 else 0

        return {
            'final_bankroll': bankroll,
            'initial_bankroll': self.bankroll,
            'profit': bankroll - self.bankroll,
            'max_drawdown': max_drawdown,
            'total_bets': total_bets,
            'total_hits': total_hits,
            'hit_rate': total_hits / total_bets if total_bets > 0 else 0,
            'roi': roi,
            'history': history,
        }

    def get_risk_assessment(self, drawdown: float) -> str:
        """
        ドローダウンからリスク評価

        Args:
            drawdown: ドローダウン（0.0 ~ 1.0）

        Returns:
            リスク評価 ('低', '中', '高', '危険')
        """
        if drawdown < 0.1:
            return '低'
        elif drawdown < 0.25:
            return '中'
        elif drawdown < 0.5:
            return '高'
        else:
            return '危険'


class SimpleKelly:
    """
    シンプルなKelly計算（ユーティリティクラス）

    計画書の仕様に準拠:
    - FRACTION = 0.25
    - MAX_BET_RATIO = 0.05
    - MIN_EDGE = 0.05
    """

    FRACTION = 0.25
    MAX_BET_RATIO = 0.05
    MIN_EDGE = 0.05

    @classmethod
    def calc_bet_amount(
        cls,
        bankroll: int,
        edge: float,
        odds: float
    ) -> int:
        """
        賭け金を計算

        Args:
            bankroll: 資金
            edge: Edge
            odds: オッズ

        Returns:
            賭け金（円）
        """
        if edge < cls.MIN_EDGE:
            return 0

        # 勝率を推定
        p = 0.75 / odds + edge  # 市場確率 + Edge
        q = 1 - p
        b = odds - 1

        if b <= 0 or p <= 0 or p >= 1:
            return 0

        # Kelly計算
        kelly_fraction = (b * p - q) / b
        if kelly_fraction <= 0:
            return 0

        # 0.25 Kelly + キャップ
        bet_ratio = min(kelly_fraction * cls.FRACTION, cls.MAX_BET_RATIO)
        bet_amount = int(bankroll * bet_ratio)

        # 100円単位に丸め
        return max(100, (bet_amount // 100) * 100)
