# -*- coding: utf-8 -*-
"""
会場×コース別 ポイント調整クラス

2024-2025年データから算出した各会場のコース別勝率差分に基づいて、
予測スコアにデバフ/バフを適用する。

主な機能:
- 会場×コース別の調整ポイント適用
- 予測スコアの調整
- 調整理由の生成

使用方法:
    from src.betting.venue_course_adjuster import VenueCourseAdjuster

    adjuster = VenueCourseAdjuster()

    # 単一コースの調整
    adjusted_score = adjuster.apply_adjustment(
        base_score=50.0,
        venue_code='02',  # 戸田
        course=1          # 1コース
    )
    # 結果: 50.0 + (-12) = 38.0pt (1コースが弱い会場なのでデバフ)

    # 全コースの調整（レース全体）
    adjustments = adjuster.get_race_adjustments(venue_code='18')  # 徳山
    # 結果: {1: +9, 2: -2, 3: -3, 4: -2, 5: -2, 6: 0}
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

# 設定ファイルから調整データを読み込む
try:
    from config.venue_course_adjustments import (
        VENUE_COURSE_ADJUSTMENTS,
        OVERALL_WIN_RATES,
        WEAK_IN_VENUES,
        STRONG_IN_VENUES,
        STRONG_CENTER_VENUES,
        STRONG_OUT_VENUES,
        get_adjustment as config_get_adjustment,
        get_all_adjustments as config_get_all_adjustments,
    )
except ImportError:
    # フォールバック用のデフォルト値
    VENUE_COURSE_ADJUSTMENTS = {}
    OVERALL_WIN_RATES = {1: 57.87, 2: 12.84, 3: 12.32, 4: 10.16, 5: 6.01, 6: 1.91}
    WEAK_IN_VENUES = ['02', '04', '03', '14']
    STRONG_IN_VENUES = ['18', '24', '19']
    STRONG_CENTER_VENUES = ['02', '04', '22']
    STRONG_OUT_VENUES = ['01', '14']

    def config_get_adjustment(venue_code: str, course: int) -> int:
        return 0

    def config_get_all_adjustments(venue_code: str) -> Dict[int, int]:
        return {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}


logger = logging.getLogger(__name__)


# 会場名マッピング
VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村',
}


@dataclass
class AdjustmentResult:
    """調整結果"""
    original_score: float
    adjusted_score: float
    adjustment: int
    venue_code: str
    venue_name: str
    course: int
    reason: str
    venue_characteristic: Optional[str] = None


@dataclass
class RaceAdjustmentResult:
    """レース全体の調整結果"""
    venue_code: str
    venue_name: str
    adjustments: Dict[int, int]
    venue_characteristics: List[str]
    significant_adjustments: List[Tuple[int, int, str]]  # (course, adjustment, reason)


class VenueCourseAdjuster:
    """会場×コース別のポイント調整クラス"""

    def __init__(
        self,
        enabled: bool = True,
        adjustment_scale: float = 1.0,
        min_adjustment: int = -20,
        max_adjustment: int = 20,
    ):
        """
        初期化

        Args:
            enabled: 調整を有効化するか
            adjustment_scale: 調整値のスケール（デフォルト1.0 = 100%適用）
            min_adjustment: 最小調整値
            max_adjustment: 最大調整値
        """
        self.enabled = enabled
        self.adjustment_scale = adjustment_scale
        self.min_adjustment = min_adjustment
        self.max_adjustment = max_adjustment

    def get_adjustment(self, venue_code: str, course: int) -> int:
        """
        会場×コース別の調整ポイントを取得

        Args:
            venue_code: 会場コード ('01'-'24')
            course: コース番号 (1-6)

        Returns:
            int: 調整ポイント (-20 ～ +20)
        """
        if not self.enabled:
            return 0

        # 会場コードを正規化
        venue_code = self._normalize_venue_code(venue_code)

        # 設定から調整値を取得
        raw_adjustment = config_get_adjustment(venue_code, course)

        # スケールを適用
        scaled = int(raw_adjustment * self.adjustment_scale)

        # 範囲制限
        return max(self.min_adjustment, min(self.max_adjustment, scaled))

    def get_all_adjustments(self, venue_code: str) -> Dict[int, int]:
        """
        会場の全コース調整ポイントを取得

        Args:
            venue_code: 会場コード

        Returns:
            {course: adjustment}
        """
        venue_code = self._normalize_venue_code(venue_code)
        raw_adjustments = config_get_all_adjustments(venue_code)

        if not self.enabled:
            return {c: 0 for c in range(1, 7)}

        result = {}
        for course, adj in raw_adjustments.items():
            scaled = int(adj * self.adjustment_scale)
            result[course] = max(self.min_adjustment, min(self.max_adjustment, scaled))

        return result

    def apply_adjustment(
        self,
        base_score: float,
        venue_code: str,
        course: int
    ) -> float:
        """
        予測スコアに調整を適用

        Args:
            base_score: 元の予測スコア
            venue_code: 会場コード
            course: コース番号

        Returns:
            float: 調整後スコア
        """
        adjustment = self.get_adjustment(venue_code, course)
        return base_score + adjustment

    def apply_adjustment_with_details(
        self,
        base_score: float,
        venue_code: str,
        course: int
    ) -> AdjustmentResult:
        """
        予測スコアに調整を適用し、詳細情報を返す

        Args:
            base_score: 元の予測スコア
            venue_code: 会場コード
            course: コース番号

        Returns:
            AdjustmentResult: 調整結果と詳細情報
        """
        venue_code = self._normalize_venue_code(venue_code)
        venue_name = VENUE_NAMES.get(venue_code, '不明')
        adjustment = self.get_adjustment(venue_code, course)
        adjusted_score = base_score + adjustment

        # 会場特性を判定
        venue_characteristic = self._get_venue_characteristic(venue_code, course)

        # 理由を生成
        if adjustment > 0:
            reason = f"{venue_name}は{course}コース勝率が平均より高い（+{adjustment}pt）"
        elif adjustment < 0:
            reason = f"{venue_name}は{course}コース勝率が平均より低い（{adjustment}pt）"
        else:
            reason = f"{venue_name}の{course}コースは平均的（調整なし）"

        return AdjustmentResult(
            original_score=base_score,
            adjusted_score=adjusted_score,
            adjustment=adjustment,
            venue_code=venue_code,
            venue_name=venue_name,
            course=course,
            reason=reason,
            venue_characteristic=venue_characteristic,
        )

    def get_race_adjustments(self, venue_code: str) -> RaceAdjustmentResult:
        """
        レース全体の調整情報を取得

        Args:
            venue_code: 会場コード

        Returns:
            RaceAdjustmentResult: レース全体の調整情報
        """
        venue_code = self._normalize_venue_code(venue_code)
        venue_name = VENUE_NAMES.get(venue_code, '不明')
        adjustments = self.get_all_adjustments(venue_code)

        # 会場特性を判定
        characteristics = []
        if venue_code in WEAK_IN_VENUES:
            characteristics.append('イン弱')
        if venue_code in STRONG_IN_VENUES:
            characteristics.append('イン強')
        if venue_code in STRONG_CENTER_VENUES:
            characteristics.append('センター強')
        if venue_code in STRONG_OUT_VENUES:
            characteristics.append('アウト強')

        # 顕著な調整を抽出
        significant = []
        for course, adj in adjustments.items():
            if abs(adj) >= 5:
                direction = "強い" if adj > 0 else "弱い"
                significant.append((course, adj, f"{course}コースが{direction}"))

        return RaceAdjustmentResult(
            venue_code=venue_code,
            venue_name=venue_name,
            adjustments=adjustments,
            venue_characteristics=characteristics,
            significant_adjustments=significant,
        )

    def adjust_predictions(
        self,
        predictions: List[Dict],
        venue_code: str,
        score_key: str = 'total_score'
    ) -> List[Dict]:
        """
        予測リストにまとめて調整を適用

        Args:
            predictions: 予測データのリスト（各要素に pit_number と score_key が必要）
            venue_code: 会場コード
            score_key: スコアのキー名

        Returns:
            調整後の予測リスト（元のリストを変更せず新しいリストを返す）
        """
        venue_code = self._normalize_venue_code(venue_code)
        adjustments = self.get_all_adjustments(venue_code)

        adjusted_predictions = []
        for pred in predictions:
            new_pred = pred.copy()
            pit_number = pred.get('pit_number')

            if pit_number is not None and 1 <= pit_number <= 6:
                # actual_courseがあればそれを使用、なければpit_numberを使用
                course = pred.get('actual_course', pit_number)
                adjustment = adjustments.get(course, 0)

                if score_key in new_pred:
                    new_pred[score_key] = pred[score_key] + adjustment
                    new_pred['venue_course_adjustment'] = adjustment

            adjusted_predictions.append(new_pred)

        return adjusted_predictions

    def should_apply_strong_debuff(
        self,
        venue_code: str,
        course: int,
        threshold: int = -5
    ) -> Tuple[bool, str]:
        """
        強いデバフを適用すべきかを判定

        Args:
            venue_code: 会場コード
            course: コース番号
            threshold: デバフの閾値（この値以下でTrue）

        Returns:
            (適用すべきか, 理由)
        """
        venue_code = self._normalize_venue_code(venue_code)
        adjustment = self.get_adjustment(venue_code, course)
        venue_name = VENUE_NAMES.get(venue_code, '不明')

        if adjustment <= threshold:
            return True, f"{venue_name}の{course}コースは勝率が低い（{adjustment}pt）"
        return False, ""

    def should_apply_strong_buff(
        self,
        venue_code: str,
        course: int,
        threshold: int = 5
    ) -> Tuple[bool, str]:
        """
        強いバフを適用すべきかを判定

        Args:
            venue_code: 会場コード
            course: コース番号
            threshold: バフの閾値（この値以上でTrue）

        Returns:
            (適用すべきか, 理由)
        """
        venue_code = self._normalize_venue_code(venue_code)
        adjustment = self.get_adjustment(venue_code, course)
        venue_name = VENUE_NAMES.get(venue_code, '不明')

        if adjustment >= threshold:
            return True, f"{venue_name}の{course}コースは勝率が高い（+{adjustment}pt）"
        return False, ""

    def _normalize_venue_code(self, venue_code) -> str:
        """会場コードを正規化"""
        if venue_code is None:
            return '00'
        if isinstance(venue_code, int):
            return f"{venue_code:02d}"
        return str(venue_code).zfill(2)

    def _get_venue_characteristic(self, venue_code: str, course: int) -> Optional[str]:
        """会場×コースの特性を判定"""
        if course == 1:
            if venue_code in WEAK_IN_VENUES:
                return 'イン弱会場'
            elif venue_code in STRONG_IN_VENUES:
                return 'イン強会場'
        elif course in [3, 4]:
            if venue_code in STRONG_CENTER_VENUES:
                return 'センター強会場'
        elif course in [5, 6]:
            if venue_code in STRONG_OUT_VENUES:
                return 'アウト強会場'
        return None

    def get_summary_for_venue(self, venue_code: str) -> str:
        """
        会場のサマリー文字列を生成

        Args:
            venue_code: 会場コード

        Returns:
            サマリー文字列
        """
        result = self.get_race_adjustments(venue_code)

        lines = [f"=== {result.venue_name}({result.venue_code}) ==="]

        if result.venue_characteristics:
            lines.append(f"特性: {', '.join(result.venue_characteristics)}")

        lines.append("コース別調整:")
        for course in range(1, 7):
            adj = result.adjustments.get(course, 0)
            if adj > 0:
                lines.append(f"  {course}コース: +{adj}pt")
            elif adj < 0:
                lines.append(f"  {course}コース: {adj}pt")
            else:
                lines.append(f"  {course}コース: 0pt")

        if result.significant_adjustments:
            lines.append("注目点:")
            for course, adj, reason in result.significant_adjustments:
                lines.append(f"  - {reason}")

        return "\n".join(lines)


# シングルトンインスタンス
_default_adjuster: Optional[VenueCourseAdjuster] = None


def get_default_adjuster() -> VenueCourseAdjuster:
    """デフォルトのVenueCourseAdjusterインスタンスを取得"""
    global _default_adjuster
    if _default_adjuster is None:
        _default_adjuster = VenueCourseAdjuster()
    return _default_adjuster


def apply_venue_course_adjustment(
    base_score: float,
    venue_code: str,
    course: int
) -> float:
    """
    便利関数: 予測スコアに会場×コース調整を適用

    Args:
        base_score: 元の予測スコア
        venue_code: 会場コード
        course: コース番号

    Returns:
        float: 調整後スコア
    """
    return get_default_adjuster().apply_adjustment(base_score, venue_code, course)
