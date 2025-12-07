# -*- coding: utf-8 -*-
"""
期待値計算エンジン（Edge対応版）

Phase A-③: Edge計算の導入
市場との乖離度（Edge）を数値化し、プラスEdgeの買い目のみを選択
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .config import (
    FEATURES,
    CONFIDENCE_HIT_RATES,
    EV_THRESHOLD,
    KELLY_CONFIG,
    SAFETY_CONFIG,
)


@dataclass
class EVResult:
    """期待値計算結果"""
    ev: float                     # 期待値（prob * odds）
    edge: float                   # 市場乖離度（(model_prob / market_prob) - 1）
    model_prob: float             # モデル予測確率
    market_prob: float            # 市場想定確率（オッズから逆算）
    is_value_bet: bool            # バリューベットか（Edge > 0 かつ EV >= 1.0）
    breakeven_odds: float         # 損益分岐点オッズ


class EVCalculator:
    """
    期待値計算エンジン

    Edge = (モデル確率 / 市場確率) - 1
    - Edge > 0: 市場が過小評価（買い）
    - Edge < 0: 市場が過大評価（見送り）
    """

    # 控除率（競艇は約25%）
    TAKEOUT_RATE = 0.25

    def __init__(self):
        """初期化"""
        pass

    def calc_ev(self, prob: float, odds: float) -> float:
        """
        期待値を計算

        Args:
            prob: 予測確率
            odds: オッズ

        Returns:
            期待値（1.0 = 損益分岐点）
        """
        return prob * odds

    def calc_edge(self, model_prob: float, market_prob: float) -> float:
        """
        市場とのズレ（Edge）を計算

        Edge = (モデル確率 / 市場確率) - 1
        正の値 = 市場が過小評価している（買い）
        負の値 = 市場が過大評価している（見送り）

        Args:
            model_prob: モデルの予測確率
            market_prob: 市場の想定確率（オッズから逆算）

        Returns:
            Edge値（-1.0 ~ ∞）
        """
        if market_prob <= 0:
            return 0.0
        return (model_prob / market_prob) - 1.0

    def market_prob_from_odds(self, odds: float) -> float:
        """
        オッズから市場の想定確率を逆算

        市場確率 = (1 - 控除率) / オッズ

        Args:
            odds: オッズ

        Returns:
            市場想定確率
        """
        if odds <= 0:
            return 0.0
        return (1.0 - self.TAKEOUT_RATE) / odds

    def calc_breakeven_odds(self, prob: float) -> float:
        """
        損益分岐点オッズを計算

        Args:
            prob: 予測確率

        Returns:
            損益分岐点オッズ
        """
        if prob <= 0:
            return float('inf')
        return 1.0 / prob

    def calc_ev_with_edge(
        self,
        confidence: str,
        odds: float,
        bet_type: str = 'trifecta'
    ) -> EVResult:
        """
        EV + Edgeを計算

        Args:
            confidence: 信頼度 (B/C/D)
            odds: オッズ
            bet_type: 賭け式 ('trifecta' or 'exacta')

        Returns:
            EVResult
        """
        # モデル確率を取得
        hit_rates = CONFIDENCE_HIT_RATES.get(confidence, {})
        model_prob = hit_rates.get(bet_type, 0.01)

        # 市場確率を計算
        market_prob = self.market_prob_from_odds(odds)

        # Edge計算
        edge = self.calc_edge(model_prob, market_prob)

        # EV計算
        ev = self.calc_ev(model_prob, odds)

        # 損益分岐点オッズ
        breakeven_odds = self.calc_breakeven_odds(model_prob)

        # バリューベット判定
        is_value = False
        if FEATURES.get('use_edge_filter', True):
            is_value = edge > 0 and ev >= EV_THRESHOLD
        else:
            is_value = ev >= EV_THRESHOLD

        return EVResult(
            ev=ev,
            edge=edge,
            model_prob=model_prob,
            market_prob=market_prob,
            is_value_bet=is_value,
            breakeven_odds=breakeven_odds
        )

    def calc_ev_from_prediction(
        self,
        pred_prob: float,
        odds: float
    ) -> EVResult:
        """
        予測確率とオッズからEVを計算

        Args:
            pred_prob: 予測確率（0.0 ~ 1.0）
            odds: オッズ

        Returns:
            EVResult
        """
        market_prob = self.market_prob_from_odds(odds)
        edge = self.calc_edge(pred_prob, market_prob)
        ev = self.calc_ev(pred_prob, odds)
        breakeven_odds = self.calc_breakeven_odds(pred_prob)

        is_value = False
        if FEATURES.get('use_edge_filter', True):
            is_value = edge > 0 and ev >= EV_THRESHOLD
        else:
            is_value = ev >= EV_THRESHOLD

        return EVResult(
            ev=ev,
            edge=edge,
            model_prob=pred_prob,
            market_prob=market_prob,
            is_value_bet=is_value,
            breakeven_odds=breakeven_odds
        )

    def is_valid_ev(self, ev: float) -> bool:
        """
        EV値が異常でないかチェック

        Args:
            ev: 期待値

        Returns:
            正常ならTrue
        """
        max_ev = SAFETY_CONFIG.get('max_ev', 5.0)
        return 0 < ev <= max_ev

    def get_ev_grade(self, ev: float) -> str:
        """
        EV値からグレードを判定

        Args:
            ev: 期待値

        Returns:
            グレード ('S', 'A', 'B', 'C', 'D')
        """
        if ev >= 2.0:
            return 'S'
        elif ev >= 1.5:
            return 'A'
        elif ev >= 1.2:
            return 'B'
        elif ev >= 1.0:
            return 'C'
        else:
            return 'D'

    def get_edge_grade(self, edge: float) -> str:
        """
        Edge値からグレードを判定

        Args:
            edge: 市場乖離度

        Returns:
            グレード ('++++', '+++', '++', '+', '-')
        """
        if edge >= 0.30:
            return '++++'
        elif edge >= 0.20:
            return '+++'
        elif edge >= 0.10:
            return '++'
        elif edge >= 0.0:
            return '+'
        else:
            return '-'

    def compare_bets(
        self,
        bets: list
    ) -> list:
        """
        複数の買い目をEV/Edgeで比較・ソート

        Args:
            bets: [{'combination': '1-2-3', 'odds': 30.5, 'confidence': 'D'}, ...]

        Returns:
            EV順にソートされたリスト
        """
        results = []

        for bet in bets:
            ev_result = self.calc_ev_with_edge(
                confidence=bet.get('confidence', 'D'),
                odds=bet.get('odds', 0),
                bet_type=bet.get('bet_type', 'trifecta')
            )

            results.append({
                **bet,
                'ev': ev_result.ev,
                'edge': ev_result.edge,
                'is_value_bet': ev_result.is_value_bet,
                'ev_grade': self.get_ev_grade(ev_result.ev),
                'edge_grade': self.get_edge_grade(ev_result.edge),
            })

        # EV降順でソート
        results.sort(key=lambda x: x['ev'], reverse=True)

        return results


def calc_simple_ev(prob: float, odds: float) -> float:
    """
    シンプルな期待値計算（ユーティリティ関数）

    Args:
        prob: 確率
        odds: オッズ

    Returns:
        期待値
    """
    return prob * odds


def calc_simple_edge(model_prob: float, odds: float, takeout: float = 0.25) -> float:
    """
    シンプルなEdge計算（ユーティリティ関数）

    Args:
        model_prob: モデル予測確率
        odds: オッズ
        takeout: 控除率

    Returns:
        Edge値
    """
    if odds <= 0:
        return 0.0
    market_prob = (1.0 - takeout) / odds
    if market_prob <= 0:
        return 0.0
    return (model_prob / market_prob) - 1.0
