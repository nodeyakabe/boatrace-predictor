"""
レース展開シナリオ計算エンジン

決まり手確率から考えられる展開シナリオを生成し、
各シナリオでの着順パターンを計算
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging

from .kimarite_constants import Kimarite, KIMARITE_NAMES

logger = logging.getLogger(__name__)


@dataclass
class RaceScenario:
    """レース展開シナリオ"""
    scenario_id: str  # "1_nige", "2_sashi" など
    scenario_name: str  # "1号艇逃げ成功"
    leading_boat: int  # 主導権を握る艇
    kimarite: Kimarite  # 決まり手
    probability: float  # シナリオの発生確率
    finish_patterns: List[Tuple[Tuple[int, int, int], float]]  # [(着順, 確率), ...]


class RaceScenarioEngine:
    """レース展開シナリオ計算エンジン"""

    def __init__(self):
        """初期化"""
        pass

    def calculate_race_scenarios(
        self,
        kimarite_probs: Dict[int, Dict[Kimarite, float]],
        min_probability: float = 0.01
    ) -> List[RaceScenario]:
        """
        決まり手確率から展開シナリオを計算

        Args:
            kimarite_probs: 各艇の決まり手確率
            min_probability: シナリオの最小確率閾値

        Returns:
            シナリオリスト（確率順）
        """
        scenarios = []

        # 各艇が各決まり手で1着になるシナリオを生成
        for pit_number, kimarite_dict in kimarite_probs.items():
            for kimarite, prob in kimarite_dict.items():
                # 確率が低すぎるシナリオは除外
                if prob < min_probability:
                    continue

                # 恵まれは基本1着にならないので除外
                if kimarite == Kimarite.MEGUMARE:
                    continue

                scenario = self._create_scenario(
                    pit_number,
                    kimarite,
                    prob,
                    kimarite_probs
                )
                scenarios.append(scenario)

        # 確率順にソート
        scenarios.sort(key=lambda x: x.probability, reverse=True)

        # 上位シナリオのみ返す（累積確率95%まで）
        filtered_scenarios = []
        cumulative_prob = 0.0
        for scenario in scenarios:
            filtered_scenarios.append(scenario)
            cumulative_prob += scenario.probability
            if cumulative_prob >= 0.95:
                break

        return filtered_scenarios

    def _create_scenario(
        self,
        winner: int,
        kimarite: Kimarite,
        base_prob: float,
        all_kimarite_probs: Dict[int, Dict[Kimarite, float]]
    ) -> RaceScenario:
        """
        個別シナリオの作成

        Args:
            winner: 1着艇
            kimarite: 決まり手
            base_prob: 基本確率
            all_kimarite_probs: 全艇の決まり手確率

        Returns:
            RaceScenario
        """
        scenario_id = f"{winner}_{kimarite.name.lower()}"
        scenario_name = f"{winner}号艇{KIMARITE_NAMES[kimarite]}成功"

        # 2着以降のパターンを計算
        remaining_boats = [pit for pit in all_kimarite_probs.keys() if pit != winner]
        finish_patterns = self._calculate_finish_patterns(
            winner,
            kimarite,
            remaining_boats,
            all_kimarite_probs
        )

        return RaceScenario(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            leading_boat=winner,
            kimarite=kimarite,
            probability=base_prob,
            finish_patterns=finish_patterns
        )

    def _calculate_finish_patterns(
        self,
        winner: int,
        kimarite: Kimarite,
        remaining_boats: List[int],
        all_kimarite_probs: Dict[int, Dict[Kimarite, float]]
    ) -> List[Tuple[Tuple[int, int, int], float]]:
        """
        1着が決まった後の2-3着パターンを計算

        Args:
            winner: 1着艇
            kimarite: 決まり手
            remaining_boats: 残りの艇
            all_kimarite_probs: 全艇の決まり手確率

        Returns:
            [(着順タプル, 確率), ...]（確率順にソート）
        """
        # 決まり手に応じた2着確率を計算
        second_place_probs = self._calculate_second_place_probs(
            winner,
            kimarite,
            remaining_boats
        )

        patterns = []

        # 2着候補の上位3艇で組み合わせを生成
        sorted_seconds = sorted(
            second_place_probs.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        for second, second_prob in sorted_seconds:
            # 3着候補
            third_candidates = [b for b in remaining_boats if b != second]

            # 3着確率を計算
            third_place_probs = self._calculate_third_place_probs(
                winner,
                second,
                kimarite,
                third_candidates
            )

            # 3着候補の上位2艇
            sorted_thirds = sorted(
                third_place_probs.items(),
                key=lambda x: x[1],
                reverse=True
            )[:2]

            for third, third_prob in sorted_thirds:
                # パターンの確率 = 2着確率 × 3着確率
                pattern_prob = second_prob * third_prob
                patterns.append(((winner, second, third), pattern_prob))

        # 確率順にソート
        patterns.sort(key=lambda x: x[1], reverse=True)

        # 確率を正規化
        total_prob = sum(p[1] for p in patterns)
        if total_prob > 0:
            patterns = [(p[0], p[1] / total_prob) for p in patterns]

        return patterns

    def _calculate_second_place_probs(
        self,
        winner: int,
        kimarite: Kimarite,
        candidates: List[int]
    ) -> Dict[int, float]:
        """
        2着確率の計算

        決まり手に応じた典型的な2着パターン
        """
        probs = {}

        # 1逃げ成功の場合
        if winner == 1 and kimarite == Kimarite.NIGE:
            for boat in candidates:
                if boat == 2:
                    probs[boat] = 0.40  # 2コースが2着になりやすい
                elif boat == 3:
                    probs[boat] = 0.25
                elif boat == 4:
                    probs[boat] = 0.20
                elif boat == 5:
                    probs[boat] = 0.10
                else:
                    probs[boat] = 0.05

        # 2差し成功の場合
        elif winner == 2 and kimarite == Kimarite.SASHI:
            for boat in candidates:
                if boat == 1:
                    probs[boat] = 0.45  # 1コースが2着になりやすい
                elif boat == 3:
                    probs[boat] = 0.25
                elif boat == 4:
                    probs[boat] = 0.15
                elif boat == 5:
                    probs[boat] = 0.10
                else:
                    probs[boat] = 0.05

        # まくり成功の場合
        elif kimarite == Kimarite.MAKURI:
            for boat in candidates:
                if boat == 1:
                    probs[boat] = 0.35  # 1コースが2着になりやすい
                elif boat < winner:
                    probs[boat] = 0.30  # 内側の艇
                else:
                    probs[boat] = 0.15  # 外側の艇

        # まくり差し成功の場合
        elif kimarite == Kimarite.MAKURI_SASHI:
            for boat in candidates:
                if boat == 1:
                    probs[boat] = 0.30
                elif boat < winner:
                    probs[boat] = 0.35  # 内側の艇が有利
                else:
                    probs[boat] = 0.15  # 外側の艇

        # その他（差し、抜き等）
        else:
            # コース番号が近い艇が有利
            for boat in candidates:
                if abs(boat - winner) == 1:
                    probs[boat] = 0.30
                elif abs(boat - winner) == 2:
                    probs[boat] = 0.20
                else:
                    probs[boat] = 0.10

        # 正規化
        total = sum(probs.values())
        if total > 0:
            for boat in probs:
                probs[boat] /= total

        return probs

    def _calculate_third_place_probs(
        self,
        first: int,
        second: int,
        kimarite: Kimarite,
        candidates: List[int]
    ) -> Dict[int, float]:
        """
        3着確率の計算

        1着・2着が確定した後の3着確率
        """
        probs = {}

        # 1-2が確定した場合の3着傾向
        if first == 1 and second == 2:
            # 1-2のパターンでは3コースが3着に来やすい
            for boat in candidates:
                if boat == 3:
                    probs[boat] = 0.40
                elif boat == 4:
                    probs[boat] = 0.30
                elif boat == 5:
                    probs[boat] = 0.20
                else:
                    probs[boat] = 0.10

        elif first == 1 and second == 3:
            # 1-3のパターンでは2コースが3着に来やすい
            for boat in candidates:
                if boat == 2:
                    probs[boat] = 0.40
                elif boat == 4:
                    probs[boat] = 0.30
                elif boat == 5:
                    probs[boat] = 0.20
                else:
                    probs[boat] = 0.10

        # センター勢が1-2の場合
        elif first >= 3 and second >= 3:
            # 1コースが3着に来やすい
            for boat in candidates:
                if boat == 1:
                    probs[boat] = 0.40
                elif boat == 2:
                    probs[boat] = 0.30
                else:
                    probs[boat] = 0.15

        # その他のパターン
        else:
            # コース順に確率を割り当て
            for boat in candidates:
                if boat <= 3:
                    probs[boat] = 0.30
                elif boat == 4:
                    probs[boat] = 0.25
                else:
                    probs[boat] = 0.15

        # 正規化
        total = sum(probs.values())
        if total > 0:
            for boat in probs:
                probs[boat] /= total

        return probs

    def get_scenario_summary(self, scenarios: List[RaceScenario], top_n: int = 5) -> str:
        """
        シナリオのサマリーを文字列で取得

        Args:
            scenarios: シナリオリスト
            top_n: 上位何件を表示するか

        Returns:
            サマリー文字列
        """
        lines = [f"=== 上位{top_n}シナリオ ===\n"]

        for i, scenario in enumerate(scenarios[:top_n], 1):
            lines.append(f"{i}. {scenario.scenario_name} (確率: {scenario.probability*100:.1f}%)")

            # 上位3パターンを表示
            for j, (pattern, prob) in enumerate(scenario.finish_patterns[:3], 1):
                pattern_str = f"{pattern[0]}-{pattern[1]}-{pattern[2]}"
                lines.append(f"   {pattern_str}: {prob*100:.1f}%")

        return "\n".join(lines)
