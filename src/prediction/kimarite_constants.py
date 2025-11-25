"""
決まり手予測のための定数定義

決まり手の種類、会場マスタ、コース別基本確率などを定義
"""

from enum import IntEnum
from typing import Dict, List


class Kimarite(IntEnum):
    """決まり手の定義（winning_techniqueの値に対応）"""
    NIGE = 1           # 逃げ
    SASHI = 2          # 差し
    MAKURI = 3         # まくり
    MAKURI_SASHI = 4   # まくり差し
    NUKI = 5           # 抜き
    MEGUMARE = 6       # 恵まれ


# 決まり手の日本語名マッピング
KIMARITE_NAMES = {
    Kimarite.NIGE: "逃げ",
    Kimarite.SASHI: "差し",
    Kimarite.MAKURI: "まくり",
    Kimarite.MAKURI_SASHI: "まくり差し",
    Kimarite.NUKI: "抜き",
    Kimarite.MEGUMARE: "恵まれ"
}


# コース別決まり手事前確率（全国平均）
# 統計データに基づく基本確率
COURSE_KIMARITE_PRIOR = {
    1: {  # 1コース
        Kimarite.NIGE: 0.950,
        Kimarite.SASHI: 0.005,
        Kimarite.MAKURI: 0.010,
        Kimarite.MAKURI_SASHI: 0.005,
        Kimarite.NUKI: 0.025,
        Kimarite.MEGUMARE: 0.005
    },
    2: {  # 2コース
        Kimarite.NIGE: 0.020,
        Kimarite.SASHI: 0.650,
        Kimarite.MAKURI: 0.250,
        Kimarite.MAKURI_SASHI: 0.030,
        Kimarite.NUKI: 0.040,
        Kimarite.MEGUMARE: 0.010
    },
    3: {  # 3コース
        Kimarite.NIGE: 0.005,
        Kimarite.SASHI: 0.150,
        Kimarite.MAKURI: 0.400,
        Kimarite.MAKURI_SASHI: 0.350,
        Kimarite.NUKI: 0.080,
        Kimarite.MEGUMARE: 0.015
    },
    4: {  # 4コース
        Kimarite.NIGE: 0.002,
        Kimarite.SASHI: 0.200,
        Kimarite.MAKURI: 0.450,
        Kimarite.MAKURI_SASHI: 0.300,
        Kimarite.NUKI: 0.040,
        Kimarite.MEGUMARE: 0.008
    },
    5: {  # 5コース
        Kimarite.NIGE: 0.001,
        Kimarite.SASHI: 0.100,
        Kimarite.MAKURI: 0.250,
        Kimarite.MAKURI_SASHI: 0.550,
        Kimarite.NUKI: 0.090,
        Kimarite.MEGUMARE: 0.009
    },
    6: {  # 6コース
        Kimarite.NIGE: 0.001,
        Kimarite.SASHI: 0.150,
        Kimarite.MAKURI: 0.300,
        Kimarite.MAKURI_SASHI: 0.450,
        Kimarite.NUKI: 0.090,
        Kimarite.MEGUMARE: 0.009
    }
}


# 会場別水質情報
VENUE_WATER_QUALITY = {
    '01': '淡水',  # 桐生
    '02': '淡水',  # 戸田
    '03': '汽水',  # 江戸川
    '04': '淡水',  # 平和島（海水）→実際は海水だが、淡水的な特性
    '05': '淡水',  # 多摩川
    '06': '淡水',  # 浜名湖
    '07': '淡水',  # 蒲郡
    '08': '淡水',  # 常滑
    '09': '淡水',  # 津
    '10': '淡水',  # 三国
    '11': '淡水',  # びわこ
    '12': '淡水',  # 住之江
    '13': '汽水',  # 尼崎
    '14': '海水',  # 鳴門
    '15': '海水',  # 丸亀
    '16': '海水',  # 児島
    '17': '海水',  # 宮島
    '18': '海水',  # 徳山
    '19': '海水',  # 下関
    '20': '海水',  # 若松
    '21': '海水',  # 芦屋
    '22': '海水',  # 福岡
    '23': '海水',  # 唐津
    '24': '海水',  # 大村
}


