#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信頼度別パターン適用のユニットテスト

Phase 1実装内容:
- 信頼度Aではパターンを適用しない
- 信頼度Eではパターンを適用しない
- 信頼度B/Cではパターンを適用する
- 信頼度Dはフィーチャーフラグで制御
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import unittest
from unittest.mock import Mock, patch, MagicMock
from src.analysis.race_predictor import RacePredictor
from config.feature_flags import is_feature_enabled


class TestConfidencePatternApplication(unittest.TestCase):
    """信頼度別パターン適用テスト"""

    def setUp(self):
        """テストセットアップ"""
        self.predictor = RacePredictor()

    def create_mock_predictions(self, confidence_level):
        """モック予測データを作成"""
        return [
            {
                'pit_number': 1,
                'racer_name': 'テスト選手1',
                'total_score': 85.0,
                'confidence': confidence_level,
                'rank_prediction': 1
            },
            {
                'pit_number': 2,
                'racer_name': 'テスト選手2',
                'total_score': 75.0,
                'confidence': confidence_level,
                'rank_prediction': 2
            },
            {
                'pit_number': 3,
                'racer_name': 'テスト選手3',
                'total_score': 65.0,
                'confidence': confidence_level,
                'rank_prediction': 3
            }
        ]

    @patch('src.analysis.race_predictor.get_connection')
    def test_confidence_a_skips_pattern(self, mock_conn):
        """信頼度Aではパターンを適用しないことをテスト"""
        # モックデータ準備
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 6.80, 0.12),  # pit_number, exhibition_time, st_time
            (2, 6.85, 0.15),
            (3, 6.90, 0.18),
            (4, 6.95, 0.20),
            (5, 7.00, 0.22),
            (6, 7.05, 0.25)
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        predictions = self.create_mock_predictions('A')
        result = self.predictor._apply_pattern_bonus(predictions, race_id=12345)

        # 検証
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['integration_mode'], 'pattern_skipped_confidence_A')
        self.assertEqual(result[0]['pattern_multiplier'], 1.0)
        self.assertEqual(result[0]['matched_patterns'], [])
        print("✓ 信頼度Aテスト成功: パターンがスキップされた")

    @patch('src.analysis.race_predictor.get_connection')
    def test_confidence_e_skips_pattern(self, mock_conn):
        """信頼度Eではパターンを適用しないことをテスト"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 6.80, 0.12),
            (2, 6.85, 0.15),
            (3, 6.90, 0.18),
            (4, 6.95, 0.20),
            (5, 7.00, 0.22),
            (6, 7.05, 0.25)
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        predictions = self.create_mock_predictions('E')
        result = self.predictor._apply_pattern_bonus(predictions, race_id=12345)

        # 検証
        self.assertEqual(result[0]['integration_mode'], 'pattern_skipped_confidence_E')
        self.assertEqual(result[0]['pattern_multiplier'], 1.0)
        print("✓ 信頼度Eテスト成功: パターンがスキップされた")

    @patch('src.analysis.race_predictor.get_connection')
    def test_confidence_b_applies_pattern(self, mock_conn):
        """信頼度Bではパターンを適用することをテスト"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 6.80, 0.12),  # PRE1位, 展示1位, ST1位 → パターンマッチ
            (2, 6.85, 0.15),
            (3, 6.90, 0.18),
            (4, 6.95, 0.20),
            (5, 7.00, 0.22),
            (6, 7.05, 0.25)
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        predictions = self.create_mock_predictions('B')
        result = self.predictor._apply_pattern_bonus(predictions, race_id=12345)

        # 検証: パターンが適用されているはず
        self.assertNotEqual(result[0]['integration_mode'], 'pattern_skipped_confidence_B')
        self.assertEqual(result[0]['integration_mode'], 'pattern_bonus')
        # パターンマッチしているはず（PRE1位×展示1位×ST1位）
        self.assertGreater(result[0]['pattern_multiplier'], 1.0)
        print(f"✓ 信頼度Bテスト成功: パターンが適用された (multiplier={result[0]['pattern_multiplier']:.3f})")

    @patch('src.analysis.race_predictor.get_connection')
    def test_confidence_c_applies_pattern(self, mock_conn):
        """信頼度Cではパターンを適用することをテスト"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 6.80, 0.12),
            (2, 6.85, 0.15),
            (3, 6.90, 0.18),
            (4, 6.95, 0.20),
            (5, 7.00, 0.22),
            (6, 7.05, 0.25)
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        predictions = self.create_mock_predictions('C')
        result = self.predictor._apply_pattern_bonus(predictions, race_id=12345)

        # 検証
        self.assertNotEqual(result[0]['integration_mode'], 'pattern_skipped_confidence_C')
        self.assertEqual(result[0]['integration_mode'], 'pattern_bonus')
        self.assertGreater(result[0]['pattern_multiplier'], 1.0)
        print(f"✓ 信頼度Cテスト成功: パターンが適用された (multiplier={result[0]['pattern_multiplier']:.3f})")

    @patch('src.analysis.race_predictor.is_feature_enabled')
    @patch('src.analysis.race_predictor.get_connection')
    def test_confidence_d_with_flag_disabled(self, mock_conn, mock_feature):
        """信頼度D・フラグ無効時はパターンをスキップ"""
        mock_feature.return_value = False
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 6.80, 0.12),
            (2, 6.85, 0.15),
            (3, 6.90, 0.18),
            (4, 6.95, 0.20),
            (5, 7.00, 0.22),
            (6, 7.05, 0.25)
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        predictions = self.create_mock_predictions('D')
        result = self.predictor._apply_pattern_bonus(predictions, race_id=12345)

        # 検証
        self.assertEqual(result[0]['integration_mode'], 'pattern_skipped_confidence_D')
        self.assertEqual(result[0]['pattern_multiplier'], 1.0)
        print("✓ 信頼度D（フラグ無効）テスト成功: パターンがスキップされた")

    @patch('src.analysis.race_predictor.is_feature_enabled')
    @patch('src.analysis.race_predictor.get_connection')
    def test_confidence_d_with_flag_enabled(self, mock_conn, mock_feature):
        """信頼度D・フラグ有効時はパターンを適用"""
        mock_feature.return_value = True
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 6.80, 0.12),
            (2, 6.85, 0.15),
            (3, 6.90, 0.18),
            (4, 6.95, 0.20),
            (5, 7.00, 0.22),
            (6, 7.05, 0.25)
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor

        predictions = self.create_mock_predictions('D')
        result = self.predictor._apply_pattern_bonus(predictions, race_id=12345)

        # 検証
        self.assertNotEqual(result[0]['integration_mode'], 'pattern_skipped_confidence_D')
        self.assertEqual(result[0]['integration_mode'], 'pattern_bonus')
        print(f"✓ 信頼度D（フラグ有効）テスト成功: パターンが適用された (multiplier={result[0]['pattern_multiplier']:.3f})")

    def test_confidence_distribution(self):
        """信頼度別の適用状況を確認"""
        test_cases = [
            ('A', False, "高精度のため不要"),
            ('B', True, "最も効果的（+9.5pt）"),
            ('C', True, "安定効果（+8.3pt）"),
            ('D', False, "フラグで制御（+3.9pt）"),
            ('E', False, "データ不足"),
        ]

        print("\n" + "=" * 60)
        print("信頼度別パターン適用状況")
        print("=" * 60)
        for confidence, should_apply, reason in test_cases:
            status = "✓ 適用" if should_apply else "✗ スキップ"
            print(f"信頼度 {confidence}: {status:12s} - {reason}")
        print("=" * 60)


def run_tests():
    """テストを実行"""
    # テストスイート作成
    suite = unittest.TestLoader().loadTestsFromTestCase(TestConfidencePatternApplication)

    # テスト実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 結果サマリー
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)
    print(f"実行: {result.testsRun}件")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}件")
    print(f"失敗: {len(result.failures)}件")
    print(f"エラー: {len(result.errors)}件")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
