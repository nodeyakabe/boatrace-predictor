# -*- coding: utf-8 -*-
"""
会場別除外・採用ロジック
2024-2025年データ分析に基づく会場×風向き×風速条件の評価

パターンH複数点買い戦略の改善用モジュール
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 会場情報
VENUE_INFO = {
    '01': {'name': '桐生', 'water_type': '淡水', 'in_strength': 'weak', 'c1_rate': 51.93},
    '02': {'name': '戸田', 'water_type': '淡水', 'in_strength': 'very_weak', 'c1_rate': 45.87},
    '03': {'name': '江戸川', 'water_type': '汽水', 'in_strength': 'weak', 'c1_rate': 49.54},
    '04': {'name': '平和島', 'water_type': '海水', 'in_strength': 'very_weak', 'c1_rate': 46.18},
    '05': {'name': '多摩川', 'water_type': '淡水', 'in_strength': 'normal', 'c1_rate': 54.56},
    '06': {'name': '浜名湖', 'water_type': '汽水', 'in_strength': 'normal', 'c1_rate': 55.28},
    '07': {'name': '蒲郡', 'water_type': '海水', 'in_strength': 'strong', 'c1_rate': 60.74},
    '08': {'name': '常滑', 'water_type': '海水', 'in_strength': 'strong', 'c1_rate': 60.56},
    '09': {'name': '津', 'water_type': '海水', 'in_strength': 'strong', 'c1_rate': 60.37},
    '10': {'name': '三国', 'water_type': '淡水', 'in_strength': 'normal', 'c1_rate': 56.26},
    '11': {'name': 'びわこ', 'water_type': '淡水', 'in_strength': 'normal', 'c1_rate': 58.85},
    '12': {'name': '住之江', 'water_type': '淡水', 'in_strength': 'strong', 'c1_rate': 61.11},
    '13': {'name': '尼崎', 'water_type': '海水', 'in_strength': 'strong', 'c1_rate': 61.81},
    '14': {'name': '鳴門', 'water_type': '海水', 'in_strength': 'weak', 'c1_rate': 49.51},
    '15': {'name': '丸亀', 'water_type': '海水', 'in_strength': 'normal', 'c1_rate': 58.17},
    '16': {'name': '児島', 'water_type': '海水', 'in_strength': 'strong', 'c1_rate': 60.66},
    '17': {'name': '宮島', 'water_type': '海水', 'in_strength': 'strong', 'c1_rate': 61.84},
    '18': {'name': '徳山', 'water_type': '海水', 'in_strength': 'very_strong', 'c1_rate': 66.41},
    '19': {'name': '下関', 'water_type': '海水', 'in_strength': 'strong', 'c1_rate': 62.61},
    '20': {'name': '若松', 'water_type': '海水', 'in_strength': 'normal', 'c1_rate': 58.48},
    '21': {'name': '芦屋', 'water_type': '淡水', 'in_strength': 'normal', 'c1_rate': 57.81},
    '22': {'name': '福岡', 'water_type': '海水', 'in_strength': 'normal', 'c1_rate': 58.53},
    '23': {'name': '唐津', 'water_type': '海水', 'in_strength': 'normal', 'c1_rate': 55.21},
    '24': {'name': '大村', 'water_type': '海水', 'in_strength': 'very_strong', 'c1_rate': 65.80},
}

# 会場の予測安定性（標準偏差に基づく）
VENUE_STABILITY = {
    # 安定会場（予測しやすい）- std < 8.0
    'stable': ['13', '23', '02', '03', '12', '01', '14', '08'],
    # 中程度 - 8.0 <= std < 10.0
    'moderate': ['20', '07', '15', '16', '10', '24', '04', '22'],
    # 不安定（予測が難しい）- std >= 10.0
    'unstable': ['11', '18', '05', '06', '21', '09', '19', '17'],
}

# 特別な注意が必要な会場
SPECIAL_VENUES = {
    # 荒れやすい会場（波・風の影響大）
    'rough': ['03', '14', '06', '09'],  # 江戸川、鳴門、浜名湖、津

    # イン逃げ率が特に高い会場
    'in_dominant': ['18', '24', '19'],  # 徳山、大村、下関

    # まくり/差しが決まりやすい会場
    'upset_prone': ['02', '04', '01'],  # 戸田、平和島、桐生
}


@dataclass
class VenueCondition:
    """会場条件の評価結果"""
    venue_code: str
    venue_name: str
    wind_speed: float
    wave_height: Optional[float] = None

    # 評価結果
    should_bet: bool = True
    confidence_modifier: float = 1.0  # 信頼度への乗数
    score_modifier: float = 1.0       # スコアへの乗数

    # 詳細
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    exclusion_reason: Optional[str] = None


class VenueEvaluator:
    """会場評価クラス"""

    def __init__(self, strict_mode: bool = False):
        """
        初期化

        Args:
            strict_mode: 厳格モード（除外条件を厳しくする）
        """
        self.strict_mode = strict_mode

    def evaluate(
        self,
        venue_code: str,
        wind_speed: float,
        wave_height: Optional[float] = None,
        confidence: Optional[str] = None,
        predicted_pit: Optional[int] = None
    ) -> VenueCondition:
        """
        会場条件を評価

        Args:
            venue_code: 会場コード
            wind_speed: 風速 (m/s)
            wave_height: 波高 (cm)
            confidence: 予測信頼度 ('A', 'B', 'C', 'D', 'E')
            predicted_pit: 予測1着コース (1-6)

        Returns:
            VenueCondition: 評価結果
        """
        venue_info = VENUE_INFO.get(venue_code, {})
        venue_name = venue_info.get('name', '不明')

        result = VenueCondition(
            venue_code=venue_code,
            venue_name=venue_name,
            wind_speed=wind_speed,
            wave_height=wave_height
        )

        # 評価項目
        self._evaluate_wind_conditions(result, venue_info)
        self._evaluate_venue_stability(result)
        self._evaluate_wave_conditions(result, venue_info)
        self._evaluate_special_conditions(result, venue_info, predicted_pit)
        self._evaluate_confidence_compatibility(result, confidence, predicted_pit)

        # 最終判定
        self._make_final_decision(result, confidence)

        return result

    def _evaluate_wind_conditions(
        self,
        result: VenueCondition,
        venue_info: Dict
    ):
        """風速条件を評価"""
        wind_speed = result.wind_speed

        # 超強風（6m以上）
        if wind_speed >= 6.0:
            result.warnings.append(f"超強風（{wind_speed}m）")
            result.confidence_modifier *= 0.7
            result.score_modifier *= 0.85

            if self.strict_mode:
                result.should_bet = False
                result.exclusion_reason = f"超強風（{wind_speed}m）のため除外"

        # 強風（4-6m）
        elif wind_speed >= 4.0:
            result.warnings.append(f"強風（{wind_speed}m）")
            result.confidence_modifier *= 0.85
            result.score_modifier *= 0.95

        # 微風（0-2m）
        elif wind_speed < 2.0:
            result.recommendations.append("微風時はインコース有利")
            result.score_modifier *= 1.02  # わずかに有利

    def _evaluate_venue_stability(self, result: VenueCondition):
        """会場安定性を評価"""
        venue_code = result.venue_code

        if venue_code in VENUE_STABILITY['unstable']:
            result.warnings.append("不安定会場（予測精度が低い傾向）")
            result.confidence_modifier *= 0.9

            # 強風との組み合わせ
            if result.wind_speed >= 4.0:
                result.warnings.append("不安定会場＋強風の組み合わせ")
                result.confidence_modifier *= 0.85

                if self.strict_mode:
                    result.should_bet = False
                    result.exclusion_reason = "不安定会場＋強風のため除外"

        elif venue_code in VENUE_STABILITY['stable']:
            result.recommendations.append("安定会場（予測精度が高い傾向）")
            result.confidence_modifier *= 1.05

    def _evaluate_wave_conditions(
        self,
        result: VenueCondition,
        venue_info: Dict
    ):
        """波高条件を評価"""
        wave_height = result.wave_height

        if wave_height is None:
            return

        # 高波（5cm以上）
        if wave_height >= 5:
            result.warnings.append(f"高波（{wave_height}cm）")
            result.confidence_modifier *= 0.85
            result.score_modifier *= 0.9

        # 海水会場での波の影響
        if venue_info.get('water_type') == '海水' and wave_height >= 3:
            result.warnings.append("海水会場での波の影響あり")

    def _evaluate_special_conditions(
        self,
        result: VenueCondition,
        venue_info: Dict,
        predicted_pit: Optional[int]
    ):
        """特殊条件を評価"""
        venue_code = result.venue_code

        # 荒れやすい会場
        if venue_code in SPECIAL_VENUES['rough']:
            if result.wind_speed >= 4.0 or (result.wave_height and result.wave_height >= 3):
                result.warnings.append("荒れやすい会場での悪天候")
                result.confidence_modifier *= 0.85

        # イン支配の会場での予測
        if venue_code in SPECIAL_VENUES['in_dominant']:
            if predicted_pit == 1:
                result.recommendations.append("インが非常に強い会場")
                result.score_modifier *= 1.05
            elif predicted_pit and predicted_pit >= 4:
                result.warnings.append("インが強い会場でのアウト予測")
                result.confidence_modifier *= 0.9

        # 荒れやすい会場でのイン予測
        if venue_code in SPECIAL_VENUES['upset_prone']:
            if predicted_pit == 1:
                result.warnings.append("荒れやすい会場でのイン予測")
                result.confidence_modifier *= 0.95

    def _evaluate_confidence_compatibility(
        self,
        result: VenueCondition,
        confidence: Optional[str],
        predicted_pit: Optional[int]
    ):
        """信頼度と予測の整合性を評価"""
        if confidence is None:
            return

        # 低信頼度＋不安定会場
        if confidence in ['D', 'E']:
            if result.venue_code in VENUE_STABILITY['unstable']:
                result.warnings.append("低信頼度＋不安定会場")
                result.should_bet = False
                result.exclusion_reason = "低信頼度＋不安定会場のため除外"

        # 低信頼度＋強風
        if confidence in ['C', 'D', 'E'] and result.wind_speed >= 6.0:
            result.warnings.append("低信頼度＋超強風")
            result.should_bet = False
            result.exclusion_reason = "低信頼度＋超強風のため除外"

    def _make_final_decision(
        self,
        result: VenueCondition,
        confidence: Optional[str]
    ):
        """最終判定"""
        # 信頼度修正値の下限/上限
        result.confidence_modifier = max(0.5, min(1.2, result.confidence_modifier))
        result.score_modifier = max(0.7, min(1.3, result.score_modifier))

        # 追加の推奨事項
        if result.warnings and not result.exclusion_reason:
            if len(result.warnings) >= 3:
                result.recommendations.append("複数の警告あり - 慎重な判断を推奨")
            elif len(result.warnings) >= 2:
                result.recommendations.append("注意が必要な条件")

        # 良好条件の場合
        if not result.warnings and result.recommendations:
            result.recommendations.append("好条件のためベット推奨")

    def get_venue_summary(self, venue_code: str) -> Dict:
        """
        会場のサマリー情報を取得

        Args:
            venue_code: 会場コード

        Returns:
            会場サマリーの辞書
        """
        venue_info = VENUE_INFO.get(venue_code, {})

        # 安定性カテゴリを判定
        if venue_code in VENUE_STABILITY['stable']:
            stability = 'stable'
        elif venue_code in VENUE_STABILITY['unstable']:
            stability = 'unstable'
        else:
            stability = 'moderate'

        # 特殊カテゴリ
        categories = []
        if venue_code in SPECIAL_VENUES['rough']:
            categories.append('荒れやすい')
        if venue_code in SPECIAL_VENUES['in_dominant']:
            categories.append('インが強い')
        if venue_code in SPECIAL_VENUES['upset_prone']:
            categories.append('波乱が多い')

        return {
            'code': venue_code,
            'name': venue_info.get('name', '不明'),
            'water_type': venue_info.get('water_type', '不明'),
            'in_strength': venue_info.get('in_strength', 'normal'),
            'course1_win_rate': venue_info.get('c1_rate', 55.0),
            'stability': stability,
            'special_categories': categories,
        }

    def should_exclude_venue(
        self,
        venue_code: str,
        wind_speed: float,
        confidence: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        会場を除外すべきか簡易判定

        Args:
            venue_code: 会場コード
            wind_speed: 風速
            confidence: 信頼度

        Returns:
            (除外すべきか, 理由)
        """
        result = self.evaluate(
            venue_code=venue_code,
            wind_speed=wind_speed,
            confidence=confidence
        )

        return not result.should_bet, result.exclusion_reason or ""


