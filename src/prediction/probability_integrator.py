"""
確率統合と買い目選定エンジン

展開シナリオから2連単・3連単の確率を統合し、
最適な買い目を選定する
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

from .race_scenario_engine import RaceScenario

logger = logging.getLogger(__name__)


@dataclass
class BetRecommendation:
    """買い目推奨"""
    combination: Tuple[int, int, int]  # 3連単の組み合わせ
    probability: float  # 的中確率
    scenario: str  # 主なシナリオ
    confidence: str  # 信頼度（Very High, High, Medium, Low）
    rank: int  # 推奨順位


class ProbabilityIntegrator:
    """確率統合と買い目選定エンジン"""

    def __init__(self):
        """初期化"""
        pass

    def calculate_exacta_probabilities(
        self,
        scenarios: List[RaceScenario]
    ) -> Dict[Tuple[int, int], float]:
        """
        2連単確率の計算

        全シナリオの確率を統合して2連単の確率を算出

        Args:
            scenarios: シナリオリスト

        Returns:
            {(1着, 2着): 確率}
        """
        exacta_probs = {}

        for scenario in scenarios:
            for pattern, pattern_prob in scenario.finish_patterns:
                first, second, third = pattern
                key = (first, second)

                # パターンの出現確率 = シナリオ確率 × パターン内での確率
                total_prob = scenario.probability * pattern_prob

                if key not in exacta_probs:
                    exacta_probs[key] = 0.0
                exacta_probs[key] += total_prob

        return exacta_probs

    def calculate_trifecta_probabilities(
        self,
        scenarios: List[RaceScenario]
    ) -> Dict[Tuple[int, int, int], float]:
        """
        3連単確率の計算

        全シナリオの確率を統合して3連単の確率を算出

        Args:
            scenarios: シナリオリスト

        Returns:
            {(1着, 2着, 3着): 確率}
        """
        trifecta_probs = {}
        scenario_map = {}  # 各買い目の主シナリオを記録

        for scenario in scenarios:
            for pattern, pattern_prob in scenario.finish_patterns:
                # パターンの出現確率 = シナリオ確率 × パターン内での確率
                total_prob = scenario.probability * pattern_prob

                if pattern not in trifecta_probs:
                    trifecta_probs[pattern] = 0.0
                    scenario_map[pattern] = scenario.scenario_name

                trifecta_probs[pattern] += total_prob

        return trifecta_probs, scenario_map

    def select_optimal_bets(
        self,
        scenarios: List[RaceScenario],
        min_bets: int = 3,
        max_bets: int = 6,
        strategy: str = 'probability'
    ) -> List[BetRecommendation]:
        """
        最適な買い目を選定

        Args:
            scenarios: シナリオリスト
            min_bets: 最小買い目数
            max_bets: 最大買い目数
            strategy: 'probability'（確率重視）or 'coverage'（カバレッジ重視）

        Returns:
            買い目推奨リスト（確率順）
        """
        # 3連単確率を計算
        trifecta_probs, scenario_map = self.calculate_trifecta_probabilities(scenarios)

        # 買い目候補を作成
        bet_candidates = []

        for combination, prob in trifecta_probs.items():
            bet_info = BetRecommendation(
                combination=combination,
                probability=prob,
                scenario=scenario_map.get(combination, ''),
                confidence=self._calculate_confidence(prob),
                rank=0  # 後で設定
            )
            bet_candidates.append(bet_info)

        # 確率順にソート
        bet_candidates.sort(key=lambda x: x.probability, reverse=True)

        # 買い目数を決定
        selected_bets = self._determine_bet_count(
            bet_candidates,
            min_bets,
            max_bets,
            strategy
        )

        # 順位を設定
        for i, bet in enumerate(selected_bets, 1):
            bet.rank = i

        return selected_bets

    def _calculate_confidence(self, probability: float) -> str:
        """確率から信頼度を判定"""
        if probability >= 0.20:
            return 'Very High'
        elif probability >= 0.10:
            return 'High'
        elif probability >= 0.05:
            return 'Medium'
        elif probability >= 0.02:
            return 'Low'
        else:
            return 'Very Low'

    def _determine_bet_count(
        self,
        candidates: List[BetRecommendation],
        min_bets: int,
        max_bets: int,
        strategy: str
    ) -> List[BetRecommendation]:
        """
        累積確率を考慮して買い目数を決定

        Args:
            candidates: 買い目候補
            min_bets: 最小買い目数
            max_bets: 最大買い目数
            strategy: 戦略

        Returns:
            選定された買い目リスト
        """
        selected = []
        cumulative_prob = 0.0

        for i, bet in enumerate(candidates):
            if i < min_bets:
                # 最小買い目数まで無条件に選択
                selected.append(bet)
                cumulative_prob += bet.probability
            elif i < max_bets:
                if strategy == 'probability':
                    # 確率が一定値以上なら追加
                    if bet.probability >= 0.02:
                        selected.append(bet)
                        cumulative_prob += bet.probability
                    else:
                        break
                elif strategy == 'coverage':
                    # 累積確率が70%未満なら追加
                    if cumulative_prob < 0.70:
                        selected.append(bet)
                        cumulative_prob += bet.probability
                    else:
                        break
            else:
                break

        return selected

    def get_bet_statistics(self, bets: List[BetRecommendation]) -> Dict:
        """
        買い目の統計情報を取得

        Args:
            bets: 買い目リスト

        Returns:
            統計情報の辞書
        """
        total_probability = sum(b.probability for b in bets)
        avg_probability = total_probability / len(bets) if bets else 0.0

        # 1着艇の分布
        first_boats = {}
        for bet in bets:
            first = bet.combination[0]
            if first not in first_boats:
                first_boats[first] = 0
            first_boats[first] += 1

        # 最頻出の1着艇
        main_favorite = max(first_boats.items(), key=lambda x: x[1])[0] if first_boats else None

        return {
            'total_bets': len(bets),
            'total_probability': total_probability,
            'avg_probability': avg_probability,
            'main_favorite': main_favorite,
            'first_boat_distribution': first_boats,
            'confidence_distribution': {
                'Very High': sum(1 for b in bets if b.confidence == 'Very High'),
                'High': sum(1 for b in bets if b.confidence == 'High'),
                'Medium': sum(1 for b in bets if b.confidence == 'Medium'),
                'Low': sum(1 for b in bets if b.confidence == 'Low'),
            }
        }

    def format_bets_for_display(self, bets: List[BetRecommendation]) -> List[Dict]:
        """
        買い目をUI表示用にフォーマット

        Args:
            bets: 買い目リスト

        Returns:
            表示用の辞書リスト
        """
        formatted = []

        for bet in bets:
            formatted.append({
                '順位': bet.rank,
                '買い目': f"{bet.combination[0]}-{bet.combination[1]}-{bet.combination[2]}",
                '確率': f"{bet.probability * 100:.1f}%",
                '信頼度': bet.confidence,
                'シナリオ': bet.scenario,
                '1着': f"{bet.combination[0]}号艇",
                '2着': f"{bet.combination[1]}号艇",
                '3着': f"{bet.combination[2]}号艇",
            })

        return formatted
