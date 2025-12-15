# -*- coding: utf-8 -*-
"""
会場×風速補正係数
2024-2025年データから算出（約29,000レース分析結果）

使用方法:
from config.venue_wind_adjustments import (
    get_wind_coefficient,
    get_venue_coefficient,
    apply_wind_venue_adjustment,
    should_exclude_race
)

# 風速による補正
coef = get_wind_coefficient(wind_speed=5.0, pit_number=1)  # 0.95など

# 会場による補正
coef = get_venue_coefficient(venue_code='01', pit_number=1)  # 0.91など

# 複合補正
adjusted = apply_wind_venue_adjustment(base_score=10.0, venue_code='01', wind_speed=6.0, pit_number=1)

# 除外判定
exclude = should_exclude_race(venue_code='01', wind_speed=6.0)
"""

from typing import Dict, Optional, Tuple

# ==============================================================================
# 風速レンジ別 コース別係数
# ベースライン(全体平均)を1.0とした相対係数
# 2024-2025年 約29,000レースから算出
# ==============================================================================
WIND_SPEED_COEFFICIENTS = {
    '0-2m': {
        1: 1.0356,   # 微風時は1コース勝率UP (+3.56%)
        2: 0.9324,   # 微風時は2コース勝率DOWN (-6.76%)
        3: 0.9684,
        4: 0.9609,
        5: 0.9418,
        6: 0.9769,
    },
    '2-4m': {
        1: 0.9941,   # 通常風速ではほぼ変化なし
        2: 1.0149,
        3: 0.9829,
        4: 1.0080,
        5: 1.0249,
        6: 1.0210,
    },
    '4-6m': {
        1: 1.0024,
        2: 0.9965,
        3: 1.0555,   # やや強風時は3コース勝率UP (+5.55%)
        4: 0.9560,
        5: 0.9665,
        6: 0.9510,
    },
    '6m+': {
        1: 0.9068,   # 強風時は1コース勝率大幅DOWN (-9.32%)
        2: 1.1565,   # 強風時は2コース勝率大幅UP (+15.65%)
        3: 1.0531,
        4: 1.1869,   # 強風時は4コース勝率大幅UP (+18.69%)
        5: 1.1705,   # 強風時は5コース勝率大幅UP (+17.05%)
        6: 1.0700,
    },
}

# ==============================================================================
# 会場別 1コース補正係数
# 全国平均(57.35%)を1.0とした相対係数
# ==============================================================================
VENUE_COURSE1_COEFFICIENTS = {
    '18': 1.1579,  # 徳山: 66.41% - イン最強クラス
    '24': 1.1473,  # 大村: 65.80% - イン最強クラス
    '19': 1.0916,  # 下関: 62.61%
    '17': 1.0782,  # 宮島: 61.84%
    '13': 1.0777,  # 尼崎: 61.81%
    '12': 1.0654,  # 住之江: 61.11%
    '07': 1.0591,  # 蒲郡: 60.74%
    '16': 1.0577,  # 児島: 60.66%
    '08': 1.0559,  # 常滑: 60.56%
    '09': 1.0525,  # 津: 60.37%
    '11': 1.0262,  # びわこ: 58.85%
    '22': 1.0205,  # 福岡: 58.53%
    '20': 1.0197,  # 若松: 58.48%
    '15': 1.0142,  # 丸亀: 58.17%
    '21': 1.0079,  # 芦屋: 57.81%
    '10': 0.9810,  # 三国: 56.26%
    '06': 0.9638,  # 浜名湖: 55.28%
    '23': 0.9626,  # 唐津: 55.21%
    '05': 0.9513,  # 多摩川: 54.56%
    '01': 0.9054,  # 桐生: 51.93% - イン弱会場
    '03': 0.8638,  # 江戸川: 49.54% - イン弱会場
    '14': 0.8633,  # 鳴門: 49.51% - イン弱会場
    '04': 0.8051,  # 平和島: 46.18% - イン最弱
    '02': 0.7997,  # 戸田: 45.87% - イン最弱
}

