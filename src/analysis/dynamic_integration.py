"""
動的スコア統合モジュール

条件に応じてPRE_SCOREとBEFORE_SCOREの合成比を動的に調整する。
偏差日（直前情報の重要度が特に高い/低い日）に対応。
"""

from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import math


class IntegrationCondition(Enum):
    """統合条件タイプ"""
    NORMAL = "normal"           # 通常
    BEFOREINFO_CRITICAL = "before_critical"  # 直前情報重視
    PREINFO_RELIABLE = "pre_reliable"        # 事前情報重視
    UNCERTAIN = "uncertain"     # 不確実性高


@dataclass
class IntegrationWeights:
    """統合重み"""
    pre_weight: float      # PRE_SCOREの重み (0.0-1.0)
    before_weight: float   # BEFORE_SCOREの重み (0.0-1.0)
    condition: IntegrationCondition
    reason: str
    confidence: float      # この重み判断の信頼度


class DynamicIntegrator:
    """動的スコア統合クラス"""

    # デフォルト重み
    DEFAULT_PRE_WEIGHT = 0.6
    DEFAULT_BEFORE_WEIGHT = 0.4

    # 条件別重み設定
    CONDITION_WEIGHTS = {
        IntegrationCondition.NORMAL: (0.6, 0.4),
        IntegrationCondition.BEFOREINFO_CRITICAL: (0.4, 0.6),
        IntegrationCondition.PREINFO_RELIABLE: (0.75, 0.25),
        IntegrationCondition.UNCERTAIN: (0.5, 0.5),
    }

    # 直前情報重視の閾値
    EXHIBITION_VARIANCE_THRESHOLD = 0.10  # 展示タイム分散が高い（0.10秒の標準偏差）
    ST_VARIANCE_THRESHOLD = 0.05          # ST分散が高い（0.05秒の標準偏差）
    ENTRY_CHANGE_THRESHOLD = 2            # 進入変更艇数

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def determine_weights(
        self,
        race_id: int,
        beforeinfo_data: Dict,
        pre_predictions: list,
        venue_code: str,
        weather_data: Optional[Dict] = None
    ) -> IntegrationWeights:
        """
        レース状況に応じた動的重みを決定

        Args:
            race_id: レースID
            beforeinfo_data: 直前情報データ
            pre_predictions: 事前予測結果
            venue_code: 会場コード
            weather_data: 天候データ

        Returns:
            IntegrationWeights: 決定された重み
        """
        reasons = []
        condition = IntegrationCondition.NORMAL

        # 1. 展示タイムの分散をチェック
        exhibition_variance = self._calculate_exhibition_variance(beforeinfo_data)
        if exhibition_variance > self.EXHIBITION_VARIANCE_THRESHOLD:
            condition = IntegrationCondition.BEFOREINFO_CRITICAL
            reasons.append(f"展示タイム分散高({exhibition_variance:.3f})")

        # 2. STの分散をチェック
        st_variance = self._calculate_st_variance(beforeinfo_data)
        if st_variance > self.ST_VARIANCE_THRESHOLD:
            condition = IntegrationCondition.BEFOREINFO_CRITICAL
            reasons.append(f"ST分散高({st_variance:.3f})")

        # 3. 進入変更をチェック
        entry_changes = self._count_entry_changes(beforeinfo_data)
        if entry_changes >= self.ENTRY_CHANGE_THRESHOLD:
            condition = IntegrationCondition.BEFOREINFO_CRITICAL
            reasons.append(f"進入変更{entry_changes}艇")

        # 4. 事前予測の信頼度をチェック
        pre_confidence = self._evaluate_pre_confidence(pre_predictions)
        if pre_confidence > 0.85:
            # 事前予測が高信頼の場合は事前重視
            if condition == IntegrationCondition.NORMAL:
                condition = IntegrationCondition.PREINFO_RELIABLE
                reasons.append(f"事前予測高信頼({pre_confidence:.2f})")
        elif pre_confidence < 0.5:
            # 事前予測が低信頼の場合は直前情報重視
            condition = IntegrationCondition.BEFOREINFO_CRITICAL
            reasons.append(f"事前予測低信頼({pre_confidence:.2f})")

        # 5. 天候変化をチェック
        if weather_data:
            weather_impact = self._evaluate_weather_impact(weather_data)
            if weather_impact > 0.3:
                condition = IntegrationCondition.BEFOREINFO_CRITICAL
                reasons.append(f"天候変動大({weather_impact:.2f})")

        # 6. 直前情報のデータ充実度をチェック
        before_completeness = self._calculate_before_completeness(beforeinfo_data)
        if before_completeness < 0.5:
            # 直前情報不足の場合は事前重視
            condition = IntegrationCondition.PREINFO_RELIABLE
            reasons.append(f"直前情報不足({before_completeness:.2f})")

        # 重みを取得
        pre_w, before_w = self.CONDITION_WEIGHTS[condition]

        # データ充実度で微調整
        if before_completeness < 0.8:
            # 直前情報が不完全な場合、その分事前重みを上げる
            adjustment = (1.0 - before_completeness) * 0.2
            pre_w = min(0.85, pre_w + adjustment)
            before_w = max(0.15, before_w - adjustment)

        # 正規化
        total = pre_w + before_w
        pre_w /= total
        before_w /= total

        return IntegrationWeights(
            pre_weight=pre_w,
            before_weight=before_w,
            condition=condition,
            reason="; ".join(reasons) if reasons else "通常条件",
            confidence=min(pre_confidence, before_completeness)
        )

    def _calculate_exhibition_variance(self, beforeinfo_data: Dict) -> float:
        """展示タイムの分散を計算"""
        times = beforeinfo_data.get('exhibition_times', {})
        if len(times) < 4:
            return 0.0

        values = list(times.values())
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def _calculate_st_variance(self, beforeinfo_data: Dict) -> float:
        """STの分散を計算"""
        timings = beforeinfo_data.get('start_timings', {})
        if len(timings) < 4:
            return 0.0

        values = [v for v in timings.values() if v >= 0]  # フライング除外
        if len(values) < 3:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def _count_entry_changes(self, beforeinfo_data: Dict) -> int:
        """進入変更艇数をカウント"""
        courses = beforeinfo_data.get('exhibition_courses', {})
        changes = 0
        for pit, course in courses.items():
            if pit != course:
                changes += 1
        return changes

    def _evaluate_pre_confidence(self, predictions: list) -> float:
        """事前予測の信頼度を評価"""
        if not predictions:
            return 0.5

        # トップと2位のスコア差
        if len(predictions) >= 2:
            gap = predictions[0].get('total_score', 0) - predictions[1].get('total_score', 0)
            # ギャップが大きいほど信頼度高
            gap_factor = min(gap / 15.0, 1.0)  # 15点差で最大
        else:
            gap_factor = 0.5

        # 信頼度の分布
        confidence_map = {'A': 1.0, 'B': 0.8, 'C': 0.6, 'D': 0.4, 'E': 0.2}
        top_conf = confidence_map.get(predictions[0].get('confidence', 'C'), 0.6)

        return (gap_factor + top_conf) / 2

    def _evaluate_weather_impact(self, weather_data: Dict) -> float:
        """天候変化の影響度を評価"""
        impact = 0.0

        wind_speed = weather_data.get('wind_speed', 0)
        wave_height = weather_data.get('wave_height', 0)

        if wind_speed >= 6:
            impact += 0.3
        elif wind_speed >= 4:
            impact += 0.15

        if wave_height >= 10:
            impact += 0.2
        elif wave_height >= 5:
            impact += 0.1

        return min(impact, 1.0)

    def _calculate_before_completeness(self, beforeinfo_data: Dict) -> float:
        """直前情報のデータ充実度を計算"""
        if not beforeinfo_data.get('is_published', False):
            return 0.0

        score = 0
        max_score = 6

        if len(beforeinfo_data.get('exhibition_times', {})) >= 5:
            score += 1
        if len(beforeinfo_data.get('start_timings', {})) >= 5:
            score += 1
        if len(beforeinfo_data.get('exhibition_courses', {})) >= 5:
            score += 1
        if len(beforeinfo_data.get('tilt_angles', {})) >= 5:
            score += 1
        if beforeinfo_data.get('weather', {}):
            score += 1
        if len(beforeinfo_data.get('previous_race', {})) >= 3:
            score += 1

        return score / max_score

    def integrate_scores(
        self,
        pre_score: float,
        before_score: float,
        weights: IntegrationWeights
    ) -> float:
        """
        スコアを統合

        Args:
            pre_score: 事前スコア (0-100)
            before_score: 直前情報スコア (0-100)
            weights: 統合重み

        Returns:
            統合後スコア
        """
        return pre_score * weights.pre_weight + before_score * weights.before_weight
