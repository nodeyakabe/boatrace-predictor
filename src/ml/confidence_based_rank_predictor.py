"""
信頼度ベースの2着・3着予測戦略切り替え

アプローチ1: 1着予測の確信度に応じた2着・3着予測方法の切り替え

理論的根拠:
- 1着予測が正しい場合: 2着的中率 31.67%（良好）
- 1着予測が誤りの場合: 2着的中率 16.93%（ランダム20%以下）

つまり、1着予測の確信度が低い場合は、条件付きモデルを使わない方が良い。

実装方針:
- 高信頼度: 条件付きモデル + 2着専用スコアリング
- 中信頼度: 2着専用スコアリングのみ
- 低信頼度: 独立予測（1着を条件としない全艇並列評価）

期待効果: 2着・3着的中率の向上、三連単的中率の改善
"""

import numpy as np
import math
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ConfidenceScore:
    """信頼度スコアの詳細"""
    score_gap: float              # 1位と2位のスコア差
    top_score_abs: float          # 1位の絶対スコア
    odds_agreement: float         # オッズとの一致度
    preset_match: float           # プリセットパターンへの該当度
    total_confidence: float       # 総合信頼度（0.0-1.0）
    confidence_level: str         # 信頼度レベル（high/medium/low）

    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return {
            'score_gap': round(self.score_gap, 3),
            'top_score_abs': round(self.top_score_abs, 3),
            'odds_agreement': round(self.odds_agreement, 3),
            'preset_match': round(self.preset_match, 3),
            'total_confidence': round(self.total_confidence, 3),
            'confidence_level': self.confidence_level
        }


