"""
TJ-9: 展示タイム信頼性マップ設定

会場別の展示タイム信頼性に基づくスコア調整係数。
展示タイム1位と6位の勝率差が大きい会場ほど、展示タイムの予測精度が高い。

市場効率性検証結果:
- 高信頼性会場（徳山等）: 平均オッズ90.57倍、ROI 69.26%
- 低信頼性会場（江戸川等）: 平均オッズ59.02倍、ROI 39.07%
- ROI差: +30.19pt → 市場は展示タイムの会場別信頼性を正しく評価していない
"""

# 会場別信頼性係数マップ（強化版: ±50%）
# - 勝率差20pt以上の会場: 係数1.50（+50%）
# - 勝率差12pt程度の会場: 係数0.50（-50%）
# - その他の会場: 係数1.0（調整なし）
EXHIBITION_RELIABILITY_COEFFICIENTS = {
    # 高信頼性会場（勝率差20pt以上）
    '18': {  # 徳山
        'coefficient': 1.50,
        'win_rate_diff': 24.87,
        'description': '最高信頼性: 展示1位勝率76.47%, 6位51.60%（差24.87pt）'
    },
    '07': {  # 蒲郡
        'coefficient': 1.50,
        'win_rate_diff': 21.52,
        'description': '高信頼性: 展示1位と6位の勝率差21.52pt'
    },
    '12': {  # 住之江
        'coefficient': 1.50,
        'win_rate_diff': 21.46,
        'description': '高信頼性: 展示1位と6位の勝率差21.46pt'
    },
    '15': {  # 丸亀
        'coefficient': 1.50,
        'win_rate_diff': 21.27,
        'description': '高信頼性: 展示1位と6位の勝率差21.27pt'
    },
    '13': {  # 尼崎
        'coefficient': 1.50,
        'win_rate_diff': 20.78,
        'description': '高信頼性: 展示1位と6位の勝率差20.78pt'
    },
    '22': {  # 福岡
        'coefficient': 1.50,
        'win_rate_diff': 20.01,
        'description': '高信頼性: 展示1位と6位の勝率差20.01pt'
    },

    # 低信頼性会場（勝率差12pt程度）
    '03': {  # 江戸川
        'coefficient': 0.50,
        'win_rate_diff': 12.03,
        'description': '低信頼性: 展示1位と6位の勝率差12.03pt（河川特性）'
    },

    # その他の会場: デフォルト係数1.0（調整なし）
}

def get_exhibition_coefficient(venue_code: str) -> float:
    """
    会場コードから展示タイム信頼性係数を取得

    Args:
        venue_code: 会場コード（例: '18' = 徳山）

    Returns:
        係数（0.90～1.10、デフォルト1.0）
    """
    if venue_code in EXHIBITION_RELIABILITY_COEFFICIENTS:
        return EXHIBITION_RELIABILITY_COEFFICIENTS[venue_code]['coefficient']
    return 1.0  # デフォルト: 調整なし


def get_exhibition_reliability_info(venue_code: str) -> dict:
    """
    会場の展示タイム信頼性情報を取得

    Args:
        venue_code: 会場コード

    Returns:
        {'coefficient': float, 'win_rate_diff': float, 'description': str}
        会場情報がない場合はデフォルト値を返す
    """
    if venue_code in EXHIBITION_RELIABILITY_COEFFICIENTS:
        return EXHIBITION_RELIABILITY_COEFFICIENTS[venue_code]
    return {
        'coefficient': 1.0,
        'win_rate_diff': None,
        'description': '標準信頼性（調整なし）'
    }
