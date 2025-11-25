"""
日付ユーティリティのテスト
"""

import unittest
from datetime import datetime
import sys
from pathlib import Path

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from utils.date_utils import to_yyyymmdd, to_iso_format, to_datetime, validate_date


class TestDateUtils(unittest.TestCase):
    """日付ユーティリティのテストケース"""

    def test_to_yyyymmdd_from_iso(self):
        """ISO形式からYYYYMMDD形式への変換"""
        result = to_yyyymmdd("2024-11-02")
        self.assertEqual(result, "20241102")

    def test_to_yyyymmdd_from_yyyymmdd(self):
        """YYYYMMDD形式からYYYYMMDD形式への変換（そのまま）"""
        result = to_yyyymmdd("20241102")
        self.assertEqual(result, "20241102")

    def test_to_yyyymmdd_from_datetime(self):
        """datetimeからYYYYMMDD形式への変換"""
        dt = datetime(2024, 11, 2)
        result = to_yyyymmdd(dt)
        self.assertEqual(result, "20241102")

    def test_to_yyyymmdd_invalid_format(self):
        """無効な形式でエラーが発生"""
        with self.assertRaises(ValueError):
            to_yyyymmdd("2024/11/02")

    def test_to_iso_format_from_yyyymmdd(self):
        """YYYYMMDD形式からISO形式への変換"""
        result = to_iso_format("20241102")
        self.assertEqual(result, "2024-11-02")

    def test_to_iso_format_from_iso(self):
        """ISO形式からISO形式への変換（そのまま）"""
        result = to_iso_format("2024-11-02")
        self.assertEqual(result, "2024-11-02")

    def test_to_iso_format_from_datetime(self):
        """datetimeからISO形式への変換"""
        dt = datetime(2024, 11, 2)
        result = to_iso_format(dt)
        self.assertEqual(result, "2024-11-02")

    def test_to_iso_format_invalid_date(self):
        """無効な日付でエラーが発生"""
        with self.assertRaises(ValueError):
            to_iso_format("2024-13-01")  # 13月は存在しない

    def test_to_datetime_from_yyyymmdd(self):
        """YYYYMMDD形式からdatetimeへの変換"""
        result = to_datetime("20241102")
        expected = datetime(2024, 11, 2)
        self.assertEqual(result, expected)

    def test_to_datetime_from_iso(self):
        """ISO形式からdatetimeへの変換"""
        result = to_datetime("2024-11-02")
        expected = datetime(2024, 11, 2)
        self.assertEqual(result, expected)

    def test_to_datetime_from_datetime(self):
        """datetimeからdatetimeへの変換（そのまま）"""
        dt = datetime(2024, 11, 2)
        result = to_datetime(dt)
        self.assertEqual(result, dt)

    def test_validate_date_valid_iso(self):
        """有効なISO形式の検証"""
        self.assertTrue(validate_date("2024-11-02"))

    def test_validate_date_invalid_iso(self):
        """無効なISO形式の検証"""
        self.assertFalse(validate_date("2024-13-01"))  # 13月は存在しない

    def test_validate_date_valid_yyyymmdd(self):
        """有効なYYYYMMDD形式の検証"""
        self.assertTrue(validate_date("20241102", "%Y%m%d"))

    def test_validate_date_invalid_yyyymmdd(self):
        """無効なYYYYMMDD形式の検証"""
        self.assertFalse(validate_date("20241301", "%Y%m%d"))  # 13月は存在しない


if __name__ == '__main__':
    unittest.main()