# 会場別特性（インコース有利度）
# 1.0が標準、1.2なら1コース有利、0.8なら不利
VENUE_INNER_ADVANTAGE = {
    '01': 1.0,   # 桐生
    '02': 1.3,   # 戸田（超インコース有利）
    '03': 1.2,   # 江戸川（インコース有利）
    '04': 0.9,   # 平和島（センター有利）
    '05': 1.0,   # 多摩川
    '06': 1.1,   # 浜名湖
    '07': 1.0,   # 蒲郡
    '08': 1.0,   # 常滑
    '09': 1.0,   # 津
    '10': 1.0,   # 三国
    '11': 1.2,   # びわこ（インコース有利）
    '12': 1.1,   # 住之江
    '13': 0.9,   # 尼崎（センター有利）
    '14': 1.0,   # 鳴門
    '15': 1.0,   # 丸亀
    '16': 1.0,   # 児島
    '17': 1.1,   # 宮島
    '18': 0.9,   # 徳山（センター有利）
    '19': 0.9,   # 下関（センター有利）
    '20': 1.0,   # 若松
    '21': 1.0,   # 芦屋
    '22': 1.0,   # 福岡
    '23': 0.9,   # 唐津（センター有利）
    '24': 1.1,   # 大村
}


# 風向の数値化（度数法）
WIND_DIRECTION_DEGREES = {
    '北': 0,
    '北北東': 22.5,
    '北東': 45,
    '東北東': 67.5,
    '東': 90,
    '東南東': 112.5,
    '南東': 135,
    '南南東': 157.5,
    '南': 180,
    '南南西': 202.5,
    '南西': 225,
    '西南西': 247.5,
    '西': 270,
    '西北西': 292.5,
    '北西': 315,
    '北北西': 337.5,
}


def get_wind_effect(wind_direction: str, wind_speed: float, venue_code: str) -> Dict[str, float]:
    """
    風の影響を数値化

    Args:
        wind_direction: 風向（テキスト）
        wind_speed: 風速（m/s）
        venue_code: 会場コード

    Returns:
        {'追い風成分': float, '向かい風成分': float, '横風成分': float}
    """
    if not wind_direction or wind_speed is None:
        return {'追い風': 0.0, '向かい風': 0.0, '横風': 0.0}

    # 風向を度数に変換
    degrees = WIND_DIRECTION_DEGREES.get(wind_direction, 0)

    # 会場のコース向き（仮定: 0度が正面）
    # 実際の会場ごとのコース向きは別途定義が必要
    # ここでは簡略化のため、北を向かい風、南を追い風とする

    # 追い風成分（0-180度が追い風傾向）
    if degrees <= 180:
        tailwind = wind_speed * (1 - abs(degrees - 90) / 90)
        headwind = 0
    else:
        tailwind = 0
        headwind = wind_speed * (1 - abs(degrees - 270) / 90)

    # 横風成分
    crosswind = wind_speed * abs(90 - (degrees % 180)) / 90

    return {
        '追い風': max(0, tailwind),
        '向かい風': max(0, headwind),
        '横風': max(0, crosswind)
    }


def estimate_motor_output_type(motor_2tan_rate: float, exhibition_time: float = None) -> str:
    """
    モーター性能から出力特性を推定

    Args:
        motor_2tan_rate: モーター2連率
        exhibition_time: 展示タイム（あれば）

    Returns:
        '出足型' or '伸び型' or 'バランス型'
    """
    if motor_2tan_rate is None:
        return 'バランス型'

    # 高性能モーター
    if motor_2tan_rate >= 0.40:
        if exhibition_time and exhibition_time <= 6.70:
            return '伸び型'  # タイムが速い = 伸び型
        else:
            return 'バランス型'

    # 中性能モーター
    elif motor_2tan_rate >= 0.30:
        return 'バランス型'

    # 低性能モーター
    else:
        return '出足型'  # 低性能でも出足で勝負


# STタイミングの評価基準
ST_EXCELLENT = 0.10  # 優秀なST
ST_GOOD = 0.15       # 良好なST
ST_AVERAGE = 0.17    # 平均的なST
ST_POOR = 0.20       # 遅いST


# 決まり手ごとの成功に必要な要素
KIMARITE_SUCCESS_FACTORS = {
    Kimarite.NIGE: {
        'ST': 0.4,           # STの重要度
        'motor': 0.3,        # モーター性能の重要度
        'skill': 0.2,        # 選手技術の重要度
        'course': 0.1        # コース有利度の重要度
    },
    Kimarite.SASHI: {
        'ST': 0.2,
        'motor': 0.3,
        'skill': 0.4,
        'course': 0.1
    },
    Kimarite.MAKURI: {
        'ST': 0.5,           # まくりはSTが最重要
        'motor': 0.3,
        'skill': 0.2,
        'course': 0.0
    },
    Kimarite.MAKURI_SASHI: {
        'ST': 0.4,
        'motor': 0.2,
        'skill': 0.3,
        'course': 0.1
    },
    Kimarite.NUKI: {
        'ST': 0.1,
        'motor': 0.5,        # 抜きはモーター性能が重要
        'skill': 0.3,
        'course': 0.1
    },
    Kimarite.MEGUMARE: {
        'ST': 0.0,
        'motor': 0.0,
        'skill': 0.0,
        'course': 0.0        # 恵まれは運次第
    }
}
