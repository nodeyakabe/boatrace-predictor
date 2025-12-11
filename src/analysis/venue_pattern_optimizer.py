#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会場別パターン最適化

Phase 3 Task 3: 会場特性に応じたパターン倍率の最適化
- 会場ごとのパターン的中率を学習
- 効果的なパターンの優先順位調整
- 会場特性に応じた倍率補正
"""

import sqlite3
from typing import Dict, List, Optional
from collections import defaultdict
import logging


logger = logging.getLogger(__name__)


class VenuePatternOptimizer:
    """
    会場別パターン最適化クラス

    会場特性に応じてパターンの効果を調整
    """

    def __init__(self, db_path: str = 'data/boatrace.db'):
        """
        初期化

        Args:
            db_path: データベースファイルパス
        """
        self.db_path = db_path
        self.venue_pattern_stats = {}  # 会場別パターン統計
        self.venue_multipliers = {}  # 会場別倍率補正

        # 統計を読み込み
        self._load_venue_statistics()

    def _load_venue_statistics(self):
        """会場別パターン統計を読み込み"""
        # 実装例: 過去データからパターン的中率を計算
        # ここでは簡易版として固定値を設定

        # 会場別の特性（インコース有利度など）
        venue_characteristics = {
            # インコース超有利会場（イン有利度高）
            1: {'name': '桐生', 'in_advantage': 1.2, 'pattern_effectiveness': 1.1},
            2: {'name': '戸田', 'in_advantage': 1.25, 'pattern_effectiveness': 1.15},
            17: {'name': '宮島', 'in_advantage': 1.15, 'pattern_effectiveness': 1.05},

            # バランス会場（標準）
            3: {'name': '江戸川', 'in_advantage': 0.95, 'pattern_effectiveness': 0.95},
            4: {'name': '平和島', 'in_advantage': 1.0, 'pattern_effectiveness': 1.0},
            5: {'name': '多摩川', 'in_advantage': 1.05, 'pattern_effectiveness': 1.02},

            # センター・アウト有利会場（展示・STの重要性高）
            6: {'name': '浜名湖', 'in_advantage': 0.9, 'pattern_effectiveness': 1.15},
            7: {'name': '蒲郡', 'in_advantage': 0.85, 'pattern_effectiveness': 1.2},
            9: {'name': '津', 'in_advantage': 0.9, 'pattern_effectiveness': 1.1},
            20: {'name': '若松', 'in_advantage': 0.8, 'pattern_effectiveness': 1.25},

            # その他会場（デフォルト）
            'default': {'name': 'その他', 'in_advantage': 1.0, 'pattern_effectiveness': 1.0}
        }

        for venue_code, characteristics in venue_characteristics.items():
            if venue_code != 'default':
                self.venue_multipliers[venue_code] = characteristics['pattern_effectiveness']

        self.default_multiplier = venue_characteristics['default']['pattern_effectiveness']

        logger.info(f"会場別倍率補正を読み込み: {len(self.venue_multipliers)}会場")

    def get_venue_multiplier(self, venue_code: Optional[int]) -> float:
        """
        会場別の倍率補正を取得

        Args:
            venue_code: 会場コード

        Returns:
            倍率補正係数（1.0が標準、1.2なら20%増強）
        """
        if venue_code is None:
            return 1.0

        return self.venue_multipliers.get(venue_code, self.default_multiplier)

    def optimize_pattern_multiplier(
        self,
        base_multiplier: float,
        venue_code: Optional[int],
        pattern_name: str
    ) -> float:
        """
        パターン倍率を会場特性に応じて最適化

        Args:
            base_multiplier: 基本倍率
            venue_code: 会場コード
            pattern_name: パターン名

        Returns:
            最適化された倍率
        """
        venue_multiplier = self.get_venue_multiplier(venue_code)

        # 基本倍率 × 会場補正
        optimized = base_multiplier * venue_multiplier

        # 倍率の上限・下限を設定
        optimized = max(1.0, min(optimized, 1.5))  # 1.0～1.5の範囲

        logger.debug(
            f"パターン倍率最適化: {pattern_name} @ 会場{venue_code} | "
            f"基本{base_multiplier:.3f} × 会場補正{venue_multiplier:.2f} = {optimized:.3f}"
        )

        return optimized

    def get_venue_pattern_recommendations(self, venue_code: int) -> Dict:
        """
        会場別のパターン推奨事項を取得

        Args:
            venue_code: 会場コード

        Returns:
            推奨事項の辞書
        """
        venue_multiplier = self.get_venue_multiplier(venue_code)

        # 推奨事項を生成
        if venue_multiplier > 1.1:
            recommendation = {
                'type': 'high_effectiveness',
                'message': 'この会場ではBEFOREパターンが特に有効です',
                'confidence': 'high'
            }
        elif venue_multiplier < 0.95:
            recommendation = {
                'type': 'low_effectiveness',
                'message': 'この会場ではBEFOREパターンの効果が限定的です',
                'confidence': 'medium'
            }
        else:
            recommendation = {
                'type': 'normal',
                'message': '標準的なパターン効果が期待されます',
                'confidence': 'medium'
            }

        recommendation['multiplier'] = venue_multiplier

        return recommendation

    def analyze_venue_pattern_performance(
        self,
        venue_code: int,
        min_races: int = 20
    ) -> Optional[Dict]:
        """
        会場別のパターンパフォーマンスを分析

        Args:
            venue_code: 会場コード
            min_races: 最小レース数

        Returns:
            分析結果の辞書
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 会場の基本情報
            cursor.execute("""
                SELECT COUNT(DISTINCT id) as race_count
                FROM races
                WHERE venue_code = ?
                  AND race_date >= date('now', '-180 days')
            """, (venue_code,))

            result = cursor.fetchone()
            race_count = result[0] if result else 0

            if race_count < min_races:
                return None

            # パターンが適用されたレースの成績を分析
            # （簡易版: 実際には予測結果テーブルが必要）

            analysis = {
                'venue_code': venue_code,
                'race_count': race_count,
                'pattern_effectiveness': self.get_venue_multiplier(venue_code),
                'recommendation': self.get_venue_pattern_recommendations(venue_code)
            }

            return analysis

        finally:
            cursor.close()
            conn.close()


if __name__ == "__main__":
    # テスト実行
    optimizer = VenuePatternOptimizer()

    # 各会場の倍率補正を表示
    print("=" * 60)
    print("会場別パターン倍率補正")
    print("=" * 60)

    test_venues = [1, 2, 6, 7, 20, 4, 99]  # 桐生、戸田、浜名湖、蒲郡、若松、平和島、不明
    for venue_code in test_venues:
        multiplier = optimizer.get_venue_multiplier(venue_code)
        recommendation = optimizer.get_venue_pattern_recommendations(venue_code)

        print(f"会場{venue_code:2d}: 倍率補正 {multiplier:.2f}x | {recommendation['message']}")

    print()

    # パターン最適化の例
    print("=" * 60)
    print("パターン倍率最適化の例")
    print("=" * 60)

    base_multiplier = 1.286  # pre1_ex1 の例
    for venue_code in [2, 7, 4]:  # 戸田、蒲郡、平和島
        optimized = optimizer.optimize_pattern_multiplier(
            base_multiplier, venue_code, "pre1_ex1"
        )
        print(f"会場{venue_code}: {base_multiplier:.3f} → {optimized:.3f}")
