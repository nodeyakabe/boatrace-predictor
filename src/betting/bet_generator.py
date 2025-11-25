"""
買い目生成ロジック

Phase 1-3の統合予測機能を活用した買い目生成システム
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import itertools
from datetime import datetime

@dataclass
class BetTicket:
    """買い目情報"""
    bet_type: str  # "3連単", "3連複", "2連単", "2連複"
    combination: List[int]  # 艇番の組み合わせ
    confidence: float  # 信頼度（0-1）
    expected_value: float  # 期待値
    estimated_odds: float  # 推定オッズ
    recommendation_score: float  # 推奨度スコア（0-100）
    recommendation_level: int  # 推奨レベル（1-5）

    def format_combination(self) -> str:
        """買い目の表示形式"""
        if self.bet_type in ["3連単", "2連単"]:
            return "-".join(map(str, self.combination))
        else:
            return "=".join(map(str, self.combination))

class BetGenerator:
    """買い目生成クラス"""

    def __init__(self):
        """初期化"""
        # 舟券種別ごとのパラメータ
        self.bet_params = {
            "3連単": {"max_tickets": 6, "min_confidence": 0.05},
            "3連複": {"max_tickets": 3, "min_confidence": 0.10},
            "2連単": {"max_tickets": 1, "min_confidence": 0.15},
            "2連複": {"max_tickets": 1, "min_confidence": 0.20}
        }

    def generate_bets(self,
                     predictions: Dict[str, float],
                     odds_data: Optional[Dict] = None,
                     max_total_tickets: int = 10) -> List[BetTicket]:
        """
        買い目を生成

        Args:
            predictions: 予測確率 {boat_num: prob}
            odds_data: オッズデータ（オプション）
            max_total_tickets: 最大買い目数

        Returns:
            買い目リスト
        """
        all_bets = []

        # 3連単買い目生成
        trifecta_bets = self.generate_trifecta(predictions, odds_data)
        all_bets.extend(trifecta_bets[:self.bet_params["3連単"]["max_tickets"]])

        # 3連複買い目生成
        trio_bets = self.generate_trio(predictions, odds_data)
        all_bets.extend(trio_bets[:self.bet_params["3連複"]["max_tickets"]])

        # 2連単買い目生成
        exacta_bets = self.generate_exacta(predictions, odds_data)
        all_bets.extend(exacta_bets[:self.bet_params["2連単"]["max_tickets"]])

        # 推奨度スコアで並び替え
        all_bets.sort(key=lambda x: x.recommendation_score, reverse=True)

        # 最大買い目数で制限
        return all_bets[:max_total_tickets]

    def generate_trifecta(self,
                         predictions: Dict[str, float],
                         odds_data: Optional[Dict] = None) -> List[BetTicket]:
        """
        3連単買い目生成

        Args:
            predictions: 予測確率
            odds_data: オッズデータ

        Returns:
            3連単買い目リスト
        """
        bets = []

        # 上位4艇を取得
        sorted_boats = sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:4]
        boat_nums = [int(boat[0]) for boat in sorted_boats]
        boat_probs = {int(boat[0]): boat[1] for boat in sorted_boats}

        # 3連単の全組み合わせを生成
        for perm in itertools.permutations(boat_nums, 3):
            # 各艇の着順確率を計算
            first_prob = boat_probs[perm[0]]
            second_prob = boat_probs[perm[1]] * (1 - first_prob)
            third_prob = boat_probs[perm[2]] * (1 - first_prob - second_prob)

            # 3連単の的中確率
            confidence = first_prob * second_prob * third_prob * 2.0  # 補正係数

            if confidence < self.bet_params["3連単"]["min_confidence"]:
                continue

            # オッズから期待値を計算
            estimated_odds = self._estimate_trifecta_odds(perm, boat_probs, odds_data)
            expected_value = confidence * estimated_odds

            # 推奨度スコアを計算
            recommendation_score = self._calculate_recommendation_score(
                confidence, expected_value, "3連単"
            )

            # 推奨レベル（1-5つ星）
            recommendation_level = self._get_recommendation_level(recommendation_score)

            bet = BetTicket(
                bet_type="3連単",
                combination=list(perm),
                confidence=confidence,
                expected_value=expected_value,
                estimated_odds=estimated_odds,
                recommendation_score=recommendation_score,
                recommendation_level=recommendation_level
            )
            bets.append(bet)

        # 信頼度順にソート
        bets.sort(key=lambda x: x.confidence, reverse=True)
        return bets

    def generate_trio(self,
                     predictions: Dict[str, float],
                     odds_data: Optional[Dict] = None) -> List[BetTicket]:
        """
        3連複買い目生成

        Args:
            predictions: 予測確率
            odds_data: オッズデータ

        Returns:
            3連複買い目リスト
        """
        bets = []

        # 上位4艇を取得
        sorted_boats = sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:4]
        boat_nums = [int(boat[0]) for boat in sorted_boats]
        boat_probs = {int(boat[0]): boat[1] for boat in sorted_boats}

        # 3連複の組み合わせを生成
        for combo in itertools.combinations(boat_nums, 3):
            # 3艇が上位3着に入る確率を計算
            combo_probs = [boat_probs[b] for b in combo]
            confidence = np.prod(combo_probs) * 6.0  # 順列補正

            if confidence < self.bet_params["3連複"]["min_confidence"]:
                continue

            # オッズから期待値を計算
            estimated_odds = self._estimate_trio_odds(combo, boat_probs, odds_data)
            expected_value = confidence * estimated_odds

            # 推奨度スコアを計算
            recommendation_score = self._calculate_recommendation_score(
                confidence, expected_value, "3連複"
            )

            # 推奨レベル
            recommendation_level = self._get_recommendation_level(recommendation_score)

            bet = BetTicket(
                bet_type="3連複",
                combination=sorted(combo),
                confidence=confidence,
                expected_value=expected_value,
                estimated_odds=estimated_odds,
                recommendation_score=recommendation_score,
                recommendation_level=recommendation_level
            )
            bets.append(bet)

        # 信頼度順にソート
        bets.sort(key=lambda x: x.confidence, reverse=True)
        return bets

    def generate_exacta(self,
                       predictions: Dict[str, float],
                       odds_data: Optional[Dict] = None) -> List[BetTicket]:
        """
        2連単買い目生成

        Args:
            predictions: 予測確率
            odds_data: オッズデータ

        Returns:
            2連単買い目リスト
        """
        bets = []

        # 上位3艇を取得
        sorted_boats = sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:3]
        boat_nums = [int(boat[0]) for boat in sorted_boats]
        boat_probs = {int(boat[0]): boat[1] for boat in sorted_boats}

        # 2連単の組み合わせを生成
        for perm in itertools.permutations(boat_nums, 2):
            # 2連単の的中確率
            first_prob = boat_probs[perm[0]]
            second_prob = boat_probs[perm[1]] * (1 - first_prob) * 1.2  # 補正
            confidence = first_prob * second_prob

            if confidence < self.bet_params["2連単"]["min_confidence"]:
                continue

            # オッズから期待値を計算
            estimated_odds = self._estimate_exacta_odds(perm, boat_probs, odds_data)
            expected_value = confidence * estimated_odds

            # 推奨度スコアを計算
            recommendation_score = self._calculate_recommendation_score(
                confidence, expected_value, "2連単"
            )

            # 推奨レベル
            recommendation_level = self._get_recommendation_level(recommendation_score)

            bet = BetTicket(
                bet_type="2連単",
                combination=list(perm),
                confidence=confidence,
                expected_value=expected_value,
                estimated_odds=estimated_odds,
                recommendation_score=recommendation_score,
                recommendation_level=recommendation_level
            )
            bets.append(bet)

        # 信頼度順にソート
        bets.sort(key=lambda x: x.confidence, reverse=True)
        return bets

    def _estimate_trifecta_odds(self,
                               combination: Tuple[int, ...],
                               boat_probs: Dict[int, float],
                               odds_data: Optional[Dict] = None) -> float:
        """3連単オッズを推定"""
        if odds_data and "3連単" in odds_data:
            key = "-".join(map(str, combination))
            if key in odds_data["3連単"]:
                return odds_data["3連単"][key]

        # オッズデータがない場合は確率から推定
        base_odds = 100.0
        for boat in combination:
            base_odds *= (1.0 / max(boat_probs[boat], 0.01))
        return min(base_odds * 0.7, 999.9)  # 控除率を考慮

    def _estimate_trio_odds(self,
                           combination: Tuple[int, ...],
                           boat_probs: Dict[int, float],
                           odds_data: Optional[Dict] = None) -> float:
        """3連複オッズを推定"""
        if odds_data and "3連複" in odds_data:
            key = "=".join(map(str, sorted(combination)))
            if key in odds_data["3連複"]:
                return odds_data["3連複"][key]

        # オッズデータがない場合は確率から推定
        base_odds = 20.0
        for boat in combination:
            base_odds *= (1.0 / max(boat_probs[boat], 0.01))
        return min(base_odds * 0.7, 999.9)

    def _estimate_exacta_odds(self,
                             combination: Tuple[int, ...],
                             boat_probs: Dict[int, float],
                             odds_data: Optional[Dict] = None) -> float:
        """2連単オッズを推定"""
        if odds_data and "2連単" in odds_data:
            key = "-".join(map(str, combination))
            if key in odds_data["2連単"]:
                return odds_data["2連単"][key]

        # オッズデータがない場合は確率から推定
        base_odds = 15.0
        for boat in combination:
            base_odds *= (1.0 / max(boat_probs[boat], 0.01))
        return min(base_odds * 0.7, 99.9)

    def _calculate_recommendation_score(self,
                                       confidence: float,
                                       expected_value: float,
                                       bet_type: str) -> float:
        """
        推奨度スコアを計算

        Args:
            confidence: 信頼度
            expected_value: 期待値
            bet_type: 舟券種別

        Returns:
            推奨度スコア（0-100）
        """
        # 舟券種別ごとの重み
        type_weights = {
            "3連単": {"confidence": 0.4, "value": 0.6},
            "3連複": {"confidence": 0.5, "value": 0.5},
            "2連単": {"confidence": 0.6, "value": 0.4},
            "2連複": {"confidence": 0.7, "value": 0.3}
        }

        weights = type_weights.get(bet_type, {"confidence": 0.5, "value": 0.5})

        # 信頼度スコア（0-100）
        confidence_score = min(confidence * 200, 100)  # 50%で満点

        # 期待値スコア（0-100）
        if expected_value >= 2.0:
            value_score = 100
        elif expected_value >= 1.5:
            value_score = 80 + (expected_value - 1.5) * 40
        elif expected_value >= 1.0:
            value_score = 50 + (expected_value - 1.0) * 60
        else:
            value_score = expected_value * 50

        # 総合スコア
        score = (confidence_score * weights["confidence"] +
                value_score * weights["value"])

        return min(max(score, 0), 100)

    def _get_recommendation_level(self, score: float) -> int:
        """
        推奨レベルを取得（1-5つ星）

        Args:
            score: 推奨度スコア

        Returns:
            推奨レベル
        """
        if score >= 80:
            return 5
        elif score >= 65:
            return 4
        elif score >= 50:
            return 3
        elif score >= 35:
            return 2
        else:
            return 1

    def calculate_bet_confidence(self,
                                bet_type: str,
                                combination: List[int],
                                predictions: Dict[str, float]) -> float:
        """
        買い目の信頼度を計算

        Args:
            bet_type: 舟券種別
            combination: 買い目の組み合わせ
            predictions: 予測確率

        Returns:
            信頼度
        """
        boat_probs = {int(k): v for k, v in predictions.items()}

        if bet_type == "3連単":
            first_prob = boat_probs.get(combination[0], 0.01)
            second_prob = boat_probs.get(combination[1], 0.01) * (1 - first_prob)
            third_prob = boat_probs.get(combination[2], 0.01) * (1 - first_prob - second_prob)
            return first_prob * second_prob * third_prob * 2.0

        elif bet_type == "3連複":
            combo_probs = [boat_probs.get(b, 0.01) for b in combination]
            return np.prod(combo_probs) * 6.0

        elif bet_type == "2連単":
            first_prob = boat_probs.get(combination[0], 0.01)
            second_prob = boat_probs.get(combination[1], 0.01) * (1 - first_prob) * 1.2
            return first_prob * second_prob

        elif bet_type == "2連複":
            combo_probs = [boat_probs.get(b, 0.01) for b in combination]
            return np.prod(combo_probs) * 2.0

        return 0.0

    def calculate_bet_expected_value(self,
                                    confidence: float,
                                    odds: float) -> float:
        """
        買い目の期待値を計算

        Args:
            confidence: 信頼度
            odds: オッズ

        Returns:
            期待値
        """
        return confidence * odds