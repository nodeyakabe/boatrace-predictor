"""
まくり系決まり手リスク評価エンジン

P-6-2タスク: まくり系（まくり、差し、まくり差し）の発生パターンを分析し、
予測ロジックに決まり手別の分岐を追加。

分析に基づく知見:
1. 1コースB1/B2級の敗北率が高い（65.1%, 54.1%）
2. 1コースのSTが遅い（0.20秒以上）とまくられ率が上昇（34.9%-51.6%）
3. まくり成功者の平均STは0.13-0.16秒程度
4. 会場によりまくり発生率が大きく異なる（22.8%-36.1%）
5. 格下からのまくりも多い（級別だけでは判断不可）
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.feature_flags import is_feature_enabled

logger = logging.getLogger(__name__)


@dataclass
class MakuriRiskAssessment:
    """まくりリスク評価結果"""
    course1_risk_level: str  # "high", "medium", "low"
    course1_makuri_prob: float  # 1コースがまくられる確率
    makuri_candidates: List[Tuple[int, float, str]]  # [(コース, 確率, 理由), ...]
    confidence: float  # 評価の信頼度
    factors: Dict[str, any]  # 評価要因の詳細


class MakuriRiskEvaluator:
    """
    まくり系決まり手のリスク評価エンジン

    1コースがまくられるリスクを評価し、
    まくり候補となる外コースを特定する。
    """

    # 会場別まくり発生率（分析結果に基づく）
    VENUE_MAKURI_RATES = {
        '02': 0.361,  # 戸田（最高）
        '04': 0.296,  # 平和島
        '05': 0.294,  # 多摩川
        '03': 0.291,  # 江戸川
        '01': 0.284,  # 桐生
        '14': 0.281,  # 鳴門
        '07': 0.275,  # 蒲郡
        '06': 0.260,  # 浜名湖
        '08': 0.253,  # 常滑
        '22': 0.250,  # 福岡
        '23': 0.247,  # 唐津
        '17': 0.229,  # 宮島
        '20': 0.229,  # 若松
        '11': 0.228,  # 琵琶湖
        '10': 0.228,  # 三国
        # 以下はデフォルト値を使用
    }
    DEFAULT_MAKURI_RATE = 0.25

    # 1コース級別別の敗北率（分析結果）
    COURSE1_LOSS_RATES = {
        'B2': 0.651,
        'B1': 0.541,
        'A2': 0.366,
        'A1': 0.281,
    }

    # 1コースST帯別のまくられ率（分析結果）
    ST_MAKURI_LOSS_RATES = {
        (0.00, 0.10): 0.135,
        (0.10, 0.15): 0.184,
        (0.15, 0.20): 0.255,
        (0.20, 0.25): 0.349,
        (0.25, 1.00): 0.516,
    }

    # コース別まくり成功傾向（分析結果）
    # key: コース, value: (まくり件数, まくり差し件数)
    COURSE_MAKURI_TENDENCY = {
        2: (2900, 0),      # 2コースはまくりのみ
        3: (4231, 4131),   # 3コースはまくり/まくり差し均等
        4: (4547, 2613),   # 4コースはまくり優勢
        5: (1150, 3281),   # 5コースはまくり差し優勢
        6: (468, 806),     # 6コースはまくり差し優勢
    }

    # まくり成功者の平均ST（分析結果）
    MAKURI_SUCCESS_AVG_ST = {
        2: 0.160,
        3: 0.155,
        4: 0.138,
        5: 0.153,
        6: 0.129,
    }

    def __init__(self, db_path: str = None):
        """初期化"""
        self.db_path = db_path or DATABASE_PATH

    def evaluate_makuri_risk(
        self,
        race_context: Dict,
        entries: List[Dict],
        course1_st: Optional[float] = None
    ) -> MakuriRiskAssessment:
        """
        まくりリスクを総合評価

        Args:
            race_context: レース情報 {'venue_code', 'race_date', ...}
            entries: 出走情報リスト [{'pit_number', 'racer_rank', 'avg_st', 'motor_2ren', ...}, ...]
            course1_st: 1コースの当日ST（直前情報）

        Returns:
            MakuriRiskAssessment
        """
        venue_code = race_context.get('venue_code', '01')
        factors = {}

        # 1コース選手を特定
        course1_entry = next((e for e in entries if e.get('pit_number') == 1), None)
        if not course1_entry:
            return self._create_default_assessment()

        # === 要因1: 1コース級別リスク ===
        course1_rank = course1_entry.get('racer_rank', 'B1')
        rank_loss_rate = self.COURSE1_LOSS_RATES.get(course1_rank, 0.45)
        factors['course1_rank'] = {
            'rank': course1_rank,
            'loss_rate': rank_loss_rate
        }

        # === 要因2: 1コースSTリスク ===
        st_value = course1_st or course1_entry.get('avg_st', 0.15)
        st_makuri_rate = self._get_st_makuri_rate(st_value)
        factors['course1_st'] = {
            'st': st_value,
            'makuri_rate': st_makuri_rate
        }

        # === 要因3: 会場リスク ===
        venue_makuri_rate = self.VENUE_MAKURI_RATES.get(venue_code, self.DEFAULT_MAKURI_RATE)
        factors['venue'] = {
            'venue_code': venue_code,
            'makuri_rate': venue_makuri_rate
        }

        # === 総合リスク計算 ===
        # 各要因を重み付けして統合
        base_risk = 0.25  # ベース（全体のまくり+まくり差し率は約25%）

        # 級別による補正
        rank_factor = rank_loss_rate / 0.45  # 平均敗北率45%を基準

        # STによる補正
        st_factor = st_makuri_rate / 0.25  # 平均まくられ率25%を基準

        # 会場による補正
        venue_factor = venue_makuri_rate / 0.25

        # 総合リスク（各要因の加重平均）
        total_risk = base_risk * (
            rank_factor * 0.35 +
            st_factor * 0.40 +
            venue_factor * 0.25
        )
        total_risk = min(0.80, max(0.10, total_risk))

        # === リスクレベル判定 ===
        if total_risk >= 0.45:
            risk_level = "high"
        elif total_risk >= 0.30:
            risk_level = "medium"
        else:
            risk_level = "low"

        # === まくり候補の特定 ===
        makuri_candidates = self._identify_makuri_candidates(
            entries, course1_entry, venue_code, total_risk
        )

        # === 信頼度計算 ===
        confidence = self._calculate_confidence(factors, entries)

        return MakuriRiskAssessment(
            course1_risk_level=risk_level,
            course1_makuri_prob=round(total_risk, 3),
            makuri_candidates=makuri_candidates,
            confidence=round(confidence, 3),
            factors=factors
        )

    def _get_st_makuri_rate(self, st_value: float) -> float:
        """ST値に対応するまくられ率を取得"""
        for (st_min, st_max), rate in self.ST_MAKURI_LOSS_RATES.items():
            if st_min <= st_value < st_max:
                return rate
        return 0.25  # デフォルト

    def _identify_makuri_candidates(
        self,
        entries: List[Dict],
        course1_entry: Dict,
        venue_code: str,
        total_risk: float
    ) -> List[Tuple[int, float, str]]:
        """
        まくり候補を特定

        Returns:
            [(コース, 確率, 理由), ...]
        """
        candidates = []
        course1_rank_score = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}.get(
            course1_entry.get('racer_rank', 'B1'), 2
        )

        for entry in entries:
            pit = entry.get('pit_number', 0)
            if pit <= 1:
                continue  # 1コースはスキップ

            # コース別の基本確率
            makuri_cnt, makuri_sashi_cnt = self.COURSE_MAKURI_TENDENCY.get(pit, (0, 0))
            total_cnt = makuri_cnt + makuri_sashi_cnt
            if total_cnt == 0:
                continue

            # コース別確率（全体に対する比率）
            course_base_prob = total_cnt / 48000  # 概算の総まくり数

            # 選手属性による補正
            entry_rank = entry.get('racer_rank', 'B1')
            entry_rank_score = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}.get(entry_rank, 2)

            # 級別差による補正（格上がまくりやすい）
            rank_diff = entry_rank_score - course1_rank_score
            rank_multiplier = 1.0 + (rank_diff * 0.15)

            # ST比較による補正
            entry_st = entry.get('avg_st', 0.15)
            makuri_avg_st = self.MAKURI_SUCCESS_AVG_ST.get(pit, 0.15)
            if entry_st <= makuri_avg_st:
                st_multiplier = 1.2  # STが早い
            elif entry_st <= makuri_avg_st + 0.03:
                st_multiplier = 1.0
            else:
                st_multiplier = 0.8

            # モーター成績による補正
            motor_2ren = entry.get('motor_2ren', 30)
            motor_multiplier = 1.0 + (motor_2ren - 30) * 0.01  # 30%基準で±1%ごとに補正

            # 総合確率
            candidate_prob = course_base_prob * rank_multiplier * st_multiplier * motor_multiplier
            candidate_prob *= (total_risk / 0.25)  # 全体リスクで調整
            candidate_prob = min(0.30, max(0.01, candidate_prob))

            # 理由の生成
            reasons = []
            if rank_diff > 0:
                reasons.append(f"格上({entry_rank})")
            if entry_st <= makuri_avg_st:
                reasons.append(f"ST早い({entry_st:.2f}秒)")
            if motor_2ren >= 35:
                reasons.append(f"モーター好調({motor_2ren:.0f}%)")
            if pit in [3, 4]:
                reasons.append("まくり主力コース")
            elif pit == 5:
                reasons.append("まくり差し狙い")

            reason_str = ", ".join(reasons) if reasons else "標準"

            candidates.append((pit, round(candidate_prob, 3), reason_str))

        # 確率順にソート
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:4]  # 上位4候補

    def _calculate_confidence(self, factors: Dict, entries: List[Dict]) -> float:
        """評価の信頼度を計算"""
        confidence = 0.7  # 基準値

        # データが揃っているほど信頼度UP
        if factors.get('course1_st', {}).get('st'):
            confidence += 0.1

        # エントリー数が6なら信頼度UP
        if len(entries) == 6:
            confidence += 0.05

        # 級別が明確なら信頼度UP
        ranks_known = sum(1 for e in entries if e.get('racer_rank'))
        confidence += (ranks_known / 6) * 0.1

        return min(1.0, confidence)

    def _create_default_assessment(self) -> MakuriRiskAssessment:
        """デフォルトの評価結果を作成"""
        return MakuriRiskAssessment(
            course1_risk_level="medium",
            course1_makuri_prob=0.25,
            makuri_candidates=[],
            confidence=0.5,
            factors={}
        )

    def adjust_scores_for_makuri(
        self,
        course_scores: Dict[int, float],
        assessment: MakuriRiskAssessment,
        adjustment_strength: float = 1.0
    ) -> Dict[int, float]:
        """
        まくりリスク評価に基づいてスコアを調整

        Args:
            course_scores: 元のコース別スコア {1: 85.0, 2: 70.0, ...}
            assessment: まくりリスク評価結果
            adjustment_strength: 調整の強さ（0.0-2.0）

        Returns:
            調整後のスコア
        """
        if not is_feature_enabled('makuri_risk_adjustment'):
            return course_scores

        adjusted = course_scores.copy()

        # リスクレベルに応じた調整係数
        risk_adjustments = {
            'high': -0.08,    # 高リスク: 1コース-8%
            'medium': -0.04,  # 中リスク: 1コース-4%
            'low': 0.0        # 低リスク: 調整なし
        }

        base_adj = risk_adjustments.get(assessment.course1_risk_level, 0.0)
        base_adj *= adjustment_strength

        # 1コースのスコア調整
        if 1 in adjusted and base_adj != 0:
            adjusted[1] = adjusted[1] * (1.0 + base_adj)

        # まくり候補のスコア調整
        for course, prob, reason in assessment.makuri_candidates:
            if course in adjusted and prob > 0.05:
                # 確率に応じたボーナス（最大+5%）
                bonus = min(prob * 0.5, 0.05) * adjustment_strength
                adjusted[course] = adjusted[course] * (1.0 + bonus)

        return adjusted

    def get_kimarite_prediction(
        self,
        assessment: MakuriRiskAssessment,
        predicted_winner_course: int
    ) -> Tuple[str, float]:
        """
        勝者コースに対する決まり手予測

        Args:
            assessment: まくりリスク評価
            predicted_winner_course: 予測された勝者コース

        Returns:
            (予測決まり手, 確率)
        """
        if predicted_winner_course == 1:
            # 1コース勝利なら逃げ
            if assessment.course1_risk_level == 'low':
                return ('逃げ', 0.85)
            elif assessment.course1_risk_level == 'medium':
                return ('逃げ', 0.75)
            else:
                return ('逃げ', 0.60)

        elif predicted_winner_course == 2:
            # 2コースは差しが多い
            return ('差し', 0.65)

        elif predicted_winner_course == 3:
            # 3コースはまくりとまくり差しが拮抗
            return ('まくり', 0.45)

        elif predicted_winner_course == 4:
            # 4コースはまくりが優勢
            return ('まくり', 0.55)

        elif predicted_winner_course >= 5:
            # 5-6コースはまくり差し
            return ('まくり差し', 0.55)

        return ('不明', 0.5)


def test_makuri_evaluator():
    """テスト"""
    evaluator = MakuriRiskEvaluator()

    # テストケース1: B1の1コース、ST遅い
    race_context = {'venue_code': '02'}  # 戸田（まくり多い）
    entries = [
        {'pit_number': 1, 'racer_rank': 'B1', 'avg_st': 0.22, 'motor_2ren': 28},
        {'pit_number': 2, 'racer_rank': 'A2', 'avg_st': 0.14, 'motor_2ren': 35},
        {'pit_number': 3, 'racer_rank': 'A1', 'avg_st': 0.12, 'motor_2ren': 42},
        {'pit_number': 4, 'racer_rank': 'B1', 'avg_st': 0.15, 'motor_2ren': 30},
        {'pit_number': 5, 'racer_rank': 'A2', 'avg_st': 0.16, 'motor_2ren': 33},
        {'pit_number': 6, 'racer_rank': 'B1', 'avg_st': 0.18, 'motor_2ren': 25},
    ]

    print("=" * 60)
    print("まくりリスク評価テスト")
    print("=" * 60)

    assessment = evaluator.evaluate_makuri_risk(race_context, entries)

    print(f"\n【テストケース: 戸田、1コースB1、ST遅い】")
    print(f"1コースリスクレベル: {assessment.course1_risk_level}")
    print(f"1コースまくられ確率: {assessment.course1_makuri_prob:.1%}")
    print(f"信頼度: {assessment.confidence:.1%}")
    print(f"\nまくり候補:")
    for course, prob, reason in assessment.makuri_candidates:
        print(f"  {course}コース: {prob:.1%} ({reason})")

    print(f"\n評価要因:")
    for key, value in assessment.factors.items():
        print(f"  {key}: {value}")

    # スコア調整テスト
    original_scores = {1: 85, 2: 70, 3: 75, 4: 65, 5: 60, 6: 50}
    adjusted_scores = evaluator.adjust_scores_for_makuri(original_scores, assessment)

    print(f"\n【スコア調整】")
    print(f"元スコア: {original_scores}")
    print(f"調整後: {adjusted_scores}")

    # 決まり手予測
    kimarite, prob = evaluator.get_kimarite_prediction(assessment, 3)
    print(f"\n【決まり手予測（3コース勝利時）】")
    print(f"予測: {kimarite} ({prob:.1%})")


if __name__ == "__main__":
    test_makuri_evaluator()
