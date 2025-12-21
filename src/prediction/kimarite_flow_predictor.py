"""
決まり手別展開予測エンジン

P-3タスク Phase 3: 決まり手から2着・3着の展開を予測
P-6-2タスク: まくり系対策（まくりリスク評価統合）

設計:
- 1着の決まり手確率から展開シナリオを生成
- 各シナリオの2着・3着候補を出力
- 3着専用スコアラーと連携
- まくりリスク評価による分岐ロジック（P-6-2）
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ml.third_place_specialized_model import ThirdPlaceSpecializedScorer
from src.prediction.makuri_risk_evaluator import MakuriRiskEvaluator, MakuriRiskAssessment
from config.feature_flags import is_feature_enabled

logger = logging.getLogger(__name__)


@dataclass
class RaceScenario:
    """レース展開シナリオ"""
    winner_course: int
    winner_kimarite: str
    probability: float
    second_candidates: List[Tuple[int, float]]  # [(コース, 確率), ...]
    third_candidates: List[Tuple[int, float]]   # [(コース, 確率), ...]


class KimariteFlowPredictor:
    """決まり手別展開予測エンジン"""

    # 主要決まり手とコース別の基本確率
    KIMARITE_BASE_PROB = {
        1: {'逃げ': 0.55, '差し': 0.02, 'まくり': 0.01, '抜き': 0.03, '恵まれ': 0.01},
        2: {'差し': 0.15, 'まくり差し': 0.05, 'まくり': 0.02, '抜き': 0.01, '恵まれ': 0.01},
        3: {'まくり': 0.08, 'まくり差し': 0.06, '差し': 0.04, '抜き': 0.01, '恵まれ': 0.01},
        4: {'まくり': 0.06, 'まくり差し': 0.08, '差し': 0.03, '抜き': 0.01, '恵まれ': 0.01},
        5: {'まくり': 0.03, 'まくり差し': 0.04, '差し': 0.01, '抜き': 0.01, '恵まれ': 0.01},
        6: {'まくり': 0.02, 'まくり差し': 0.02, '差し': 0.01, '抜き': 0.01, '恵まれ': 0.01},
    }

    def __init__(self, flow_stats_path: Optional[str] = None):
        """
        初期化

        Args:
            flow_stats_path: 決まり手別統計ファイルのパス
        """
        if flow_stats_path is None:
            flow_stats_path = Path(__file__).parent.parent.parent / "data" / "kimarite_flow_stats.json"

        self.flow_stats = self._load_flow_stats(flow_stats_path)
        self.third_scorer = ThirdPlaceSpecializedScorer(flow_stats_path)
        self.makuri_evaluator = MakuriRiskEvaluator()

    def _load_flow_stats(self, path: str) -> Optional[Dict]:
        """統計ファイルを読み込む"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                stats = json.load(f)
            converted = {}
            for winner_course, kimarite_data in stats.items():
                converted[int(winner_course)] = kimarite_data
            return converted
        except Exception as e:
            logger.warning(f"統計ファイル読み込み失敗: {e}")
            return None

    def predict_kimarite_probabilities(
        self,
        course_scores: Dict[int, float],
        course1_grade: str = 'A1',
        entries: Optional[List[Dict]] = None,
        race_context: Optional[Dict] = None
    ) -> Dict[int, Dict[str, float]]:
        """
        各コースの決まり手確率を予測

        Args:
            course_scores: 各コースの予測スコア {1: 85.0, 2: 70.0, ...}
            course1_grade: 1コースの選手級別
            entries: 出走情報リスト（まくりリスク評価用）
            race_context: レース情報（まくりリスク評価用）

        Returns:
            {コース: {決まり手: 確率, ...}, ...}
        """
        # スコアから1着確率を計算
        total_score = sum(course_scores.values())
        first_prob = {c: s / total_score for c, s in course_scores.items()}

        # P-6-2: まくりリスク評価による補正
        makuri_adjustment = {}
        if is_feature_enabled('makuri_risk_adjustment') and entries and race_context:
            assessment = self.makuri_evaluator.evaluate_makuri_risk(race_context, entries)
            makuri_adjustment = self._calculate_makuri_adjustment(assessment)
            logger.debug(f"まくりリスク評価: {assessment.course1_risk_level}, 確率: {assessment.course1_makuri_prob:.1%}")

        result = {}
        for course in range(1, 7):
            course_first_prob = first_prob.get(course, 0.1)
            base_kimarite = self.KIMARITE_BASE_PROB.get(course, {})

            # 決まり手確率 = 基本確率 × 1着確率の調整
            kimarite_probs = {}
            for kimarite, base_prob in base_kimarite.items():
                # 1着確率が高いほど決まり手確率も上がる
                adjusted_prob = base_prob * (course_first_prob / 0.167)  # 0.167 = 1/6

                # P-6-2: まくり系の補正適用
                if kimarite in ['まくり', 'まくり差し', '差し'] and course in makuri_adjustment:
                    adjusted_prob *= (1.0 + makuri_adjustment[course])

                kimarite_probs[kimarite] = min(adjusted_prob, 0.95)

            result[course] = kimarite_probs

        return result

    def _calculate_makuri_adjustment(self, assessment: MakuriRiskAssessment) -> Dict[int, float]:
        """
        まくりリスク評価から決まり手確率の補正係数を計算

        Args:
            assessment: まくりリスク評価結果

        Returns:
            {コース: 補正係数, ...}  正の値=まくり確率UP
        """
        adjustments = {}

        # リスクレベルに応じた基本補正
        risk_base = {
            'high': 0.30,    # 高リスク: まくり系+30%
            'medium': 0.15,  # 中リスク: まくり系+15%
            'low': 0.0       # 低リスク: 補正なし
        }
        base_adj = risk_base.get(assessment.course1_risk_level, 0.0)

        # まくり候補に対する個別補正
        for course, prob, reason in assessment.makuri_candidates:
            # 確率に応じた追加補正（最大+20%）
            candidate_adj = min(prob * 0.5, 0.20)
            adjustments[course] = base_adj + candidate_adj

        # 補正がない外コースにはベース補正のみ適用
        for course in range(2, 7):
            if course not in adjustments:
                adjustments[course] = base_adj * 0.5  # 候補外は半分

        return adjustments

    def generate_scenarios(
        self,
        course_scores: Dict[int, float],
        kimarite_probs: Optional[Dict[int, Dict[str, float]]] = None,
        min_probability: float = 0.05,
        max_scenarios: int = 5
    ) -> List[RaceScenario]:
        """
        レース展開シナリオを生成

        Args:
            course_scores: 各コースの予測スコア
            kimarite_probs: 決まり手確率（Noneの場合は自動計算）
            min_probability: 最小確率閾値
            max_scenarios: 最大シナリオ数

        Returns:
            展開シナリオのリスト（確率順）
        """
        if kimarite_probs is None:
            kimarite_probs = self.predict_kimarite_probabilities(course_scores)

        scenarios = []

        for course, kimarite_dict in kimarite_probs.items():
            for kimarite, prob in kimarite_dict.items():
                if prob < min_probability:
                    continue

                # 2着候補を取得
                second_candidates = self._get_second_candidates(course, kimarite)

                # 3着候補を取得（上位2着候補に対して）
                if second_candidates:
                    top_second = second_candidates[0][0]
                    third_candidates = self.third_scorer.get_third_candidates(
                        course, kimarite, top_second,
                        base_scores=course_scores,
                        top_n=3
                    )
                else:
                    third_candidates = []

                scenario = RaceScenario(
                    winner_course=course,
                    winner_kimarite=kimarite,
                    probability=prob,
                    second_candidates=second_candidates,
                    third_candidates=third_candidates
                )
                scenarios.append(scenario)

        # 確率順にソートして上位を返す
        scenarios.sort(key=lambda x: x.probability, reverse=True)
        return scenarios[:max_scenarios]

    def _get_second_candidates(
        self,
        winner_course: int,
        kimarite: str,
        top_n: int = 3
    ) -> List[Tuple[int, float]]:
        """統計データから2着候補を取得"""
        if self.flow_stats is None:
            return []

        try:
            kimarite_data = self.flow_stats.get(winner_course, {}).get(kimarite, {})
            second_prob = kimarite_data.get('second_course_prob', {})
            sorted_prob = sorted(second_prob.items(), key=lambda x: x[1], reverse=True)
            return [(int(c), p) for c, p in sorted_prob[:top_n]]
        except Exception:
            return []

    def predict_full_ranking(
        self,
        course_scores: Dict[int, float],
        winner_kimarite: Optional[str] = None,
        entries: Optional[List[Dict]] = None,
        race_context: Optional[Dict] = None
    ) -> Dict[str, any]:
        """
        完全順位予測（1着～3着）

        Args:
            course_scores: 各コースの予測スコア
            winner_kimarite: 1着の決まり手（指定しない場合は最有力を使用）
            entries: 出走情報リスト（まくりリスク評価用）
            race_context: レース情報（まくりリスク評価用）

        Returns:
            {
                'first': {'course': int, 'kimarite': str, 'prob': float},
                'second': {'course': int, 'prob': float},
                'third': {'course': int, 'prob': float},
                'trifecta': str,  # "1-2-3" 形式
                'confidence': float,  # 信頼度
                'makuri_risk': dict  # まくりリスク評価（P-6-2）
            }
        """
        # P-6-2: まくりリスク評価によるスコア調整
        adjusted_scores = course_scores.copy()
        makuri_risk_info = None

        if is_feature_enabled('makuri_risk_adjustment') and entries and race_context:
            assessment = self.makuri_evaluator.evaluate_makuri_risk(race_context, entries)
            adjusted_scores = self.makuri_evaluator.adjust_scores_for_makuri(
                course_scores, assessment, adjustment_strength=1.0
            )
            makuri_risk_info = {
                'risk_level': assessment.course1_risk_level,
                'makuri_prob': assessment.course1_makuri_prob,
                'candidates': assessment.makuri_candidates,
                'confidence': assessment.confidence
            }
            logger.debug(f"まくりリスク評価適用: {assessment.course1_risk_level}")

        # 1着を決定（調整後スコア最高）
        sorted_scores = sorted(adjusted_scores.items(), key=lambda x: x[1], reverse=True)
        first_course = sorted_scores[0][0]
        first_score = sorted_scores[0][1]

        # 決まり手を決定（P-6-2: まくりリスクを考慮）
        if winner_kimarite is None:
            if first_course == 1:
                winner_kimarite = '逃げ'
            else:
                # まくりリスク評価がある場合はそれを参考に
                if makuri_risk_info and first_course in [c for c, _, _ in makuri_risk_info.get('candidates', [])]:
                    # まくり候補として評価されている場合
                    kimarite, _ = self.makuri_evaluator.get_kimarite_prediction(
                        MakuriRiskAssessment(
                            course1_risk_level=makuri_risk_info['risk_level'],
                            course1_makuri_prob=makuri_risk_info['makuri_prob'],
                            makuri_candidates=makuri_risk_info['candidates'],
                            confidence=makuri_risk_info['confidence'],
                            factors={}
                        ),
                        first_course
                    )
                    winner_kimarite = kimarite
                else:
                    # 従来のロジック
                    score_gap = first_score - sorted_scores[1][1]
                    if score_gap > 10 and first_course in [3, 4, 5]:
                        winner_kimarite = 'まくり'
                    elif first_course == 2:
                        winner_kimarite = '差し'
                    else:
                        winner_kimarite = 'まくり差し'

        # 2着候補を取得
        second_candidates = self._get_second_candidates(first_course, winner_kimarite)

        if second_candidates:
            # 統計ベースで2着決定（ただしスコアも考慮）
            best_second = None
            best_combined = 0
            for second_course, stat_prob in second_candidates:
                score_prob = course_scores.get(second_course, 0) / sum(course_scores.values())
                combined = stat_prob * 0.6 + score_prob * 0.4
                if combined > best_combined:
                    best_combined = combined
                    best_second = (second_course, stat_prob)

            second_course, second_prob = best_second if best_second else (sorted_scores[1][0], 0.3)
        else:
            # 統計がない場合はスコア2位
            second_course = sorted_scores[1][0]
            second_prob = 0.3

        # 3着を決定
        third_candidates = self.third_scorer.get_third_candidates(
            first_course, winner_kimarite, second_course,
            base_scores=course_scores,
            top_n=1
        )

        if third_candidates:
            third_course, third_prob = third_candidates[0]
        else:
            # 統計がない場合はスコア3位
            remaining = [c for c, _ in sorted_scores if c not in [first_course, second_course]]
            third_course = remaining[0] if remaining else 3
            third_prob = 0.25

        # 信頼度計算
        total_scores = sum(adjusted_scores.values())
        score_gap_12 = first_score - adjusted_scores.get(second_course, 0)
        confidence = min(score_gap_12 / 20, 1.0) * 0.5 + second_prob * 0.3 + third_prob * 0.2

        result = {
            'first': {'course': first_course, 'kimarite': winner_kimarite, 'prob': first_score / total_scores},
            'second': {'course': second_course, 'prob': second_prob},
            'third': {'course': third_course, 'prob': third_prob},
            'trifecta': f"{first_course}-{second_course}-{third_course}",
            'confidence': round(confidence, 3)
        }

        # P-6-2: まくりリスク情報を追加
        if makuri_risk_info:
            result['makuri_risk'] = makuri_risk_info

        return result


