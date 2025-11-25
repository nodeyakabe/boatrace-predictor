"""
特徴量生成モジュールのユニットテスト

データ取得に依存せず、特徴量生成ロジックをテスト
- 基本特徴量生成
- 派生特徴量生成
- 数値計算の正確性
- エッジケース処理
"""

import unittest
import pandas as pd
import numpy as np
import sys
sys.path.append('.')

from src.analysis.feature_generator import FeatureGenerator


class TestFeatureGenerator(unittest.TestCase):
    """FeatureGeneratorクラスのテスト"""

    def setUp(self):
        """各テストの前に実行"""
        self.generator = FeatureGenerator()

    def test_initialization(self):
        """正しく初期化されるか"""
        self.assertIsNotNone(self.generator)
        self.assertEqual(self.generator.feature_columns, [])

    def test_pit_advantage_calculation(self):
        """枠番優位性スコアが正しく計算されるか"""
        # テストデータ作成
        df = pd.DataFrame({
            'pit_number': [1, 2, 3, 4, 5, 6]
        })

        result = self.generator.generate_basic_features(df)

        # pit_advantageカラムが追加されているか
        self.assertIn('pit_advantage', result.columns)

        # 値が正しい範囲にあるか（0-1の範囲を想定）
        self.assertTrue((result['pit_advantage'] >= 0).all())
        self.assertTrue((result['pit_advantage'] <= 1).all())

        # 1号艇が最も有利なはず
        pit1_advantage = result.loc[result['pit_number'] == 1, 'pit_advantage'].values[0]
        pit6_advantage = result.loc[result['pit_number'] == 6, 'pit_advantage'].values[0]
        self.assertGreater(pit1_advantage, pit6_advantage)

    def test_class_score_mapping(self):
        """級別スコアが正しくマッピングされるか"""
        df = pd.DataFrame({
            'pit_number': [1, 2, 3, 4, 5],
            'racer_rank': ['A1', 'A2', 'B1', 'B2', None]
        })

        result = self.generator.generate_basic_features(df)

        # class_scoreカラムが追加されているか
        self.assertIn('class_score', result.columns)

        # 値が正しいか
        self.assertEqual(result.loc[result['racer_rank'] == 'A1', 'class_score'].values[0], 4)
        self.assertEqual(result.loc[result['racer_rank'] == 'A2', 'class_score'].values[0], 3)
        self.assertEqual(result.loc[result['racer_rank'] == 'B1', 'class_score'].values[0], 2)
        self.assertEqual(result.loc[result['racer_rank'] == 'B2', 'class_score'].values[0], 1)
        # Noneは0にマッピングされるはず
        self.assertEqual(result.loc[result['racer_rank'].isna(), 'class_score'].values[0], 0)

    def test_experience_score_calculation(self):
        """経験値スコア（勝率 × 級別スコア）が正しく計算されるか"""
        df = pd.DataFrame({
            'pit_number': [1, 2, 3],
            'racer_rank': ['A1', 'A2', 'B1'],
            'win_rate': [0.5, 0.3, 0.2]
        })

        # 基本特徴量を追加
        df = self.generator.generate_basic_features(df)

        # 派生特徴量を追加
        result = self.generator.generate_derived_features(df)

        # experience_scoreカラムが追加されているか
        self.assertIn('experience_score', result.columns)

        # 値が正しいか
        # A1 (class_score=4) × win_rate=0.5 = 2.0
        self.assertAlmostEqual(
            result.loc[result['racer_rank'] == 'A1', 'experience_score'].values[0],
            2.0,
            places=5
        )

        # A2 (class_score=3) × win_rate=0.3 = 0.9
        self.assertAlmostEqual(
            result.loc[result['racer_rank'] == 'A2', 'experience_score'].values[0],
            0.9,
            places=5
        )

    def test_motor_performance_calculation(self):
        """モーター性能スコアが正しく計算されるか"""
        df = pd.DataFrame({
            'pit_number': [1, 2, 3],
            'racer_rank': ['A1', 'A1', 'A1'],
            'win_rate': [0.5, 0.5, 0.5],
            'motor_second_rate': [0.3, 0.2, None],
            'motor_third_rate': [0.4, 0.5, None]
        })

        df = self.generator.generate_basic_features(df)
        result = self.generator.generate_derived_features(df)

        # motor_performanceカラムが追加されているか
        self.assertIn('motor_performance', result.columns)

        # 値が正しいか
        # 0.3 + 0.4 = 0.7
        self.assertAlmostEqual(result.iloc[0]['motor_performance'], 0.7, places=5)
        # 0.2 + 0.5 = 0.7
        self.assertAlmostEqual(result.iloc[1]['motor_performance'], 0.7, places=5)
        # None + None = 0 (fillna)
        self.assertAlmostEqual(result.iloc[2]['motor_performance'], 0.0, places=5)

    def test_boat_performance_calculation(self):
        """ボート性能スコアが正しく計算されるか"""
        df = pd.DataFrame({
            'pit_number': [1, 2],
            'racer_rank': ['A1', 'A1'],
            'win_rate': [0.5, 0.5],
            'boat_second_rate': [0.25, None],
            'boat_third_rate': [0.35, 0.4]
        })

        df = self.generator.generate_basic_features(df)
        result = self.generator.generate_derived_features(df)

        # boat_performanceカラムが追加されているか
        self.assertIn('boat_performance', result.columns)

        # 値が正しいか
        # 0.25 + 0.35 = 0.6
        self.assertAlmostEqual(result.iloc[0]['boat_performance'], 0.6, places=5)
        # 0 (fillna) + 0.4 = 0.4
        self.assertAlmostEqual(result.iloc[1]['boat_performance'], 0.4, places=5)

    def test_equipment_advantage_calculation(self):
        """機材総合優位性が正しく計算されるか"""
        df = pd.DataFrame({
            'pit_number': [1],
            'racer_rank': ['A1'],
            'win_rate': [0.5],
            'motor_second_rate': [0.3],
            'motor_third_rate': [0.4],
            'boat_second_rate': [0.25],
            'boat_third_rate': [0.35]
        })

        df = self.generator.generate_basic_features(df)
        result = self.generator.generate_derived_features(df)

        # equipment_advantageカラムが追加されているか
        self.assertIn('equipment_advantage', result.columns)

        # 値が正しいか
        # motor_performance (0.7) + boat_performance (0.6) = 1.3
        expected = 0.7 + 0.6
        self.assertAlmostEqual(result.iloc[0]['equipment_advantage'], expected, places=5)

    def test_empty_dataframe(self):
        """空のDataFrameを渡したときにエラーが発生しないか"""
        df = pd.DataFrame()

        # エラーが発生しないことを確認
        try:
            result = self.generator.generate_basic_features(df)
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"空のDataFrameでエラーが発生: {e}")

    def test_missing_columns(self):
        """必須カラムが欠けているときの動作"""
        df = pd.DataFrame({
            'pit_number': [1, 2, 3]
            # racer_rankなどが欠けている
        })

        # KeyErrorまたは適切な処理がされることを確認
        # 現在の実装では欠損値として処理されるはず
        result = self.generator.generate_basic_features(df)
        self.assertIn('pit_advantage', result.columns)
        self.assertIn('class_score', result.columns)

    def test_all_nan_values(self):
        """すべてNaNの列が渡されたときの動作"""
        df = pd.DataFrame({
            'pit_number': [1, 2, 3],
            'racer_rank': [None, None, None],
            'win_rate': [None, None, None],
            'motor_second_rate': [None, None, None],
            'motor_third_rate': [None, None, None],
            'boat_second_rate': [None, None, None],
            'boat_third_rate': [None, None, None]
        })

        df = self.generator.generate_basic_features(df)
        result = self.generator.generate_derived_features(df)

        # class_scoreは0で埋められるはず
        self.assertTrue((result['class_score'] == 0).all())

        # experience_scoreも0になるはず
        self.assertTrue((result['experience_score'].fillna(0) == 0).all())

    def test_extreme_values(self):
        """極端な値が入力されたときの動作"""
        df = pd.DataFrame({
            'pit_number': [1, 2, 3],
            'racer_rank': ['A1', 'A1', 'A1'],
            'win_rate': [1.0, 0.0, 0.5],
            'motor_second_rate': [1.0, 0.0, 0.5],
            'motor_third_rate': [1.0, 0.0, 0.5],
            'boat_second_rate': [1.0, 0.0, 0.5],
            'boat_third_rate': [1.0, 0.0, 0.5]
        })

        df = self.generator.generate_basic_features(df)
        result = self.generator.generate_derived_features(df)

        # 極端な値でもエラーが発生しないか
        self.assertIsNotNone(result)

        # 最大値のケース
        max_row = result.iloc[0]
        self.assertEqual(max_row['experience_score'], 4.0)  # 1.0 * 4
        self.assertEqual(max_row['motor_performance'], 2.0)  # 1.0 + 1.0
        self.assertEqual(max_row['boat_performance'], 2.0)  # 1.0 + 1.0
        self.assertEqual(max_row['equipment_advantage'], 4.0)  # 2.0 + 2.0

        # 最小値のケース
        min_row = result.iloc[1]
        self.assertEqual(min_row['experience_score'], 0.0)  # 0.0 * 4
        self.assertEqual(min_row['motor_performance'], 0.0)  # 0.0 + 0.0
        self.assertEqual(min_row['boat_performance'], 0.0)  # 0.0 + 0.0
        self.assertEqual(min_row['equipment_advantage'], 0.0)  # 0.0 + 0.0

    def test_feature_generation_pipeline(self):
        """基本特徴量→派生特徴量のパイプラインが正しく動作するか"""
        df = pd.DataFrame({
            'pit_number': [1, 2, 3, 4, 5, 6],
            'racer_rank': ['A1', 'A2', 'B1', 'B2', 'A1', 'B1'],
            'win_rate': [0.5, 0.4, 0.3, 0.2, 0.6, 0.25],
            'motor_second_rate': [0.3, 0.25, 0.2, 0.15, 0.35, 0.22],
            'motor_third_rate': [0.4, 0.35, 0.3, 0.25, 0.45, 0.32],
            'boat_second_rate': [0.28, 0.23, 0.18, 0.13, 0.33, 0.20],
            'boat_third_rate': [0.38, 0.33, 0.28, 0.23, 0.43, 0.30]
        })

        # パイプライン実行
        df = self.generator.generate_basic_features(df)
        result = self.generator.generate_derived_features(df)

        # 全ての期待される特徴量が存在するか
        expected_features = [
            'pit_advantage',
            'class_score',
            'experience_score',
            'motor_performance',
            'boat_performance',
            'equipment_advantage'
        ]

        for feature in expected_features:
            self.assertIn(feature, result.columns, f"特徴量 '{feature}' が生成されていません")

        # 元のカラムも保持されているか
        original_columns = ['pit_number', 'racer_rank', 'win_rate']
        for col in original_columns:
            self.assertIn(col, result.columns, f"元のカラム '{col}' が失われています")

        # 行数が保持されているか
        self.assertEqual(len(result), 6)


if __name__ == '__main__':
    # テストスイートを作成
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFeatureGenerator)

    # テスト実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 結果サマリー
    print("\n" + "=" * 70)
    print("テスト結果サマリー")
    print("=" * 70)
    print(f"実行テスト数: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失敗: {len(result.failures)}")
    print(f"エラー: {len(result.errors)}")

    # 終了コード
    sys.exit(0 if result.wasSuccessful() else 1)