class ConfidenceBasedRankPredictor:
    """
    信頼度ベースの着順予測器

    1着予測の信頼度を評価し、それに応じて最適な2着・3着予測戦略を選択する。

    戦略:
    - HIGH: 条件付きモデル + 2着専用スコアリング（既存の最も精度が高い方法）
    - MEDIUM: 2着専用スコアリングのみ（条件付きモデルをスキップ）
    - LOW: 独立予測（全艇を並列評価、1着を条件としない）
    """

    # 信頼度閾値（チューニング可能）
    DEFAULT_THRESHOLDS = {
        'high': 0.7,      # この値以上で高信頼度
        'medium': 0.5,    # この値以上で中信頼度
    }

    # コース別2着・3着基準勝率（独立予測用）
    # 全国平均データに基づく
    COURSE_SECOND_RATES = {
        1: 0.18,  # 1コースは逃げが多いため2着率低め
        2: 0.22,  # 差し狙いで2着多い
        3: 0.20,
        4: 0.18,
        5: 0.12,
        6: 0.10
    }

    COURSE_THIRD_RATES = {
        1: 0.12,
        2: 0.18,
        3: 0.19,
        4: 0.19,
        5: 0.17,
        6: 0.15
    }

    def __init__(
        self,
        high_threshold: float = None,
        medium_threshold: float = None,
        weight_score_gap: float = 0.4,
        weight_top_score: float = 0.3,
        weight_odds: float = 0.2,
        weight_preset: float = 0.1
    ):
        """
        Args:
            high_threshold: 高信頼度の閾値（None時はデフォルト）
            medium_threshold: 中信頼度の閾値（None時はデフォルト）
            weight_score_gap: スコア差の重み
            weight_top_score: トップスコアの重み
            weight_odds: オッズ一致度の重み
            weight_preset: プリセットパターンの重み
        """
        self.high_threshold = high_threshold or self.DEFAULT_THRESHOLDS['high']
        self.medium_threshold = medium_threshold or self.DEFAULT_THRESHOLDS['medium']

        # 信頼度計算の重み
        self.weight_score_gap = weight_score_gap
        self.weight_top_score = weight_top_score
        self.weight_odds = weight_odds
        self.weight_preset = weight_preset

        self.logger = logging.getLogger(__name__)

    def calculate_confidence(
        self,
        predictions: List[Dict],
        market_probs: Optional[Dict[int, float]] = None,
        preset_pattern: Optional[str] = None
    ) -> ConfidenceScore:
        """
        1着予測の信頼度を計算

        Args:
            predictions: 予測結果リスト（スコア順にソート済み）
            market_probs: 市場確率（オッズから計算、pit_number -> 確率）
            preset_pattern: 適用されたプリセットパターン名

        Returns:
            ConfidenceScore: 信頼度スコアの詳細
        """
        if len(predictions) < 2:
            return ConfidenceScore(
                score_gap=0.0,
                top_score_abs=0.0,
                odds_agreement=0.0,
                preset_match=0.0,
                total_confidence=0.0,
                confidence_level='low'
            )

        # 1. スコア差（1位と2位の差）の正規化
        scores = [p['total_score'] for p in predictions]
        score_gap = scores[0] - scores[1]
        # スコア差を0-1に正規化（10点差で満点）
        score_gap_normalized = min(score_gap / 10.0, 1.0)

        # 2. トップスコアの絶対値の正規化
        top_score = scores[0]
        # 80点以上で高スコア、60点以下で低スコア
        top_score_normalized = max(0.0, min((top_score - 60.0) / 20.0, 1.0))

        # 3. オッズとの一致度
        odds_agreement = 0.5  # デフォルト（オッズがない場合）
        if market_probs:
            predicted_first_pit = predictions[0]['pit_number']
            if predicted_first_pit in market_probs:
                # 市場確率が高いほど一致度が高い
                market_prob = market_probs.get(predicted_first_pit, 0.0)
                # 市場確率が50%以上なら高一致
                odds_agreement = min(market_prob / 0.5, 1.0)

        # 4. プリセットパターンへの該当度
        preset_match = 0.0
        if preset_pattern:
            # 信頼できるパターンにボーナス
            TRUSTED_PATTERNS = [
                'A1_NIGE',      # A1選手の1コース逃げ
                'DOUBLE_A1',    # A1選手が2人以上
                'HIGH_IN',      # イン有利会場
            ]
            if any(p in preset_pattern for p in TRUSTED_PATTERNS):
                preset_match = 1.0
            else:
                preset_match = 0.5  # その他のパターン

        # 総合信頼度を計算
        total_confidence = (
            self.weight_score_gap * score_gap_normalized +
            self.weight_top_score * top_score_normalized +
            self.weight_odds * odds_agreement +
            self.weight_preset * preset_match
        )

        # 信頼度レベルを判定
        if total_confidence >= self.high_threshold:
            confidence_level = 'high'
        elif total_confidence >= self.medium_threshold:
            confidence_level = 'medium'
        else:
            confidence_level = 'low'

        return ConfidenceScore(
            score_gap=score_gap_normalized,
            top_score_abs=top_score_normalized,
            odds_agreement=odds_agreement,
            preset_match=preset_match,
            total_confidence=total_confidence,
            confidence_level=confidence_level
        )

    def predict_second_place(
        self,
        predictions: List[Dict],
        confidence: ConfidenceScore,
        conditional_second_probs: Optional[Dict[int, float]] = None,
        specialized_second_probs: Optional[Dict[int, float]] = None
    ) -> Dict[int, float]:
        """
        信頼度に基づいて2着予測を行う

        Args:
            predictions: 予測結果リスト（スコア順）
            confidence: 信頼度スコア
            conditional_second_probs: 条件付きモデルの2着確率
            specialized_second_probs: 2着専用モデルの確率

        Returns:
            {艇番: 2着確率} の辞書
        """
        predicted_first = predictions[0]['pit_number']
        remaining = [p for p in predictions if p['pit_number'] != predicted_first]

        if confidence.confidence_level == 'high':
            # 高信頼度: 条件付きモデル + 2着専用スコアリングの統合
            return self._integrate_high_confidence(
                conditional_second_probs or {},
                specialized_second_probs or {},
                remaining,
                alpha=0.5  # 条件付き50%, 専用50%
            )

        elif confidence.confidence_level == 'medium':
            # 中信頼度: 2着専用スコアリングのみ
            if specialized_second_probs:
                return specialized_second_probs
            else:
                return self._calculate_independent_second_probs(remaining)

        else:
            # 低信頼度: 独立予測（1着を条件としない）
            return self._calculate_independent_second_probs(remaining)

    def predict_third_place(
        self,
        predictions: List[Dict],
        confidence: ConfidenceScore,
        predicted_second: int,
        conditional_third_probs: Optional[Dict[int, float]] = None
    ) -> Dict[int, float]:
        """
        信頼度に基づいて3着予測を行う

        Args:
            predictions: 予測結果リスト
            confidence: 信頼度スコア
            predicted_second: 予測2着の艇番
            conditional_third_probs: 条件付きモデルの3着確率

        Returns:
            {艇番: 3着確率} の辞書
        """
        predicted_first = predictions[0]['pit_number']
        remaining = [
            p for p in predictions
            if p['pit_number'] not in [predicted_first, predicted_second]
        ]

        if confidence.confidence_level == 'high':
            # 高信頼度: 条件付きモデルを使用
            if conditional_third_probs:
                return conditional_third_probs
            else:
                return self._calculate_independent_third_probs(remaining)

        else:
            # 中/低信頼度: 独立予測
            return self._calculate_independent_third_probs(remaining)

    def _integrate_high_confidence(
        self,
        conditional_probs: Dict[int, float],
        specialized_probs: Dict[int, float],
        remaining: List[Dict],
        alpha: float = 0.5
    ) -> Dict[int, float]:
        """
        高信頼度時の確率統合

        条件付きモデルと専用モデルの重み付き平均
        """
        integrated = {}
        all_pits = set()

        for p in remaining:
            all_pits.add(p['pit_number'])

        for pit in all_pits:
            cond_prob = conditional_probs.get(pit, 0.0)
            spec_prob = specialized_probs.get(pit, 0.0)

            if cond_prob > 0 and spec_prob > 0:
                integrated[pit] = (1 - alpha) * cond_prob + alpha * spec_prob
            elif spec_prob > 0:
                integrated[pit] = spec_prob
            elif cond_prob > 0:
                integrated[pit] = cond_prob
            else:
                # どちらもない場合はスコアベース
                pred = next((p for p in remaining if p['pit_number'] == pit), None)
                if pred:
                    integrated[pit] = pred['total_score'] / 100.0

        # 正規化
        total = sum(integrated.values())
        if total > 0:
            integrated = {k: v / total for k, v in integrated.items()}

        return integrated

    def _calculate_independent_second_probs(
        self,
        remaining: List[Dict]
    ) -> Dict[int, float]:
        """
        独立予測（1着を条件としない）による2着確率計算

        全艇を並列評価し、コース別基準勝率とスコアを組み合わせる
        """
        probs = {}

        for pred in remaining:
            pit = pred['pit_number']

            # コース別基準2着率
            course_rate = self.COURSE_SECOND_RATES.get(pit, 0.16)

            # スコアによる補正（スコアが高いほど確率上昇）
            score = pred['total_score']
            score_factor = 1.0 + (score - 50.0) / 100.0  # 50点を基準に補正
            score_factor = max(0.5, min(2.0, score_factor))  # 0.5-2.0倍に制限

            probs[pit] = course_rate * score_factor

        # 正規化
        total = sum(probs.values())
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}

        return probs

    def _calculate_independent_third_probs(
        self,
        remaining: List[Dict]
    ) -> Dict[int, float]:
        """
        独立予測による3着確率計算
        """
        probs = {}

        for pred in remaining:
            pit = pred['pit_number']

            # コース別基準3着率
            course_rate = self.COURSE_THIRD_RATES.get(pit, 0.16)

            # スコアによる補正
            score = pred['total_score']
            score_factor = 1.0 + (score - 50.0) / 100.0
            score_factor = max(0.5, min(2.0, score_factor))

            probs[pit] = course_rate * score_factor

        # 正規化
        total = sum(probs.values())
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}

        return probs

    def rerank_predictions(
        self,
        predictions: List[Dict],
        confidence: ConfidenceScore,
        second_probs: Dict[int, float],
        third_probs: Dict[int, float]
    ) -> List[Dict]:
        """
        信頼度ベースの確率を使用して予測結果を再ランキング

        Args:
            predictions: 元の予測結果
            confidence: 信頼度スコア
            second_probs: 2着確率
            third_probs: 3着確率

        Returns:
            再ランキング後の予測結果
        """
        predicted_first_pit = predictions[0]['pit_number']

        # 各予測に信頼度ベースの情報を追加
        for pred in predictions:
            pit = pred['pit_number']

            pred['confidence_based'] = True
            pred['confidence_score'] = confidence.to_dict()

            if pit == predicted_first_pit:
                pred['cb_second_prob'] = 0.0
                pred['cb_third_prob'] = 0.0
            else:
                pred['cb_second_prob'] = round(second_probs.get(pit, 0.0), 4)
                pred['cb_third_prob'] = round(third_probs.get(pit, 0.0), 4)

        # 1着は維持、2着以降を再ソート
        first_pred = predictions[0]
        rest_preds = [p for p in predictions if p['pit_number'] != predicted_first_pit]

        # 2着確率でソート
        rest_preds.sort(key=lambda x: x.get('cb_second_prob', 0.0), reverse=True)

        # 再結合
        reranked = [first_pred] + rest_preds

        # rank_predictionを更新
        for rank, pred in enumerate(reranked, 1):
            pred['rank_prediction'] = rank

        return reranked

    def get_recommended_strategy(self, confidence: ConfidenceScore) -> Dict:
        """
        信頼度に基づく推奨戦略を取得

        Args:
            confidence: 信頼度スコア

        Returns:
            推奨戦略の詳細
        """
        if confidence.confidence_level == 'high':
            return {
                'level': 'high',
                'use_conditional_model': True,
                'use_specialized_scorer': True,
                'description': '高信頼度: 条件付きモデル + 2着専用スコアリング併用',
                'expected_accuracy': {
                    'second_place': 0.35,  # 期待2着的中率
                    'third_place': 0.28,   # 期待3着的中率
                }
            }
        elif confidence.confidence_level == 'medium':
            return {
                'level': 'medium',
                'use_conditional_model': False,
                'use_specialized_scorer': True,
                'description': '中信頼度: 2着専用スコアリングのみ使用',
                'expected_accuracy': {
                    'second_place': 0.28,
                    'third_place': 0.24,
                }
            }
        else:
            return {
                'level': 'low',
                'use_conditional_model': False,
                'use_specialized_scorer': False,
                'description': '低信頼度: 独立予測（全艇並列評価）',
                'expected_accuracy': {
                    'second_place': 0.22,
                    'third_place': 0.20,
                }
            }


