"""
クイックA/Bテスト（少数サンプル）

処理を高速化するため、少数のレースでテストします。
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.evaluation.ab_test_dynamic_integration import ABTestDynamicIntegration

if __name__ == "__main__":
    print("=" * 70)
    print("クイックA/Bテスト実行（10日間サンプル）")
    print("=" * 70)
    print()
    print("期間: 2025-11-08 ~ 2025-11-17（10日間）")
    print("予想レース数: 約350-400レース")
    print()
    print("実行中...")
    print()

    ab_test = ABTestDynamicIntegration()

    try:
        comparison = ab_test.run_ab_test(
            start_date='2025-11-08',
            end_date='2025-11-17',
            output_dir='temp/ab_test/quick'
        )

        print("\n" + "=" * 70)
        print("クイックA/Bテスト完了")
        print("=" * 70)
        print(f"\n対象レース数: {comparison['total_races']}")

        if comparison['total_races'] > 0:
            print(f"期間: {comparison['test_period'][0]} ~ {comparison['test_period'][1]}")

            print("\n【動的統合モード】")
            print(f"  1着的中率: {comparison['dynamic']['hit_rate_1st']:.2%}")
            print(f"  3連単的中率: {comparison['dynamic']['hit_rate_top3']:.2%}")
            print(f"  スコア精度: {comparison['dynamic']['avg_score_accuracy']:.4f}")

            print("\n【レガシーモード】")
            print(f"  1着的中率: {comparison['legacy']['hit_rate_1st']:.2%}")
            print(f"  3連単的中率: {comparison['legacy']['hit_rate_top3']:.2%}")
            print(f"  スコア精度: {comparison['legacy']['avg_score_accuracy']:.4f}")

            print("\n【改善率】")
            print(f"  1着的中率: {comparison['improvement']['hit_rate_1st']:+.2f}%")
            print(f"  3連単的中率: {comparison['improvement']['hit_rate_top3']:+.2f}%")
            print(f"  スコア精度: {comparison['improvement']['score_accuracy']:+.2f}%")

            print(f"\n【結論】")
            print(f"  {comparison['conclusion']}")

            print("\n" + "=" * 70)
            print("[SUCCESS] クイックテスト成功")
            print("=" * 70)
        else:
            print("\n[WARNING] 評価可能なレースが0件でした")
            print("データの期間を確認してください")

    except Exception as e:
        print(f"\n[ERROR] テスト実行エラー: {e}")
        import traceback
        traceback.print_exc()
