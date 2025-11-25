"""
レーススコアリングシステム

Phase 1-3の統合予測機能を活用したレース評価・ランキング
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class RaceScore:
    """レーススコア情報"""
    race_id: str
    venue: str
    race_no: int
    race_time: str

    # スコア情報
    accuracy_score: float  # 的中率スコア（0-100）
    value_score: float  # 期待値スコア（0-100）
    stability_score: float  # 安定性スコア（0-100）

    # 予測情報
    favorite_boat: int  # 本命艇番
    favorite_prob: float  # 本命勝率
    confidence_level: float  # 全体的な信頼度

    # オッズ情報
    odds_discrepancy: float  # オッズ乖離度
    expected_return: float  # 期待リターン率

    # メタデータ
    feature_importance: Dict[str, float]  # 重要特徴量
    prediction_reasons: List[str]  # 予測理由（XAI）

    def get_overall_score(self, mode: str = "balanced") -> float:
        """総合スコアを取得"""
        if mode == "accuracy":
            return self.accuracy_score * 0.7 + self.stability_score * 0.3
        elif mode == "value":
            return self.value_score * 0.6 + self.accuracy_score * 0.4
        else:  # balanced
            return (self.accuracy_score + self.value_score + self.stability_score) / 3

class RaceScorer:
    """レーススコアリングクラス"""

    def __init__(self):
        """初期化"""
        self.scoring_weights = {
            "accuracy": {
                "favorite_prob": 0.5,
                "confidence": 0.3,
                "stability": 0.2
            },
            "value": {
                "expected_return": 0.4,
                "odds_discrepancy": 0.3,
                "favorite_prob": 0.3
            }
        }

    def score_race(self,
                  race_id: str,
                  predictions: Dict[str, float],
                  feature_importance: Dict[str, float],
                  odds_data: Optional[Dict] = None,
                  historical_accuracy: Optional[float] = None,
                  xai_explanations: Optional[List[str]] = None) -> RaceScore:
        """
        レースをスコアリング

        Args:
            race_id: レースID（例: "2024-01-15_浜名湖_1R"）
            predictions: 予測確率 {boat_num: prob}
            feature_importance: 特徴量重要度
            odds_data: オッズデータ
            historical_accuracy: 過去の的中率
            xai_explanations: XAI説明

        Returns:
            レーススコア
        """
        # レース情報を解析
        parts = race_id.split("_")
        venue = parts[1] if len(parts) > 1 else "不明"
        race_no = int(parts[2].replace("R", "")) if len(parts) > 2 else 0
        race_time = ""  # 後で設定

        # 本命艇を特定
        sorted_boats = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
        favorite_boat = int(sorted_boats[0][0])
        favorite_prob = sorted_boats[0][1]

        # 的中率スコアを計算
        accuracy_score = self.calculate_accuracy_score(
            predictions, historical_accuracy
        )

        # 期待値スコアを計算
        value_score, odds_discrepancy, expected_return = self.calculate_value_score(
            predictions, odds_data
        )

        # 安定性スコアを計算
        stability_score = self.calculate_stability_score(
            predictions, feature_importance
        )

        # 全体的な信頼度
        confidence_level = self._calculate_confidence_level(
            predictions, feature_importance
        )

        # 予測理由を生成
        prediction_reasons = xai_explanations or self._generate_prediction_reasons(
            predictions, feature_importance
        )

        return RaceScore(
            race_id=race_id,
            venue=venue,
            race_no=race_no,
            race_time=race_time,
            accuracy_score=accuracy_score,
            value_score=value_score,
            stability_score=stability_score,
            favorite_boat=favorite_boat,
            favorite_prob=favorite_prob,
            confidence_level=confidence_level,
            odds_discrepancy=odds_discrepancy,
            expected_return=expected_return,
            feature_importance=feature_importance,
            prediction_reasons=prediction_reasons
        )

    def calculate_accuracy_score(self,
                                predictions: Dict[str, float],
                                historical_accuracy: Optional[float] = None) -> float:
        """
        的中率スコアを計算

        Args:
            predictions: 予測確率
            historical_accuracy: 過去の的中率

        Returns:
            的中率スコア（0-100）
        """
        # 予測確率の分散を計算（集中度の指標）
        probs = list(predictions.values())
        prob_variance = np.var(probs)
        # 6艇均等の場合の最大分散: (1/6 - 1/6)^2 = 0
        # 1艇が100%の場合の分散: (5 * (0-1/6)^2 + 1 * (1-1/6)^2) / 6 ≈ 0.139
        max_variance = 0.139
        concentration_score = min((prob_variance / max_variance) * 100, 100)

        # 本命の強さ（確率をそのまま%に変換）
        max_prob = max(probs)
        favorite_strength = max_prob * 100  # 100%で満点

        # 上位3艇の合計確率
        sorted_probs = sorted(probs, reverse=True)
        top3_prob = sum(sorted_probs[:3])
        top3_score = min(top3_prob * 100, 100)  # 100%で満点

        # 過去の的中率を反映
        if historical_accuracy is not None:
            history_score = historical_accuracy * 100
            weights = [0.3, 0.3, 0.2, 0.2]
            scores = [concentration_score, favorite_strength, top3_score, history_score]
        else:
            weights = [0.35, 0.35, 0.3]
            scores = [concentration_score, favorite_strength, top3_score]

        return sum(w * s for w, s in zip(weights, scores))

    def calculate_value_score(self,
                             predictions: Dict[str, float],
                             odds_data: Optional[Dict] = None) -> Tuple[float, float, float]:
        """
        期待値スコアを計算

        Args:
            predictions: 予測確率
            odds_data: オッズデータ

        Returns:
            (期待値スコア, オッズ乖離度, 期待リターン率)
        """
        if not odds_data:
            # オッズデータがない場合はデフォルト値
            return 50.0, 0.0, 1.0

        # 単勝オッズから期待値を計算
        win_odds = odds_data.get("単勝", {})
        if not win_odds:
            return 50.0, 0.0, 1.0

        total_discrepancy = 0.0
        total_expected_return = 0.0
        count = 0

        for boat_str, prob in predictions.items():
            if boat_str in win_odds:
                odds = win_odds[boat_str]

                # オッズから市場の予測確率を逆算
                market_prob = 0.75 / odds  # 控除率25%と仮定

                # 乖離度を計算（予測確率 / 市場確率）
                if market_prob > 0:
                    discrepancy = prob / market_prob
                    total_discrepancy += discrepancy

                    # 期待リターン
                    expected_return = prob * odds
                    total_expected_return += expected_return
                    count += 1

        if count == 0:
            return 50.0, 0.0, 1.0

        avg_discrepancy = total_discrepancy / count
        avg_expected_return = total_expected_return / count

        # 期待値スコアを計算
        if avg_expected_return >= 1.5:
            value_score = 100
        elif avg_expected_return >= 1.2:
            value_score = 70 + (avg_expected_return - 1.2) * 100
        elif avg_expected_return >= 1.0:
            value_score = 50 + (avg_expected_return - 1.0) * 100
        elif avg_expected_return >= 0.8:
            value_score = 30 + (avg_expected_return - 0.8) * 100
        else:
            value_score = avg_expected_return * 37.5

        return value_score, avg_discrepancy, avg_expected_return

    def calculate_stability_score(self,
                                 predictions: Dict[str, float],
                                 feature_importance: Dict[str, float]) -> float:
        """
        安定性スコアを計算

        Args:
            predictions: 予測確率
            feature_importance: 特徴量重要度

        Returns:
            安定性スコア（0-100）
        """
        # 予測の確信度（エントロピーの逆数）
        probs = list(predictions.values())
        entropy = -sum(p * np.log(p + 1e-10) for p in probs if p > 0)
        max_entropy = -np.log(1/6) * 6  # 6艇の場合の最大エントロピー
        certainty_score = (1 - entropy / max_entropy) * 100

        # 重要特徴量の安定性
        stable_features = [
            "勝率", "連対率", "3連対率", "平均ST", "コース別1着率",
            "モーター2連率", "モーター勝率"
        ]

        stable_importance = sum(
            feature_importance.get(f, 0) for f in stable_features
        )
        total_importance = sum(feature_importance.values())

        if total_importance > 0:
            stability_ratio = stable_importance / total_importance
            feature_stability_score = stability_ratio * 100
        else:
            feature_stability_score = 50

        # 上位艇の差
        sorted_probs = sorted(probs, reverse=True)
        if len(sorted_probs) >= 2:
            gap_score = min((sorted_probs[0] - sorted_probs[1]) * 200, 100)
        else:
            gap_score = 100

        # 総合安定性スコア
        weights = [0.4, 0.3, 0.3]
        scores = [certainty_score, feature_stability_score, gap_score]

        return sum(w * s for w, s in zip(weights, scores))

    def rank_races(self,
                  race_scores: List[RaceScore],
                  mode: str = "accuracy") -> List[RaceScore]:
        """
        レースをランキング

        Args:
            race_scores: レーススコアのリスト
            mode: "accuracy"（的中率重視）または "value"（期待値重視）

        Returns:
            ソート済みレーススコアリスト
        """
        if mode == "accuracy":
            # 的中率重視: accuracy_score * 0.7 + stability_score * 0.3
            return sorted(
                race_scores,
                key=lambda x: x.accuracy_score * 0.7 + x.stability_score * 0.3,
                reverse=True
            )
        elif mode == "value":
            # 期待値重視: value_score * 0.6 + accuracy_score * 0.4
            return sorted(
                race_scores,
                key=lambda x: x.value_score * 0.6 + x.accuracy_score * 0.4,
                reverse=True
            )
        else:
            # バランス重視
            return sorted(
                race_scores,
                key=lambda x: x.get_overall_score("balanced"),
                reverse=True
            )

    def _calculate_confidence_level(self,
                                   predictions: Dict[str, float],
                                   feature_importance: Dict[str, float]) -> float:
        """全体的な信頼度を計算"""
        # 予測確率の最大値
        max_prob = max(predictions.values())

        # 重要特徴量の合計
        total_importance = sum(feature_importance.values())

        # 予測の分散
        prob_std = np.std(list(predictions.values()))

        # 信頼度を計算
        confidence = (max_prob * 0.5 +
                     min(total_importance, 1.0) * 0.3 +
                     prob_std * 0.2)

        return min(confidence, 1.0)

    def _generate_prediction_reasons(self,
                                    predictions: Dict[str, float],
                                    feature_importance: Dict[str, float]) -> List[str]:
        """予測理由を生成"""
        reasons = []

        # 本命艇の情報
        sorted_boats = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
        favorite_boat = sorted_boats[0][0]
        favorite_prob = sorted_boats[0][1]

        reasons.append(f"{favorite_boat}号艇が本命（勝率{favorite_prob:.1%}）")

        # 重要特徴量TOP3
        sorted_features = sorted(
            feature_importance.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        for feature, importance in sorted_features:
            reasons.append(f"{feature}が重要な要因（重要度{importance:.2f}）")

        # 予測の確信度
        if favorite_prob > 0.6:
            reasons.append("高い確信度での予測")
        elif favorite_prob > 0.4:
            reasons.append("中程度の確信度での予測")
        else:
            reasons.append("競合が接戦の予測")

        return reasons

    def get_race_recommendation(self,
                              race_score: RaceScore,
                              mode: str = "accuracy") -> Dict:
        """
        レースの推奨情報を取得

        Args:
            race_score: レーススコア
            mode: 評価モード

        Returns:
            推奨情報の辞書
        """
        if mode == "accuracy":
            score = race_score.accuracy_score * 0.7 + race_score.stability_score * 0.3
            if score >= 80:
                level = "最高"
                stars = 5
                message = "非常に高い的中率が期待できます"
            elif score >= 65:
                level = "高"
                stars = 4
                message = "高い的中率が期待できます"
            elif score >= 50:
                level = "中"
                stars = 3
                message = "平均的な的中率が期待できます"
            elif score >= 35:
                level = "低"
                stars = 2
                message = "的中率はやや低めです"
            else:
                level = "最低"
                stars = 1
                message = "的中率は低いです"
        else:  # value mode
            score = race_score.value_score * 0.6 + race_score.accuracy_score * 0.4
            if score >= 80:
                level = "最高"
                stars = 5
                message = "非常に高い期待値です"
            elif score >= 65:
                level = "高"
                stars = 4
                message = "高い期待値です"
            elif score >= 50:
                level = "中"
                stars = 3
                message = "平均的な期待値です"
            elif score >= 35:
                level = "低"
                stars = 2
                message = "期待値はやや低めです"
            else:
                level = "最低"
                stars = 1
                message = "期待値は低いです"

        return {
            "level": level,
            "stars": stars,
            "score": score,
            "message": message,
            "favorite_boat": race_score.favorite_boat,
            "favorite_prob": race_score.favorite_prob,
            "reasons": race_score.prediction_reasons[:3]
        }