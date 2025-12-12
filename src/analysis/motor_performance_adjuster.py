"""
モーター成績による補正スコア計算

2025年通年データ（802,344エントリー）に基づくモーター2連率の影響分析
ベースライン: 1コース勝率 56.1%
"""
from typing import Optional


def calculate_motor_performance_adjustment(
    course: int,
    motor_second_rate: Optional[float]
) -> float:
    """
    モーター2連率による補正スコアを計算

    2025年通年データの統計:
    【1コース】
    - 0-30%: 53.9% (-2.2pt)
    - 30-35%: 56.4% (+0.3pt)
    - 35-40%: 58.0% (+1.9pt)
    - 40-45%: 60.3% (+4.2pt)
    - 45%+: 61.6% (+5.5pt)
    最大差分: +6.8pt (良いモーター40%+ vs 悪いモーター0-30%)

    【2コース】
    - 0-30%: 11.7% (-1.2pt)
    - 40%+: 16.3% (+3.4pt)
    最大差分: +4.6pt

    【3コース】
    - 0-30%: 11.2% (-0.9pt)
    - 40%+: 14.5% (+2.4pt)
    最大差分: +3.2pt

    【4コース】
    - 0-30%: 8.7% (-1.2pt)
    - 40%+: 12.0% (+2.1pt)
    最大差分: +3.3pt

    【5-6コース】
    - 影響は小さいが存在する (+1.1pt ~ +1.9pt)

    Args:
        course: コース番号(1-6)
        motor_second_rate: モーター2連率(%)

    Returns:
        補正スコア（-5.0 ~ +5.0点）
    """
    score = 0.0

    # モーター2連率データがない場合は補正なし
    if motor_second_rate is None:
        return 0.0

    # コース別の補正係数（インコースほど影響が大きい）
    course_weight = {
        1: 1.0,   # 1コース: 最大影響（基準）
        2: 0.68,  # 2コース: 4.6pt / 6.8pt = 0.68
        3: 0.47,  # 3コース: 3.2pt / 6.8pt = 0.47
        4: 0.49,  # 4コース: 3.3pt / 6.8pt = 0.49
        5: 0.16,  # 5コース: 1.1pt / 6.8pt = 0.16
        6: 0.28,  # 6コース: 1.9pt / 6.8pt = 0.28
    }

    weight = course_weight.get(course, 0.0)
    if weight == 0.0:
        return 0.0

    # モーター2連率による補正（1コース基準）
    if motor_second_rate < 30:
        # 悪いモーター: -2.2pt → -2.0点
        base_score = -2.0
    elif motor_second_rate < 35:
        # やや悪い: +0.3pt → 0点（ほぼベースライン）
        base_score = 0.0
    elif motor_second_rate < 40:
        # やや良い: +1.9pt → +1.5点
        base_score = +1.5
    elif motor_second_rate < 45:
        # 良い: +4.2pt → +3.5点
        base_score = +3.5
    else:
        # 非常に良い: +5.5pt → +4.5点
        base_score = +4.5

    # コース別の重み付け
    score = base_score * weight

    # スコア範囲を制限（-5.0 ~ +5.0点）
    return min(max(score, -5.0), 5.0)


if __name__ == "__main__":
    # テスト
    print("=" * 80)
    print("モーター成績補正スコアのテスト")
    print("=" * 80)

    # テストケース
    test_cases = [
        # (コース, モーター2連率, 期待される効果)
        (1, 25, "悪いモーター（-2.0点）"),
        (1, 32, "やや悪い（0点）"),
        (1, 37, "やや良い（+1.5点）"),
        (1, 42, "良い（+3.5点）"),
        (1, 48, "非常に良い（+4.5点）"),
        (2, 25, "2コース×悪いモーター（-1.4点）"),
        (2, 48, "2コース×非常に良い（+3.1点）"),
        (3, 48, "3コース×非常に良い（+2.1点）"),
        (4, 48, "4コース×非常に良い（+2.2点）"),
        (5, 48, "5コース×非常に良い（+0.7点）"),
        (6, 48, "6コース×非常に良い（+1.3点）"),
        (1, None, "データなし（0点）"),
    ]

    for course, motor_2rate, expected in test_cases:
        score = calculate_motor_performance_adjustment(course, motor_2rate)
        motor_str = f"{motor_2rate}%" if motor_2rate is not None else "なし"
        print(f"\nコース{course}, モーター2連率{motor_str}")
        print(f"  → スコア補正: {score:+6.1f}点 ({expected})")

    print("\n" + "=" * 80)
    print("全パターンの表示（1コース）")
    print("=" * 80)

    print(f"\n{'モーター2連率':<15} {'補正スコア':<12} {'実際の勝率（参考）':<20}")
    print("-" * 50)

    motor_ranges = [
        (25, "0-30%", "53.9%"),
        (32, "30-35%", "56.4%"),
        (37, "35-40%", "58.0%"),
        (42, "40-45%", "60.3%"),
        (48, "45%+", "61.6%"),
    ]

    for motor_val, motor_label, win_rate in motor_ranges:
        score = calculate_motor_performance_adjustment(1, motor_val)
        print(f"{motor_label:<15} {score:+6.1f}点     {win_rate:<20}")

    print("\n" + "=" * 80)
    print("コース別の補正効果（モーター2連率45%+の場合）")
    print("=" * 80)

    print(f"\n{'コース':<8} {'補正スコア':<12} {'実際の勝率（参考）':<20}")
    print("-" * 50)

    course_data = [
        (1, "60.6%"),
        (2, "16.3%"),
        (3, "14.5%"),
        (4, "12.0%"),
        (5, "6.7%"),
        (6, "4.0%"),
    ]

    for course, win_rate in course_data:
        score = calculate_motor_performance_adjustment(course, 48)
        print(f"{course}コース   {score:+6.1f}点     {win_rate:<20}")
