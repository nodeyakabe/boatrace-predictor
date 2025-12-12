"""
会場×風向×風速による補正スコア計算（修正版）

2025年通年データ（264暴風レース）から抽出した
会場別・風向別の1コース勝率パターンに基づく補正

データ検証済み: 2025-12-12
ベースライン: 1コース勝率 56.3% (9448/16780艇)
"""
from typing import Dict, Optional


# 会場×風向×風速の補正テーブル（暴風時8m+）
# 値は1コース勝率の差分（ベースライン56.3%からの乖離）
# サンプル数5件以上のデータのみ
VENUE_WIND_DIRECTION_ADJUSTMENT = {
    '02': {  # 会場02（戸田）
        '北':  -31.3,  # 勝率 25.0% (3/12艇)
        '南東':  -18.8,  # 勝率 37.5% (9/24艇)
    },
    '03': {  # 会場03（江戸川）
        '東':   -8.2,  # 勝率 48.1% (25/52艇)
    },
    '04': {  # 会場04（平和島）
        '東南東':   -6.3,  # 勝率 50.0% (5/10艇)
    },
    '08': {  # 会場08（常滑）
        '北北西':   +3.7,  # 勝率 60.0% (9/15艇)
        '西北西':   -1.8,  # 勝率 54.5% (6/11艇)
    },
    '10': {  # 会場10（桐生）
        '西':  -23.0,  # 勝率 33.3% (10/30艇)
    },
    '13': {  # 会場13（尼崎）
        '西':  +35.4,  # 勝率 91.7% (11/12艇)
        '北':  +10.4,  # 勝率 66.7% (8/12艇)
    },
    '14': {  # 会場14（三国）
        '東南東':  -19.9,  # 勝率 36.4% (4/11艇)
        '東北東':  -56.3,  # 勝率  0.0% (0/6艇) ← 修正: 東北東が正しい（極端な不利）
    },
    '15': {  # 会場15（丸亀）
        '西南西':   +2.0,  # 勝率 58.3% (7/12艇)
    },
    '19': {  # 会場19（下関）
        '北北東':  +34.6,  # 勝率 90.9% (10/11艇) ← 修正: 北北東が正しい
    },
    '23': {  # 会場23（唐津）
        '西':  +34.6,  # 勝率 90.9% (10/11艇)
        '東':   +3.7,  # 勝率 60.0% (6/10艇)
    },
}


def calculate_venue_wind_adjustment(
    course: int,
    venue_code: str,
    wind_speed: Optional[float],
    wind_direction: Optional[str]
) -> float:
    """
    会場×風向×風速による補正スコアを計算

    Args:
        course: コース番号(1-6)
        venue_code: 会場コード（'01'~'24'）
        wind_speed: 風速(m/s)
        wind_direction: 風向（'北'、'南東'など）

    Returns:
        補正スコア（-20.0 ~ +20.0点）
    """
    score = 0.0

    # 風速・風向がない場合は補正なし
    if wind_speed is None or wind_direction is None:
        return 0.0

    # 暴風時（8m以上）のみ補正
    if wind_speed < 8.0:
        return 0.0

    # 1コース以外は補正対象外（現時点では）
    if course != 1:
        return 0.0

    # 会場コードを2桁にフォーマット
    venue_key = f"{int(venue_code):02d}" if isinstance(venue_code, (int, str)) else str(venue_code)

    # 会場別の風向補正を取得
    if venue_key in VENUE_WIND_DIRECTION_ADJUSTMENT:
        venue_adjustments = VENUE_WIND_DIRECTION_ADJUSTMENT[venue_key]

        if wind_direction in venue_adjustments:
            # 補正値を取得
            diff = venue_adjustments[wind_direction]

            # スコアに換算（差分の50%を適用）
            # 例: 差分+35.4pt → スコア+17.7点
            # 例: 差分-31.3pt → スコア-15.7点
            score = diff * 0.5

    # スコア範囲を制限（-20 ~ +20点）
    return min(max(score, -20.0), 20.0)


def get_venue_wind_info(venue_code: str, wind_direction: str) -> Optional[Dict]:
    """
    会場×風向の補正情報を取得（デバッグ用）

    Args:
        venue_code: 会場コード
        wind_direction: 風向

    Returns:
        補正情報の辞書（なければNone）
    """
    venue_key = f"{int(venue_code):02d}" if isinstance(venue_code, (int, str)) else str(venue_code)

    if venue_key not in VENUE_WIND_DIRECTION_ADJUSTMENT:
        return None

    venue_adjustments = VENUE_WIND_DIRECTION_ADJUSTMENT[venue_key]

    if wind_direction not in venue_adjustments:
        return None

    diff = venue_adjustments[wind_direction]

    return {
        'venue_code': venue_key,
        'wind_direction': wind_direction,
        'diff': diff,
        'score_adjustment': diff * 0.5
    }


def list_all_venue_wind_patterns() -> list:
    """
    全ての会場×風向パターンをリスト化（デバッグ用）

    Returns:
        パターンのリスト
    """
    patterns = []

    for venue_code, directions in VENUE_WIND_DIRECTION_ADJUSTMENT.items():
        for wind_direction, diff in directions.items():
            patterns.append({
                'venue_code': venue_code,
                'wind_direction': wind_direction,
                'diff': diff,
                'score_adjustment': diff * 0.5
            })

    # 差分の絶対値でソート
    patterns.sort(key=lambda x: abs(x['diff']), reverse=True)

    return patterns


if __name__ == "__main__":
    # テスト
    print("=" * 80)
    print("会場×風向×風速補正スコアのテスト（修正版）")
    print("=" * 80)

    # テストケース
    test_cases = [
        # (コース, 会場, 風速, 風向, 期待される効果)
        (1, '13', 8.5, '西', "超有利（+35.4pt → +17.7点）"),
        (1, '19', 8.0, '北北東', "超有利（+34.6pt → +17.3点）"),
        (1, '02', 8.2, '北', "大幅不利（-31.3pt → -15.7点）"),
        (1, '10', 9.5, '西', "大幅不利（-23.0pt → -11.5点）"),
        (1, '14', 8.0, '東北東', "極端な不利（-56.3pt → -28.2点）"),
        (1, '03', 8.0, '東', "やや不利（-8.2pt → -4.1点）"),
        (1, '08', 8.0, '北北西', "やや有利（+3.7pt → +1.9点）"),
        (1, '14', 6.0, '東北東', "風速不足（補正なし）"),
        (2, '14', 9.0, '東北東', "1コース以外（補正なし）"),
        (1, '14', 9.0, '南', "風向データなし（補正なし）"),
    ]

    for course, venue, wind_speed, wind_dir, expected in test_cases:
        score = calculate_venue_wind_adjustment(course, venue, wind_speed, wind_dir)
        print(f"\nコース{course}, 会場{venue}, 風速{wind_speed}m, 風向{wind_dir}")
        print(f"  → スコア補正: {score:+6.1f}点 ({expected})")

    # 全パターンの表示
    print("\n" + "=" * 80)
    print("登録されている全パターン（差分の大きい順）")
    print("=" * 80)

    patterns = list_all_venue_wind_patterns()

    print(f"\n{'会場':<6} {'風向':<10} {'差分':<10} {'スコア補正':<12}")
    print("-" * 50)

    for p in patterns:
        print(f"{p['venue_code']:<6} {p['wind_direction']:<10} "
              f"{p['diff']:+6.1f}pt   {p['score_adjustment']:+6.1f}点")

    print(f"\n合計: {len(patterns)}パターン")
