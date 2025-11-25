"""
リスク調整モジュール
Phase 3.3: 買い目間の相関を考慮したリスク管理
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from itertools import combinations


@dataclass
class AdjustedBet:
    """リスク調整後の賭け情報"""
    combination: str
    original_prob: float
    adjusted_prob: float
    odds: float
    expected_value: float
    risk_score: float
    correlation_penalty: float
    recommended_bet: float
    confidence_score: float


class RiskAdjuster:
    """
    リスク調整器

    買い目間の相関を考慮し、過度なリスク集中を回避
    """

    def __init__(
        self,
        max_total_exposure: float = 0.3,  # 最大総賭け金比率
        max_single_exposure: float = 0.1,  # 単一買い目の最大比率
        correlation_penalty_factor: float = 0.5,  # 相関ペナルティ係数
        min_diversification: int = 3  # 最小分散買い目数
    ):
        self.max_total_exposure = max_total_exposure
        self.max_single_exposure = max_single_exposure
        self.correlation_penalty_factor = correlation_penalty_factor
        self.min_diversification = min_diversification

    def calculate_bet_correlation(
        self,
        combo1: str,
        combo2: str
    ) -> float:
        """
        2つの買い目の相関を計算

        相関が高い = 同じ艇を含む買い目
        """
        boats1 = set(combo1.split('-'))
        boats2 = set(combo2.split('-'))

        # Jaccard係数
        intersection = len(boats1 & boats2)
        union = len(boats1 | boats2)

        return intersection / union if union > 0 else 0.0

    def calculate_position_correlation(
        self,
        combo1: str,
        combo2: str
    ) -> float:
        """
        位置を考慮した相関計算

        1着が同じ = 高い相関
        2着が同じ = 中程度の相関
        3着が同じ = 低い相関
        """
        positions1 = combo1.split('-')
        positions2 = combo2.split('-')

        correlation = 0.0

        # 1着が同じ
        if positions1[0] == positions2[0]:
            correlation += 0.6

        # 2着が同じ
        if positions1[1] == positions2[1]:
            correlation += 0.3

        # 3着が同じ
        if positions1[2] == positions2[2]:
            correlation += 0.1

        return min(1.0, correlation)

    def build_correlation_matrix(
        self,
        combinations_list: List[str]
    ) -> np.ndarray:
        """相関行列を構築"""
        n = len(combinations_list)
        corr_matrix = np.eye(n)

        for i in range(n):
            for j in range(i + 1, n):
                corr = self.calculate_position_correlation(
                    combinations_list[i],
                    combinations_list[j]
                )
                corr_matrix[i, j] = corr
                corr_matrix[j, i] = corr

        return corr_matrix

    def calculate_portfolio_risk(
        self,
        bets: List[Dict],
        correlation_matrix: np.ndarray
    ) -> float:
        """
        ポートフォリオ全体のリスクを計算

        相関を考慮したVaR的なリスク指標
        """
        if len(bets) == 0:
            return 0.0

        # 各賭けの重み（賭け金比率）
        total_bet = sum(b['bet_amount'] for b in bets)
        if total_bet == 0:
            return 0.0

        weights = np.array([b['bet_amount'] / total_bet for b in bets])

        # 各賭けのリスク（1 - 予測確率）
        risks = np.array([1.0 - b['prob'] for b in bets])

        # ポートフォリオ分散
        portfolio_risk = 0.0

        for i in range(len(bets)):
            for j in range(len(bets)):
                portfolio_risk += (
                    weights[i] * weights[j] *
                    risks[i] * risks[j] *
                    correlation_matrix[i, j]
                )

        return np.sqrt(portfolio_risk)

    def calculate_concentration_risk(
        self,
        bets: List[Dict]
    ) -> float:
        """集中リスクを計算（HHI - Herfindahl-Hirschman Index）"""
        if len(bets) == 0:
            return 0.0

        total_bet = sum(b['bet_amount'] for b in bets)
        if total_bet == 0:
            return 0.0

        # 各賭けのシェア
        shares = [b['bet_amount'] / total_bet for b in bets]

        # HHI計算（0〜1、高いほど集中）
        hhi = sum(s ** 2 for s in shares)

        return hhi

    def calculate_boat_exposure(
        self,
        bets: List[Dict]
    ) -> Dict[str, float]:
        """各艇へのエクスポージャーを計算"""
        exposure = {}
        total_bet = sum(b['bet_amount'] for b in bets)

        if total_bet == 0:
            return exposure

        for bet in bets:
            boats = bet['combination'].split('-')

            # 1着は重み大、3着は重み小
            weights = [0.6, 0.3, 0.1]

            for boat, weight in zip(boats, weights):
                if boat not in exposure:
                    exposure[boat] = 0.0

                exposure[boat] += (bet['bet_amount'] / total_bet) * weight

        return exposure

    def adjust_bets_for_correlation(
        self,
        bets: List[Dict],
        bankroll: float
    ) -> List[AdjustedBet]:
        """
        相関を考慮して賭け金を調整

        Args:
            bets: 元の賭け情報
                [{'combination': '1-2-3', 'prob': 0.15, 'odds': 10.5, 'bet_amount': 1000}, ...]
            bankroll: 現在の資金

        Returns:
            調整後の賭け情報
        """
        if len(bets) == 0:
            return []

        combinations_list = [b['combination'] for b in bets]
        corr_matrix = self.build_correlation_matrix(combinations_list)

        adjusted_bets = []

        for i, bet in enumerate(bets):
            # 他の買い目との平均相関
            correlations = [corr_matrix[i, j] for j in range(len(bets)) if i != j]
            avg_correlation = np.mean(correlations) if correlations else 0.0

            # 相関ペナルティ
            correlation_penalty = avg_correlation * self.correlation_penalty_factor

            # 調整後の確率（相関が高いほどペナルティ）
            adjusted_prob = bet['prob'] * (1.0 - correlation_penalty * 0.2)

            # 期待値再計算
            ev = adjusted_prob * bet['odds'] - 1.0

            # リスクスコア計算
            risk_score = self._calculate_individual_risk_score(
                bet, i, bets, corr_matrix
            )

            # 賭け金調整
            max_bet = bankroll * self.max_single_exposure
            adjusted_bet_amount = min(bet['bet_amount'] * (1.0 - risk_score * 0.3), max_bet)

            # 信頼度スコア
            confidence_score = self._calculate_confidence_score(
                bet['prob'], ev, risk_score
            )

            adjusted_bets.append(AdjustedBet(
                combination=bet['combination'],
                original_prob=bet['prob'],
                adjusted_prob=adjusted_prob,
                odds=bet['odds'],
                expected_value=ev,
                risk_score=risk_score,
                correlation_penalty=correlation_penalty,
                recommended_bet=max(0, adjusted_bet_amount),
                confidence_score=confidence_score
            ))

        # 総エクスポージャー制限
        adjusted_bets = self._apply_total_exposure_limit(adjusted_bets, bankroll)

        return adjusted_bets

    def _calculate_individual_risk_score(
        self,
        bet: Dict,
        index: int,
        all_bets: List[Dict],
        corr_matrix: np.ndarray
    ) -> float:
        """個別賭けのリスクスコアを計算"""
        # 基本リスク（低確率ほど高リスク）
        base_risk = 1.0 - bet['prob']

        # 相関リスク
        corr_risk = 0.0
        for j in range(len(all_bets)):
            if j != index:
                corr_risk += corr_matrix[index, j] * all_bets[j]['bet_amount']

        total_bet = sum(b['bet_amount'] for b in all_bets)
        corr_risk = corr_risk / total_bet if total_bet > 0 else 0.0

        # オッズリスク（高オッズほど高リスク）
        odds_risk = min(1.0, bet['odds'] / 100.0)

        # 総合リスクスコア
        risk_score = base_risk * 0.4 + corr_risk * 0.4 + odds_risk * 0.2

        return min(1.0, risk_score)

    def _calculate_confidence_score(
        self,
        prob: float,
        ev: float,
        risk_score: float
    ) -> float:
        """信頼度スコアを計算"""
        # 確率要素（高いほど信頼）
        prob_factor = prob * 2.0  # 0〜1を0〜2にスケール

        # 期待値要素（高いほど信頼）
        ev_factor = max(0, min(1.0, ev))

        # リスク要素（低いほど信頼）
        risk_factor = 1.0 - risk_score

        confidence = prob_factor * 0.3 + ev_factor * 0.4 + risk_factor * 0.3

        return min(1.0, confidence)

    def _apply_total_exposure_limit(
        self,
        bets: List[AdjustedBet],
        bankroll: float
    ) -> List[AdjustedBet]:
        """総エクスポージャー制限を適用"""
        total_bet = sum(b.recommended_bet for b in bets)
        max_exposure = bankroll * self.max_total_exposure

        if total_bet > max_exposure:
            # 比例配分で調整
            adjustment_factor = max_exposure / total_bet

            adjusted = []
            for bet in bets:
                adjusted.append(AdjustedBet(
                    combination=bet.combination,
                    original_prob=bet.original_prob,
                    adjusted_prob=bet.adjusted_prob,
                    odds=bet.odds,
                    expected_value=bet.expected_value,
                    risk_score=bet.risk_score,
                    correlation_penalty=bet.correlation_penalty,
                    recommended_bet=bet.recommended_bet * adjustment_factor,
                    confidence_score=bet.confidence_score
                ))
            return adjusted

        return bets

    def calculate_value_at_risk(
        self,
        bets: List[AdjustedBet],
        confidence_level: float = 0.95
    ) -> float:
        """
        VaR（Value at Risk）を計算

        指定した信頼水準での最大損失額
        """
        if len(bets) == 0:
            return 0.0

        total_bet = sum(b.recommended_bet for b in bets)

        # 最悪ケース：全外れ
        worst_case_loss = total_bet

        # 期待損失の計算（モンテカルロ的アプローチの簡易版）
        # 全外れ確率
        all_miss_prob = 1.0
        for bet in bets:
            all_miss_prob *= (1.0 - bet.adjusted_prob)

        # 95%信頼区間での損失
        if all_miss_prob >= (1.0 - confidence_level):
            var = worst_case_loss
        else:
            # 期待損失
            expected_loss = total_bet - sum(
                b.recommended_bet * b.adjusted_prob * b.odds
                for b in bets
            )
            var = max(0, expected_loss)

        return var

    def get_risk_report(
        self,
        bets: List[AdjustedBet],
        bankroll: float
    ) -> Dict:
        """リスクレポートを生成"""
        if len(bets) == 0:
            return {
                'total_exposure': 0.0,
                'exposure_ratio': 0.0,
                'concentration_risk': 0.0,
                'avg_risk_score': 0.0,
                'var_95': 0.0,
                'max_loss': 0.0,
                'expected_return': 0.0,
                'risk_adjusted_return': 0.0,
                'boat_exposures': {},
                'recommendations': []
            }

        total_bet = sum(b.recommended_bet for b in bets)

        # 各艇へのエクスポージャー
        bet_dicts = [
            {'combination': b.combination, 'bet_amount': b.recommended_bet}
            for b in bets
        ]
        boat_exposures = self.calculate_boat_exposure(bet_dicts)

        # 集中リスク
        concentration = self.calculate_concentration_risk(bet_dicts)

        # 平均リスクスコア
        avg_risk = np.mean([b.risk_score for b in bets])

        # VaR
        var_95 = self.calculate_value_at_risk(bets, 0.95)

        # 期待リターン
        expected_return = sum(
            b.recommended_bet * b.adjusted_prob * b.odds
            for b in bets
        ) - total_bet

        # リスク調整後リターン
        risk_adjusted_return = expected_return / (var_95 + 1.0)

        # 推奨事項
        recommendations = self._generate_risk_recommendations(
            total_bet, bankroll, concentration, avg_risk, boat_exposures
        )

        return {
            'total_exposure': total_bet,
            'exposure_ratio': total_bet / bankroll if bankroll > 0 else 0.0,
            'concentration_risk': concentration,
            'avg_risk_score': avg_risk,
            'var_95': var_95,
            'max_loss': total_bet,
            'expected_return': expected_return,
            'risk_adjusted_return': risk_adjusted_return,
            'boat_exposures': boat_exposures,
            'recommendations': recommendations
        }

    def _generate_risk_recommendations(
        self,
        total_bet: float,
        bankroll: float,
        concentration: float,
        avg_risk: float,
        boat_exposures: Dict[str, float]
    ) -> List[str]:
        """リスク推奨事項を生成"""
        recommendations = []

        exposure_ratio = total_bet / bankroll if bankroll > 0 else 0.0

        if exposure_ratio > 0.25:
            recommendations.append("警告: 総エクスポージャーが25%を超えています。資金管理を見直してください。")

        if concentration > 0.5:
            recommendations.append("警告: 買い目が集中しています。分散を検討してください。")

        if avg_risk > 0.7:
            recommendations.append("注意: 平均リスクが高めです。低リスク買い目を優先してください。")

        # 特定艇への過度なエクスポージャー
        for boat, exposure in boat_exposures.items():
            if exposure > 0.8:
                recommendations.append(f"警告: {boat}号艇への依存度が高すぎます（{exposure:.1%}）。")

        if len(recommendations) == 0:
            recommendations.append("リスク水準は適切です。")

        return recommendations


class DrawdownManager:
    """ドローダウン管理"""

    def __init__(
        self,
        max_drawdown_threshold: float = 0.2,  # 最大ドローダウン閾値（20%）
        recovery_mode_threshold: float = 0.1,  # リカバリーモード閾値（10%）
        aggressive_mode_threshold: float = 0.05  # アグレッシブモード閾値（5%）
    ):
        self.max_drawdown_threshold = max_drawdown_threshold
        self.recovery_mode_threshold = recovery_mode_threshold
        self.aggressive_mode_threshold = aggressive_mode_threshold
        self.peak_bankroll = 0.0
        self.current_drawdown = 0.0

    def update(self, current_bankroll: float):
        """資金状態を更新"""
        if current_bankroll > self.peak_bankroll:
            self.peak_bankroll = current_bankroll

        if self.peak_bankroll > 0:
            self.current_drawdown = (self.peak_bankroll - current_bankroll) / self.peak_bankroll
        else:
            self.current_drawdown = 0.0

    def get_bet_multiplier(self) -> float:
        """現在のドローダウンに基づく賭け金倍率"""
        if self.current_drawdown >= self.max_drawdown_threshold:
            # 最大ドローダウン到達：賭け停止
            return 0.0
        elif self.current_drawdown >= self.recovery_mode_threshold:
            # リカバリーモード：控えめに賭ける
            return 0.5
        elif self.current_drawdown <= self.aggressive_mode_threshold:
            # アグレッシブモード：通常より積極的に
            return 1.2
        else:
            # 通常モード
            return 1.0

    def get_mode(self) -> str:
        """現在のモードを取得"""
        if self.current_drawdown >= self.max_drawdown_threshold:
            return "STOP"
        elif self.current_drawdown >= self.recovery_mode_threshold:
            return "RECOVERY"
        elif self.current_drawdown <= self.aggressive_mode_threshold:
            return "AGGRESSIVE"
        else:
            return "NORMAL"

    def should_stop_betting(self) -> bool:
        """賭けを停止すべきか"""
        return self.current_drawdown >= self.max_drawdown_threshold

    def get_status(self) -> Dict:
        """現在の状態を取得"""
        return {
            'peak_bankroll': self.peak_bankroll,
            'current_drawdown': self.current_drawdown,
            'mode': self.get_mode(),
            'bet_multiplier': self.get_bet_multiplier(),
            'should_stop': self.should_stop_betting()
        }


if __name__ == "__main__":
    print("=" * 60)
    print("リスク調整モジュール テスト")
    print("=" * 60)

    # リスク調整器の初期化
    adjuster = RiskAdjuster(
        max_total_exposure=0.3,
        max_single_exposure=0.1,
        correlation_penalty_factor=0.5
    )

    # サンプル賭け情報
    bets = [
        {'combination': '1-2-3', 'prob': 0.15, 'odds': 8.5, 'bet_amount': 1000},
        {'combination': '1-2-4', 'prob': 0.12, 'odds': 12.3, 'bet_amount': 800},
        {'combination': '1-3-2', 'prob': 0.10, 'odds': 15.8, 'bet_amount': 600},
        {'combination': '2-1-3', 'prob': 0.08, 'odds': 18.2, 'bet_amount': 500},
    ]

    bankroll = 10000

    print("\n【相関行列】")
    combinations_list = [b['combination'] for b in bets]
    corr_matrix = adjuster.build_correlation_matrix(combinations_list)

    for i, c1 in enumerate(combinations_list):
        for j, c2 in enumerate(combinations_list):
            if i < j:
                print(f"  {c1} vs {c2}: {corr_matrix[i, j]:.2f}")

    print("\n【リスク調整後の賭け】")
    adjusted = adjuster.adjust_bets_for_correlation(bets, bankroll)

    for bet in adjusted:
        print(f"\n{bet.combination}:")
        print(f"  元確率: {bet.original_prob:.1%} → 調整後: {bet.adjusted_prob:.1%}")
        print(f"  期待値: {bet.expected_value:.1%}")
        print(f"  リスクスコア: {bet.risk_score:.2f}")
        print(f"  相関ペナルティ: {bet.correlation_penalty:.2f}")
        print(f"  推奨賭け金: ¥{bet.recommended_bet:.0f}")
        print(f"  信頼度: {bet.confidence_score:.2f}")

    print("\n【リスクレポート】")
    report = adjuster.get_risk_report(adjusted, bankroll)

    print(f"総エクスポージャー: ¥{report['total_exposure']:.0f} ({report['exposure_ratio']:.1%})")
    print(f"集中リスク: {report['concentration_risk']:.2f}")
    print(f"平均リスクスコア: {report['avg_risk_score']:.2f}")
    print(f"VaR (95%): ¥{report['var_95']:.0f}")
    print(f"期待リターン: ¥{report['expected_return']:+.0f}")
    print(f"リスク調整後リターン: {report['risk_adjusted_return']:.3f}")

    print("\n【艇別エクスポージャー】")
    for boat, exp in sorted(report['boat_exposures'].items()):
        print(f"  {boat}号艇: {exp:.1%}")

    print("\n【推奨事項】")
    for rec in report['recommendations']:
        print(f"  - {rec}")

    print("\n【ドローダウン管理】")
    dd_manager = DrawdownManager()
    dd_manager.update(10000)  # 初期資金
    print(f"初期状態: {dd_manager.get_status()}")

    dd_manager.update(9500)  # 5%の損失
    print(f"5%損失後: {dd_manager.get_status()}")

    dd_manager.update(8500)  # 15%の損失
    print(f"15%損失後: {dd_manager.get_status()}")

    dd_manager.update(7500)  # 25%の損失
    print(f"25%損失後: {dd_manager.get_status()}")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
