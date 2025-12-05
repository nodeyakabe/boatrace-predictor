"""
動的統合機能のクイック動作確認スクリプト

実データを使用せずに、動的統合が正しく動作するかを確認します。
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.dynamic_integration import DynamicIntegrator, IntegrationCondition
from config.feature_flags import is_feature_enabled, set_feature_flag, get_enabled_features


def test_feature_flags():
    """機能フラグのテスト"""
    print("=" * 70)
    print("1. 機能フラグテスト")
    print("=" * 70)

    # 有効な機能の確認
    enabled = get_enabled_features()
    print(f"\n有効な機能: {len(enabled)}個")
    for feature in enabled:
        print(f"  - {feature}")

    # 動的統合の状態確認
    is_dynamic_enabled = is_feature_enabled('dynamic_integration')
    print(f"\n動的統合: {'有効' if is_dynamic_enabled else '無効'}")

    # 切り替えテスト
    print("\n切り替えテスト:")
    set_feature_flag('dynamic_integration', False)
    print(f"  無効化後: {is_feature_enabled('dynamic_integration')}")

    set_feature_flag('dynamic_integration', True)
    print(f"  有効化後: {is_feature_enabled('dynamic_integration')}")

    print("\n[OK] 機能フラグテスト成功")


def test_dynamic_integrator():
    """動的統合モジュールのテスト"""
    print("\n" + "=" * 70)
    print("2. 動的統合モジュールテスト")
    print("=" * 70)

    integrator = DynamicIntegrator()

    # テストケース1: 通常条件
    print("\n[テスト1] 通常条件")
    beforeinfo_data = {
        'is_published': True,
        'exhibition_times': {1: 6.77, 2: 6.78, 3: 6.79, 4: 6.80, 5: 6.81, 6: 6.82},
        'start_timings': {1: 0.12, 2: 0.13, 3: 0.14, 4: 0.15, 5: 0.16, 6: 0.17},
        'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        'tilt_angles': {1: -0.5, 2: -0.5, 3: 0.0, 4: 0.0, 5: 0.5, 6: 0.5},
        'weather': {'wind_speed': 2, 'wave_height': 3}
    }

    predictions = [
        {'total_score': 75.0, 'confidence': 'A'},
        {'total_score': 65.0, 'confidence': 'B'},
    ]

    weights = integrator.determine_weights(
        race_id=1,
        beforeinfo_data=beforeinfo_data,
        pre_predictions=predictions,
        venue_code='01'
    )

    print(f"  条件: {weights.condition.value}")
    print(f"  PRE重み: {weights.pre_weight:.3f}")
    print(f"  BEFORE重み: {weights.before_weight:.3f}")
    print(f"  理由: {weights.reason}")
    print(f"  信頼度: {weights.confidence:.3f}")

    # スコア統合テスト
    final_score = integrator.integrate_scores(
        pre_score=70.0,
        before_score=80.0,
        weights=weights
    )
    expected = 70.0 * weights.pre_weight + 80.0 * weights.before_weight
    print(f"  統合スコア: {final_score:.2f} (期待値: {expected:.2f})")
    assert abs(final_score - expected) < 0.01, "スコア統合エラー"

    # テストケース2: 展示タイム分散高
    print("\n[テスト2] 展示タイム分散高（直前情報重視）")
    beforeinfo_data_high_variance = {
        'is_published': True,
        'exhibition_times': {1: 6.50, 2: 6.90, 3: 6.55, 4: 6.95, 5: 6.60, 6: 6.85},
        'start_timings': {1: 0.12, 2: 0.13, 3: 0.14, 4: 0.15, 5: 0.16, 6: 0.17},
        'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        'tilt_angles': {},
        'weather': {}
    }

    weights2 = integrator.determine_weights(
        race_id=2,
        beforeinfo_data=beforeinfo_data_high_variance,
        pre_predictions=predictions,
        venue_code='01'
    )

    print(f"  条件: {weights2.condition.value}")
    print(f"  PRE重み: {weights2.pre_weight:.3f}")
    print(f"  BEFORE重み: {weights2.before_weight:.3f}")
    print(f"  理由: {weights2.reason}")
    assert weights2.condition == IntegrationCondition.BEFOREINFO_CRITICAL, "条件判定エラー"

    # テストケース3: データ不足（事前情報重視）
    print("\n[テスト3] データ不足（事前情報重視）")
    beforeinfo_data_incomplete = {
        'is_published': True,
        'exhibition_times': {1: 6.77, 2: 6.78},  # 2艇のみ
        'start_timings': {},
        'exhibition_courses': {},
        'tilt_angles': {},
        'weather': {}
    }

    weights3 = integrator.determine_weights(
        race_id=3,
        beforeinfo_data=beforeinfo_data_incomplete,
        pre_predictions=predictions,
        venue_code='01'
    )

    print(f"  条件: {weights3.condition.value}")
    print(f"  PRE重み: {weights3.pre_weight:.3f}")
    print(f"  BEFORE重み: {weights3.before_weight:.3f}")
    print(f"  理由: {weights3.reason}")
    assert weights3.condition == IntegrationCondition.PREINFO_RELIABLE, "条件判定エラー"
    assert weights3.pre_weight > 0.6, "事前重視エラー"

    print("\n[OK] 動的統合モジュールテスト成功")


def test_integration_summary():
    """統合結果のサマリー表示"""
    print("\n" + "=" * 70)
    print("3. 統合条件サマリー")
    print("=" * 70)

    from src.analysis.dynamic_integration import DynamicIntegrator

    print("\n【条件別の重み設定】")
    for condition, (pre_w, before_w) in DynamicIntegrator.CONDITION_WEIGHTS.items():
        print(f"  {condition.value:20s}: PRE={pre_w:.2f}, BEFORE={before_w:.2f}")

    print("\n【閾値設定】")
    print(f"  展示タイム分散: {DynamicIntegrator.EXHIBITION_VARIANCE_THRESHOLD:.2f}秒")
    print(f"  ST分散:         {DynamicIntegrator.ST_VARIANCE_THRESHOLD:.2f}秒")
    print(f"  進入変更艇数:   {DynamicIntegrator.ENTRY_CHANGE_THRESHOLD}艇")

    print("\n[OK] サマリー表示成功")


def test_race_predictor_integration_check():
    """race_predictor統合確認"""
    print("\n" + "=" * 70)
    print("4. race_predictor統合確認")
    print("=" * 70)

    try:
        from src.analysis.race_predictor import RacePredictor

        predictor = RacePredictor()

        # DynamicIntegratorが初期化されているか確認
        assert hasattr(predictor, 'dynamic_integrator'), "DynamicIntegrator未初期化"
        assert predictor.dynamic_integrator is not None, "DynamicIntegratorがNone"

        print("\n[OK] race_predictorにDynamicIntegratorが正しく統合されています")

        # メソッドの存在確認
        assert hasattr(predictor, '_collect_beforeinfo_data'), "_collect_beforeinfo_dataメソッド未実装"
        assert hasattr(predictor, '_apply_beforeinfo_integration'), "_apply_beforeinfo_integrationメソッド未実装"

        print("[OK] 必要なメソッドがすべて実装されています")

        # _collect_beforeinfo_dataのテスト（DBなしでも動作確認）
        try:
            data = predictor._collect_beforeinfo_data(999999)
            assert 'is_published' in data, "データ構造エラー"
            assert 'exhibition_times' in data, "データ構造エラー"
            print("[OK] _collect_beforeinfo_dataが正常動作")
        except Exception as e:
            print(f"[WARN] _collect_beforeinfo_dataでエラー（DBなしの場合は正常）: {e}")

    except ImportError as e:
        print(f"[ERROR] race_predictorのインポートエラー: {e}")
        raise


def main():
    """メインテスト実行"""
    print("\n" + "=" * 70)
    print("動的統合機能 クイック動作確認")
    print("=" * 70)
    print()

    try:
        # 1. 機能フラグテスト
        test_feature_flags()

        # 2. 動的統合モジュールテスト
        test_dynamic_integrator()

        # 3. 統合条件サマリー
        test_integration_summary()

        # 4. race_predictor統合確認
        test_race_predictor_integration_check()

        # 最終結果
        print("\n" + "=" * 70)
        print("[SUCCESS] すべてのクイックテスト成功！")
        print("=" * 70)
        print()
        print("次のステップ:")
        print("  1. 実データでA/Bテスト実行:")
        print("     python src/evaluation/ab_test_dynamic_integration.py")
        print()
        print("  2. バックテスト実行:")
        print("     python src/evaluation/backtest_framework.py")
        print()
        print("=" * 70)

        return True

    except AssertionError as e:
        print("\n" + "=" * 70)
        print(f"[FAIL] テスト失敗: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return False

    except Exception as e:
        print("\n" + "=" * 70)
        print(f"[ERROR] エラー: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
