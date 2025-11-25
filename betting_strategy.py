"""
賭け戦略システム

実験#019のオッズ期待値分析結果を基に、実戦的な賭け推奨を行う。
- 3つの戦略: 保守的、バランス、穴狙い
- 期待値計算
- リスク管理
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from enum import Enum


class BettingStrategy(Enum):
    """賭け戦略の種類"""
    CONSERVATIVE = "conservative"  # 保守的
    BALANCED = "balanced"          # バランス
    VALUE = "value"                # 穴狙い


class BettingRecommender:
    """賭け推奨システム"""

    # 戦略別パラメータ（実験#019の結果）
    STRATEGY_PARAMS = {
        BettingStrategy.CONSERVATIVE: {
            'min_probability': 0.8,
            'min_expected_value': 0.0,
            'name': '保守的戦略',
            'description': '高確率・低リスク',
            'expected_hit_rate': 0.8571,
            'expected_roi': 0.4710,
            'avg_races_per_month': 42
        },
        BettingStrategy.BALANCED: {
            'min_probability': 0.0,
            'min_expected_value': 0.10,
            'name': 'バランス戦略',
            'description': '中確率・中リスク・最大期待利益',
            'expected_hit_rate': 0.2502,
            'expected_roi': 0.4535,
            'avg_races_per_month': 2350
        },
        BettingStrategy.VALUE: {
            'min_probability': 0.3,
            'min_expected_value': 0.20,
            'name': '穴狙い戦略',
            'description': '中確率・高期待値',
            'expected_hit_rate': 0.6046,
            'expected_roi': 0.4663,
            'avg_races_per_month': 521
        }
    }

    # ケリー基準係数（推奨: 0.25-0.5）
    KELLY_FRACTION = 0.25

    def __init__(self, bankroll: float = 100000):
        """
        初期化

        Args:
            bankroll: 総資金（円）
        """
        self.bankroll = bankroll
        self.bet_history: List[Dict] = []

    def calculate_expected_value(
        self,
        win_probability: float,
        odds: float
    ) -> float:
        """
        期待値を計算

        Args:
            win_probability: 勝利確率（0-1）
            odds: オッズ（倍率）

        Returns:
            期待値（-1 〜 ∞）
            正の値: 期待利益あり
            負の値: 期待損失あり
        """
        return win_probability * odds - 1.0

    def should_bet(
        self,
        win_probability: float,
        odds: float,
        strategy: BettingStrategy = BettingStrategy.BALANCED
    ) -> bool:
        """
        賭けるべきかを判定

        Args:
            win_probability: 勝利確率
            odds: オッズ
            strategy: 使用する戦略

        Returns:
            True: 賭け推奨、False: 見送り
        """
        params = self.STRATEGY_PARAMS[strategy]
        ev = self.calculate_expected_value(win_probability, odds)

        # 戦略ごとの条件チェック
        if strategy == BettingStrategy.CONSERVATIVE:
            return win_probability >= params['min_probability'] and ev > params['min_expected_value']
        elif strategy == BettingStrategy.BALANCED:
            return ev >= params['min_expected_value']
        elif strategy == BettingStrategy.VALUE:
            return win_probability >= params['min_probability'] and ev >= params['min_expected_value']

        return False

    def calculate_kelly_bet(
        self,
        win_probability: float,
        odds: float,
        fraction: Optional[float] = None
    ) -> float:
        """
        ケリー基準に基づく推奨賭け金を計算

        Args:
            win_probability: 勝利確率
            odds: オッズ
            fraction: ケリー係数（デフォルト: 0.25）

        Returns:
            推奨賭け金（円）
        """
        if fraction is None:
            fraction = self.KELLY_FRACTION

        # ケリー基準: f = (bp - q) / b
        # b: オッズ - 1
        # p: 勝利確率
        # q: 敗北確率 = 1 - p
        b = odds - 1
        p = win_probability
        q = 1 - p

        if b <= 0:
            return 0.0

        kelly = (b * p - q) / b

        # 負の値の場合は賭けない
        if kelly <= 0:
            return 0.0

        # フラクショナルケリー
        recommended_fraction = kelly * fraction

        # 推奨賭け金（総資金の何%）
        bet_amount = self.bankroll * recommended_fraction

        # 最大5%制限
        max_bet = self.bankroll * 0.05
        bet_amount = min(bet_amount, max_bet)

        return bet_amount

    def get_recommendation(
        self,
        win_probability: float,
        odds: float,
        pit_number: int,
        race_info: Optional[Dict] = None
    ) -> Dict:
        """
        包括的な賭け推奨を取得

        Args:
            win_probability: 勝利確率
            odds: オッズ
            pit_number: 艇番
            race_info: レース情報（オプション）

        Returns:
            推奨情報辞書
        """
        ev = self.calculate_expected_value(win_probability, odds)
        kelly_bet = self.calculate_kelly_bet(win_probability, odds)

        # 各戦略での判定
        recommendations = {}
        for strategy in BettingStrategy:
            should_bet = self.should_bet(win_probability, odds, strategy)
            params = self.STRATEGY_PARAMS[strategy]

            recommendations[strategy.value] = {
                'should_bet': should_bet,
                'strategy_name': params['name'],
                'expected_hit_rate': params['expected_hit_rate'],
                'expected_roi': params['expected_roi']
            }

        # 総合推奨
        any_recommendation = any(r['should_bet'] for r in recommendations.values())

        result = {
            'pit_number': pit_number,
            'win_probability': win_probability,
            'odds': odds,
            'expected_value': ev,
            'expected_value_pct': ev * 100,
            'kelly_bet_amount': kelly_bet,
            'kelly_fraction': self.KELLY_FRACTION,
            'max_bet_limit': self.bankroll * 0.05,
            'recommendations': recommendations,
            'overall_recommendation': 'ベット推奨' if any_recommendation else '見送り',
            'confidence_level': self._get_confidence_level(win_probability, ev)
        }

        if race_info:
            result['race_info'] = race_info

        return result

    def _get_confidence_level(self, win_probability: float, ev: float) -> str:
        """
        信頼度レベルを取得

        Args:
            win_probability: 勝利確率
            ev: 期待値

        Returns:
            信頼度レベル（文字列）
        """
        if win_probability >= 0.8 and ev > 0.2:
            return '★★★ 非常に高い'
        elif win_probability >= 0.7 and ev > 0.1:
            return '★★ 高い'
        elif win_probability >= 0.5 and ev > 0:
            return '★ 中程度'
        elif ev > 0:
            return '低い'
        else:
            return '推奨なし'

    def analyze_race(
        self,
        probabilities: np.ndarray,
        odds_list: np.ndarray,
        race_info: Optional[Dict] = None
    ) -> pd.DataFrame:
        """
        レース全体を分析

        Args:
            probabilities: 各艇の勝利確率（6要素）
            odds_list: 各艇のオッズ（6要素）
            race_info: レース情報

        Returns:
            分析結果DataFrame
        """
        results = []

        for pit in range(1, 7):
            idx = pit - 1
            prob = probabilities[idx]
            odds = odds_list[idx]

            rec = self.get_recommendation(prob, odds, pit, race_info)

            results.append({
                '艇番': pit,
                '勝利確率': f"{prob:.1%}",
                'オッズ': f"{odds:.2f}",
                '期待値': f"{rec['expected_value_pct']:+.1f}%",
                '保守的': '✅' if rec['recommendations']['conservative']['should_bet'] else '❌',
                'バランス': '✅' if rec['recommendations']['balanced']['should_bet'] else '❌',
                '穴狙い': '✅' if rec['recommendations']['value']['should_bet'] else '❌',
                'ケリー推奨額': f"{rec['kelly_bet_amount']:.0f}円",
                '信頼度': rec['confidence_level']
            })

        return pd.DataFrame(results)

    def print_strategy_info(self):
        """戦略情報を表示"""
        print("=" * 80)
        print("賭け戦略システム - 戦略情報")
        print("=" * 80)

        for strategy, params in self.STRATEGY_PARAMS.items():
            print(f"\n【{params['name']}】")
            print(f"  説明: {params['description']}")
            print(f"  条件:")
            if params['min_probability'] > 0:
                print(f"    - 最低勝利確率: {params['min_probability']:.0%}")
            if params['min_expected_value'] > 0:
                print(f"    - 最低期待値: {params['min_expected_value']:+.0%}")
            print(f"  期待性能:")
            print(f"    - 的中率: {params['expected_hit_rate']:.2%}")
            print(f"    - ROI: {params['expected_roi']:.2%}")
            print(f"    - 月間対象レース: 約{params['avg_races_per_month']}レース")

        print(f"\n資金管理:")
        print(f"  - 総資金: {self.bankroll:,}円")
        print(f"  - ケリー係数: {self.KELLY_FRACTION}")
        print(f"  - 最大賭け金制限: {self.bankroll * 0.05:,.0f}円（総資金の5%）")
        print("=" * 80)


def demo_usage():
    """使用例デモ"""
    print("=" * 80)
    print("賭け戦略システム - 使用例")
    print("=" * 80)

    # 初期化（総資金10万円）
    recommender = BettingRecommender(bankroll=100000)

    # 戦略情報表示
    recommender.print_strategy_info()

    # サンプルレース分析
    print("\n" + "=" * 80)
    print("【サンプルレース分析】")
    print("=" * 80)

    # ダミーデータ
    probabilities = np.array([0.85, 0.45, 0.25, 0.15, 0.10, 0.05])
    odds_list = np.array([1.5, 3.2, 5.8, 12.5, 18.0, 35.0])

    race_info = {
        'race_id': '20240601-07-12',
        'venue': '07',
        'race_number': 12
    }

    # レース全体分析
    analysis_df = recommender.analyze_race(probabilities, odds_list, race_info)
    print("\nレース分析結果:")
    print(analysis_df.to_string(index=False))

    # 個別推奨例
    print("\n" + "=" * 80)
    print("【1号艇の詳細推奨】")
    print("=" * 80)

    rec = recommender.get_recommendation(
        win_probability=0.85,
        odds=1.5,
        pit_number=1,
        race_info=race_info
    )

    print(f"\n艇番: {rec['pit_number']}")
    print(f"勝利確率: {rec['win_probability']:.1%}")
    print(f"オッズ: {rec['odds']:.2f}")
    print(f"期待値: {rec['expected_value_pct']:+.1f}%")
    print(f"ケリー推奨賭け金: {rec['kelly_bet_amount']:.0f}円")
    print(f"信頼度: {rec['confidence_level']}")
    print(f"総合推奨: {rec['overall_recommendation']}")

    print("\n戦略別推奨:")
    for strategy_name, strategy_rec in rec['recommendations'].items():
        status = '✅ 推奨' if strategy_rec['should_bet'] else '❌ 見送り'
        print(f"  {strategy_rec['strategy_name']}: {status}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    demo_usage()
