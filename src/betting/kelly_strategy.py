"""
Kelly基準投資戦略

期待値ベースで購入判定を行い、Kelly基準で最適な賭け金を計算
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class BetRecommendation:
    """購入推奨情報"""
    combination: str  # 買い目（例: "1-2-3"）
    pred_prob: float  # 予測確率（校正済み）
    odds: float  # オッズ
    expected_value: float  # 期待値
    kelly_fraction: float  # Kelly分数
    recommended_bet: float  # 推奨賭け金
    confidence: str  # 信頼度（High/Medium/Low）


class KellyBettingStrategy:
    """
    Kelly基準での投資戦略

    期待値 = pred_prob × odds - 1
    EV > 0 の買い目のみ購入
    Kelly基準で資金配分
    """

    def __init__(
        self,
        bankroll: float = 10000,
        kelly_fraction: float = 0.25,
        min_ev: float = 0.05,
        max_bet_ratio: float = 0.2
    ):
        """
        Args:
            bankroll: 資金（円）
            kelly_fraction: Kelly分数（0.25 = 1/4 Kelly、リスク調整）
            min_ev: 最小期待値（5%以上）
            max_bet_ratio: 最大賭け金比率（資金の20%まで）
        """
        self.bankroll = bankroll
        self.kelly_fraction = kelly_fraction
        self.min_ev = min_ev
        self.max_bet_ratio = max_bet_ratio

    def calculate_expected_value(self, pred_prob: float, odds: float) -> float:
        """
        期待値を計算

        期待値 = pred_prob × odds - 1

        Args:
            pred_prob: 予測確率（校正済み）
            odds: オッズ

        Returns:
            expected_value: 期待値
        """
        return pred_prob * odds - 1.0

    def calculate_kelly_bet(
        self,
        pred_prob: float,
        odds: float
    ) -> Tuple[float, float]:
        """
        Kelly基準での賭け金を計算

        Kelly formula: f* = (bp - q) / b
        where:
            b = odds - 1 (純利益倍率)
            p = pred_prob (勝率)
            q = 1 - p (負率)

        Args:
            pred_prob: 予測確率
            odds: オッズ

        Returns:
            kelly_fraction: Kelly分数（0〜1）
            bet_amount: 賭け金（円）
        """
        p = pred_prob
        b = odds - 1.0  # 純利益倍率
        q = 1.0 - p

        # Kelly formula
        kelly_f = (b * p - q) / b

        # フラクショナルKelly（リスク削減）
        adjusted_kelly_f = max(0.0, kelly_f * self.kelly_fraction)

        # 最大賭け金制限
        adjusted_kelly_f = min(adjusted_kelly_f, self.max_bet_ratio)

        # 賭け金計算
        bet_amount = self.bankroll * adjusted_kelly_f

        return adjusted_kelly_f, bet_amount

    def select_bets(
        self,
        predictions: List[Dict],
        odds_data: Dict[str, float],
        buy_score: float = 1.0
    ) -> List[BetRecommendation]:
        """
        購入すべき買い目を選定

        Args:
            predictions: 予測結果のリスト
                [
                    {'combination': '1-2-3', 'prob': 0.15},
                    {'combination': '1-3-2', 'prob': 0.12},
                    ...
                ]
            odds_data: オッズデータ
                {'1-2-3': 10.5, '1-3-2': 15.2, ...}
            buy_score: レース選別スコア（Stage1の出力）

        Returns:
            List[BetRecommendation]: 購入推奨リスト
        """
        recommendations = []

        for pred in predictions:
            combination = pred['combination']
            pred_prob = pred['prob']

            # オッズ取得
            if combination not in odds_data:
                continue

            odds = odds_data[combination]

            # 期待値計算
            ev = self.calculate_expected_value(pred_prob, odds)

            # 期待値が閾値以下ならスキップ
            if ev < self.min_ev:
                continue

            # Kelly賭け金計算
            kelly_f, bet_amount = self.calculate_kelly_bet(pred_prob, odds)

            # buy_scoreで調整（Stage1の信頼度を反映）
            adjusted_bet_amount = bet_amount * buy_score

            # 信頼度判定
            if ev > 0.15 and buy_score > 0.7:
                confidence = "High"
            elif ev > 0.08 and buy_score > 0.5:
                confidence = "Medium"
            else:
                confidence = "Low"

            recommendations.append(BetRecommendation(
                combination=combination,
                pred_prob=pred_prob,
                odds=odds,
                expected_value=ev,
                kelly_fraction=kelly_f,
                recommended_bet=adjusted_bet_amount,
                confidence=confidence
            ))

        # 期待値順にソート
        recommendations.sort(key=lambda x: x.expected_value, reverse=True)

        return recommendations

    def optimize_portfolio(
        self,
        recommendations: List[BetRecommendation],
        max_combinations: int = 5
    ) -> List[BetRecommendation]:
        """
        ポートフォリオ最適化

        複数の買い目を組み合わせて、リスク分散しつつリターンを最大化

        Args:
            recommendations: 購入推奨リスト
            max_combinations: 最大購入組み合わせ数

        Returns:
            List[BetRecommendation]: 最適化された購入推奨リスト
        """
        # 上位N件を選択
        top_recommendations = recommendations[:max_combinations]

        # 総賭け金が資金を超えないように調整
        total_bet = sum(rec.recommended_bet for rec in top_recommendations)

        if total_bet > self.bankroll * self.max_bet_ratio:
            # 比例配分で調整
            adjustment_factor = (self.bankroll * self.max_bet_ratio) / total_bet

            optimized = []
            for rec in top_recommendations:
                optimized.append(BetRecommendation(
                    combination=rec.combination,
                    pred_prob=rec.pred_prob,
                    odds=rec.odds,
                    expected_value=rec.expected_value,
                    kelly_fraction=rec.kelly_fraction * adjustment_factor,
                    recommended_bet=rec.recommended_bet * adjustment_factor,
                    confidence=rec.confidence
                ))
            return optimized

        return top_recommendations

    def simulate_outcome(
        self,
        recommendations: List[BetRecommendation],
        actual_result: str
    ) -> Dict:
        """
        結果をシミュレーション（実際の購入後の検証用）

        Args:
            recommendations: 実際に購入した買い目リスト
            actual_result: 実際の結果（例: "1-2-3"）

        Returns:
            Dict: シミュレーション結果
        """
        total_bet = sum(rec.recommended_bet for rec in recommendations)
        total_return = 0.0
        hit_combination = None

        for rec in recommendations:
            if rec.combination == actual_result:
                total_return = rec.recommended_bet * rec.odds
                hit_combination = rec.combination
                break

        profit = total_return - total_bet
        roi = (profit / total_bet * 100) if total_bet > 0 else 0

        return {
            'total_bet': total_bet,
            'total_return': total_return,
            'profit': profit,
            'roi': roi,
            'hit': hit_combination is not None,
            'hit_combination': hit_combination
        }

    def calculate_bankroll_growth(
        self,
        initial_bankroll: float,
        bet_history: List[Dict]
    ) -> pd.DataFrame:
        """
        資金推移を計算

        Args:
            initial_bankroll: 初期資金
            bet_history: 賭けの履歴
                [
                    {'bet': 1000, 'return': 3000, 'date': '2024-01-01'},
                    {'bet': 800, 'return': 0, 'date': '2024-01-02'},
                    ...
                ]

        Returns:
            pd.DataFrame: 資金推移
        """
        bankroll = initial_bankroll
        history = []

        for bet in bet_history:
            bankroll += (bet['return'] - bet['bet'])

            history.append({
                'date': bet['date'],
                'bet': bet['bet'],
                'return': bet['return'],
                'profit': bet['return'] - bet['bet'],
                'bankroll': bankroll,
                'roi': (bet['return'] - bet['bet']) / bet['bet'] * 100 if bet['bet'] > 0 else 0
            })

        df = pd.DataFrame(history)
        return df

    def calculate_risk_metrics(self, bet_history: pd.DataFrame) -> Dict:
        """
        リスク指標を計算

        Args:
            bet_history: 資金推移データ

        Returns:
            Dict: リスク指標
        """
        # 最大ドローダウン
        cummax = bet_history['bankroll'].cummax()
        drawdown = (bet_history['bankroll'] - cummax) / cummax
        max_drawdown = drawdown.min()

        # 勝率
        win_rate = (bet_history['profit'] > 0).mean()

        # 平均ROI
        avg_roi = bet_history['roi'].mean()

        # シャープレシオ（リスク調整後リターン）
        returns = bet_history['bankroll'].pct_change().dropna()
        sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0

        return {
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'avg_roi': avg_roi,
            'sharpe_ratio': sharpe_ratio,
            'total_bets': len(bet_history),
            'total_profit': bet_history['profit'].sum(),
            'final_bankroll': bet_history['bankroll'].iloc[-1]
        }


class ExpectedValueCalculator:
    """
    期待値計算ユーティリティ
    """

    @staticmethod
    def calculate_breakeven_odds(pred_prob: float) -> float:
        """
        損益分岐点オッズを計算

        Args:
            pred_prob: 予測確率

        Returns:
            breakeven_odds: 損益分岐点オッズ
        """
        return 1.0 / pred_prob

    @staticmethod
    def calculate_edge(pred_prob: float, odds: float) -> float:
        """
        エッジ（優位性）を計算

        Args:
            pred_prob: 予測確率
            odds: オッズ

        Returns:
            edge: エッジ（%）
        """
        implied_prob = 1.0 / odds
        edge = (pred_prob - implied_prob) / implied_prob * 100
        return edge

    @staticmethod
    def calculate_roi_range(
        pred_prob: float,
        odds: float,
        bet_amount: float,
        confidence_interval: float = 0.95
    ) -> Tuple[float, float]:
        """
        ROIの信頼区間を計算

        Args:
            pred_prob: 予測確率
            odds: オッズ
            bet_amount: 賭け金
            confidence_interval: 信頼区間（95%）

        Returns:
            (lower_roi, upper_roi): ROIの下限・上限
        """
        # 簡易的な計算（正規近似）
        expected_return = pred_prob * odds * bet_amount
        std_return = np.sqrt(pred_prob * (1 - pred_prob)) * odds * bet_amount

        z_score = 1.96  # 95%信頼区間

        lower_return = expected_return - z_score * std_return
        upper_return = expected_return + z_score * std_return

        lower_roi = (lower_return - bet_amount) / bet_amount * 100
        upper_roi = (upper_return - bet_amount) / bet_amount * 100

        return lower_roi, upper_roi


if __name__ == "__main__":
    # テスト実行
    print("=" * 60)
    print("Kelly基準投資戦略 テスト")
    print("=" * 60)

    # 初期化
    strategy = KellyBettingStrategy(
        bankroll=10000,
        kelly_fraction=0.25,
        min_ev=0.05
    )

    # サンプル予測データ
    predictions = [
        {'combination': '1-2-3', 'prob': 0.15},
        {'combination': '1-3-2', 'prob': 0.12},
        {'combination': '2-1-3', 'prob': 0.10},
        {'combination': '1-2-4', 'prob': 0.08},
    ]

    # サンプルオッズデータ
    odds_data = {
        '1-2-3': 8.5,
        '1-3-2': 12.3,
        '2-1-3': 15.8,
        '1-2-4': 18.2,
    }

    # 買い目選定
    print("\n【買い目選定】")
    recommendations = strategy.select_bets(
        predictions=predictions,
        odds_data=odds_data,
        buy_score=0.8
    )

    for rec in recommendations:
        print(f"\n組み合わせ: {rec.combination}")
        print(f"  予測確率: {rec.pred_prob:.1%}")
        print(f"  オッズ: {rec.odds:.1f}倍")
        print(f"  期待値: {rec.expected_value:.1%}")
        print(f"  推奨賭け金: ¥{rec.recommended_bet:.0f}")
        print(f"  信頼度: {rec.confidence}")

    # ポートフォリオ最適化
    print("\n【ポートフォリオ最適化】")
    optimized = strategy.optimize_portfolio(recommendations, max_combinations=3)

    total_bet = sum(rec.recommended_bet for rec in optimized)
    print(f"総賭け金: ¥{total_bet:.0f}")

    for rec in optimized:
        print(f"  {rec.combination}: ¥{rec.recommended_bet:.0f}")

    # 結果シミュレーション
    print("\n【結果シミュレーション】")
    actual_result = '1-3-2'  # 実際の結果
    outcome = strategy.simulate_outcome(optimized, actual_result)

    print(f"実際の結果: {actual_result}")
    print(f"総賭け金: ¥{outcome['total_bet']:.0f}")
    print(f"総リターン: ¥{outcome['total_return']:.0f}")
    print(f"利益: ¥{outcome['profit']:+.0f}")
    print(f"ROI: {outcome['roi']:+.1f}%")
    print(f"的中: {'はい' if outcome['hit'] else 'いいえ'}")

    # 期待値計算ユーティリティ
    print("\n【期待値分析】")
    calc = ExpectedValueCalculator()

    pred_prob = 0.15
    odds = 8.5

    breakeven_odds = calc.calculate_breakeven_odds(pred_prob)
    edge = calc.calculate_edge(pred_prob, odds)

    print(f"予測確率: {pred_prob:.1%}")
    print(f"オッズ: {odds:.1f}倍")
    print(f"損益分岐点オッズ: {breakeven_odds:.1f}倍")
    print(f"エッジ: {edge:+.1f}%")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
