"""
動的統合 vs レガシーモード A/Bテスト

同じデータセットで両モードの精度を比較し、
動的統合の効果を定量的に評価する。
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from src.evaluation.backtest_framework import BacktestFramework
from config.feature_flags import set_feature_flag


class ABTestDynamicIntegration:
    """動的統合A/Bテスト"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path
        self.framework = BacktestFramework(db_path)

    def run_ab_test(
        self,
        start_date: str,
        end_date: str,
        venue_codes=None,
        output_dir: str = "temp/ab_test"
    ):
        """
        A/Bテスト実行

        Args:
            start_date: 開始日
            end_date: 終了日
            venue_codes: 対象会場コード
            output_dir: 結果出力ディレクトリ
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        print("=" * 70)
        print("動的統合 vs レガシーモード A/Bテスト")
        print("=" * 70)
        print(f"期間: {start_date} ~ {end_date}")
        print()

        # テストA: 動的統合モード
        print("[A] 動的統合モードでバックテスト実行中...")
        set_feature_flag('dynamic_integration', True)
        summary_dynamic = self.framework.run_backtest(
            start_date=start_date,
            end_date=end_date,
            venue_codes=venue_codes,
            output_dir=f"{output_dir}/dynamic"
        )

        # テストB: レガシーモード
        print("\n[B] レガシーモードでバックテスト実行中...")
        set_feature_flag('dynamic_integration', False)
        summary_legacy = self.framework.run_backtest(
            start_date=start_date,
            end_date=end_date,
            venue_codes=venue_codes,
            output_dir=f"{output_dir}/legacy"
        )

        # 動的統合を元に戻す
        set_feature_flag('dynamic_integration', True)

        # 比較分析
        comparison = self._compare_results(summary_dynamic, summary_legacy)

        # レポート作成
        self._generate_report(comparison, output_dir)

        # 結果表示
        self._print_results(comparison)

        return comparison

    def _compare_results(self, summary_dynamic, summary_legacy):
        """結果比較"""
        # 精度向上率計算
        hit_1st_improvement = (
            (summary_dynamic.hit_rate_1st - summary_legacy.hit_rate_1st)
            / summary_legacy.hit_rate_1st * 100
            if summary_legacy.hit_rate_1st > 0 else 0
        )

        hit_top3_improvement = (
            (summary_dynamic.hit_rate_top3 - summary_legacy.hit_rate_top3)
            / summary_legacy.hit_rate_top3 * 100
            if summary_legacy.hit_rate_top3 > 0 else 0
        )

        score_accuracy_improvement = (
            (summary_dynamic.avg_score_accuracy - summary_legacy.avg_score_accuracy)
            / abs(summary_legacy.avg_score_accuracy) * 100
            if summary_legacy.avg_score_accuracy != 0 else 0
        )

        return {
            'test_period': summary_dynamic.date_range,
            'total_races': summary_dynamic.total_races,
            'dynamic': {
                'hit_rate_1st': summary_dynamic.hit_rate_1st,
                'hit_rate_top3': summary_dynamic.hit_rate_top3,
                'avg_score_accuracy': summary_dynamic.avg_score_accuracy,
                'mode_stats': summary_dynamic.mode_stats,
                'condition_stats': summary_dynamic.condition_stats
            },
            'legacy': {
                'hit_rate_1st': summary_legacy.hit_rate_1st,
                'hit_rate_top3': summary_legacy.hit_rate_top3,
                'avg_score_accuracy': summary_legacy.avg_score_accuracy,
                'mode_stats': summary_legacy.mode_stats
            },
            'improvement': {
                'hit_rate_1st': hit_1st_improvement,
                'hit_rate_top3': hit_top3_improvement,
                'score_accuracy': score_accuracy_improvement
            },
            'conclusion': self._determine_conclusion(
                hit_1st_improvement,
                hit_top3_improvement,
                score_accuracy_improvement
            )
        }

    def _determine_conclusion(
        self,
        hit_1st_improvement: float,
        hit_top3_improvement: float,
        score_accuracy_improvement: float
    ) -> str:
        """結論を判定"""
        if hit_1st_improvement > 10 and score_accuracy_improvement > 5:
            return "優秀 - 動的統合は大幅な精度向上を実現"
        elif hit_1st_improvement > 5 and score_accuracy_improvement > 2:
            return "良好 - 動的統合は明確な精度向上を実現"
        elif hit_1st_improvement > 0 and score_accuracy_improvement > 0:
            return "改善 - 動的統合は小幅な精度向上を実現"
        elif hit_1st_improvement > -5:
            return "中立 - 動的統合の効果は限定的"
        else:
            return "要改善 - 動的統合の調整が必要"

    def _generate_report(self, comparison: dict, output_dir: str):
        """レポート作成"""
        # JSON保存
        report_data = {
            'test_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'test_period': comparison['test_period'],
            'total_races': comparison['total_races'],
            'dynamic_mode': {
                'hit_rate_1st': round(comparison['dynamic']['hit_rate_1st'], 4),
                'hit_rate_top3': round(comparison['dynamic']['hit_rate_top3'], 4),
                'avg_score_accuracy': round(comparison['dynamic']['avg_score_accuracy'], 4)
            },
            'legacy_mode': {
                'hit_rate_1st': round(comparison['legacy']['hit_rate_1st'], 4),
                'hit_rate_top3': round(comparison['legacy']['hit_rate_top3'], 4),
                'avg_score_accuracy': round(comparison['legacy']['avg_score_accuracy'], 4)
            },
            'improvement': {
                'hit_rate_1st': round(comparison['improvement']['hit_rate_1st'], 2),
                'hit_rate_top3': round(comparison['improvement']['hit_rate_top3'], 2),
                'score_accuracy': round(comparison['improvement']['score_accuracy'], 2)
            },
            'conclusion': comparison['conclusion']
        }

        with open(f"{output_dir}/ab_test_report.json", 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        # テキストレポート作成
        with open(f"{output_dir}/ab_test_report.txt", 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("動的統合 vs レガシーモード A/Bテスト結果\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"テスト実行日時: {report_data['test_date']}\n")
            f.write(f"テスト期間: {comparison['test_period'][0]} ~ {comparison['test_period'][1]}\n")
            f.write(f"対象レース数: {comparison['total_races']}\n\n")

            f.write("【動的統合モード】\n")
            f.write(f"  1着的中率: {comparison['dynamic']['hit_rate_1st']:.2%}\n")
            f.write(f"  3連単的中率: {comparison['dynamic']['hit_rate_top3']:.2%}\n")
            f.write(f"  平均スコア精度: {comparison['dynamic']['avg_score_accuracy']:.4f}\n\n")

            f.write("【レガシーモード】\n")
            f.write(f"  1着的中率: {comparison['legacy']['hit_rate_1st']:.2%}\n")
            f.write(f"  3連単的中率: {comparison['legacy']['hit_rate_top3']:.2%}\n")
            f.write(f"  平均スコア精度: {comparison['legacy']['avg_score_accuracy']:.4f}\n\n")

            f.write("【改善率】\n")
            f.write(f"  1着的中率: {comparison['improvement']['hit_rate_1st']:+.2f}%\n")
            f.write(f"  3連単的中率: {comparison['improvement']['hit_rate_top3']:+.2f}%\n")
            f.write(f"  スコア精度: {comparison['improvement']['score_accuracy']:+.2f}%\n\n")

            f.write("【結論】\n")
            f.write(f"  {comparison['conclusion']}\n\n")

            # 条件別統計（動的統合のみ）
            if comparison['dynamic']['condition_stats']:
                f.write("【動的統合 - 条件別統計】\n")
                for cond, stats in comparison['dynamic']['condition_stats'].items():
                    f.write(f"  {cond}:\n")
                    f.write(f"    レース数: {stats['count']}\n")
                    f.write(f"    1着的中率: {stats['hit_rate_1st']:.2%}\n")
                    f.write(f"    3連単的中率: {stats['hit_rate_top3']:.2%}\n")
                    f.write(f"    平均スコア精度: {stats['avg_score_accuracy']:.4f}\n\n")

            f.write("=" * 70 + "\n")

        print(f"[INFO] レポートを保存しました: {output_dir}/ab_test_report.txt")

    def _print_results(self, comparison: dict):
        """結果を表示"""
        print("\n" + "=" * 70)
        print("A/Bテスト結果サマリー")
        print("=" * 70)
        print(f"対象レース数: {comparison['total_races']}")
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

        # 条件別統計
        if comparison['dynamic']['condition_stats']:
            print(f"\n【動的統合 - 条件別統計】")
            for cond, stats in comparison['dynamic']['condition_stats'].items():
                print(f"  {cond}: レース{stats['count']}件, 1着的中率{stats['hit_rate_1st']:.2%}")

        print("\n" + "=" * 70)


if __name__ == "__main__":
    print("=" * 70)
    print("動的統合 A/Bテスト 実行")
    print("=" * 70)

    # テスト期間設定（過去1週間）
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    print(f"\nテスト期間: {start_date} ~ {end_date}")
    print("注: 実運用では過去1ヶ月以上のデータで検証してください\n")

    ab_test = ABTestDynamicIntegration()

    try:
        comparison = ab_test.run_ab_test(
            start_date=start_date,
            end_date=end_date,
            output_dir="temp/ab_test"
        )

        print("\n[SUCCESS] A/Bテスト完了")

    except Exception as e:
        print(f"\n[ERROR] A/Bテスト実行エラー: {e}")
        import traceback
        traceback.print_exc()
