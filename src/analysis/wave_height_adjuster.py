"""
波高による補正スコア計算

2025年通年データ（16,136レース）に基づく波高の影響分析
ベースライン: 1コース勝率 56.4%
"""
from typing import Optional


def calculate_wave_height_adjustment(
    course: int,
    wave_height: Optional[float]
) -> float:
    """
    波高による補正スコアを計算

    2025年通年データの統計:
    - 10-14cm: 1コース 40.3% (-16.1pt)、2コース 22.2% (+9.3pt)
    - 15-19cm: 1コース 51.0% (-5.4pt)
    - 20cm+:   1コース 47.3% (-9.1pt)

    Args:
        course: コース番号(1-6)
        wave_height: 波高(cm)

    Returns:
        補正スコア（-10.0 ~ +5.0点）
    """
    score = 0.0

    # 波高データがない場合は補正なし
    if wave_height is None:
        return 0.0

    # 10-14cm: 最も1コースに不利、2コースに有利
    if 10 <= wave_height < 15:
        if course == 1:
            # 1コース: 大幅不利（-16.1pt → -8.0点）
            score -= 8.0
        elif course == 2:
            # 2コース: 有利（+9.3pt → +5.0点）
            score += 5.0

    # 15cm以上: やや不利（15-19cmと20cm+の平均を取る）
    elif wave_height >= 15:
        if course == 1:
            # 1コース: やや不利（平均-7.3pt → -3.5点）
            score -= 3.5
        elif course == 2:
            # 2コースもやや有利（18-19%程度）
            score += 2.0

    # スコア範囲を制限（-10.0 ~ +5.0点）
    return min(max(score, -10.0), 5.0)


if __name__ == "__main__":
    # テスト
    print("=" * 80)
    print("波高補正スコアのテスト")
    print("=" * 80)

    # テストケース
    test_cases = [
        # (コース, 波高, 期待される効果)
        (1, 12, "10-14cm: 大幅不利（-8.0点）"),
        (2, 12, "10-14cm: 有利（+5.0点）"),
        (3, 12, "10-14cm: 補正なし（0点）"),
        (1, 16, "15cm以上: やや不利（-3.5点）"),
        (2, 20, "15cm以上: やや有利（+2.0点）"),
        (1, 5, "5cm: 補正なし（0点）"),
        (1, None, "波高データなし（0点）"),
    ]

    for course, wave_height, expected in test_cases:
        score = calculate_wave_height_adjustment(course, wave_height)
        wave_str = f"{wave_height}cm" if wave_height is not None else "なし"
        print(f"\nコース{course}, 波高{wave_str}")
        print(f"  → スコア補正: {score:+6.1f}点 ({expected})")

    print("\n" + "=" * 80)
    print("全パターンの表示")
    print("=" * 80)

    print(f"\n{'波高':<12} {'コース':<8} {'補正スコア':<12}")
    print("-" * 40)

    for wave_height in [5, 10, 12, 14, 15, 18, 20]:
        for course in range(1, 7):
            score = calculate_wave_height_adjustment(course, wave_height)
            if score != 0.0:
                print(f"{wave_height:4d}cm      {course}コース   {score:+6.1f}点")