class ConfidenceBasedIntegrator:
    """
    信頼度ベース予測の統合器

    既存の予測システムと信頼度ベース予測を統合する。
    """

    def __init__(
        self,
        predictor: ConfidenceBasedRankPredictor = None,
        enable_logging: bool = True
    ):
        """
        Args:
            predictor: 信頼度ベース予測器（None時は新規作成）
            enable_logging: ログ出力を有効化
        """
        self.predictor = predictor or ConfidenceBasedRankPredictor()
        self.enable_logging = enable_logging
        self.logger = logging.getLogger(__name__)

        # 統計情報
        self.stats = {
            'high_count': 0,
            'medium_count': 0,
            'low_count': 0,
            'high_correct_2nd': 0,
            'medium_correct_2nd': 0,
            'low_correct_2nd': 0,
        }

    def process_predictions(
        self,
        predictions: List[Dict],
        market_probs: Optional[Dict[int, float]] = None,
        preset_pattern: Optional[str] = None,
        conditional_second_probs: Optional[Dict[int, float]] = None,
        specialized_second_probs: Optional[Dict[int, float]] = None,
        conditional_third_probs: Optional[Dict[int, float]] = None
    ) -> Tuple[List[Dict], ConfidenceScore]:
        """
        予測結果を信頼度ベースで処理

        Args:
            predictions: 元の予測結果
            market_probs: 市場確率
            preset_pattern: プリセットパターン
            conditional_second_probs: 条件付き2着確率
            specialized_second_probs: 専用2着確率
            conditional_third_probs: 条件付き3着確率

        Returns:
            (処理後の予測結果, 信頼度スコア)
        """
        # 信頼度を計算
        confidence = self.predictor.calculate_confidence(
            predictions, market_probs, preset_pattern
        )

        # 統計を更新
        self._update_stats(confidence)

        # 2着確率を計算
        second_probs = self.predictor.predict_second_place(
            predictions,
            confidence,
            conditional_second_probs,
            specialized_second_probs
        )

        # 予測2着を決定
        if second_probs:
            predicted_second = max(second_probs, key=second_probs.get)
        else:
            predicted_second = predictions[1]['pit_number'] if len(predictions) > 1 else 0

        # 3着確率を計算
        third_probs = self.predictor.predict_third_place(
            predictions,
            confidence,
            predicted_second,
            conditional_third_probs
        )

        # 予測を再ランキング
        processed = self.predictor.rerank_predictions(
            predictions,
            confidence,
            second_probs,
            third_probs
        )

        if self.enable_logging:
            self.logger.debug(
                f"信頼度: {confidence.confidence_level} "
                f"(score={confidence.total_confidence:.3f})"
            )

        return processed, confidence

    def _update_stats(self, confidence: ConfidenceScore):
        """統計情報を更新"""
        if confidence.confidence_level == 'high':
            self.stats['high_count'] += 1
        elif confidence.confidence_level == 'medium':
            self.stats['medium_count'] += 1
        else:
            self.stats['low_count'] += 1

    def update_result(
        self,
        confidence_level: str,
        actual_second: int,
        predicted_second: int
    ):
        """
        実際の結果で統計を更新

        Args:
            confidence_level: 信頼度レベル
            actual_second: 実際の2着
            predicted_second: 予測2着
        """
        if actual_second == predicted_second:
            if confidence_level == 'high':
                self.stats['high_correct_2nd'] += 1
            elif confidence_level == 'medium':
                self.stats['medium_correct_2nd'] += 1
            else:
                self.stats['low_correct_2nd'] += 1

    def get_stats_summary(self) -> Dict:
        """統計サマリーを取得"""
        total = (
            self.stats['high_count'] +
            self.stats['medium_count'] +
            self.stats['low_count']
        )

        if total == 0:
            return {'total': 0, 'message': 'No data'}

        return {
            'total': total,
            'high': {
                'count': self.stats['high_count'],
                'ratio': self.stats['high_count'] / total,
                'accuracy_2nd': (
                    self.stats['high_correct_2nd'] / self.stats['high_count']
                    if self.stats['high_count'] > 0 else 0
                )
            },
            'medium': {
                'count': self.stats['medium_count'],
                'ratio': self.stats['medium_count'] / total,
                'accuracy_2nd': (
                    self.stats['medium_correct_2nd'] / self.stats['medium_count']
                    if self.stats['medium_count'] > 0 else 0
                )
            },
            'low': {
                'count': self.stats['low_count'],
                'ratio': self.stats['low_count'] / total,
                'accuracy_2nd': (
                    self.stats['low_correct_2nd'] / self.stats['low_count']
                    if self.stats['low_count'] > 0 else 0
                )
            }
        }

    def reset_stats(self):
        """統計をリセット"""
        for key in self.stats:
            self.stats[key] = 0