# ==============================================================================
# 会場別全コース係数
# 各コースの全国平均に対する相対係数
# ==============================================================================
VENUE_ALL_COURSE_COEFFICIENTS = {
    # venue_code: {pit_number: coefficient}
    '01': {1: 0.9054, 2: 0.9451, 3: 1.0576, 4: 1.3558, 5: 1.2656, 6: 1.1329},  # 桐生（アウト有利）
    '02': {1: 0.7997, 2: 1.2538, 3: 1.2691, 4: 1.2452, 5: 1.1873, 6: 1.4930},  # 戸田（イン不利）
    '03': {1: 0.8638, 2: 1.3766, 3: 1.0477, 4: 1.1980, 5: 1.1747, 6: 0.9650},  # 江戸川
    '04': {1: 0.8051, 2: 1.3123, 3: 1.2395, 4: 1.1478, 5: 1.2353, 6: 1.6538},  # 平和島
    '05': {1: 0.9513, 2: 1.0023, 3: 1.0165, 4: 1.0955, 5: 1.1337, 6: 1.0629},  # 多摩川
    '06': {1: 0.9638, 2: 1.0008, 3: 1.0551, 4: 0.9598, 5: 1.2014, 6: 1.1643},  # 浜名湖
    '07': {1: 1.0591, 2: 0.8639, 3: 0.8757, 4: 1.0764, 5: 0.9304, 6: 0.7797},  # 蒲郡
    '08': {1: 1.0559, 2: 0.9505, 3: 0.8346, 4: 0.9146, 5: 1.0749, 6: 0.9231},  # 常滑
    '09': {1: 1.0525, 2: 0.9317, 3: 0.8395, 4: 0.9347, 5: 1.0891, 6: 0.9650},  # 津
    '10': {1: 0.9810, 2: 1.0436, 3: 1.1119, 4: 0.8563, 5: 1.0767, 6: 1.1643},  # 三国
    '11': {1: 1.0262, 2: 0.8859, 3: 1.0724, 4: 1.0241, 5: 1.0018, 6: 0.6259},  # びわこ
    '12': {1: 1.0654, 2: 0.9278, 3: 0.9424, 4: 0.8553, 5: 1.0767, 6: 0.9021},  # 住之江
    '13': {1: 1.0777, 2: 0.7913, 3: 1.0675, 4: 0.9859, 5: 0.8092, 6: 0.4231},  # 尼崎
    '14': {1: 0.8633, 2: 1.1244, 3: 1.2067, 4: 1.2653, 5: 1.1836, 6: 1.1713},  # 鳴門
    '15': {1: 1.0142, 2: 1.0593, 3: 1.0190, 4: 0.8251, 5: 1.0428, 6: 0.8986},  # 丸亀
    '16': {1: 1.0577, 2: 0.9044, 3: 0.8420, 4: 0.9407, 5: 0.9679, 6: 1.0559},  # 児島
    '17': {1: 1.0782, 2: 0.8123, 3: 0.8856, 4: 0.8312, 5: 1.0695, 6: 1.1329},  # 宮島
    '18': {1: 1.1579, 2: 0.9166, 3: 0.8338, 4: 0.6975, 5: 0.4956, 6: 0.7762},  # 徳山
    '19': {1: 1.0916, 2: 0.8649, 3: 0.9037, 4: 0.8513, 5: 0.7808, 6: 1.0350},  # 下関
    '20': {1: 1.0197, 2: 0.9962, 3: 0.8058, 4: 1.0834, 5: 1.0713, 6: 1.0105},  # 若松
    '21': {1: 1.0079, 2: 0.9189, 3: 0.9119, 4: 1.1578, 5: 0.9750, 6: 1.0944},  # 芦屋
    '22': {1: 1.0205, 2: 1.0458, 3: 1.2790, 4: 0.8754, 5: 0.4545, 6: 0.7692},  # 福岡
    '23': {1: 0.9626, 2: 1.2020, 3: 0.9095, 4: 1.0040, 5: 0.9162, 6: 1.2343},  # 唐津
    '24': {1: 1.1473, 2: 0.8649, 3: 0.9070, 4: 0.7709, 5: 0.6899, 6: 0.5490},  # 大村
}

