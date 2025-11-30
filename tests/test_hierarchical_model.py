"""
階層的確率モデルのテスト
Phase 5: 特徴量変換・条件付きモデル・三連単確率計算のテスト
"""
import os
import sys
import unittest
import sqlite3
import pandas as pd
import numpy as np

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.features.feature_transforms import (
    FeatureTransformer,
    RaceRelativeFeatureBuilder,
    create_training_dataset_with_relative_features
)
from src.prediction.trifecta_calculator import TrifectaCalculator, NaiveTrifectaCalculator


class TestFeatureTransformer(unittest.TestCase):
    """特徴量変換のテスト"""

    def setUp(self):
        self.transformer = FeatureTransformer()

    def test_exhibition_features_basic(self):
        """展示タイム相対特徴量の基本テスト"""
        # テストデータ作成（6艇のレース）
        data = {
            'race_id': ['R001'] * 6,
            'pit_number': [1, 2, 3, 4, 5, 6],
            'exhibition_time': [6.72, 6.78, 6.75, 6.80, 6.70, 6.85],
            'actual_course': [1, 2, 3, 4, 5, 6]
        }
        df = pd.DataFrame(data)

        result = self.transformer.add_exhibition_features(df)

        # 必要な列が追加されていることを確認
        self.assertIn('exh_rank', result.columns)
        self.assertIn('exh_diff', result.columns)
        self.assertIn('exh_zscore', result.columns)
        self.assertIn('exh_gap_to_best', result.columns)
        self.assertIn('exh_relative_position', result.columns)

        # 6艇分のデータがあること
        self.assertEqual(len(result), 6)

        # 展示タイムは低いほど速いので、6.70が最速
        # コース補正があるため順位は変動する
        # 全艇に1-6の順位が割り当てられていることを確認
        self.assertTrue(all(result['exh_rank'].between(1, 6)))

    def test_st_features_basic(self):
        """STタイム相対特徴量の基本テスト"""
        data = {
            'race_id': ['R001'] * 6,
            'pit_number': [1, 2, 3, 4, 5, 6],
            'avg_st': [0.15, 0.12, 0.18, 0.10, 0.14, 0.20],
            'actual_course': [1, 2, 3, 4, 5, 6]
        }
        df = pd.DataFrame(data)

        result = self.transformer.add_st_features(df)

        # 必要な列が追加されていることを確認
        self.assertIn('st_rank', result.columns)
        self.assertIn('st_diff', result.columns)
        self.assertIn('st_zscore', result.columns)
        self.assertIn('st_relative', result.columns)
        self.assertIn('st_vs_expectation', result.columns)

        # 最速ST（4号艇: 0.10）の順位が1であること
        fastest_rank = result[result['pit_number'] == 4]['st_rank'].values[0]
        self.assertEqual(fastest_rank, 1)

    def test_winner_context_features(self):
        """1着艇コンテキスト特徴量のテスト"""
        data = {
            'race_id': ['R001'] * 5,  # 1着除外なので5艇
            'pit_number': [2, 3, 4, 5, 6],
            'actual_course': [2, 3, 4, 5, 6]
        }
        df = pd.DataFrame(data)

        result = self.transformer.add_winner_context_features(df, winner_pit=1)

        self.assertIn('gap_to_winner_course', result.columns)
        self.assertIn('is_adjacent_to_winner', result.columns)
        self.assertIn('winner_is_inner', result.columns)

        # 2号艇は1号艇に隣接
        is_adjacent = result[result['pit_number'] == 2]['is_adjacent_to_winner'].values[0]
        self.assertEqual(is_adjacent, 1)

    def test_multiple_races(self):
        """複数レースでの相対特徴量計算"""
        data = {
            'race_id': ['R001'] * 6 + ['R002'] * 6,
            'pit_number': [1, 2, 3, 4, 5, 6] * 2,
            'exhibition_time': [6.72, 6.78, 6.75, 6.80, 6.70, 6.85,
                               6.65, 6.70, 6.68, 6.72, 6.75, 6.80],
            'actual_course': [1, 2, 3, 4, 5, 6] * 2
        }
        df = pd.DataFrame(data)

        result = self.transformer.add_exhibition_features(df)

        # 各レースで独立して順位が計算されていること
        r1_ranks = result[result['race_id'] == 'R001']['exh_rank'].values
        r2_ranks = result[result['race_id'] == 'R002']['exh_rank'].values

        # 各レースで1-6の順位が割り当てられていること
        self.assertEqual(len(set(r1_ranks)), 6)
        self.assertEqual(len(set(r2_ranks)), 6)


