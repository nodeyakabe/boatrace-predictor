"""
Laplace平滑化のテストスクリプト
外枠ゼロ化問題が解決されるかを確認
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis.smoothing import LaplaceSmoothing
from src.analysis.statistics_calculator import StatisticsCalculator


def test_smoothing_basic():
    """基本的なLaplace平滑化のテスト"""
    print("=" * 80)
    print("Laplace平滑化テスト")
    print("=" * 80)
    print()

    smoother = LaplaceSmoothing()

    print(f"設定: enabled={smoother.enabled}, alpha={smoother.alpha}")
    print()

    # テストケース
    test_cases = [
        ("データ極少（5レース、1勝）", 1, 5),
        ("ゼロ化ケース（2レース、0勝）", 0, 2),
        ("中程度データ（20レース、3勝）", 3, 20),
        ("データ十分（100レース、12勝）", 12, 100),
        ("4号艇実績（10レース、1勝）", 1, 10),
        ("5号艇実績（10レース、0勝）", 0, 10),
        ("6号艇実績（10レース、0勝）", 0, 10),
    ]

    print("テストケース別の平滑化結果:")
    print("-" * 80)
    print("ケース                          | 実績勝率 | 平滑化後 | 差分")
    print("-" * 80)

    for name, wins, total in test_cases:
        raw_rate = (wins / total * 100) if total > 0 else 0.0
        smoothed_rate = smoother.smooth_win_rate(wins, total, k=2) * 100
        diff = smoothed_rate - raw_rate

        print(f"{name:30s} | {raw_rate:6.2f}% | {smoothed_rate:6.2f}% | {diff:+6.2f}%")

    print()


def test_course_stats_smoothing():
    """実際のコース別統計にLaplace平滑化を適用"""
    print("=" * 80)
    print("実際のコース別統計へのLaplace平滑化適用テスト")
    print("=" * 80)
    print()

    calc = StatisticsCalculator()

    # 全国統計
    print("【全国統計（過去90日）】")
    print("-" * 80)
    stats = calc.calculate_course_stats(venue_code=None, days=90)

    print("コース | レース数 | 元の勝率 | 平滑化後 | 差分")
    print("-" * 80)

    for course in range(1, 7):
        if course in stats:
            s = stats[course]
            raw_rate = s.get('raw_win_rate', s['win_rate']) * 100
            smoothed_rate = s['win_rate'] * 100
            diff = smoothed_rate - raw_rate

            print(f"  {course}    | {s['total_races']:6,} | "
                  f"{raw_rate:6.2f}% | {smoothed_rate:6.2f}% | {diff:+6.2f}%")
        else:
            print(f"  {course}    | データなし")

    print()

    # 会場別統計（データ少ない会場を選択）
    print("【会場別統計例: 桐生02（データ少なめ）】")
    print("-" * 80)
    stats_venue = calc.calculate_course_stats(venue_code='02', days=90)

    print("コース | レース数 | 元の勝率 | 平滑化後 | 差分")
    print("-" * 80)

    for course in range(1, 7):
        if course in stats_venue:
            s = stats_venue[course]
            raw_rate = s.get('raw_win_rate', s['win_rate']) * 100
            smoothed_rate = s['win_rate'] * 100
            diff = smoothed_rate - raw_rate

            print(f"  {course}    | {s['total_races']:6,} | "
                  f"{raw_rate:6.2f}% | {smoothed_rate:6.2f}% | {diff:+6.2f}%")
        else:
            print(f"  {course}    | データなし（全国平均を使用）")

    print()


def test_default_rates():
    """デフォルト勝率のLaplace平滑化"""
    print("=" * 80)
    print("全国デフォルト勝率の平滑化")
    print("=" * 80)
    print()

    smoother = LaplaceSmoothing()
    smoothed_defaults = smoother.get_default_win_rates_smoothed()

    print("コース | 元の勝率 | 平滑化後")
    print("-" * 40)

    original_defaults = {
        1: 0.55,
        2: 0.14,
        3: 0.12,
        4: 0.10,
        5: 0.06,
        6: 0.03,
    }

    for course in range(1, 7):
        orig = original_defaults[course] * 100
        smoothed = smoothed_defaults[course] * 100
        diff = smoothed - orig

        print(f"  {course}    | {orig:6.2f}% | {smoothed:6.2f}% ({diff:+5.2f}%)")

    print()


if __name__ == "__main__":
    test_smoothing_basic()
    print()
    test_course_stats_smoothing()
    print()
    test_default_rates()

    print("=" * 80)
    print("テスト完了")
    print("外枠（4-6号艇）のゼロ化問題が改善されていることを確認してください。")
    print("=" * 80)
