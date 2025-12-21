"""
3着専用スコアラー

P-3タスク Phase 2: 決まり手別の3着有利パターンを活用した3着予測

設計コンセプト:
- 1着・2着が確定したとして、残り4艇から誰が3着かを予測
- 決まり手別の3着有利コースパターンを適用
- 追走有利度（コース位置関係）を計算
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# 決まり手別の3着有利パターン（事前定義）
KIMARITE_THIRD_ADVANTAGE = {
    '逃げ': {
        'advantage_courses': [4, 5],     # 4,5コースが追走有利
        'neutral_courses': [2, 3],       # 2,3コースは2着争い後
        'disadvantage_courses': [6],     # 6コースは不利
        'base_boost': 1.2,
    },
    'まくり': {
        'advantage_courses': [5, 6],     # 外追走有利
        'neutral_courses': [4],
        'disadvantage_courses': [1, 2, 3],  # 内は沈む
        'base_boost': 1.3,
    },
    'まくり差し': {
        'advantage_courses': [4, 5],     # 展開次第で浮上
        'neutral_courses': [3, 6],
        'disadvantage_courses': [1, 2],
        'base_boost': 1.2,
    },
    '差し': {
        'advantage_courses': [1, 3],     # 1コース粘り、3コース追走
        'neutral_courses': [4],
        'disadvantage_courses': [5, 6],
        'base_boost': 1.15,
    },
    '抜き': {
        'advantage_courses': [1, 2, 3],  # 内コース残り有利
        'neutral_courses': [4],
        'disadvantage_courses': [5, 6],
        'base_boost': 1.1,
    },
    '恵まれ': {
        'advantage_courses': [2, 3, 4],  # 展開荒れ時は中間コース
        'neutral_courses': [5],
        'disadvantage_courses': [6],
        'base_boost': 1.0,
    },
}


class ThirdPlaceSpecializedScorer:
    """3着専用スコアラー"""

    def __init__(self, flow_stats_path: Optional[str] = None):
        """
        初期化

        Args:
            flow_stats_path: 決まり手別統計ファイルのパス
                           Noneの場合はデフォルトパスを使用
        """
        if flow_stats_path is None:
            flow_stats_path = Path(__file__).parent.parent.parent / "data" / "kimarite_flow_stats.json"

        self.flow_stats = self._load_flow_stats(flow_stats_path)
        self.use_stats = self.flow_stats is not None

    def _load_flow_stats(self, path: str) -> Optional[Dict]:
        """統計ファイルを読み込む"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                stats = json.load(f)
            # キーを整数に変換
            converted = {}
            for winner_course, kimarite_data in stats.items():
                converted[int(winner_course)] = kimarite_data
            logger.info(f"決まり手統計を読み込みました: {path}")
            return converted
        except Exception as e:
            logger.warning(f"統計ファイル読み込み失敗: {e}")
            return None

    def calculate_third_scores(
        self,
        winner_course: int,
        winner_kimarite: str,
        second_course: int,
        remaining_courses: List[int],
        base_scores: Optional[Dict[int, float]] = None
    ) -> Dict[int, float]:
        """
        3着スコアを計算

        Args:
            winner_course: 1着予測コース (1-6)
            winner_kimarite: 1着の決まり手
            second_course: 2着予測コース (1-6)
            remaining_courses: 残り4艇のコース番号リスト
            base_scores: 各コースの基本スコア（オプション）

        Returns:
            各コースの3着確率スコア（合計1.0に正規化）
        """
        scores = {}

        for course in remaining_courses:
            # 1. 基本スコア
            base = base_scores.get(course, 1.0) if base_scores else 1.0

            # 2. 決まり手パターンによるブースト
            kimarite_boost = self._get_kimarite_boost(course, winner_kimarite)

            # 3. 統計データによる確率
            stats_prob = self._get_stats_probability(
                winner_course, winner_kimarite, second_course, course
            )

            # 4. 追走有利度
            chase_advantage = self._calculate_chase_advantage(
                course, winner_course, second_course, winner_kimarite
            )

            # 総合スコア計算
            # 統計データがある場合は重視、なければルールベース
            if self.use_stats and stats_prob > 0:
                score = base * (stats_prob * 2 + kimarite_boost * 0.5 + chase_advantage * 0.5)
            else:
                score = base * kimarite_boost * chase_advantage

            scores[course] = score

        # 正規化（合計1.0）
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        return scores

    def _get_kimarite_boost(self, course: int, kimarite: str) -> float:
        """決まり手パターンによるブースト係数を取得"""
        pattern = KIMARITE_THIRD_ADVANTAGE.get(kimarite, {})

        if course in pattern.get('advantage_courses', []):
            return pattern.get('base_boost', 1.2)
        elif course in pattern.get('disadvantage_courses', []):
            return 0.7
        else:
            return 1.0

    def _get_stats_probability(
        self,
        winner_course: int,
        kimarite: str,
        second_course: int,
        candidate_course: int
    ) -> float:
        """統計データから3着確率を取得"""
        if not self.use_stats:
            return 0.0

        try:
            kimarite_data = self.flow_stats.get(winner_course, {}).get(kimarite, {})
            third_prob = kimarite_data.get('third_course_prob', {})
            return third_prob.get(str(candidate_course), 0.0)
        except Exception:
            return 0.0

    def _calculate_chase_advantage(
        self,
        candidate_course: int,
        winner_course: int,
        second_course: int,
        kimarite: str
    ) -> float:
        """
        追走有利度を計算

        考え方:
        - 1着・2着の間にいる艇は進路が塞がれやすい
        - 1着・2着の外側にいる艇は追走しやすい
        - ただし決まり手によってパターンが異なる
        """
        advantage = 1.0

        # 1着・2着の間にいるか
        min_course = min(winner_course, second_course)
        max_course = max(winner_course, second_course)
        is_between = min_course < candidate_course < max_course

        # 最外コースにいるか
        is_outermost = candidate_course > max_course

        # 間にいる場合のペナルティ（差し・抜き以外）
        if is_between and kimarite not in ['差し', '抜き']:
            advantage *= 0.85

        # 最外追走ボーナス（まくり系のみ）
        if is_outermost and kimarite in ['まくり', 'まくり差し']:
            advantage *= 1.15

        # イン残しボーナス（差し・抜きで1コース候補の場合）
        if candidate_course == 1 and kimarite in ['差し', '抜き'] and winner_course > 1:
            advantage *= 1.2

        return advantage

    def get_third_candidates(
        self,
        winner_course: int,
        winner_kimarite: str,
        second_course: int,
        base_scores: Optional[Dict[int, float]] = None,
        top_n: int = 2
    ) -> List[Tuple[int, float]]:
        """
        3着候補を確率順で取得

        Args:
            winner_course: 1着予測コース
            winner_kimarite: 1着の決まり手
            second_course: 2着予測コース
            base_scores: 各コースの基本スコア
            top_n: 上位何件を返すか

        Returns:
            [(コース番号, 確率), ...] のリスト
        """
        # 残りコースを特定
        remaining = [c for c in range(1, 7) if c not in [winner_course, second_course]]

        # スコア計算
        scores = self.calculate_third_scores(
            winner_course, winner_kimarite, second_course, remaining, base_scores
        )

        # ソートして上位を返す
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_n]

    def predict_flow(
        self,
        winner_course: int,
        winner_kimarite: str,
        base_scores: Optional[Dict[int, float]] = None
    ) -> Dict[str, any]:
        """
        展開予測（2着・3着の候補を予測）

        Args:
            winner_course: 1着予測コース
            winner_kimarite: 1着の決まり手
            base_scores: 各コースの基本スコア

        Returns:
            {
                'winner': {'course': int, 'kimarite': str},
                'second_candidates': [(course, prob), ...],
                'third_candidates_by_second': {
                    second_course: [(third_course, prob), ...],
                    ...
                }
            }
        """
        result = {
            'winner': {'course': winner_course, 'kimarite': winner_kimarite},
            'second_candidates': [],
            'third_candidates_by_second': {}
        }

        # 統計データから2着候補を取得
        if self.use_stats:
            kimarite_data = self.flow_stats.get(winner_course, {}).get(winner_kimarite, {})
            second_prob = kimarite_data.get('second_course_prob', {})
            sorted_second = sorted(second_prob.items(), key=lambda x: x[1], reverse=True)[:3]
            result['second_candidates'] = [(int(c), p) for c, p in sorted_second]

            # 各2着候補に対して3着候補を計算
            for second_course, _ in result['second_candidates']:
                third_candidates = self.get_third_candidates(
                    winner_course, winner_kimarite, second_course, base_scores, top_n=3
                )
                result['third_candidates_by_second'][second_course] = third_candidates

        return result


