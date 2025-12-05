"""
Gradual Rollout System のテストスクリプト

段階的導入システムの動作を確認します。
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.deployment.gradual_rollout import GradualRollout

def test_rollout_stages():
    """各ステージでの有効化率をテスト"""
    print("=" * 70)
    print("段階的導入システム テスト")
    print("=" * 70)
    print()

    rollout = GradualRollout()

    # テスト用の機能名
    test_feature = 'probability_calibration'

    # サンプルレースID (100レース)
    sample_race_ids = list(range(1, 101))

    print("【ステージ別有効化率テスト】")
    print()

    for stage in ['disabled', '10%', '50%', '100%']:
        # ステージを設定
        rollout.update_rollout_stage(test_feature, stage)

        # 各レースで有効化判定
        enabled_count = sum(
            1 for race_id in sample_race_ids
            if rollout.should_enable_feature(test_feature, race_id)
        )

        enabled_rate = (enabled_count / len(sample_race_ids)) * 100

        print(f"ステージ: {stage}")
        print(f"  有効化レース数: {enabled_count}/{len(sample_race_ids)}")
        print(f"  実際の有効化率: {enabled_rate:.1f}%")
        print()


def test_hash_consistency():
    """ハッシュ割り当ての一貫性をテスト"""
    print("=" * 70)
    print("ハッシュ一貫性テスト")
    print("=" * 70)
    print()

    rollout = GradualRollout()
    test_feature = 'probability_calibration'

    # 10%ステージに設定
    rollout.update_rollout_stage(test_feature, '10%')

    # 同じrace_idで複数回判定して一貫性を確認
    test_race_ids = [123, 456, 789]

    print("同じrace_idで10回判定を実行:")
    print()

    for race_id in test_race_ids:
        results = [
            rollout.should_enable_feature(test_feature, race_id)
            for _ in range(10)
        ]

        all_same = len(set(results)) == 1
        status = "[OK]" if all_same else "[FAIL]"

        print(f"race_id {race_id}: {results[0]} (一貫性: {status})")

    print()


def test_health_check():
    """健全性チェック機能をテスト"""
    print("=" * 70)
    print("健全性チェックテスト")
    print("=" * 70)
    print()

    rollout = GradualRollout()
    test_feature = 'probability_calibration'

    # テストケース1: 正常なメトリクス
    print("【テストケース1: 正常なメトリクス】")
    healthy_metrics = {
        'hit_rate_1st': 0.25,
        'hit_rate_top3': 0.10,
        'avg_score_accuracy': 0.70,
        'error_rate': 0.02,
    }

    result = rollout.check_rollout_health(test_feature, healthy_metrics)
    print(f"ステータス: {result['status']}")
    print(f"アクション: {result['action']}")
    if result['issues']:
        print(f"問題: {result['issues']}")
    if result['warnings']:
        print(f"警告: {result['warnings']}")
    print()

    # テストケース2: 警告レベル
    print("【テストケース2: 警告レベル】")
    warning_metrics = {
        'hit_rate_1st': 0.18,
        'hit_rate_top3': 0.08,
        'avg_score_accuracy': 0.63,
        'error_rate': 0.05,
    }

    result = rollout.check_rollout_health(test_feature, warning_metrics)
    print(f"ステータス: {result['status']}")
    print(f"アクション: {result['action']}")
    if result['issues']:
        print(f"問題: {result['issues']}")
    if result['warnings']:
        print(f"警告: {result['warnings']}")
    print()

    # テストケース3: クリティカルレベル
    print("【テストケース3: クリティカルレベル】")
    critical_metrics = {
        'hit_rate_1st': 0.12,
        'hit_rate_top3': 0.03,
        'avg_score_accuracy': 0.55,
        'error_rate': 0.15,
    }

    result = rollout.check_rollout_health(test_feature, critical_metrics)
    print(f"ステータス: {result['status']}")
    print(f"アクション: {result['action']}")
    if result['issues']:
        print("問題:")
        for issue in result['issues']:
            print(f"  - {issue}")
    if result['recommendations']:
        print("推奨:")
        for rec in result['recommendations']:
            print(f"  - {rec}")
    print()


def test_rollout_status():
    """ロールアウト状況の取得をテスト"""
    print("=" * 70)
    print("ロールアウト状況確認")
    print("=" * 70)
    print()

    rollout = GradualRollout()

    status = rollout.get_rollout_status()

    print("【全機能のロールアウト状況】")
    print()

    for feature_name, feature_info in status['feature_rollouts'].items():
        print(f"{feature_name}:")
        print(f"  ステージ: {feature_info['stage']}")
        print(f"  有効化日: {feature_info.get('enabled_at', 'N/A')}")
        print()

    print(f"最終更新: {status['updated_at']}")
    print()


if __name__ == "__main__":
    try:
        test_rollout_stages()
        test_hash_consistency()
        test_health_check()
        test_rollout_status()

        print("=" * 70)
        print("[SUCCESS] 全てのテストが完了しました")
        print("=" * 70)

    except Exception as e:
        print(f"\n[ERROR] テスト実行エラー: {e}")
        import traceback
        traceback.print_exc()