# ユーティリティ関数
def calculate_market_probs_from_odds(
    trifecta_odds: Dict[str, float],
    payout_rate: float = 0.75
) -> Dict[int, float]:
    """
    3連単オッズから各艇の1着確率（市場確率）を計算

    Args:
        trifecta_odds: {'1-2-3': 10.5, ...}形式のオッズ
        payout_rate: 払戻率（デフォルト75%）

    Returns:
        {艇番: 1着確率}の辞書
    """
    if not trifecta_odds:
        return {}

    # 各艇が1着になる組み合わせの確率を合計
    first_probs = {}

    for combo, odds in trifecta_odds.items():
        try:
            parts = combo.split('-')
            if len(parts) >= 1:
                first_pit = int(parts[0])
                prob = 1.0 / (odds * payout_rate) if odds > 0 else 0
                first_probs[first_pit] = first_probs.get(first_pit, 0) + prob
        except (ValueError, IndexError):
            continue

    # 正規化
    total = sum(first_probs.values())
    if total > 0:
        first_probs = {k: v / total for k, v in first_probs.items()}

    return first_probs


if __name__ == '__main__':
    # テスト
    logging.basicConfig(level=logging.DEBUG)

    # サンプル予測データ
    predictions = [
        {'pit_number': 1, 'total_score': 75.5, 'racer_name': '選手A'},
        {'pit_number': 2, 'total_score': 68.2, 'racer_name': '選手B'},
        {'pit_number': 3, 'total_score': 62.1, 'racer_name': '選手C'},
        {'pit_number': 4, 'total_score': 55.3, 'racer_name': '選手D'},
        {'pit_number': 5, 'total_score': 48.7, 'racer_name': '選手E'},
        {'pit_number': 6, 'total_score': 42.0, 'racer_name': '選手F'},
    ]

    # 市場確率（サンプル）
    market_probs = {1: 0.45, 2: 0.20, 3: 0.15, 4: 0.10, 5: 0.06, 6: 0.04}

    # 予測器を作成
    predictor = ConfidenceBasedRankPredictor()

    # 信頼度を計算
    confidence = predictor.calculate_confidence(
        predictions,
        market_probs,
        preset_pattern='A1_NIGE'
    )

    print(f"信頼度スコア: {confidence.to_dict()}")

    # 2着確率を計算
    second_probs = predictor.predict_second_place(
        predictions,
        confidence
    )

    print(f"2着確率: {second_probs}")

    # 推奨戦略を取得
    strategy = predictor.get_recommended_strategy(confidence)
    print(f"推奨戦略: {strategy}")
