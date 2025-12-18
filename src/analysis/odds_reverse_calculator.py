"""
オッズ逆算モジュール

3連単オッズから市場の2着・3着予測確率を逆算し、
機械学習予測との統合に利用する。

理論:
- 3連単オッズ = 1 / (市場予測確率 × 払戻率)
- 払戻率 = 約75%（控除率25%）
- オッズから市場確率を逆算し、条件付き確率を計算

期待効果:
- 2着・3着予測精度の向上
- ROI改善
"""

import logging
import sqlite3
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from src.utils.db_connection_pool import get_connection


class OddsReverseCalculator:
    """
    3連単オッズから2着・3着の条件付き確率を逆算するクラス

    市場参加者の集合知を活用して、機械学習予測を補完する。
    """

    # 競艇の払戻率（控除率25%）
    PAYOUT_RATE = 0.75

    def __init__(self, db_path: str):
        """
        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)

    def get_trifecta_odds(self, race_id: int) -> Dict[str, float]:
        """
        レースの3連単オッズを取得

        Args:
            race_id: レースID

        Returns:
            組み合わせ -> オッズのマップ
            例: {'1-2-3': 10.0, '1-2-4': 15.5, ...}
        """
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

    def calculate_market_probabilities(
        self,
        odds_data: Dict[str, float]
    ) -> Dict[str, float]:
        """
        オッズから市場確率を計算

        Args:
            odds_data: 組み合わせ -> オッズのマップ

        Returns:
            組み合わせ -> 確率のマップ
        """
        if not odds_data:
            return {}

        # 各組み合わせの確率を計算
        raw_probs = {}
        for combo, odds in odds_data.items():
            if odds > 0:
                # 確率 = 1 / (オッズ × 払戻率)
                raw_probs[combo] = 1.0 / (odds * self.PAYOUT_RATE)

        # 正規化（確率の合計が1になるように調整）
        total_prob = sum(raw_probs.values())
        if total_prob > 0:
            return {combo: prob / total_prob for combo, prob in raw_probs.items()}

        return {}

    def calculate_conditional_second_probs(
        self,
        odds_data: Dict[str, float],
        first_pit: int
    ) -> Dict[int, float]:
        """
        1着が確定した場合の2着条件付き確率を計算

        P(2着=j | 1着=i) = sum_k P(i-j-k) / sum_{j',k'} P(i-j'-k')

        Args:
            odds_data: 3連単オッズデータ
            first_pit: 1着の艇番（1-6）

        Returns:
            2着候補艇番 -> 確率のマップ
        """
        if not odds_data:
            return {}

        # 市場確率を計算
        probs = self.calculate_market_probabilities(odds_data)

        # 1着がfirst_pitの組み合わせのみをフィルタ
        first_prefix = f"{first_pit}-"
        filtered_probs = {
            combo: prob for combo, prob in probs.items()
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

    def calculate_conditional_third_probs(
        self,
        odds_data: Dict[str, float],
        first_pit: int,
        second_pit: int
    ) -> Dict[int, float]:
        """
        1着・2着が確定した場合の3着条件付き確率を計算

        P(3着=k | 1着=i, 2着=j) = P(i-j-k) / sum_k' P(i-j-k')

        Args:
            odds_data: 3連単オッズデータ
            first_pit: 1着の艇番（1-6）
            second_pit: 2着の艇番（1-6）

        Returns:
            3着候補艇番 -> 確率のマップ
        """
        if not odds_data:
            return {}

        # 市場確率を計算
        probs = self.calculate_market_probabilities(odds_data)

        # 1着-2着がfirst_pit-second_pitの組み合わせのみをフィルタ
        prefix = f"{first_pit}-{second_pit}-"
        filtered_probs = {
            combo: prob for combo, prob in probs.items()
            if combo.startswith(prefix)
        }

        if not filtered_probs:
            return {}

        # 3着ごとに確率を集計
        third_probs = {}
        total_filtered = sum(filtered_probs.values())

        for combo, prob in filtered_probs.items():
            parts = combo.split('-')
            if len(parts) >= 3:
                third_pit = int(parts[2])
                third_probs[third_pit] = prob

        # 正規化
        if total_filtered > 0:
            return {
                pit: prob / total_filtered
                for pit, prob in third_probs.items()
            }

        return {}

    def calculate_first_place_probs(
        self,
        odds_data: Dict[str, float]
    ) -> Dict[int, float]:
        """
        各艇の1着確率を計算

        P(1着=i) = sum_{j,k} P(i-j-k)

        Args:
            odds_data: 3連単オッズデータ

        Returns:
            艇番 -> 1着確率のマップ
        """
        if not odds_data:
            return {}

        # 市場確率を計算
        probs = self.calculate_market_probabilities(odds_data)

        # 1着ごとに確率を集計
        first_probs = defaultdict(float)

        for combo, prob in probs.items():
            parts = combo.split('-')
            if len(parts) >= 1:
                first_pit = int(parts[0])
                first_probs[first_pit] += prob

        return dict(first_probs)

    def get_full_probability_distribution(
        self,
        race_id: int
    ) -> Optional[Dict]:
        """
        レースの完全な確率分布を取得

        Args:
            race_id: レースID

        Returns:
            以下の構造を持つ辞書:
            {
                'first_probs': {艇番: 1着確率},
                'conditional_second': {1着艇番: {2着艇番: 確率}},
                'conditional_third': {(1着, 2着): {3着艇番: 確率}},
                'raw_probs': {組み合わせ: 確率}
            }
        """
        odds_data = self.get_trifecta_odds(race_id)

        if not odds_data:
            self.logger.debug(f"Race {race_id}: オッズデータなし")
            return None

        # 市場確率計算
        raw_probs = self.calculate_market_probabilities(odds_data)

        if not raw_probs:
            return None

        # 1着確率
        first_probs = self.calculate_first_place_probs(odds_data)

        # 条件付き2着確率（各1着候補について）
        conditional_second = {}
        for first_pit in range(1, 7):
            second_probs = self.calculate_conditional_second_probs(odds_data, first_pit)
            if second_probs:
                conditional_second[first_pit] = second_probs

        # 条件付き3着確率（1着・2着の組み合わせについて）
        conditional_third = {}
        for first_pit in range(1, 7):
            for second_pit in range(1, 7):
                if first_pit == second_pit:
                    continue
                third_probs = self.calculate_conditional_third_probs(
                    odds_data, first_pit, second_pit
                )
                if third_probs:
                    conditional_third[(first_pit, second_pit)] = third_probs

        return {
            'first_probs': first_probs,
            'conditional_second': conditional_second,
            'conditional_third': conditional_third,
            'raw_probs': raw_probs
        }

    def integrate_with_ml_predictions(
        self,
        ml_second_probs: Dict[int, float],
        market_second_probs: Dict[int, float],
        alpha: float = 0.3
    ) -> Dict[int, float]:
        """
        機械学習予測と市場確率を統合

        final_prob = (1 - alpha) * ml_prob + alpha * market_prob

        Args:
            ml_second_probs: 機械学習による2着確率 {艇番: 確率}
            market_second_probs: 市場による2着確率 {艇番: 確率}
            alpha: 市場確率の重み（0.0〜1.0）

        Returns:
            統合後の2着確率 {艇番: 確率}
        """
        if not market_second_probs:
            return ml_second_probs

        if not ml_second_probs:
            return market_second_probs

        # 統合
        integrated = {}
        all_pits = set(ml_second_probs.keys()) | set(market_second_probs.keys())

        for pit in all_pits:
            ml_prob = ml_second_probs.get(pit, 0.0)
            market_prob = market_second_probs.get(pit, 0.0)
            integrated[pit] = (1 - alpha) * ml_prob + alpha * market_prob

        # 正規化
        total = sum(integrated.values())
        if total > 0:
            integrated = {pit: prob / total for pit, prob in integrated.items()}

        return integrated

    def get_top_combinations_from_odds(
        self,
        race_id: int,
        top_n: int = 10
    ) -> List[Tuple[str, float, float]]:
        """
        オッズ上位の組み合わせを取得

        Args:
            race_id: レースID
            top_n: 取得する上位件数

        Returns:
            [(組み合わせ, オッズ, 市場確率), ...] のリスト
        """
        odds_data = self.get_trifecta_odds(race_id)

        if not odds_data:
            return []

        probs = self.calculate_market_probabilities(odds_data)

        # 確率が高い順にソート
        sorted_combos = sorted(
            [(combo, odds_data[combo], probs.get(combo, 0))
             for combo in odds_data.keys()],
            key=lambda x: x[2],
            reverse=True
        )

        return sorted_combos[:top_n]


def test_odds_reverse_calculator():
    """テスト用関数"""
    import os

    db_path = "data/boatrace.db"
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return

    calculator = OddsReverseCalculator(db_path)

    # テスト用レースIDを取得
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT race_id FROM trifecta_odds LIMIT 5
    """)
    race_ids = [row[0] for row in cursor.fetchall()]
    cursor.close()

    if not race_ids:
        print("No odds data found")
        return

    for race_id in race_ids:
        print(f"\n{'='*60}")
        print(f"Race ID: {race_id}")
        print('='*60)

        dist = calculator.get_full_probability_distribution(race_id)

        if not dist:
            print("No probability distribution available")
            continue

        # 1着確率
        print("\n1着確率:")
        for pit in sorted(dist['first_probs'].keys()):
            prob = dist['first_probs'][pit]
            print(f"  {pit}号艇: {prob*100:.1f}%")

        # 上位組み合わせ
        top_combos = calculator.get_top_combinations_from_odds(race_id, top_n=5)
        print("\n上位組み合わせ（市場予測）:")
        for combo, odds, prob in top_combos:
            print(f"  {combo}: オッズ{odds:.1f}倍, 確率{prob*100:.2f}%")


if __name__ == "__main__":
    test_odds_reverse_calculator()
