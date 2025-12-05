"""
大規模統合テスト（100レース以上）

Phase 0修正版の効果を統計的に検証
- Phase 3（ST/展示なし）vs Phase 5修正版（進入無効化）
- Bootstrap信頼区間による統計的有意差検証
"""

import sqlite3
import sys
import random
from pathlib import Path
from typing import List, Dict, Tuple
import math

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent))

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import set_feature_flag, is_feature_enabled


class LargeScaleIntegrationTest:
    """大規模統合テストクラス"""

    def __init__(self, db_path: str = "data/boatrace.db", num_races: int = 100):
        """
        初期化

        Args:
            db_path: データベースパス
            num_races: テストレース数
        """
        self.db_path = db_path
        self.num_races = num_races
        self.predictor_phase3 = None
        self.predictor_phase5 = None

    def get_test_races(self) -> List[int]:
        """
        テスト用のレースIDを取得

        Returns:
            レースIDのリスト
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # ST・展示データがあるレースを取得
        query = """
            SELECT DISTINCT r.id
            FROM races r
            INNER JOIN race_details rd ON r.id = rd.race_id
            INNER JOIN results res ON r.id = res.race_id
            WHERE rd.st_time IS NOT NULL
              AND rd.st_time > 0
              AND rd.exhibition_time IS NOT NULL
              AND rd.exhibition_time > 0
              AND res.rank IS NOT NULL
              AND res.rank != ''
            ORDER BY r.id DESC
            LIMIT ?
        """

        cursor.execute(query, (self.num_races,))
        race_ids = [row[0] for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        return race_ids

    def test_phase3(self, race_ids: List[int]) -> Tuple[int, int, List[Dict]]:
        """
        Phase 3版（ST/展示なし）でテスト

        Args:
            race_ids: テストレースIDのリスト

        Returns:
            (的中数, 総レース数, 詳細結果リスト)
        """
        print("\n[Phase 3版] ST/展示なし（BEFORE_SAFEのみ）")
        print("-" * 80)

        # Phase 3設定
        set_feature_flag('before_safe_st_exhibition', False)
        self.predictor_phase3 = RacePredictor(db_path=self.db_path)

        correct = 0
        total = 0
        details = []

        for race_id in race_ids:
            try:
                # 予測実行
                predictions = self.predictor_phase3.predict_race(race_id)

                if not predictions:
                    continue

                # 1位予測を取得
                top_prediction = predictions[0]
                predicted_pit = top_prediction['pit_number']

                # 実際の結果を取得
                actual_winner = self._get_actual_winner(race_id)

                if actual_winner is None:
                    continue

                total += 1
                is_correct = (predicted_pit == actual_winner)
                if is_correct:
                    correct += 1

                details.append({
                    'race_id': race_id,
                    'predicted': predicted_pit,
                    'actual': actual_winner,
                    'correct': is_correct,
                    'score': top_prediction.get('total_score', 0)
                })

            except Exception as e:
                print(f"Warning: レース{race_id}でエラー: {e}")
                continue

        accuracy = (correct / total * 100) if total > 0 else 0
        print(f"\n的中数: {correct}/{total} ({accuracy:.1f}%)")

        return correct, total, details

    def test_phase5_fixed(self, race_ids: List[int]) -> Tuple[int, int, List[Dict]]:
        """
        Phase 5修正版（進入無効化）でテスト

        Args:
            race_ids: テストレースIDのリスト

        Returns:
            (的中数, 総レース数, 詳細結果リスト)
        """
        print("\n[Phase 5修正版] ST/展示あり + 進入無効化")
        print("-" * 80)

        # Phase 5設定
        set_feature_flag('before_safe_st_exhibition', True)
        self.predictor_phase5 = RacePredictor(db_path=self.db_path)

        correct = 0
        total = 0
        details = []

        for race_id in race_ids:
            try:
                # 予測実行
                predictions = self.predictor_phase5.predict_race(race_id)

                if not predictions:
                    continue

                # 1位予測を取得
                top_prediction = predictions[0]
                predicted_pit = top_prediction['pit_number']

                # 実際の結果を取得
                actual_winner = self._get_actual_winner(race_id)

                if actual_winner is None:
                    continue

                total += 1
                is_correct = (predicted_pit == actual_winner)
                if is_correct:
                    correct += 1

                details.append({
                    'race_id': race_id,
                    'predicted': predicted_pit,
                    'actual': actual_winner,
                    'correct': is_correct,
                    'score': top_prediction.get('total_score', 0)
                })

            except Exception as e:
                print(f"Warning: レース{race_id}でエラー: {e}")
                continue

        accuracy = (correct / total * 100) if total > 0 else 0
        print(f"\n的中数: {correct}/{total} ({accuracy:.1f}%)")

        return correct, total, details

    def _get_actual_winner(self, race_id: int) -> int:
        """
        実際の勝者を取得

        Args:
            race_id: レースID

        Returns:
            勝者の艇番（1-6）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT pit_number
            FROM results
            WHERE race_id = ? AND rank = '1'
            LIMIT 1
        """

        cursor.execute(query, (race_id,))
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        return row[0] if row else None

    def bootstrap_test(
        self,
        details_a: List[Dict],
        details_b: List[Dict],
        n_iterations: int = 1000
    ) -> Dict:
        """
        Bootstrap法による統計的有意差検定

        Args:
            details_a: Phase 3の詳細結果
            details_b: Phase 5修正版の詳細結果
            n_iterations: Bootstrap反復回数

        Returns:
            統計検定結果
        """
        print("\n[Bootstrap統計検定]")
        print("-" * 80)

        # 元の的中率
        acc_a = sum(1 for d in details_a if d['correct']) / len(details_a)
        acc_b = sum(1 for d in details_b if d['correct']) / len(details_b)
        observed_diff = acc_b - acc_a

        print(f"Phase 3的中率: {acc_a*100:.2f}%")
        print(f"Phase 5修正版的中率: {acc_b*100:.2f}%")
        print(f"観測された差: {observed_diff*100:+.2f}ポイント")

        # Bootstrap標本抽出
        diffs = []
        for _ in range(n_iterations):
            # リサンプリング
            sample_a = random.choices(details_a, k=len(details_a))
            sample_b = random.choices(details_b, k=len(details_b))

            # 的中率計算
            acc_a_boot = sum(1 for d in sample_a if d['correct']) / len(sample_a)
            acc_b_boot = sum(1 for d in sample_b if d['correct']) / len(sample_b)

            diffs.append(acc_b_boot - acc_a_boot)

        # 信頼区間計算
        diffs_sorted = sorted(diffs)
        ci_lower = diffs_sorted[int(n_iterations * 0.025)]
        ci_upper = diffs_sorted[int(n_iterations * 0.975)]

        # p値計算（片側検定：Phase 5が改善したか）
        p_value = sum(1 for d in diffs if d <= 0) / n_iterations

        print(f"\n95%信頼区間: [{ci_lower*100:.2f}%, {ci_upper*100:.2f}%]")
        print(f"p値（片側検定）: {p_value:.4f}")

        if p_value < 0.05:
            print("結論: Phase 5修正版は統計的に有意な改善を示しています（p < 0.05）")
            is_significant = True
        else:
            print("結論: Phase 5修正版の改善は統計的に有意ではありません（p >= 0.05）")
            is_significant = False

        return {
            'observed_diff': observed_diff,
            'ci_lower': ci_lower,
            'ci_upper': ci_upper,
            'p_value': p_value,
            'is_significant': is_significant
        }

    def analyze_changes(
        self,
        details_a: List[Dict],
        details_b: List[Dict]
    ) -> Dict:
        """
        予測変化の分析

        Args:
            details_a: Phase 3の詳細結果
            details_b: Phase 5修正版の詳細結果

        Returns:
            変化分析結果
        """
        print("\n[予測変化の分析]")
        print("-" * 80)

        # 予測が変化したレース
        changed_races = []
        for da, db in zip(details_a, details_b):
            if da['race_id'] == db['race_id']:
                if da['predicted'] != db['predicted']:
                    changed_races.append({
                        'race_id': da['race_id'],
                        'phase3_pred': da['predicted'],
                        'phase5_pred': db['predicted'],
                        'actual': da['actual'],
                        'phase3_correct': da['correct'],
                        'phase5_correct': db['correct']
                    })

        total_races = len(details_a)
        changed_count = len(changed_races)
        change_rate = (changed_count / total_races * 100) if total_races > 0 else 0

        print(f"予測変化レース数: {changed_count}/{total_races} ({change_rate:.1f}%)")

        if changed_races:
            # 変化したレースの的中率
            phase3_changed_correct = sum(1 for r in changed_races if r['phase3_correct'])
            phase5_changed_correct = sum(1 for r in changed_races if r['phase5_correct'])

            phase3_changed_acc = (phase3_changed_correct / changed_count * 100)
            phase5_changed_acc = (phase5_changed_correct / changed_count * 100)

            print(f"\n変化したレースの的中率:")
            print(f"  Phase 3: {phase3_changed_correct}/{changed_count} ({phase3_changed_acc:.1f}%)")
            print(f"  Phase 5修正版: {phase5_changed_correct}/{changed_count} ({phase5_changed_acc:.1f}%)")
            print(f"  差分: {phase5_changed_acc - phase3_changed_acc:+.1f}ポイント")

        return {
            'total_races': total_races,
            'changed_count': changed_count,
            'change_rate': change_rate,
            'changed_races': changed_races
        }


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='大規模統合テスト')
    parser.add_argument('--num-races', type=int, default=100, help='テストレース数（デフォルト: 100）')
    parser.add_argument('--bootstrap-iter', type=int, default=1000, help='Bootstrap反復回数（デフォルト: 1000）')

    args = parser.parse_args()

    print("=" * 80)
    print(f"大規模統合テスト: {args.num_races}レース")
    print("=" * 80)

    tester = LargeScaleIntegrationTest(num_races=args.num_races)

    # テスト用レース取得
    print("\n[1/5] テスト用レース取得中...")
    race_ids = tester.get_test_races()
    print(f"      → {len(race_ids)}レースを取得")

    # Phase 3テスト
    print("\n[2/5] Phase 3版（ST/展示なし）でテスト実行中...")
    correct_phase3, total_phase3, details_phase3 = tester.test_phase3(race_ids)

    # Phase 5修正版テスト
    print("\n[3/5] Phase 5修正版（進入無効化）でテスト実行中...")
    correct_phase5, total_phase5, details_phase5 = tester.test_phase5_fixed(race_ids)

    # Bootstrap統計検定
    print("\n[4/5] Bootstrap統計検定実行中...")
    bootstrap_result = tester.bootstrap_test(details_phase3, details_phase5, n_iterations=args.bootstrap_iter)

    # 変化分析
    print("\n[5/5] 予測変化の分析中...")
    change_analysis = tester.analyze_changes(details_phase3, details_phase5)

    # 最終結果
    print("\n" + "=" * 80)
    print("最終結果サマリー")
    print("=" * 80)

    acc_phase3 = (correct_phase3 / total_phase3 * 100) if total_phase3 > 0 else 0
    acc_phase5 = (correct_phase5 / total_phase5 * 100) if total_phase5 > 0 else 0
    diff = acc_phase5 - acc_phase3

    print(f"\nPhase 3（ST/展示なし）: {correct_phase3}/{total_phase3} ({acc_phase3:.1f}%)")
    print(f"Phase 5修正版（進入無効化）: {correct_phase5}/{total_phase5} ({acc_phase5:.1f}%)")
    print(f"差分: {diff:+.1f}ポイント")

    print(f"\n予測変化: {change_analysis['changed_count']}/{change_analysis['total_races']}レース ({change_analysis['change_rate']:.1f}%)")

    print(f"\n統計的有意性: {'有意' if bootstrap_result['is_significant'] else '有意でない'} (p = {bootstrap_result['p_value']:.4f})")
    print(f"95%信頼区間: [{bootstrap_result['ci_lower']*100:.2f}%, {bootstrap_result['ci_upper']*100:.2f}%]")

    # 推奨運用
    print("\n" + "=" * 80)
    print("推奨運用")
    print("=" * 80)

    if bootstrap_result['is_significant'] and diff > 0:
        print("\n[OK] Phase 5修正版（進入無効化）の採用を推奨")
        print("   - 統計的に有意な改善が確認されました")
        print("   - feature_flags.py: before_safe_st_exhibition = True を継続")
    elif diff > 0:
        print("\n[!] Phase 5修正版は改善傾向だが統計的有意性なし")
        print("   - より大規模なテスト（200-500レース）を推奨")
        print("   - 現時点ではPhase 3版での運用も選択肢")
    else:
        print("\n[X] Phase 3版（ST/展示なし）の継続を推奨")
        print("   - Phase 5修正版は改善効果が見られません")
        print("   - feature_flags.py: before_safe_st_exhibition = False に戻す")

    print("\nテスト完了！")


if __name__ == '__main__':
    main()
