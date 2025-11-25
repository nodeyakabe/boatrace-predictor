"""
統計的平滑化機能
データ不足時の極端な値を避けるための平滑化手法
"""

import json
from pathlib import Path
from typing import Dict, Optional


class LaplaceSmoothing:
    """Laplace平滑化（加法平滑化）"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: 設定ファイルのパス
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / 'config' / 'prediction_improvements.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.enabled = config['laplace_smoothing']['enabled']
        self.alpha = config['laplace_smoothing']['alpha']

    def smooth_win_rate(self, wins: int, total_races: int, k: int = 2) -> float:
        """
        Laplace平滑化による勝率計算

        Args:
            wins: 勝利数
            total_races: 総レース数
            k: クラス数（通常は2: 勝ち/負け）

        Returns:
            平滑化された勝率（0.0-1.0）

        数式:
            smoothed_win_rate = (wins + alpha) / (total_races + alpha * k)

        効果:
            - データ少ない時: 極端な値（0%や100%）を避ける
            - データ十分時: 実績値にほぼ一致

        例:
            wins=0, total=2, alpha=2.0, k=2
            → (0 + 2) / (2 + 2*2) = 2/6 = 0.333 (33.3%)

            wins=12, total=100, alpha=2.0, k=2
            → (12 + 2) / (100 + 2*2) = 14/104 = 0.135 (13.5%)
        """
        if not self.enabled:
            # 平滑化無効の場合は通常の勝率
            if total_races == 0:
                return 0.0
            return wins / total_races

        if total_races == 0:
            # データがない場合は事前確率（1/k）を返す
            return 1.0 / k

        smoothed = (wins + self.alpha) / (total_races + self.alpha * k)
        return smoothed

    def smooth_course_stats(self, course_stats: Dict[int, Dict]) -> Dict[int, Dict]:
        """
        コース別統計にLaplace平滑化を適用

        Args:
            course_stats: {
                1: {'total_races': 500, 'win_rate': 0.55, ...},
                2: {'total_races': 480, 'win_rate': 0.15, ...},
                ...
            }

        Returns:
            平滑化されたコース別統計
        """
        if not self.enabled:
            return course_stats

        smoothed_stats = {}

        for course, stats in course_stats.items():
            total_races = stats['total_races']
            wins = int(stats['win_rate'] * total_races)

            smoothed_win_rate = self.smooth_win_rate(wins, total_races, k=2)

            smoothed_stats[course] = {
                'total_races': total_races,
                'win_rate': smoothed_win_rate,
                'place_rate_2': stats.get('place_rate_2', 0.0),
                'place_rate_3': stats.get('place_rate_3', 0.0),
                'smoothing_applied': True
            }

        return smoothed_stats

    def get_default_win_rates_smoothed(self) -> Dict[int, float]:
        """
        全国平均勝率にLaplace平滑化を適用

        Returns:
            {1: 0.55, 2: 0.14, 3: 0.12, 4: 0.10, 5: 0.06, 6: 0.03}
            ※ alpha=2.0の場合、若干調整される
        """
        # 実績ベースの全国平均（仮想的な1000レースとして）
        default_data = {
            1: {'wins': 550, 'total': 1000},
            2: {'wins': 140, 'total': 1000},
            3: {'wins': 120, 'total': 1000},
            4: {'wins': 100, 'total': 1000},
            5: {'wins': 60, 'total': 1000},
            6: {'wins': 30, 'total': 1000},
        }

        smoothed_rates = {}
        for course, data in default_data.items():
            smoothed_rates[course] = self.smooth_win_rate(
                data['wins'],
                data['total'],
                k=2
            )

        return smoothed_rates


class EmpiricalBayesSmoothing:
    """
    経験的ベイズ平滑化（今後実装）

    会場全体の勝率分布を事前分布として、
    個別コースの勝率を事後分布で推定する。
    """

    def __init__(self):
        pass

    def smooth_with_prior(self, wins: int, total_races: int,
                         prior_mean: float, prior_confidence: float) -> float:
        """
        事前分布を考慮したベイズ平滑化

        Args:
            wins: 勝利数
            total_races: 総レース数
            prior_mean: 事前平均（例: 会場全体の勝率）
            prior_confidence: 事前分布の信頼度（仮想サンプル数）

        Returns:
            平滑化された勝率

        TODO: 今後実装予定
        """
        # ベイズ推定: 事前分布と実測値の加重平均
        posterior_mean = (
            (prior_confidence * prior_mean + total_races * (wins / total_races if total_races > 0 else 0)) /
            (prior_confidence + total_races)
        )
        return posterior_mean
