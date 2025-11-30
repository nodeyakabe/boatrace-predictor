"""
TOP N セレクター
Phase 6: 三連単上位抽出と買い目最適化
"""
import numpy as np
from typing import Dict, List, Tuple, Optional


class TopNSelector:
    """
    TOP N セレクタークラス

    三連単確率から最適な買い目を選択
    """

    def __init__(self, default_top_n: int = 10):
        self.default_top_n = default_top_n

    def select_top_n(self, trifecta_probs: Dict[str, float],
                     top_n: int = None) -> List[Tuple[str, float]]:
        """
        確率上位N件を選択

        Args:
            trifecta_probs: 三連単確率
            top_n: 選択件数

        Returns:
            [(組み合わせ, 確率), ...]
        """
        if top_n is None:
            top_n = self.default_top_n

        sorted_probs = sorted(trifecta_probs.items(), key=lambda x: x[1], reverse=True)
        return sorted_probs[:top_n]

    def select_by_threshold(self, trifecta_probs: Dict[str, float],
                            min_prob: float = 0.01) -> List[Tuple[str, float]]:
        """
        確率閾値以上を選択

        Args:
            trifecta_probs: 三連単確率
            min_prob: 最小確率

        Returns:
            [(組み合わせ, 確率), ...]
        """
        filtered = [(combo, prob) for combo, prob in trifecta_probs.items() if prob >= min_prob]
        return sorted(filtered, key=lambda x: x[1], reverse=True)

    def select_by_ev(self, trifecta_probs: Dict[str, float],
                     odds: Dict[str, float],
                     min_ev: float = 0.0,
                     top_n: int = None) -> List[Dict]:
        """
        期待値ベースで選択

        Args:
            trifecta_probs: 三連単確率
            odds: オッズ
            min_ev: 最小期待値
            top_n: 最大選択件数

        Returns:
            [{combination, prob, odds, ev}, ...]
        """
        if top_n is None:
            top_n = self.default_top_n

        ev_list = []
        for combo, prob in trifecta_probs.items():
            if combo in odds:
                odd = odds[combo]
                ev = prob * odd - 1
                if ev >= min_ev:
                    ev_list.append({
                        'combination': combo,
                        'probability': prob,
                        'odds': odd,
                        'expected_value': ev,
                    })

        # EVでソート
        ev_list.sort(key=lambda x: x['expected_value'], reverse=True)

        return ev_list[:top_n]

    def select_coverage(self, trifecta_probs: Dict[str, float],
                        target_coverage: float = 0.6) -> List[Tuple[str, float]]:
        """
        目標カバレッジまで選択

        Args:
            trifecta_probs: 三連単確率
            target_coverage: 目標カバレッジ（累積確率）

        Returns:
            [(組み合わせ, 確率), ...]
        """
        sorted_probs = sorted(trifecta_probs.items(), key=lambda x: x[1], reverse=True)

        selected = []
        cumulative = 0.0

        for combo, prob in sorted_probs:
            if cumulative >= target_coverage:
                break
            selected.append((combo, prob))
            cumulative += prob

        return selected

    def select_dynamic(self, trifecta_probs: Dict[str, float],
                       confidence_level: float) -> List[Tuple[str, float]]:
        """
        信頼度に応じて動的に選択件数を決定

        Args:
            trifecta_probs: 三連単確率
            confidence_level: 予測信頼度（0-1）

        Returns:
            [(組み合わせ, 確率), ...]
        """
        # 信頼度が高いほど絞る
        if confidence_level >= 0.8:
            top_n = 3
        elif confidence_level >= 0.6:
            top_n = 5
        elif confidence_level >= 0.4:
            top_n = 7
        else:
            top_n = 10

        return self.select_top_n(trifecta_probs, top_n)

    def calculate_bet_amounts(self, selected: List[Dict],
                               budget: float,
                               method: str = 'kelly') -> List[Dict]:
        """
        買い目に応じたベット額を計算

        Args:
            selected: 選択された買い目リスト
            budget: 予算
            method: 配分方法（'equal', 'proportional', 'kelly'）

        Returns:
            ベット額が追加された買い目リスト
        """
        if not selected:
            return []

        result = []

        if method == 'equal':
            # 均等配分
            amount = budget / len(selected)
            for bet in selected:
                bet_copy = bet.copy()
                bet_copy['amount'] = round(amount / 100) * 100
                result.append(bet_copy)

        elif method == 'proportional':
            # 確率比例配分
            total_prob = sum(bet.get('probability', 0) for bet in selected)
            for bet in selected:
                prob = bet.get('probability', 0)
                amount = budget * (prob / total_prob) if total_prob > 0 else budget / len(selected)
                bet_copy = bet.copy()
                bet_copy['amount'] = round(amount / 100) * 100
                result.append(bet_copy)

        elif method == 'kelly':
            # ケリー基準
            for bet in selected:
                prob = bet.get('probability', 0)
                odds = bet.get('odds', 0)
                ev = bet.get('expected_value', 0)

                if ev > 0 and odds > 1:
                    # Kelly: f* = (p * b - q) / b
                    b = odds - 1
                    q = 1 - prob
                    kelly_fraction = max(0, (prob * b - q) / b)
                    # 控えめに1/4 Kellyを使用
                    fraction = kelly_fraction / 4
                    amount = budget * fraction
                else:
                    amount = 0

                bet_copy = bet.copy()
                bet_copy['amount'] = round(amount / 100) * 100
                result.append(bet_copy)

        return result

    def optimize_portfolio(self, trifecta_probs: Dict[str, float],
                           odds: Dict[str, float],
                           budget: float,
                           min_bet: float = 100,
                           max_bets: int = 10) -> Dict:
        """
        ポートフォリオ最適化

        Args:
            trifecta_probs: 三連単確率
            odds: オッズ
            budget: 予算
            min_bet: 最小ベット額
            max_bets: 最大買い目数

        Returns:
            最適化されたポートフォリオ
        """
        # 期待値でフィルタ
        ev_bets = self.select_by_ev(trifecta_probs, odds, min_ev=0.05, top_n=max_bets * 2)

        if not ev_bets:
            # 期待値プラスがない場合は確率上位
            top_combos = self.select_top_n(trifecta_probs, max_bets)
            ev_bets = [
                {
                    'combination': combo,
                    'probability': prob,
                    'odds': odds.get(combo, 0),
                    'expected_value': prob * odds.get(combo, 0) - 1 if combo in odds else 0,
                }
                for combo, prob in top_combos
            ]

        # ケリー基準でベット額計算
        bets_with_amounts = self.calculate_bet_amounts(ev_bets, budget, 'kelly')

        # 最小ベット額でフィルタ
        valid_bets = [bet for bet in bets_with_amounts if bet['amount'] >= min_bet][:max_bets]

        # 総ベット額を調整
        total_bet = sum(bet['amount'] for bet in valid_bets)
        if total_bet > budget:
            # 予算オーバーの場合はスケールダウン
            scale = budget / total_bet
            for bet in valid_bets:
                bet['amount'] = round(bet['amount'] * scale / 100) * 100

        # 期待リターンを計算
        expected_return = sum(
            bet['probability'] * bet['odds'] * bet['amount']
            for bet in valid_bets
        )
        total_bet = sum(bet['amount'] for bet in valid_bets)

        return {
            'bets': valid_bets,
            'total_bet': total_bet,
            'expected_return': expected_return,
            'expected_roi': (expected_return - total_bet) / total_bet if total_bet > 0 else 0,
            'n_bets': len(valid_bets),
        }