def test_scorer():
    """スコアラーのテスト"""
    scorer = ThirdPlaceSpecializedScorer()

    print("=" * 60)
    print("3着専用スコアラー テスト")
    print("=" * 60)

    # テストケース1: 1コース逃げ
    print("\n【テスト1: 1コース逃げ、2着=2コース】")
    scores = scorer.calculate_third_scores(
        winner_course=1,
        winner_kimarite='逃げ',
        second_course=2,
        remaining_courses=[3, 4, 5, 6]
    )
    for course, prob in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        print(f"  {course}コース: {prob:.3f}")

    # テストケース2: 3コースまくり
    print("\n【テスト2: 3コースまくり、2着=4コース】")
    scores = scorer.calculate_third_scores(
        winner_course=3,
        winner_kimarite='まくり',
        second_course=4,
        remaining_courses=[1, 2, 5, 6]
    )
    for course, prob in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        print(f"  {course}コース: {prob:.3f}")

    # テストケース3: 2コース差し
    print("\n【テスト3: 2コース差し、2着=1コース】")
    scores = scorer.calculate_third_scores(
        winner_course=2,
        winner_kimarite='差し',
        second_course=1,
        remaining_courses=[3, 4, 5, 6]
    )
    for course, prob in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        print(f"  {course}コース: {prob:.3f}")

    # 展開予測テスト
    print("\n【テスト4: 展開予測（4コースまくり）】")
    flow = scorer.predict_flow(
        winner_course=4,
        winner_kimarite='まくり'
    )
    print(f"  1着: {flow['winner']}")
    print(f"  2着候補: {flow['second_candidates']}")
    for second, thirds in flow['third_candidates_by_second'].items():
        print(f"  2着={second}コースの場合の3着候補: {thirds}")


if __name__ == "__main__":
    test_scorer()