# ==============================================================================
# 会場安定性ランキング（標準偏差が小さい順 = 予測しやすい順）
# ==============================================================================
VENUE_STABILITY = {
    # 安定会場（予測しやすい）
    '13': {'rank': 1, 'std': 6.77, 'category': 'stable'},       # 尼崎
    '23': {'rank': 2, 'std': 6.83, 'category': 'stable'},       # 唐津
    '02': {'rank': 3, 'std': 6.90, 'category': 'stable'},       # 戸田
    '03': {'rank': 4, 'std': 7.07, 'category': 'stable'},       # 江戸川
    '12': {'rank': 5, 'std': 7.16, 'category': 'stable'},       # 住之江
    '01': {'rank': 6, 'std': 7.58, 'category': 'stable'},       # 桐生
    '14': {'rank': 7, 'std': 7.75, 'category': 'stable'},       # 鳴門
    '08': {'rank': 8, 'std': 7.98, 'category': 'stable'},       # 常滑

    # 中程度の安定性
    '20': {'rank': 9, 'std': 8.25, 'category': 'moderate'},     # 若松
    '07': {'rank': 10, 'std': 8.29, 'category': 'moderate'},    # 蒲郡
    '15': {'rank': 11, 'std': 8.79, 'category': 'moderate'},    # 丸亀
    '16': {'rank': 12, 'std': 8.84, 'category': 'moderate'},    # 児島
    '10': {'rank': 13, 'std': 9.24, 'category': 'moderate'},    # 三国
    '24': {'rank': 14, 'std': 9.34, 'category': 'moderate'},    # 大村
    '04': {'rank': 15, 'std': 9.44, 'category': 'moderate'},    # 平和島
    '22': {'rank': 16, 'std': 9.54, 'category': 'moderate'},    # 福岡

    # 不安定会場（予測が難しい）
    '11': {'rank': 17, 'std': 9.64, 'category': 'unstable'},    # びわこ
    '18': {'rank': 18, 'std': 9.78, 'category': 'unstable'},    # 徳山
    '05': {'rank': 19, 'std': 10.07, 'category': 'unstable'},   # 多摩川
    '06': {'rank': 20, 'std': 10.45, 'category': 'unstable'},   # 浜名湖
    '21': {'rank': 21, 'std': 10.45, 'category': 'unstable'},   # 芦屋
    '09': {'rank': 22, 'std': 10.59, 'category': 'unstable'},   # 津
    '19': {'rank': 23, 'std': 10.60, 'category': 'unstable'},   # 下関
    '17': {'rank': 24, 'std': 10.71, 'category': 'unstable'},   # 宮島
}

# ==============================================================================
# ベースライン勝率（%）
# ==============================================================================
BASELINE_WIN_RATES = {
    1: 57.35,
    2: 13.32,
    3: 12.15,
    4: 9.95,
    5: 5.61,
    6: 2.86,
}

# ==============================================================================
# ヘルパー関数
# ==============================================================================

def get_wind_speed_range(wind_speed: float) -> str:
    """風速を範囲に変換"""
    if wind_speed is None:
        return '2-4m'  # デフォルト
    if wind_speed < 2:
        return '0-2m'
    elif wind_speed < 4:
        return '2-4m'
    elif wind_speed < 6:
        return '4-6m'
    else:
        return '6m+'


def get_wind_coefficient(wind_speed: float, pit_number: int) -> float:
    """
    風速による補正係数を取得

    Args:
        wind_speed: 風速 (m/s)
        pit_number: コース番号 (1-6)

    Returns:
        float: 補正係数 (1.0 = 変化なし)
    """
    wind_range = get_wind_speed_range(wind_speed)
    return WIND_SPEED_COEFFICIENTS.get(wind_range, {}).get(pit_number, 1.0)


def get_venue_coefficient(venue_code: str, pit_number: int = 1) -> float:
    """
    会場による補正係数を取得

    Args:
        venue_code: 会場コード ('01'-'24')
        pit_number: コース番号 (デフォルト: 1)

    Returns:
        float: 補正係数 (1.0 = 平均的な会場)
    """
    if pit_number == 1:
        return VENUE_COURSE1_COEFFICIENTS.get(venue_code, 1.0)

    # 全コース係数を使用
    venue_coefs = VENUE_ALL_COURSE_COEFFICIENTS.get(venue_code, {})
    return venue_coefs.get(pit_number, 1.0)


def get_venue_stability(venue_code: str) -> Dict:
    """
    会場の安定性情報を取得

    Args:
        venue_code: 会場コード

    Returns:
        安定性情報の辞書
    """
    return VENUE_STABILITY.get(venue_code, {
        'rank': 12,
        'std': 9.0,
        'category': 'moderate'
    })


def apply_wind_venue_adjustment(
    base_score: float,
    venue_code: str,
    wind_speed: float,
    pit_number: int,
    mode: str = 'multiplicative'
) -> float:
    """
    風速・会場補正を適用

    Args:
        base_score: 元のスコア
        venue_code: 会場コード
        wind_speed: 風速
        pit_number: コース番号
        mode: 'multiplicative'（乗算）または 'additive'（加算）

    Returns:
        float: 補正後スコア
    """
    wind_coef = get_wind_coefficient(wind_speed, pit_number)
    venue_coef = get_venue_coefficient(venue_code, pit_number)

    if mode == 'multiplicative':
        # 乗算モード: 両方の係数を掛け合わせる
        # ただし、極端な値を避けるため0.7-1.4の範囲に制限
        combined_coef = wind_coef * venue_coef
        combined_coef = max(0.7, min(1.4, combined_coef))
        return base_score * combined_coef
    else:
        # 加算モード: 係数の平均を使用
        combined_coef = (wind_coef + venue_coef) / 2
        return base_score * combined_coef


