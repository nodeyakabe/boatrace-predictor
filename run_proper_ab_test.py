"""
適切な期間でA/Bテストを実行

診断結果に基づき、実際にデータが存在する期間でテストを実行します。
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.evaluation.ab_test_dynamic_integration import ABTestDynamicIntegration

if __name__ == "__main__":
    print("=" * 70)
    print("適切な期間でのA/Bテスト実行")
    print("=" * 70)
    print()
    print("推奨期間: 2025-10-18 ~ 2025-11-17（30日間）")
    print("予想テスト可能レース数: 約1,126レース")
    print()
    print("実行中...")
    print()

    ab_test = ABTestDynamicIntegration()

    try:
        comparison = ab_test.run_ab_test(
            start_date='2025-10-18',
            end_date='2025-11-17',
            output_dir='temp/ab_test/proper_test'
        )

        print("\n" + "=" * 70)
        print("A/Bテスト完了 - 詳細レポート")
        print("=" * 70)
        print(f"\n対象レース数: {comparison['total_races']}")
        print(f"期間: {comparison['test_period'][0]} ~ {comparison['test_period'][1]}")

        print("\n【動的統合モード】")
        print(f"  1着的中率: {comparison['dynamic']['hit_rate_1st']:.2%}")
        print(f"  3連単的中率: {comparison['dynamic']['hit_rate_top3']:.2%}")
        print(f"  平均スコア精度: {comparison['dynamic']['avg_score_accuracy']:.4f}")

        print("\n【レガシーモード】")
        print(f"  1着的中率: {comparison['legacy']['hit_rate_1st']:.2%}")
        print(f"  3連単的中率: {comparison['legacy']['hit_rate_top3']:.2%}")
        print(f"  平均スコア精度: {comparison['legacy']['avg_score_accuracy']:.4f}")

        print("\n【改善率】")
        print(f"  1着的中率: {comparison['improvement']['hit_rate_1st']:+.2f}%")
        print(f"  3連単的中率: {comparison['improvement']['hit_rate_top3']:+.2f}%")
        print(f"  スコア精度: {comparison['improvement']['score_accuracy']:+.2f}%")

        print(f"\n【結論】")
        print(f"  {comparison['conclusion']}")

        # 条件別統計があれば表示
        if comparison['dynamic'].get('condition_stats'):
            print(f"\n【動的統合 - 条件別統計】")
            for cond, stats in comparison['dynamic']['condition_stats'].items():
                print(f"  {cond}:")
                print(f"    レース数: {stats['count']}")
                print(f"    1着的中率: {stats['hit_rate_1st']:.2%}")
                print(f"    平均スコア精度: {stats['avg_score_accuracy']:.4f}")

        print("\n" + "=" * 70)
        print("[SUCCESS] A/Bテスト成功")
        print("=" * 70)
        print(f"\n詳細レポート: temp/ab_test/proper_test/ab_test_report.txt")

    except Exception as e:
        print(f"\n[ERROR] A/Bテスト実行エラー: {e}")
        import traceback
        traceback.print_exc()
