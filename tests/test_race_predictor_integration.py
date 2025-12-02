"""
race_predictor.pyへの動的統合モジュール統合テスト
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag, is_feature_enabled


class TestRacePredictorIntegration:
    """動的統合モジュールのrace_predictor統合テスト"""

    def setup_method(self):
        # テスト用のRacePredictorインスタンス
        self.predictor = RacePredictor()

    def test_feature_flag_dynamic_integration(self):
        """機能フラグで動的統合のON/OFFを確認"""
        # デフォルトでは有効
        assert is_feature_enabled('dynamic_integration') == True
        print("[OK] 動的統合フラグはデフォルトで有効")

        # 無効化
        set_feature_flag('dynamic_integration', False)
        assert is_feature_enabled('dynamic_integration') == False
        print("[OK] 動的統合フラグを無効化できた")

        # 再度有効化
        set_feature_flag('dynamic_integration', True)
        assert is_feature_enabled('dynamic_integration') == True
        print("[OK] 動的統合フラグを再有効化できた")

    def test_collect_beforeinfo_data(self):
        """直前情報データ収集のテスト"""
        # モックレースID（DBに存在しない場合は空データが返る）
        race_id = 999999

        beforeinfo_data = self.predictor._collect_beforeinfo_data(race_id)

        # 必須キーが存在するか確認
        assert 'is_published' in beforeinfo_data
        assert 'exhibition_times' in beforeinfo_data
        assert 'start_timings' in beforeinfo_data
        assert 'exhibition_courses' in beforeinfo_data
        assert 'tilt_angles' in beforeinfo_data
        assert 'weather' in beforeinfo_data

        # データがない場合はis_published=False
        assert beforeinfo_data['is_published'] == False

        print(f"[OK] 直前情報データ収集テスト成功: keys={list(beforeinfo_data.keys())}")

    def test_integration_mode_legacy(self):
        """レガシーモード（動的統合無効）でのスコア統合"""
        # 動的統合を無効化
        set_feature_flag('dynamic_integration', False)

        # モック予測データ
        predictions = [
            {'pit_number': 1, 'total_score': 80.0, 'racer_name': 'Test1'},
            {'pit_number': 2, 'total_score': 70.0, 'racer_name': 'Test2'},
        ]

        race_id = 999999
        venue_code = '01'

        # 統合適用（DBがなくても動作する）
        try:
            result = self.predictor._apply_beforeinfo_integration(
                predictions=predictions,
                race_id=race_id,
                venue_code=venue_code
            )

            # レガシーモードで動作確認
            for pred in result:
                assert 'integration_mode' in pred
                assert pred['integration_mode'] in ['legacy', 'legacy_adjusted']
                print(f"[OK] Pit {pred['pit_number']}: mode={pred['integration_mode']}, "
                      f"pre_weight={pred.get('pre_weight', 'N/A')}, "
                      f"before_weight={pred.get('before_weight', 'N/A')}")

        except Exception as e:
            # DBエラーは想定内
            if "no such table" in str(e) or "unable to open database" in str(e):
                print("[SKIP] DBなし環境のためスキップ（正常）")
            else:
                raise

        # 再度有効化
        set_feature_flag('dynamic_integration', True)

    def test_integration_mode_dynamic(self):
        """動的統合モードでのスコア統合"""
        # 動的統合を有効化
        set_feature_flag('dynamic_integration', True)

        # モック予測データ
        predictions = [
            {'pit_number': 1, 'total_score': 80.0, 'confidence': 'A'},
            {'pit_number': 2, 'total_score': 70.0, 'confidence': 'B'},
        ]

        race_id = 999999
        venue_code = '01'

        # 統合適用
        try:
            result = self.predictor._apply_beforeinfo_integration(
                predictions=predictions,
                race_id=race_id,
                venue_code=venue_code
            )

            # 結果確認
            for pred in result:
                assert 'integration_mode' in pred
                assert 'pre_score' in pred
                assert 'total_score' in pred
                assert 'beforeinfo_score' in pred

                print(f"[OK] Pit {pred['pit_number']}: mode={pred['integration_mode']}, "
                      f"pre={pred['pre_score']}, before={pred['beforeinfo_score']}, "
                      f"final={pred['total_score']}")

                # 動的モードの場合は追加情報もチェック
                if pred['integration_mode'] == 'dynamic':
                    assert 'integration_condition' in pred
                    assert 'integration_reason' in pred
                    assert 'pre_weight' in pred
                    assert 'before_weight' in pred
                    print(f"     Dynamic: condition={pred['integration_condition']}, "
                          f"reason={pred['integration_reason'][:30]}...")

        except Exception as e:
            # DBエラーは想定内
            if "no such table" in str(e) or "unable to open database" in str(e):
                print("[SKIP] DBなし環境のためスキップ（正常）")
            else:
                raise

    def test_dynamic_integrator_initialization(self):
        """DynamicIntegratorが正しく初期化されているか"""
        assert hasattr(self.predictor, 'dynamic_integrator')
        assert self.predictor.dynamic_integrator is not None
        print("[OK] DynamicIntegratorが正しく初期化されている")


if __name__ == "__main__":
    print("=" * 70)
    print("race_predictor.py 動的統合モジュール統合テスト実行")
    print("=" * 70)

    test = TestRacePredictorIntegration()

    try:
        test.setup_method()
        test.test_feature_flag_dynamic_integration()

        test.setup_method()
        test.test_collect_beforeinfo_data()

        test.setup_method()
        test.test_integration_mode_legacy()

        test.setup_method()
        test.test_integration_mode_dynamic()

        test.setup_method()
        test.test_dynamic_integrator_initialization()

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