def test_predictor():
    """展開予測のテスト"""
    predictor = KimariteFlowPredictor()

    print("=" * 60)
    print("展開予測エンジン テスト")
    print("=" * 60)

    # テストケース: 1コース有利
    scores1 = {1: 85, 2: 70, 3: 65, 4: 60, 5: 55, 6: 50}
    print("\n【テスト1: 1コース有利】")
    print(f"スコア: {scores1}")

    result1 = predictor.predict_full_ranking(scores1)
    print(f"予測: {result1['trifecta']}")
    print(f"1着: {result1['first']}")
    print(f"2着: {result1['second']}")
    print(f"3着: {result1['third']}")
    print(f"信頼度: {result1['confidence']}")

    # テストケース: 3コース有利（まくり展開）
    scores2 = {1: 60, 2: 55, 3: 85, 4: 70, 5: 65, 6: 50}
    print("\n【テスト2: 3コース有利（まくり展開）】")
    print(f"スコア: {scores2}")

    result2 = predictor.predict_full_ranking(scores2)
    print(f"予測: {result2['trifecta']}")
    print(f"1着: {result2['first']}")
    print(f"2着: {result2['second']}")
    print(f"3着: {result2['third']}")
    print(f"信頼度: {result2['confidence']}")

    # シナリオ生成テスト
    print("\n【テスト3: シナリオ生成】")
    scenarios = predictor.generate_scenarios(scores1, max_scenarios=3)
    for i, scenario in enumerate(scenarios, 1):
        print(f"  シナリオ{i}: {scenario.winner_course}コース{scenario.winner_kimarite} (確率{scenario.probability:.2f})")
        print(f"    2着候補: {scenario.second_candidates[:2]}")
        print(f"    3着候補: {scenario.third_candidates[:2]}")

    # テストケース4: P-6-2 まくりリスク評価統合テスト
    print("\n" + "=" * 60)
    print("【テスト4: P-6-2 まくりリスク評価統合】")
    print("=" * 60)

    # 1コースB1、ST遅い、戸田（まくり多い）
    race_context = {'venue_code': '02'}  # 戸田
    entries = [
        {'pit_number': 1, 'racer_rank': 'B1', 'avg_st': 0.22, 'motor_2ren': 28},
        {'pit_number': 2, 'racer_rank': 'A2', 'avg_st': 0.14, 'motor_2ren': 35},
        {'pit_number': 3, 'racer_rank': 'A1', 'avg_st': 0.12, 'motor_2ren': 42},
        {'pit_number': 4, 'racer_rank': 'B1', 'avg_st': 0.15, 'motor_2ren': 30},
        {'pit_number': 5, 'racer_rank': 'A2', 'avg_st': 0.16, 'motor_2ren': 33},
        {'pit_number': 6, 'racer_rank': 'B1', 'avg_st': 0.18, 'motor_2ren': 25},
    ]
    scores3 = {1: 75, 2: 70, 3: 80, 4: 65, 5: 60, 6: 50}

    print(f"会場: 戸田（まくり率36.1%）")
    print(f"1コース: B1級, ST 0.22秒")
    print(f"元スコア: {scores3}")

    result3 = predictor.predict_full_ranking(scores3, entries=entries, race_context=race_context)
    print(f"\n予測: {result3['trifecta']}")
    print(f"1着: {result3['first']}")
    print(f"2着: {result3['second']}")
    print(f"3着: {result3['third']}")
    print(f"信頼度: {result3['confidence']}")

    if 'makuri_risk' in result3:
        mr = result3['makuri_risk']
        print(f"\nまくりリスク評価:")
        print(f"  リスクレベル: {mr['risk_level']}")
        print(f"  1Cまくられ確率: {mr['makuri_prob']:.1%}")
        print(f"  まくり候補:")
        for c, p, r in mr['candidates'][:3]:
            print(f"    {c}コース: {p:.1%} ({r})")


if __name__ == "__main__":
    test_predictor()