def get_venue_condition_adjustment(
    venue_code: str,
    wind_speed: float,
    wave_height: Optional[float] = None,
    confidence: Optional[str] = None,
    predicted_pit: Optional[int] = None
) -> Dict:
    """
    会場条件に基づく調整情報を取得（便利関数）

    Args:
        venue_code: 会場コード
        wind_speed: 風速
        wave_height: 波高
        confidence: 信頼度
        predicted_pit: 予測1着コース

    Returns:
        調整情報の辞書
    """
    evaluator = VenueEvaluator()
    result = evaluator.evaluate(
        venue_code=venue_code,
        wind_speed=wind_speed,
        wave_height=wave_height,
        confidence=confidence,
        predicted_pit=predicted_pit
    )

    return {
        'venue_code': result.venue_code,
        'venue_name': result.venue_name,
        'should_bet': result.should_bet,
        'confidence_modifier': result.confidence_modifier,
        'score_modifier': result.score_modifier,
        'warnings': result.warnings,
        'recommendations': result.recommendations,
        'exclusion_reason': result.exclusion_reason,
    }


# ==============================================================================
# 会場別の推奨戦略
# ==============================================================================
VENUE_STRATEGIES = {
    # イン強会場（1コース重視）
    'in_strong': {
        'venues': ['18', '24', '19', '17', '13', '12', '07', '16', '08', '09'],
        'strategy': '1コース1着を軸に堅実な舟券を推奨',
        'preferred_patterns': ['1-X-X', '1-2-X', '1-3-X'],
        'risk_level': 'low',
    },

    # イン弱会場（波乱注意）
    'in_weak': {
        'venues': ['02', '04', '14', '03', '01'],
        'strategy': 'アウト差し/まくりを考慮した広めの舟券を推奨',
        'preferred_patterns': ['2-X-X', '3-X-X', '4-X-X'],
        'risk_level': 'high',
    },

    # 標準会場
    'normal': {
        'venues': ['05', '06', '10', '11', '15', '20', '21', '22', '23'],
        'strategy': '通常のパターンH戦略を適用',
        'preferred_patterns': ['通常'],
        'risk_level': 'medium',
    },
}


def get_venue_strategy(venue_code: str) -> Dict:
    """
    会場別の推奨戦略を取得

    Args:
        venue_code: 会場コード

    Returns:
        戦略情報の辞書
    """
    for strategy_type, info in VENUE_STRATEGIES.items():
        if venue_code in info['venues']:
            return {
                'type': strategy_type,
                'strategy': info['strategy'],
                'preferred_patterns': info['preferred_patterns'],
                'risk_level': info['risk_level'],
            }

    # デフォルト
    return {
        'type': 'normal',
        'strategy': '通常のパターンH戦略を適用',
        'preferred_patterns': ['通常'],
        'risk_level': 'medium',
    }
