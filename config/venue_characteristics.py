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
