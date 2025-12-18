"""
オッズ校正スコアラー

オッズから市場の確率を逆算し、予測スコアを校正する。

理論:
- オッズの逆数は市場が見積もる確率を表す
- モデル予測と市場予測の乖離（Edge）を検出
- スコアを補正して精度向上を図る

機能:
1. 1着予測の校正（既存機能）
2. 2着・3着予測のオッズ統合（新規機能）

期待効果: +1.0~2.0pt
"""

import logging
import math
import sqlite3
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from src.utils.db_connection_pool import get_connection


class OddsCalibrator:
    """
    オッズを使用した予測スコア校正

    オッズから市場確率を逆算し、モデル予測との乖離を検出して
    スコアを補正する。

    新機能:
    - 2着・3着の条件付き確率をオッズから逆算
    - 機械学習予測との統合
    """

    # 競艇の払戻率（控除率25%）
    PAYOUT_RATE = 0.75

    def __init__(
        self,
        db_path: str,
        alpha: float = 0.5,
        temperature: float = 4.0,
        rank23_alpha: float = 0.2
    ):
        """
        Args:
            db_path: データベースパス
            alpha: 1着校正係数（0.0～1.0、大きいほどオッズの影響が強い）
            temperature: Softmax温度パラメータ（低いほど確率分布が鋭い）
            rank23_alpha: 2着・3着のオッズ統合係数（0.0～1.0）
        """
        self.db_path = db_path
        self.alpha = alpha
        self.temperature = temperature
        self.rank23_alpha = rank23_alpha
        self.logger = logging.getLogger(__name__)

    def calibrate_predictions(
        self,
        predictions: List[Dict],
        race_id: int
    ) -> List[Dict]:
        """
        オッズを使用して予測スコアを校正

        Args:
            predictions: 予測結果リスト
            race_id: レースID

        Returns:
            校正後の予測結果
        """
        # オッズデータを取得
        odds_data = self._get_odds_data(race_id)

        if not odds_data:
            self.logger.debug(f"Race {race_id}: オッズデータなし、校正スキップ")
            for pred in predictions:
                pred['odds_calibrated'] = False
                pred['odds_adjustment'] = 1.0
            return predictions

        # 単勝オッズのみを使用（3連単は組み合わせが多すぎる）
        win_odds = self._extract_win_odds(odds_data)

        if not win_odds:
            self.logger.debug(f"Race {race_id}: 単勝オッズなし、校正スキップ")
            for pred in predictions:
                pred['odds_calibrated'] = False
                pred['odds_adjustment'] = 1.0
            return predictions

        # 各艇のスコアを校正
        for pred in predictions:
            pit_number = pred['pit_number']

            if pit_number not in win_odds:
                pred['odds_calibrated'] = False
                pred['odds_adjustment'] = 1.0
                continue

            odds = win_odds[pit_number]

            # オッズから市場確率を計算
            market_prob = self._odds_to_probability(odds)

            # モデル確率を計算（スコアの正規化）
            model_prob = self._score_to_probability(predictions, pred)

            # Edge（期待値）を計算
            edge = model_prob / market_prob if market_prob > 0 else 1.0

            # スコア補正係数を計算
            adjustment = self._calculate_adjustment(edge)

            # スコアを補正
            original_score = pred['total_score']
            calibrated_score = original_score * adjustment

            pred['odds_calibrated'] = True
            pred['odds_adjustment'] = round(adjustment, 3)
            pred['market_probability'] = round(market_prob, 4)
            pred['edge'] = round(edge, 3)
            pred['original_score_before_odds'] = round(original_score, 1)
            pred['total_score'] = round(calibrated_score, 1)

        # 再ソート
        predictions.sort(key=lambda x: x['total_score'], reverse=True)

        self.logger.debug(
            f"Race {race_id}: オッズ校正完了 - "
            f"Top予測: 艇{predictions[0]['pit_number']} "
            f"補正{predictions[0]['odds_adjustment']:.3f}"
        )

        return predictions

    def calibrate_rank23_predictions(
        self,
        predictions: List[Dict],
        race_id: int,
        alpha: float = None
    ) -> List[Dict]:
        """
        2着・3着予測をオッズで校正

        3連単オッズから条件付き確率を逆算し、
        機械学習予測と統合する。

        Args:
            predictions: 予測結果リスト（スコア順）
            race_id: レースID
            alpha: 統合係数（Noneの場合はself.rank23_alphaを使用）

        Returns:
            校正後の予測結果
        """
        if alpha is None:
            alpha = self.rank23_alpha

        # 3連単オッズを取得
        trifecta_odds = self._get_trifecta_odds(race_id)

        if not trifecta_odds:
            self.logger.debug(f"Race {race_id}: 3連単オッズなし、2着・3着校正スキップ")
            for pred in predictions:
                pred['rank23_calibrated'] = False
            return predictions

        # 現在の予測1着艇を取得
        if not predictions:
            return predictions

        predicted_first = predictions[0]['pit_number']

        # 市場の2着条件付き確率を計算
        market_second_probs = self._calculate_conditional_second_probs(
            trifecta_odds, predicted_first
        )

        if not market_second_probs:
            self.logger.debug(
                f"Race {race_id}: 市場2着確率計算不可、校正スキップ"
            )
            for pred in predictions:
                pred['rank23_calibrated'] = False
            return predictions

        # 機械学習予測の2着確率を計算
        ml_second_probs = self._calculate_ml_second_probs(predictions, predicted_first)

        # 統合
        integrated_second_probs = self._integrate_probs(
            ml_second_probs, market_second_probs, alpha
        )

        # 予測をスコア更新
        for pred in predictions:
            pit = pred['pit_number']
            if pit == predicted_first:
                pred['rank23_calibrated'] = True
                pred['market_second_prob'] = 0.0
                pred['ml_second_prob'] = 0.0
                pred['integrated_second_prob'] = 0.0
            else:
                pred['rank23_calibrated'] = True
                pred['market_second_prob'] = round(
                    market_second_probs.get(pit, 0.0), 4
                )
                pred['ml_second_prob'] = round(
                    ml_second_probs.get(pit, 0.0), 4
                )
                pred['integrated_second_prob'] = round(
                    integrated_second_probs.get(pit, 0.0), 4
                )

                # スコアを統合確率で調整（1着候補を除く）
                if pit != predicted_first:
                    # 元のスコア比率を維持しつつ、オッズ情報を反映
                    original_score = pred['total_score']
                    integrated_prob = integrated_second_probs.get(pit, 0.0)

                    # スコア調整係数を計算
                    ml_prob = ml_second_probs.get(pit, 0.0)
                    if ml_prob > 0:
                        adjustment = 1.0 + alpha * (integrated_prob / ml_prob - 1.0)
                        adjustment = max(0.7, min(1.5, adjustment))
                        pred['rank23_adjustment'] = round(adjustment, 3)
                        pred['total_score'] = round(original_score * adjustment, 1)
                    else:
                        pred['rank23_adjustment'] = 1.0

        # 再ソート（1着候補を維持しつつ、2着以降を再調整）
        first_pred = predictions[0]
        rest_preds = sorted(
            [p for p in predictions if p['pit_number'] != predicted_first],
            key=lambda x: x.get('integrated_second_prob', 0.0),
            reverse=True
        )
        predictions = [first_pred] + rest_preds

        self.logger.debug(
            f"Race {race_id}: 2着・3着オッズ校正完了 - "
            f"予測1着: {predicted_first}号艇, "
            f"予測2着: {predictions[1]['pit_number']}号艇"
        )

        return predictions

    def get_optimal_trifecta_combinations(
        self,
        predictions: List[Dict],
        race_id: int,
        top_n: int = 6
    ) -> List[Dict]:
        """
        オッズ統合に基づく最適な3連単組み合わせを取得

        Args:
            predictions: 予測結果リスト
            race_id: レースID
            top_n: 取得する上位件数

        Returns:
            最適な組み合わせリスト
            [{'combination': '1-2-3', 'prob': 0.05, 'odds': 10.0, 'ev': 0.5}, ...]
        """
        trifecta_odds = self._get_trifecta_odds(race_id)

        if not trifecta_odds:
            return []

        # 市場確率を計算
        market_probs = self._calculate_market_probs(trifecta_odds)

        # ML予測確率を計算
        ml_probs = self._calculate_ml_trifecta_probs(predictions)

        # 統合確率を計算
        alpha = self.rank23_alpha
        integrated_probs = {}
        for combo in set(market_probs.keys()) | set(ml_probs.keys()):
            ml_p = ml_probs.get(combo, 0.0)
            market_p = market_probs.get(combo, 0.0)
            integrated_probs[combo] = (1 - alpha) * ml_p + alpha * market_p

        # 期待値（EV）を計算してソート
        results = []
        for combo, prob in integrated_probs.items():
            odds = trifecta_odds.get(combo, 0.0)
            if odds > 0:
                ev = prob * odds
                results.append({
                    'combination': combo,
                    'prob': round(prob, 4),
                    'odds': odds,
                    'ev': round(ev, 3),
                    'market_prob': round(market_probs.get(combo, 0.0), 4),
                    'ml_prob': round(ml_probs.get(combo, 0.0), 4)
                })

        # EVでソート（高い順）
        results.sort(key=lambda x: x['ev'], reverse=True)

        return results[:top_n]

    def _get_odds_data(self, race_id: int) -> Optional[List]:
        """オッズデータを取得"""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        # 3連単オッズを取得（単勝に変換する）
        cursor.execute("""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
            ORDER BY odds ASC
        """, (race_id,))

        odds_data = cursor.fetchall()
        cursor.close()

        return odds_data if odds_data else None

    def _get_trifecta_odds(self, race_id: int) -> Dict[str, float]:
        """3連単オッズをDict形式で取得"""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
        """, (race_id,))

        rows = cursor.fetchall()
        cursor.close()

        return {row[0]: row[1] for row in rows}

    def _extract_win_odds(self, odds_data: List) -> Dict[int, float]:
        """
        3連単オッズから単勝オッズを推定

        単勝オッズ = その艇が1着になる全組み合わせの最小オッズ
        """
        win_odds = {}

        for combination, odds in odds_data:
            # combination: "1-2-3" 形式
            try:
                parts = combination.split('-')
                if len(parts) != 3:
                    continue

                first_pit = int(parts[0])

                # その艇が1着になる組み合わせの最小オッズを記録
                if first_pit not in win_odds:
                    win_odds[first_pit] = odds
                else:
                    win_odds[first_pit] = min(win_odds[first_pit], odds)

            except (ValueError, IndexError):
                continue

        return win_odds

    def _odds_to_probability(self, odds: float) -> float:
        """
        オッズから市場確率を計算

        市場確率 = 1 / オッズ

        ただし、オーバーラウンド（控除率）を考慮して補正
        """
        if odds <= 1.0:
            return 0.5  # 異常値の場合

        # 単純逆数
        raw_prob = 1.0 / odds

        # 控除率補正（競艇の控除率は約25%）
        # 全艇の確率合計が1になるように調整
        adjusted_prob = raw_prob / 0.75  # 0.75 = 1 - 0.25

        # 上限を設定（確率は1を超えない）
        return min(adjusted_prob, 0.95)

    def _score_to_probability(
        self,
        predictions: List[Dict],
        target_pred: Dict
    ) -> float:
        """
        スコアから確率を計算（温度付きSoftmax）

        prob_i = exp(score_i / T) / sum(exp(score_j / T))
        温度T=10で緩やかな確率分布にする
        """
        scores = [pred['total_score'] for pred in predictions]
        target_score = target_pred['total_score']

        # 温度で割ってからSoftmax
        scaled_scores = [s / self.temperature for s in scores]
        max_scaled = max(scaled_scores)

        exp_scores = [math.exp(s - max_scaled) for s in scaled_scores]
        total_exp = sum(exp_scores)

        target_scaled = target_score / self.temperature
        target_exp = math.exp(target_scaled - max_scaled)
        probability = target_exp / total_exp if total_exp > 0 else 1.0 / len(predictions)

        return probability

    def _calculate_adjustment(self, edge: float) -> float:
        """
        Edgeから補正係数を計算

        adjustment = 1 + alpha * log(edge)

        - edge > 1: モデルが過小評価 → スコアを上げる
        - edge < 1: モデルが過大評価 → スコアを下げる
        - edge = 1: 市場と一致 → 補正なし
        """
        if edge <= 0:
            return 1.0

        # 対数補正（緩やかな変化）
        log_edge = math.log(edge)
        adjustment = 1.0 + self.alpha * log_edge

        # 補正範囲を制限（0.7～1.6倍）
        adjustment = max(0.7, min(1.6, adjustment))

        return adjustment

    def _calculate_conditional_second_probs(
        self,
        trifecta_odds: Dict[str, float],
        first_pit: int
    ) -> Dict[int, float]:
        """
        1着が確定した場合の2着条件付き確率を計算

        P(2着=j | 1着=i) = sum_k P(i-j-k) / sum_{j',k'} P(i-j'-k')
        """
        if not trifecta_odds:
            return {}

        # 市場確率を計算
        market_probs = self._calculate_market_probs(trifecta_odds)

        # 1着がfirst_pitの組み合わせのみをフィルタ
        first_prefix = f"{first_pit}-"
        filtered_probs = {
            combo: prob for combo, prob in market_probs.items()
            if combo.startswith(first_prefix)
        }

        if not filtered_probs:
            return {}

        # 2着ごとに確率を集計
        second_probs = defaultdict(float)
        total_filtered = sum(filtered_probs.values())

        for combo, prob in filtered_probs.items():
            parts = combo.split('-')
            if len(parts) >= 2:
                second_pit = int(parts[1])
                second_probs[second_pit] += prob

        # 正規化
        if total_filtered > 0:
            return {
                pit: prob / total_filtered
                for pit, prob in second_probs.items()
            }

        return {}

    def _calculate_market_probs(
        self,
        trifecta_odds: Dict[str, float]
    ) -> Dict[str, float]:
        """
        3連単オッズから市場確率を計算
        """
        if not trifecta_odds:
            return {}

        # 各組み合わせの確率を計算
        raw_probs = {}
        for combo, odds in trifecta_odds.items():
            if odds > 0:
                raw_probs[combo] = 1.0 / (odds * self.PAYOUT_RATE)

        # 正規化
        total_prob = sum(raw_probs.values())
        if total_prob > 0:
            return {combo: prob / total_prob for combo, prob in raw_probs.items()}

        return {}

    def _calculate_ml_second_probs(
        self,
        predictions: List[Dict],
        first_pit: int
    ) -> Dict[int, float]:
        """
        機械学習予測から2着確率を計算

        1着候補を除いた5艇のスコアを正規化して確率化
        """
        # 1着候補を除外
        remaining = [p for p in predictions if p['pit_number'] != first_pit]

        if not remaining:
            return {}

        # スコアを確率に変換（Softmax）
        scores = [p['total_score'] for p in remaining]
        scaled = [s / self.temperature for s in scores]
        max_scaled = max(scaled) if scaled else 0

        exp_scores = [math.exp(s - max_scaled) for s in scaled]
        total_exp = sum(exp_scores)

        if total_exp <= 0:
            return {}

        return {
            p['pit_number']: exp_scores[i] / total_exp
            for i, p in enumerate(remaining)
        }

    def _integrate_probs(
        self,
        ml_probs: Dict[int, float],
        market_probs: Dict[int, float],
        alpha: float
    ) -> Dict[int, float]:
        """
        機械学習確率と市場確率を統合

        integrated = (1 - alpha) * ml + alpha * market
        """
        if not market_probs:
            return ml_probs

        if not ml_probs:
            return market_probs

        integrated = {}
        all_pits = set(ml_probs.keys()) | set(market_probs.keys())

        for pit in all_pits:
            ml_p = ml_probs.get(pit, 0.0)
            market_p = market_probs.get(pit, 0.0)
            integrated[pit] = (1 - alpha) * ml_p + alpha * market_p

        # 正規化
        total = sum(integrated.values())
        if total > 0:
            integrated = {pit: prob / total for pit, prob in integrated.items()}

        return integrated

    def _calculate_ml_trifecta_probs(
        self,
        predictions: List[Dict]
    ) -> Dict[str, float]:
        """
        機械学習予測から3連単確率を計算

        P(i-j-k) = P(1着=i) × P(2着=j|1着=i) × P(3着=k|1着=i,2着=j)
        """
        if len(predictions) < 3:
            return {}

        # 1着確率（スコアベース）
        scores = [p['total_score'] for p in predictions]
        scaled = [s / self.temperature for s in scores]
        max_scaled = max(scaled) if scaled else 0
        exp_scores = [math.exp(s - max_scaled) for s in scaled]
        total_exp = sum(exp_scores)

        if total_exp <= 0:
            return {}

        first_probs = {
            p['pit_number']: exp_scores[i] / total_exp
            for i, p in enumerate(predictions)
        }

        # 3連単確率を計算
        trifecta_probs = {}

        for i, p1 in enumerate(predictions):
            pit1 = p1['pit_number']
            first_prob = first_probs[pit1]

            # 2着確率（1着を除外）
            remaining_for_second = [p for p in predictions if p['pit_number'] != pit1]
            second_scores = [p['total_score'] for p in remaining_for_second]
            second_scaled = [s / self.temperature for s in second_scores]
            max_second = max(second_scaled) if second_scaled else 0
            exp_second = [math.exp(s - max_second) for s in second_scaled]
            total_second = sum(exp_second)

            if total_second <= 0:
                continue

            second_probs = {
                p['pit_number']: exp_second[j] / total_second
                for j, p in enumerate(remaining_for_second)
            }

            for j, p2 in enumerate(remaining_for_second):
                pit2 = p2['pit_number']
                second_prob = second_probs[pit2]

                # 3着確率（1着・2着を除外）
                remaining_for_third = [
                    p for p in remaining_for_second
                    if p['pit_number'] != pit2
                ]
                third_scores = [p['total_score'] for p in remaining_for_third]
                third_scaled = [s / self.temperature for s in third_scores]
                max_third = max(third_scaled) if third_scaled else 0
                exp_third = [math.exp(s - max_third) for s in third_scaled]
                total_third = sum(exp_third)

                if total_third <= 0:
                    continue

                third_probs = {
                    p['pit_number']: exp_third[k] / total_third
                    for k, p in enumerate(remaining_for_third)
                }

                for k, p3 in enumerate(remaining_for_third):
                    pit3 = p3['pit_number']
                    third_prob = third_probs[pit3]

                    combo = f"{pit1}-{pit2}-{pit3}"
                    trifecta_probs[combo] = first_prob * second_prob * third_prob

        return trifecta_probs
