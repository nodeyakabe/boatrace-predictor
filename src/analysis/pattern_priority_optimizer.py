"""
BEFOREパターン優先度最適化モジュール

複数パターンが重複適用される場合の優先順位を最適化し、
最も効果的なパターンを選択する
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
import sqlite3


@dataclass
class PatternMatch:
    """パターンマッチ情報"""
    name: str
    description: str
    multiplier: float
    target_rank: int
    hit_rate: float = 0.0  # 実績的中率
    sample_count: int = 0  # 適用回数
    confidence_level: str = 'C'  # 信頼度レベル


class PatternPriorityOptimizer:
    """パターン優先度最適化クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.pattern_stats = {}  # パターン別統計情報のキャッシュ

    def select_best_pattern(
        self,
        matched_patterns: List[Dict],
        confidence_level: str = 'C',
        venue_code: int = None
    ) -> Optional[Dict]:
        """
        複数マッチしたパターンから最適なものを選択

        優先順位:
        1. 信頼度レベル別の最適パターン
        2. 的中率が高いパターン
        3. サンプル数が多いパターン（信頼性）
        4. multiplierが高いパターン

        Args:
            matched_patterns: マッチしたパターンのリスト
            confidence_level: 信頼度レベル（A/B/C/D/E）
            venue_code: 会場コード（会場別最適化用）

        Returns:
            最適なパターン、またはNone
        """
        if not matched_patterns:
            return None

        # 1パターンのみの場合はそのまま返す
        if len(matched_patterns) == 1:
            return matched_patterns[0]

        # パターン統計情報を取得
        pattern_matches = []
        for pattern in matched_patterns:
            stats = self._get_pattern_stats(
                pattern['name'],
                confidence_level,
                venue_code
            )
            pattern_matches.append(PatternMatch(
                name=pattern['name'],
                description=pattern['description'],
                multiplier=pattern['multiplier'],
                target_rank=pattern['target_rank'],
                hit_rate=stats.get('hit_rate', 0.0),
                sample_count=stats.get('sample_count', 0),
                confidence_level=confidence_level
            ))

        # 優先度スコアを計算してソート
        scored_patterns = [
            (pm, self._calculate_priority_score(pm, confidence_level))
            for pm in pattern_matches
        ]
        scored_patterns.sort(key=lambda x: x[1], reverse=True)

        # 最優先パターンを返す
        best_pattern_match = scored_patterns[0][0]

        # 元のパターン辞書形式で返す
        for pattern in matched_patterns:
            if pattern['name'] == best_pattern_match.name:
                return pattern

        return matched_patterns[0]  # フォールバック

    def _calculate_priority_score(
        self,
        pattern: PatternMatch,
        confidence_level: str
    ) -> float:
        """
        パターンの優先度スコアを計算

        Args:
            pattern: パターンマッチ情報
            confidence_level: 信頼度レベル

        Returns:
            優先度スコア（高いほど優先）
        """
        score = 0.0

        # 1. 的中率（最重要）: 0-100点
        score += pattern.hit_rate * 100

        # 2. サンプル数による信頼性補正: 0-20点
        if pattern.sample_count >= 100:
            sample_score = 20.0
        elif pattern.sample_count >= 50:
            sample_score = 15.0
        elif pattern.sample_count >= 20:
            sample_score = 10.0
        elif pattern.sample_count >= 10:
            sample_score = 5.0
        else:
            sample_score = 0.0
        score += sample_score

        # 3. Multiplier（補助的）: 0-10点
        # 1.0-1.5の範囲を0-10点にマッピング
        multiplier_score = (pattern.multiplier - 1.0) * 20
        multiplier_score = min(max(multiplier_score, 0), 10)
        score += multiplier_score

        # 4. 信頼度別補正: -10 ~ +10点
        confidence_bonus = {
            'A': 10.0,  # 高信頼度レースではより慎重に
            'B': 5.0,
            'C': 0.0,
            'D': -5.0,  # 低信頼度レースでは攻める
            'E': -10.0
        }
        score += confidence_bonus.get(confidence_level, 0.0)

        return score

    def _get_pattern_stats(
        self,
        pattern_name: str,
        confidence_level: str = None,
        venue_code: int = None
    ) -> Dict:
        """
        パターン統計情報を取得

        Args:
            pattern_name: パターン名
            confidence_level: 信頼度レベル（指定時は信頼度別統計）
            venue_code: 会場コード（指定時は会場別統計）

        Returns:
            統計情報 {'hit_rate': float, 'sample_count': int}
        """
        # キャッシュキー作成
        cache_key = f"{pattern_name}_{confidence_level}_{venue_code}"

        if cache_key in self.pattern_stats:
            return self.pattern_stats[cache_key]

        # デフォルト値
        default_stats = {'hit_rate': 0.5, 'sample_count': 0}

        # TODO: 実際の統計情報をDBから取得
        # 現時点ではバックテスト結果からハードコードした値を使用

        # パターン別実績値（バックテストより）
        known_patterns = {
            'pre1_ex1': {'hit_rate': 0.625, 'sample_count': 24},
            'pre1_ex1_3_st1_3': {'hit_rate': 0.491, 'sample_count': 53},
            'ex1_3_st1_3': {'hit_rate': 0.481, 'sample_count': 54},
            'pre1_4_ex1_2': {'hit_rate': 0.481, 'sample_count': 52},
            'pre1_3_ex1_3': {'hit_rate': 0.466, 'sample_count': 73},
            'pre1_3_st1_3': {'hit_rate': 0.474, 'sample_count': 76},
            'pre1_st1_3': {'hit_rate': 0.473, 'sample_count': 74},
            'ex_rank_1_2': {'hit_rate': 0.481, 'sample_count': 52},
            'pre1_st1': {'hit_rate': 0.457, 'sample_count': 35},
        }

        stats = known_patterns.get(pattern_name, default_stats)

        # キャッシュに保存
        self.pattern_stats[cache_key] = stats

        return stats

    def get_pattern_priority_list(
        self,
        patterns: List[Dict],
        confidence_level: str = 'C'
    ) -> List[Dict]:
        """
        パターンリストを優先度順にソート

        Args:
            patterns: パターンリスト
            confidence_level: 信頼度レベル

        Returns:
            優先度順にソートされたパターンリスト
        """
        if not patterns:
            return []

        pattern_matches = []
        for pattern in patterns:
            stats = self._get_pattern_stats(pattern['name'], confidence_level)
            pattern_matches.append((
                pattern,
                PatternMatch(
                    name=pattern['name'],
                    description=pattern['description'],
                    multiplier=pattern['multiplier'],
                    target_rank=pattern.get('target_rank', 1),
                    hit_rate=stats.get('hit_rate', 0.0),
                    sample_count=stats.get('sample_count', 0),
                    confidence_level=confidence_level
                )
            ))

        # 優先度スコアでソート
        scored = [
            (p, pm, self._calculate_priority_score(pm, confidence_level))
            for p, pm in pattern_matches
        ]
        scored.sort(key=lambda x: x[2], reverse=True)

        return [p for p, pm, score in scored]

    def get_pattern_combination_bonus(
        self,
        matched_patterns: List[Dict]
    ) -> float:
        """
        パターン組み合わせボーナスを計算

        特定のパターン組み合わせで相乗効果がある場合にボーナス係数を追加

        Args:
            matched_patterns: マッチしたパターンリスト

        Returns:
            組み合わせボーナス係数（1.0 = ボーナスなし）
        """
        if len(matched_patterns) < 2:
            return 1.0

        pattern_names = set(p['name'] for p in matched_patterns)

        # 相乗効果のある組み合わせ
        synergy_combinations = {
            # PRE1位 × 展示1位 × ST1-3位 = 最強パターン
            frozenset(['pre1_ex1', 'pre1_st1_3']): 1.05,

            # PRE1-3位 × 展示1-3位 × ST1-3位 = 安定パターン
            frozenset(['pre1_3_ex1_3', 'pre1_3_st1_3', 'ex1_3_st1_3']): 1.03,

            # 展示・ST両方好調
            frozenset(['ex1_3_st1_3', 'pre1_4_ex1_2']): 1.02,
        }

        # 最大ボーナスを返す
        max_bonus = 1.0
        for combo, bonus in synergy_combinations.items():
            if combo.issubset(pattern_names):
                max_bonus = max(max_bonus, bonus)

        return max_bonus