class TestTrifectaCalculator(unittest.TestCase):
    """三連単確率計算のテスト"""

    def test_naive_calculator_basic(self):
        """ナイーブ法の基本テスト"""
        # 均等な1着確率
        first_probs = np.array([0.3, 0.2, 0.15, 0.15, 0.1, 0.1])

        result = NaiveTrifectaCalculator.calculate(first_probs)

        # 120通りの組み合わせがあること
        self.assertEqual(len(result), 120)

        # 確率の合計が1に近いこと
        total_prob = sum(result.values())
        self.assertAlmostEqual(total_prob, 1.0, places=5)

        # 1-2-3の確率が最も高いこと（1着確率が高い順）
        top_comb = max(result, key=result.get)
        self.assertEqual(top_comb, '1-2-3')

    def test_naive_calculator_extreme(self):
        """極端な確率分布でのテスト"""
        # 1号艇が圧倒的に強い
        first_probs = np.array([0.7, 0.1, 0.05, 0.05, 0.05, 0.05])

        result = NaiveTrifectaCalculator.calculate(first_probs)

        # 1号艇1着の組み合わせが上位を占めること
        top5 = sorted(result.items(), key=lambda x: x[1], reverse=True)[:5]
        for comb, _ in top5:
            self.assertTrue(comb.startswith('1-'))

    def test_probability_normalization(self):
        """確率正規化のテスト"""
        first_probs = np.array([0.25, 0.25, 0.20, 0.15, 0.10, 0.05])
        result = NaiveTrifectaCalculator.calculate(first_probs)

        # 全ての確率が0-1の範囲内
        for prob in result.values():
            self.assertGreaterEqual(prob, 0)
            self.assertLessEqual(prob, 1)


class TestRaceRelativeFeatureBuilder(unittest.TestCase):
    """レース相対特徴量ビルダーのテスト"""

    def test_build_training_data(self):
        """学習データ構築のテスト"""
        builder = RaceRelativeFeatureBuilder()

        data = {
            'race_id': ['R001'] * 6,
            'pit_number': [1, 2, 3, 4, 5, 6],
            'exhibition_time': [6.72, 6.78, 6.75, 6.80, 6.70, 6.85],
            'avg_st': [0.15, 0.12, 0.18, 0.10, 0.14, 0.20],
            'actual_course': [1, 2, 3, 4, 5, 6],
            'win_rate': [30.5, 25.0, 20.0, 18.0, 15.0, 12.0]
        }
        df = pd.DataFrame(data)

        result = builder.build_training_data(df)

        # 展示・ST両方の相対特徴量が追加されていること
        expected_cols = ['exh_rank', 'exh_diff', 'st_rank', 'st_diff']
        for col in expected_cols:
            self.assertIn(col, result.columns)


class TestIntegration(unittest.TestCase):
    """統合テスト"""

    @classmethod
    def setUpClass(cls):
        """テスト用DBパスを設定"""
        cls.db_path = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')
        cls.db_exists = os.path.exists(cls.db_path)

    def test_create_training_dataset(self):
        """学習データセット作成のテスト（DBがある場合のみ）"""
        if not self.db_exists:
            self.skipTest("データベースが存在しません")

        with sqlite3.connect(self.db_path) as conn:
            df = create_training_dataset_with_relative_features(
                conn, start_date='2024-11-01', limit=1000
            )

        if len(df) > 0:
            # 相対特徴量が追加されていること
            self.assertIn('exh_rank', df.columns)
            self.assertIn('st_rank', df.columns)

            # rankカラムが存在すること
            self.assertIn('rank', df.columns)


class TestTrifectaCalculatorWithModel(unittest.TestCase):
    """モデル統合テスト"""

    def test_calculator_without_model(self):
        """モデルなしでのフォールバック動作"""
        calculator = TrifectaCalculator(model_dir='nonexistent_dir')

        # モデルがなくてもエラーにならないこと
        data = {
            'pit_number': [1, 2, 3, 4, 5, 6],
            'win_rate': [30.5, 25.0, 20.0, 18.0, 15.0, 12.0],
            'exhibition_time': [6.72, 6.78, 6.75, 6.80, 6.70, 6.85],
            'avg_st': [0.15, 0.12, 0.18, 0.10, 0.14, 0.20],
            'actual_course': [1, 2, 3, 4, 5, 6]
        }
        df = pd.DataFrame(data)

        # モデルがない場合は均等確率になる
        result = calculator.calculate(df)
        self.assertEqual(len(result), 120)


if __name__ == '__main__':
    unittest.main(verbosity=2)
