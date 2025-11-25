"""
数学ユーティリティのテスト
"""

import unittest
import sys
from pathlib import Path

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from utils.math_utils import safe_divide, safe_percentage, safe_average, safe_rate, clamp


class TestMathUtils(unittest.TestCase):
    """数学ユーティリティのテストケース"""

    def test_safe_divide_normal(self):
        """通常の除算"""
        result = safe_divide(10, 2)
        self.assertEqual(result, 5.0)

    def test_safe_divide_zero(self):
        """ゼロ除算（デフォルト値）"""
        result = safe_divide(10, 0)
        self.assertEqual(result, 0.0)

    def test_safe_divide_zero_custom_default(self):
        """ゼロ除算（カスタムデフォルト値）"""
        result = safe_divide(10, 0, default=None)
        self.assertIsNone(result)

    def test_safe_divide_float(self):
        """浮動小数点の除算"""
        result = safe_divide(7, 3)
        self.assertAlmostEqual(result, 2.333333, places=5)

    def test_safe_percentage_normal(self):
        """通常のパーセンテージ計算"""
        result = safe_percentage(25, 100)
        self.assertEqual(result, 25.0)

    def test_safe_percentage_fraction(self):
        """分数のパーセンテージ計算"""
        result = safe_percentage(1, 3)
        self.assertEqual(result, 33.33)

    def test_safe_percentage_zero_total(self):
        """全体がゼロの場合"""
        result = safe_percentage(10, 0)
        self.assertEqual(result, 0.0)

    def test_safe_percentage_custom_decimal(self):
        """カスタム小数点桁数"""
        result = safe_percentage(1, 3, decimal_places=4)
        self.assertEqual(result, 33.3333)

    def test_safe_average_normal(self):
        """通常の平均計算"""
        result = safe_average([1, 2, 3, 4, 5])
        self.assertEqual(result, 3.0)

    def test_safe_average_empty_list(self):
        """空のリストの場合"""
        result = safe_average([])
        self.assertEqual(result, 0.0)

    def test_safe_average_single_value(self):
        """単一値の平均"""
        result = safe_average([10.0])
        self.assertEqual(result, 10.0)

    def test_safe_average_custom_decimal(self):
        """カスタム小数点桁数"""
        result = safe_average([10.5, 20.3, 15.2], decimal_places=1)
        self.assertEqual(result, 15.3)

    def test_safe_rate_normal(self):
        """通常の成功率計算"""
        result = safe_rate(7, 10)
        self.assertEqual(result, 0.7)

    def test_safe_rate_perfect(self):
        """完璧な成功率"""
        result = safe_rate(10, 10)
        self.assertEqual(result, 1.0)

    def test_safe_rate_zero_attempts(self):
        """試行回数がゼロの場合"""
        result = safe_rate(5, 0)
        self.assertEqual(result, 0.0)

    def test_safe_rate_fraction(self):
        """分数の成功率"""
        result = safe_rate(1, 3)
        self.assertEqual(result, 0.333)

    def test_clamp_within_range(self):
        """範囲内の値"""
        result = clamp(5, 0, 10)
        self.assertEqual(result, 5)

    def test_clamp_below_min(self):
        """最小値以下の値"""
        result = clamp(-5, 0, 10)
        self.assertEqual(result, 0)

    def test_clamp_above_max(self):
        """最大値以上の値"""
        result = clamp(15, 0, 10)
        self.assertEqual(result, 10)

    def test_clamp_at_min(self):
        """最小値ちょうど"""
        result = clamp(0, 0, 10)
        self.assertEqual(result, 0)

    def test_clamp_at_max(self):
        """最大値ちょうど"""
        result = clamp(10, 0, 10)
        self.assertEqual(result, 10)


if __name__ == '__main__':
    unittest.main()
