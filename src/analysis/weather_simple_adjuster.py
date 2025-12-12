"""
気象条件シンプル補正（風速のみ）

2025年通年データ（264暴風レース）に基づく実データドリブン補正
会場×風向は追い風・向かい風の判定が不確実なため不採用
"""
from typing import Optional


def calculate_weather_simple_adjustment(
    course: int,
    wind_speed: Optional[float]
) -> float:
    """
    風速のみによるシンプルな気象補正スコアを計算

    2025年通年データ（264暴風レース）の統計:
    - A1級1コース: 通常71.0% → 暴風65.7%（-5.3pt）
    - B1級1コース: 通常42.7% → 暴風39.2%（-3.5pt）
    - 級別差は縮小するが消滅しない（28.3% → 26.5%）

    Args:
        course: コース番号(1-6)
        wind_speed: 風速(m/s)

    Returns:
        補正スコア（-10.0 ~ +5.0点）
    """
    score = 0.0

    # 風速データがない場合は補正なし
    if wind_speed is None:
        return 0.0

    # 暴風時（8m以上）の補正
    if wind_speed >= 8.0:
        if course == 1:
            # 1コースは不利（全級別平均で約-5pt）
            score -= 5.0
        elif course == 2:
            # 2コースはやや有利（変化小）
            score += 0.0
        elif course == 3:
            # 3コースはやや有利（A1級で+5.6pt）
            score += 3.0
        elif course == 4:
            # 4コースは有利（A1級で+8.0pt）
            score += 5.0
        elif course == 5:
            # 5コースは変化小
            score += 0.0
        elif course == 6:
            # 6コースは変化小
            score += 0.0

    # 強風時（6-8m）の補正
    elif wind_speed >= 6.0:
        if course == 1:
            # 1コースは若干不利
            score -= 2.0
        elif course == 4:
            # 4コースは有利
            score += 3.0

    # スコア範囲を制限（-10.0 ~ +5.0点）
    return min(max(score, -10.0), 5.0)


if __name__ == "__main__":
    # テスト
    print("=" * 80)
    print("気象条件シンプル補正のテスト")
    print("=" * 80)

    # テストケース
    test_cases = [
        # (コース, 風速, 期待される効果)
        (1, 9.0, "暴風時1コース不利（-5.0点）"),
        (3, 8.5, "暴風時3コース有利（+3.0点）"),
        (4, 10.0, "暴風時4コース有利（+5.0点）"),
        (1, 7.0, "強風時1コース若干不利（-2.0点）"),
        (4, 6.5, "強風時4コース有利（+3.0点）"),
        (1, 5.0, "中風（補正なし）"),
        (1, None, "風速データなし（補正なし）"),
    ]

    for course, wind_speed, expected in test_cases:
        score = calculate_weather_simple_adjustment(course, wind_speed)
        wind_str = f"{wind_speed}m" if wind_speed is not None else "なし"
        print(f"\nコース{course}, 風速{wind_str}")
        print(f"  → スコア補正: {score:+6.1f}点 ({expected})")

    print("\n" + "=" * 80)
    print("全パターンの表示")
    print("=" * 80)

    print(f"\n{'風速':<12} {'コース':<8} {'補正スコア':<12}")
    print("-" * 40)

    for wind_speed in [10.0, 8.0, 7.0, 6.0, 5.0]:
        for course in range(1, 7):
            score = calculate_weather_simple_adjustment(course, wind_speed)
            if score != 0.0:
                print(f"{wind_speed:4.1f}m      {course}コース   {score:+6.1f}点")
