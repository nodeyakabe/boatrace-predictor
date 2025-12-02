"""
Walk-forward Backtestのテストスクリプト

短期間でのテストを実行します。
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.evaluation.walkforward_backtest import WalkForwardBacktest

if __name__ == "__main__":
    print("=" * 70)
    print("Walk-forward Backtest テスト実行")
    print("=" * 70)
    print()
    print("設定:")
    print("  期間: 2025-11-01 ~ 2025-11-17 (17日間)")
    print("  訓練期間: 14日")
    print("  テスト期間: 3日")
    print("  ステップ間隔: 3日")
    print()

    backtest = WalkForwardBacktest()

    try:
        result = backtest.run_walkforward(
            start_date='2025-11-01',
            end_date='2025-11-17',
            train_days=14,
            test_days=3,
            step_days=3,
            output_dir='temp/walkforward/test'
        )

        print("\n" + "=" * 70)
        print("Walk-forward Backtest 完了")
        print("=" * 70)

        summary = result['summary']

        print(f"\n総ステップ数: {summary['total_steps']}")
        print(f"総評価レース数: {summary['total_races']}")

        print("\n【全体統計】")
        print(f"  1着的中率: {summary['overall_hit_rate_1st']:.2%}")
        print(f"  3連単的中率: {summary['overall_hit_rate_top3']:.2%}")
        print(f"  平均スコア精度: {summary['overall_score_accuracy']:.4f}")

        print("\n【ステップ平均】")
        print(f"  平均1着的中率: {summary['step_stats']['avg_hit_rate_1st']:.2%}")
        print(f"  平均3連単的中率: {summary['step_stats']['avg_hit_rate_top3']:.2%}")
        print(f"  平均スコア精度: {summary['step_stats']['avg_score_accuracy']:.4f}")

        print(f"\n詳細レポート: {result['output_dir']}/walkforward_report.txt")

        print("\n" + "=" * 70)
        print("[SUCCESS] テスト成功")
        print("=" * 70)

    except Exception as e:
        print(f"\n[ERROR] テスト実行エラー: {e}")
        import traceback
        traceback.print_exc()
