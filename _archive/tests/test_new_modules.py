"""
新規実装モジュールの簡易動作テスト
"""

import sys
sys.path.insert(0, 'c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032')

from config.feature_flags import (
    is_feature_enabled,
    get_enabled_features,
    get_feature_risk,
    FEATURE_FLAGS
)
from src.analysis.buff_auto_learner import BuffAutoLearner, BuffValidationResult
from src.analysis.probability_calibrator import ProbabilityCalibrator, CalibrationBin


def test_feature_flags():
    """機能フラグのテスト"""
    print("=" * 60)
    print("機能フラグテスト")
    print("=" * 60)

    print("\n有効な機能:")
    for feature in get_enabled_features():
        print(f"  - {feature}")

    print("\n各機能の状態:")
    for feature, enabled in FEATURE_FLAGS.items():
        status = "有効" if enabled else "無効"
        risk = get_feature_risk(feature)
        print(f"  {feature}: {status} (リスク: {risk['risk_level']})")

    print("\n[OK] 機能フラグテスト完了")


def test_buff_auto_learner():
    """バフ自動学習のテスト"""
    print("\n" + "=" * 60)
    print("バフ自動学習モジュールテスト")
    print("=" * 60)

    try:
        learner = BuffAutoLearner("data/boatrace.db")
        print("\n[OK] BuffAutoLearner インスタンス生成成功")
        print(f"  - 最低サンプル数: {learner.MIN_SAMPLES}")
        print(f"  - 統計的有意性閾値: {learner.SIGNIFICANCE_THRESHOLD}")

        # BuffValidationResult のテスト
        result = BuffValidationResult(
            rule_id="test_rule",
            sample_count=100,
            hit_rate=0.3,
            expected_rate=0.167,
            lift=1.8,
            statistical_significance=2.5,
            recommended_buff=8.0,
            is_valid=True
        )
        print(f"\n[OK] BuffValidationResult 作成成功")
        print(f"  - ルールID: {result.rule_id}")
        print(f"  - サンプル数: {result.sample_count}")
        print(f"  - リフト: {result.lift:.2f}")
        print(f"  - 有効: {result.is_valid}")

    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        return False

    print("\n[OK] バフ自動学習テスト完了")
    return True


def test_probability_calibrator():
    """確率キャリブレーションのテスト"""
    print("\n" + "=" * 60)
    print("確率キャリブレーションモジュールテスト")
    print("=" * 60)

    try:
        calibrator = ProbabilityCalibrator("data/boatrace.db")
        print("\n[OK] ProbabilityCalibrator インスタンス生成成功")
        print(f"  - ビン数: {calibrator.NUM_BINS}")
        print(f"  - 保存先: {calibrator.CALIBRATION_FILE}")

        # CalibrationBin のテスト
        bin_obj = CalibrationBin(
            score_min=50.0,
            score_max=60.0,
            predicted_count=100,
            actual_wins=30,
            predicted_prob=0.275,
            actual_prob=0.3
        )
        print(f"\n[OK] CalibrationBin 作成成功")
        print(f"  - スコア範囲: {bin_obj.score_min}-{bin_obj.score_max}")
        print(f"  - 予測確率: {bin_obj.predicted_prob:.3f}")
        print(f"  - 実際の確率: {bin_obj.actual_prob:.3f}")

        # スコアキャリブレーションのテスト
        test_score = 75.0
        calibrated = calibrator.calibrate_score(test_score)
        print(f"\n[OK] スコアキャリブレーションテスト")
        print(f"  - 元のスコア: {test_score}")
        print(f"  - キャリブレーション後: {calibrated}")

    except Exception as e:
        print(f"\n[ERROR] エラー: {e}")
        return False

    print("\n[OK] 確率キャリブレーションテスト完了")
    return True


def main():
    """メインテスト実行"""
    print("\n新規実装モジュールの動作テスト開始\n")

    results = []

    # 各テストを実行
    test_feature_flags()
    results.append(("機能フラグ", True))

    results.append(("バフ自動学習", test_buff_auto_learner()))
    results.append(("確率キャリブレーション", test_probability_calibrator()))

    # 結果サマリー
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "[OK] 成功" if passed else "[ERROR] 失敗"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("すべてのテストが成功しました!")
    else:
        print("一部のテストが失敗しました。")
    print("=" * 60)


if __name__ == "__main__":
    main()
