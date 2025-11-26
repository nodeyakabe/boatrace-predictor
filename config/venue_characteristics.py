"""
会場特性データ
歴史的データから算出した会場ごとの1号艇勝率と補正係数
"""

VENUE_CHARACTERISTICS = {
    '01': {
        'name': '桐生',
        'pit1_rate': 47.5,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '02': {
        'name': '戸田',
        'pit1_rate': 45.5,
        'characteristic': 'インが弱い',
        'pit1_adjustment': 0.95,
    },
    '03': {
        'name': '江戸川',
        'pit1_rate': 47.9,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '04': {
        'name': '平和島',
        'pit1_rate': 47.1,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '05': {
        'name': '多摩川',
        'pit1_rate': 54.4,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '06': {
        'name': '浜名湖',
        'pit1_rate': 51.9,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '07': {
        'name': 'がまかつ',
        'pit1_rate': 60.8,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '08': {
        'name': '常滑',
        'pit1_rate': 60.1,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '09': {
        'name': '津',
        'pit1_rate': 57.2,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '10': {
        'name': '三国',
        'pit1_rate': 52.9,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '11': {
        'name': 'びわこ',
        'pit1_rate': 54.9,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '12': {
        'name': '住之江',
        'pit1_rate': 56.4,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '13': {
        'name': '尼崎',
        'pit1_rate': 61.1,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '14': {
        'name': '鳴門',
        'pit1_rate': 48.1,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '15': {
        'name': '丸亀',
        'pit1_rate': 56.4,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '16': {
        'name': '児島',
        'pit1_rate': 56.2,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '17': {
        'name': '宮島',
        'pit1_rate': 60.2,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '18': {
        'name': '徳山',
        'pit1_rate': 61.4,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '19': {
        'name': '下関',
        'pit1_rate': 59.3,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '20': {
        'name': '若松',
        'pit1_rate': 56.1,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '21': {
        'name': '芦屋',
        'pit1_rate': 56.3,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '22': {
        'name': '福岡',
        'pit1_rate': 55.8,
        'characteristic': 'インが強い',
        'pit1_adjustment': 1.05,
    },
    '23': {
        'name': '唐津',
        'pit1_rate': 51.9,
        'characteristic': '標準的',
        'pit1_adjustment': 1.0,
    },
    '24': {
        'name': '大村',
        'pit1_rate': 65.8,
        'characteristic': 'インが非常に強い',
        'pit1_adjustment': 1.10,
    },
}


def get_venue_adjustment(venue_code):
    """
    会場コードから補正係数を取得

    Args:
        venue_code: 会場コード（文字列、例: '07'）

    Returns:
        float: 1号艇用の補正係数
    """
    venue_info = VENUE_CHARACTERISTICS.get(venue_code)
    if venue_info:
        return venue_info['pit1_adjustment']
    return 1.0  # デフォルトは補正なし


def get_venue_name(venue_code):
    """
    会場コードから会場名を取得

    Args:
        venue_code: 会場コード（文字列、例: '07'）

    Returns:
        str: 会場名
    """
    venue_info = VENUE_CHARACTERISTICS.get(venue_code)
    if venue_info:
        return venue_info['name']
    return '不明'


def get_venue_pit1_rate(venue_code):
    """
    会場コードから歴史的な1号艇勝率を取得

    Args:
        venue_code: 会場コード（文字列、例: '07'）

    Returns:
        float: 1号艇勝率（パーセント）
    """
    venue_info = VENUE_CHARACTERISTICS.get(venue_code)
    if venue_info:
        return venue_info['pit1_rate']
    return 50.0  # デフォルトは50%


# 会場別の全コース勝率（追加データ）
VENUE_COURSE_WIN_RATES = {
    # コース別勝率 [1コース, 2コース, 3コース, 4コース, 5コース, 6コース]
    '01': [47.5, 15.0, 12.5, 12.0, 8.0, 5.0],   # 桐生
    '02': [45.5, 16.0, 13.0, 12.5, 8.5, 4.5],   # 戸田（イン弱め）
    '03': [47.9, 15.5, 12.5, 11.5, 8.0, 4.6],   # 江戸川
    '04': [47.1, 15.5, 13.0, 12.0, 7.5, 4.9],   # 平和島
    '05': [54.4, 14.5, 11.5, 10.5, 5.5, 3.6],   # 多摩川
    '06': [51.9, 14.5, 12.0, 11.0, 6.5, 4.1],   # 浜名湖
    '07': [60.8, 12.5, 10.0, 9.0, 5.0, 2.7],    # 蒲郡（イン強い）
    '08': [60.1, 12.5, 10.5, 9.0, 5.5, 2.4],    # 常滑（イン強い）
    '09': [57.2, 13.0, 11.0, 10.0, 6.0, 2.8],   # 津（イン強い）
    '10': [52.9, 14.0, 12.0, 11.0, 6.0, 4.1],   # 三国
    '11': [54.9, 14.0, 11.5, 10.5, 5.5, 3.6],   # びわこ
    '12': [56.4, 13.5, 11.0, 10.0, 5.5, 3.6],   # 住之江（イン強い）
    '13': [61.1, 12.0, 10.0, 9.0, 5.0, 2.9],    # 尼崎（イン強い）
    '14': [48.1, 15.5, 13.0, 11.5, 7.5, 4.4],   # 鳴門（まくり多い）
    '15': [56.4, 13.5, 11.0, 10.0, 5.5, 3.6],   # 丸亀（イン強い）
    '16': [56.2, 13.5, 11.0, 10.0, 5.5, 3.8],   # 児島（イン強い）
    '17': [60.2, 12.5, 10.0, 9.0, 5.5, 2.8],    # 宮島（イン強い、差し水面）
    '18': [61.4, 12.0, 10.0, 9.0, 5.0, 2.6],    # 徳山（イン強い）
    '19': [59.3, 13.0, 10.5, 9.5, 5.0, 2.7],    # 下関（イン強い）
    '20': [56.1, 13.5, 11.0, 10.0, 5.5, 3.9],   # 若松（差し水面）
    '21': [56.3, 13.5, 11.0, 10.0, 5.5, 3.7],   # 芦屋（イン強い）
    '22': [55.8, 14.0, 11.5, 10.0, 5.5, 3.2],   # 福岡（イン強い）
    '23': [51.9, 14.5, 12.0, 11.0, 6.5, 4.1],   # 唐津
    '24': [65.8, 11.0, 9.0, 7.5, 4.5, 2.2],     # 大村（イン最強）
}


def get_venue_course_win_rate(venue_code: str, course: int) -> float:
    """
    会場・コース別の勝率を取得

    Args:
        venue_code: 会場コード（'01'〜'24'）
        course: コース番号（1-6）

    Returns:
        勝率（パーセント）
    """
    rates = VENUE_COURSE_WIN_RATES.get(venue_code)
    if rates and 1 <= course <= 6:
        return rates[course - 1]

    # デフォルト値（全国平均）
    default_rates = [55.0, 14.0, 12.0, 10.0, 6.0, 3.0]
    if 1 <= course <= 6:
        return default_rates[course - 1]
    return 10.0


def get_venue_course_adjustment(venue_code: str, course: int) -> float:
    """
    会場・コース別の補正係数を取得

    全国平均に対する相対値を返す

    Args:
        venue_code: 会場コード
        course: コース番号（1-6）

    Returns:
        補正係数（1.0が基準、1.1なら+10%、0.9なら-10%）
    """
    venue_rate = get_venue_course_win_rate(venue_code, course)

    # 全国平均
    national_avg = [55.0, 14.0, 12.0, 10.0, 6.0, 3.0]
    if 1 <= course <= 6:
        avg_rate = national_avg[course - 1]
        if avg_rate > 0:
            return venue_rate / avg_rate

    return 1.0
