"""
買い目推奨モジュール

予測結果に基づいて買い目を推奨する。
race_predictor.pyから分離（2025-12-15）
"""

from typing import Dict, List


class BetRecommender:
    """
    買い目を推奨するクラス

    予測結果に基づいて、三連単、三連複、二連単、二連複の
    買い目を推奨する。
    """

    def recommend_bets(
        self,
        predictions: List[Dict],
        bet_types: List[str] = None
    ) -> Dict:
        """
        買い目を推奨

        Args:
            predictions: predict_race()の結果
            bet_types: 舟券種別リスト（['3tan', '3fuku', '2tan']など）

        Returns:
            {
                '3tan': [{'combination': '1-2-3', 'confidence': 'A'}, ...],
                '3fuku': [...],
                ...
            }
        """
        if bet_types is None:
            bet_types = ['3tan', '3fuku']

        recommendations = {}

        # 上位3艇を取得
        top3 = predictions[:3]
        top_numbers = [p['pit_number'] for p in top3]

        if '3tan' in bet_types:
            recommendations['3tan'] = self._recommend_3tan(predictions, top_numbers)

        if '3fuku' in bet_types:
            recommendations['3fuku'] = self._recommend_3fuku(predictions, top_numbers)

        if '2tan' in bet_types:
            recommendations['2tan'] = self._recommend_2tan(predictions, top_numbers)

        if '2fuku' in bet_types:
            recommendations['2fuku'] = self._recommend_2fuku(predictions, top_numbers)

        return recommendations

    def _recommend_3tan(
        self,
        predictions: List[Dict],
        top_numbers: List[int]
    ) -> List[Dict]:
        """三連単の推奨買い目"""
        bets = []

        first = top_numbers[0]
        for second in top_numbers[1:]:
            for third in top_numbers:
                if third != first and third != second:
                    combination = f"{first}-{second}-{third}"
                    confidence = predictions[0]['confidence']
                    bets.append({
                        'combination': combination,
                        'confidence': confidence
                    })

        return bets[:5]

    def _recommend_3fuku(
        self,
        predictions: List[Dict],
        top_numbers: List[int]
    ) -> List[Dict]:
        """三連複の推奨買い目"""
        combination = '-'.join(map(str, sorted(top_numbers)))
        confidence = predictions[0]['confidence']

        return [{
            'combination': combination,
            'confidence': confidence
        }]

    def _recommend_2tan(
        self,
        predictions: List[Dict],
        top_numbers: List[int]
    ) -> List[Dict]:
        """二連単の推奨買い目"""
        bets = []

        first = top_numbers[0]
        for second in top_numbers[1:3]:
            combination = f"{first}-{second}"
            confidence = predictions[0]['confidence']
            bets.append({
                'combination': combination,
                'confidence': confidence
            })

        return bets

    def _recommend_2fuku(
        self,
        predictions: List[Dict],
        top_numbers: List[int]
    ) -> List[Dict]:
        """二連複の推奨買い目"""
        combination = '-'.join(map(str, sorted(top_numbers[:2])))
        confidence = predictions[0]['confidence']

        return [{
            'combination': combination,
            'confidence': confidence
        }]