def should_exclude_race(
    venue_code: str,
    wind_speed: float,
    confidence: Optional[str] = None
) -> Tuple[bool, str]:
    """
    レースを除外すべきか判定

    Args:
        venue_code: 会場コード
        wind_speed: 風速
        confidence: 信頼度（'A', 'B', 'C', 'D', 'E'）

    Returns:
        (除外すべきか, 理由)
    """
    stability = get_venue_stability(venue_code)

    # 超強風（6m以上）は常に注意
    if wind_speed >= 6.0:
        if stability['category'] == 'unstable':
            return True, f"超強風（{wind_speed}m）かつ不安定会場"

        if confidence in ['D', 'E']:
            return True, f"超強風（{wind_speed}m）かつ低信頼度"

    # 不安定会場 + 強風（4m以上）
    if stability['category'] == 'unstable' and wind_speed >= 4.0:
        if confidence in ['C', 'D', 'E']:
            return True, f"不安定会場（std={stability['std']:.1f}）かつ強風（{wind_speed}m）"

    return False, ""


def get_recommended_bet_adjustment(
    venue_code: str,
    wind_speed: float,
    pit_number: int
) -> Dict:
    """
    推奨ベット調整を取得

    Args:
        venue_code: 会場コード
        wind_speed: 風速
        pit_number: コース番号

    Returns:
        調整情報の辞書
    """
    wind_coef = get_wind_coefficient(wind_speed, pit_number)
    venue_coef = get_venue_coefficient(venue_code, pit_number)
    stability = get_venue_stability(venue_code)

    # 総合的な調整レベルを判定
    combined_coef = wind_coef * venue_coef

    if combined_coef >= 1.15:
        adjustment_level = 'increase'
        recommendation = 'ベット額を増やすことを検討'
    elif combined_coef <= 0.85:
        adjustment_level = 'decrease'
        recommendation = 'ベット額を減らすか見送りを検討'
    else:
        adjustment_level = 'normal'
        recommendation = '通常通り'

    # 安定性による補足
    if stability['category'] == 'unstable' and wind_speed >= 4.0:
        recommendation += '（不安定会場につき注意）'

    return {
        'wind_coefficient': wind_coef,
        'venue_coefficient': venue_coef,
        'combined_coefficient': combined_coef,
        'adjustment_level': adjustment_level,
        'recommendation': recommendation,
        'venue_stability': stability['category'],
    }


# ==============================================================================
# 主要な発見のサマリー（コメント）
# ==============================================================================
"""
【風速の影響 - 主要な発見】

1. 超強風（6m+）時の影響が非常に大きい
   - 1コース勝率: -9.32%（57.35% → 52.01%）
   - 2コース勝率: +15.65%（13.32% → 15.41%）
   - 4コース勝率: +18.69%（9.95% → 11.81%）
   - 5コース勝率: +17.05%（5.61% → 6.57%）

2. 微風（0-2m）時はインコース有利
   - 1コース勝率: +3.56%（57.35% → 59.40%）
   - アウトコースは軒並み不利

3. 通常風速（2-4m）はほぼ影響なし

【会場特性 - 主要な発見】

1. イン強会場（1コース勝率60%+）
   - 徳山(66.4%), 大村(65.8%), 下関(62.6%), 宮島(61.8%), 尼崎(61.8%)

2. イン弱会場（1コース勝率52%未満）
   - 戸田(45.9%), 平和島(46.2%), 鳴門(49.5%), 江戸川(49.5%), 桐生(51.9%)

3. 予測が難しい会場（高ボラティリティ）
   - 宮島(std=10.71), 下関(std=10.60), 津(std=10.59)
   - これらの会場では信頼度を下げるべき

4. 予測しやすい会場（低ボラティリティ）
   - 尼崎(std=6.77), 唐津(std=6.83), 戸田(std=6.90)

【推奨アクション】

1. 強風時（4m+）のインコース予測を下方修正
2. 超強風時（6m+）は2,4,5コースを上方修正
3. 不安定会場 + 強風の組み合わせでは除外を検討
4. 会場特性を考慮した補正係数を適用
"""
