"""
Phase 2-3 統合テスト

進入予測モデル、確率キャリブレーション、複合バフ学習の統合をテスト
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag, is_feature_enabled


class TestPhase23Integration:
    """Phase 2-3 統合テスト"""

    def setup_method(self):
        self.predictor = RacePredictor()

    def test_entry_prediction_model_integration(self):
        """進入予測モデル統合テスト"""
        # 機能フラグ確認
        assert is_feature_enabled('entry_prediction_model'), "進入予測モデルが有効でない"

        # EntryPredictionModelが初期化されているか
        assert hasattr(self.predictor, 'entry_prediction_model'), "EntryPredictionModel未初期化"
        assert self.predictor.entry_prediction_model is not None

        # メソッドの存在確認
        assert hasattr(self.predictor, '_apply_entry_prediction'), "_apply_entry_predictionメソッド未実装"

        print("[OK] 進入予測モデル統合確認成功")

    def test_probability_calibrator_integration(self):
        """確率キャリブレーション統合テスト"""
        # 機能フラグ確認（デフォルトではfalseの可能性）
        print(f"  probability_calibration enabled: {is_feature_enabled('probability_calibration')}")

        # ProbabilityCalibratorが初期化されているか
        assert hasattr(self.predictor, 'probability_calibrator'), "ProbabilityCalibrator未初期化"
        assert self.predictor.probability_calibrator is not None

        # メソッドの存在確認
        assert hasattr(self.predictor, '_apply_probability_calibration'), "_apply_probability_calibrationメソッド未実装"

        print("[OK] 確率キャリブレーション統合確認成功")

    def test_entry_prediction_disabled(self):
        """進入予測無効化テスト"""
        # 無効化
        set_feature_flag('entry_prediction_model', False)

        # モック予測データ
        predictions = [
            {'pit_number': 1, 'total_score': 80.0},
            {'pit_number': 2, 'total_score': 70.0},
        ]

        # 適用（無効なので変更なし）
        result = self.predictor._apply_entry_prediction(predictions, race_id=999999)

        # スコアが変わっていないことを確認
        assert result[0]['total_score'] == 80.0
        assert result[1]['total_score'] == 70.0
        assert 'entry_impact_score' not in result[0], "無効時は進入影響スコアが追加されない"

        # 再度有効化
        set_feature_flag('entry_prediction_model', True)

        print("[OK] 進入予測無効化テスト成功")

    def test_probability_calibration_disabled(self):
        """確率キャリブレーション無効化テスト"""
        # 無効化
        set_feature_flag('probability_calibration', False)

        # モック予測データ
        predictions = [
            {'pit_number': 1, 'total_score': 80.0},
            {'pit_number': 2, 'total_score': 70.0},
        ]

        # 適用（無効なので変更なし）
        result = self.predictor._apply_probability_calibration(predictions)

        # キャリブレーション情報が追加されていないことを確認
        assert 'calibrated_score' not in result[0], "無効時はキャリブレーション情報が追加されない"
        assert 'calibrated_probability' not in result[0]

        # 再度有効化（元の状態に戻す）
        set_feature_flag('probability_calibration', False)  # デフォルトはfalseのまま

        print("[OK] 確率キャリブレーション無効化テスト成功")

    def test_all_modules_initialized(self):
        """全モジュール初期化確認"""
        modules = [
            ('dynamic_integrator', 'DynamicIntegrator'),
            ('entry_prediction_model', 'EntryPredictionModel'),
            ('probability_calibrator', 'ProbabilityCalibrator'),
            ('beforeinfo_scorer', 'BeforeInfoScorer'),
        ]

        for attr_name, module_name in modules:
            assert hasattr(self.predictor, attr_name), f"{module_name}が未初期化"
            assert getattr(self.predictor, attr_name) is not None, f"{module_name}がNone"
            print(f"  [OK] {module_name}が正しく初期化されています")

        print("[OK] 全モジュール初期化確認成功")

    def test_feature_flags_state(self):
        """機能フラグ状態確認"""
        from config.feature_flags import get_all_features

        features = get_all_features()

        print("\n  現在の機能フラグ状態:")
        for name, enabled in features.items():
            status = "有効" if enabled else "無効"
            print(f"    {name}: {status}")

        # Phase 1機能は有効であるべき
        assert features['dynamic_integration'] == True, "動的統合が無効"
        assert features['entry_prediction_model'] == True, "進入予測が無効"

        # Phase 2機能はデフォルトで無効
        # (probability_calibrationは必要に応じて有効化)

        print("\n[OK] 機能フラグ状態確認成功")


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 2-3 統合テスト実行")
    print("=" * 70)

    test = TestPhase23Integration()

    try:
        test.setup_method()
        test.test_entry_prediction_model_integration()

        test.setup_method()
        test.test_probability_calibrator_integration()

        test.setup_method()
        test.test_entry_prediction_disabled()

        test.setup_method()
        test.test_probability_calibration_disabled()

        test.setup_method()
        test.test_all_modules_initialized()

        test.setup_method()
        test.test_feature_flags_state()

        print("\n" + "=" * 70)
        print("[SUCCESS] 全テスト成功！")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n[FAIL] テスト失敗: {e}")
        import traceback
        traceback.print_exc()
        raise
    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        import traceback
        traceback.print_exc()
        raise
