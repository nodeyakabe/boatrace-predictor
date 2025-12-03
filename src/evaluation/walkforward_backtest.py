"""
Walk-forward Backtest Framework

時系列を考慮した段階的バックテスト。
過去データで学習 → 未来データで検証を繰り返す。
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json
from pathlib import Path

from ..analysis.race_predictor import RacePredictor


class WalkForwardBacktest:
    """Walk-forward方式のバックテスト"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path
        self.predictor = RacePredictor(db_path=db_path)

    def run_walkforward(
        self,
        start_date: str,
        end_date: str,
        train_days: int = 30,
        test_days: int = 7,
        step_days: int = 7,
        output_dir: str = "temp/walkforward"
    ) -> Dict:
        """
        Walk-forward backtestを実行

        Parameters:
        -----------
        start_date : str
            開始日 (YYYY-MM-DD)
        end_date : str
            終了日 (YYYY-MM-DD)
        train_days : int
            訓練期間 (日数)
        test_days : int
            テスト期間 (日数)
        step_days : int
            ステップ間隔 (日数)
        output_dir : str
            出力ディレクトリ

        Returns:
        --------
        Dict: バックテスト結果
        """
        print(f"Walk-forward Backtest開始")
        print(f"期間: {start_date} ~ {end_date}")
        print(f"訓練期間: {train_days}日, テスト期間: {test_days}日, ステップ: {step_days}日")
        print()

        # 出力ディレクトリ作成
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 日付をdatetimeに変換
        current_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_datetime = datetime.strptime(end_date, '%Y-%m-%d')

        results = []
        step_count = 0

        while current_date < end_datetime:
            step_count += 1

            # 訓練期間とテスト期間を設定
            train_start = (current_date - timedelta(days=train_days)).strftime('%Y-%m-%d')
            train_end = current_date.strftime('%Y-%m-%d')
            test_start = current_date.strftime('%Y-%m-%d')
            test_end = (current_date + timedelta(days=test_days)).strftime('%Y-%m-%d')

            print(f"Step {step_count}:")
            print(f"  訓練: {train_start} ~ {train_end}")
            print(f"  テスト: {test_start} ~ {test_end}")

            # テスト期間のレースを取得
            test_races = self._get_races_in_period(test_start, test_end)

            if len(test_races) == 0:
                print(f"  テストレースなし、スキップ")
                current_date += timedelta(days=step_days)
                continue

            print(f"  テストレース数: {len(test_races)}")

            # 各レースで予測と評価
            step_results = {
                'train_period': (train_start, train_end),
                'test_period': (test_start, test_end),
                'races': [],
                'hit_rate_1st': 0.0,
                'hit_rate_top3': 0.0,
                'avg_score_accuracy': 0.0,
            }

            hits_1st = 0
            hits_top3 = 0
            total_score_accuracy = 0.0
            evaluated_races = 0

            for race in test_races:
                race_id = race[0]

                # 予測実行
                try:
                    predictions = self.predictor.predict_race(race_id)

                    if not predictions:
                        continue

                    # 実際の結果を取得
                    actual_results = self._get_race_results(race_id)

                    if not actual_results:
                        continue

                    # 評価
                    eval_result = self._evaluate_prediction(predictions, actual_results)

                    if eval_result:
                        step_results['races'].append({
                            'race_id': race_id,
                            'hit_1st': eval_result['hit_1st'],
                            'hit_top3': eval_result['hit_top3'],
                            'score_accuracy': eval_result['score_accuracy'],
                        })

                        if eval_result['hit_1st']:
                            hits_1st += 1
                        if eval_result['hit_top3']:
                            hits_top3 += 1
                        total_score_accuracy += eval_result['score_accuracy']
                        evaluated_races += 1

                except Exception as e:
                    print(f"  レース {race_id} の予測エラー: {e}")
                    continue

            # ステップの統計を計算
            if evaluated_races > 0:
                step_results['hit_rate_1st'] = hits_1st / evaluated_races
                step_results['hit_rate_top3'] = hits_top3 / evaluated_races
                step_results['avg_score_accuracy'] = total_score_accuracy / evaluated_races
                step_results['evaluated_races'] = evaluated_races

                print(f"  評価レース数: {evaluated_races}")
                print(f"  1着的中率: {step_results['hit_rate_1st']:.2%}")
                print(f"  3連単的中率: {step_results['hit_rate_top3']:.2%}")
                print(f"  スコア精度: {step_results['avg_score_accuracy']:.4f}")

                results.append(step_results)
            else:
                print(f"  評価可能なレースなし")

            print()

            # 次のステップへ
            current_date += timedelta(days=step_days)

        # 全体統計を計算
        summary = self._calculate_summary(results)

        # 結果を保存
        self._save_results(results, summary, output_path)

        return {
            'steps': results,
            'summary': summary,
            'output_dir': str(output_path),
        }

    def _get_races_in_period(self, start_date: str, end_date: str) -> List[Tuple]:
        """期間内のレースを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
            FROM races r
            JOIN results res ON r.id = res.race_id
            WHERE r.race_date >= ? AND r.race_date < ?
            ORDER BY r.race_date, r.venue_code, r.race_number
        """, (start_date, end_date))

        races = cursor.fetchall()
        conn.close()

        return races

    def _get_race_results(self, race_id: int) -> List[Dict]:
        """レースの実際の結果を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ?
            ORDER BY rank
        """, (race_id,))

        results = []
        for row in cursor.fetchall():
            results.append({
                'pit_number': row[0],
                'rank': int(row[1]) if row[1] else 999,  # TEXT型をintに変換
            })

        conn.close()
        return results

    def _evaluate_prediction(
        self,
        predictions: List[Dict],
        actual_results: List[Dict]
    ) -> Dict:
        """予測を評価"""
        if not predictions or not actual_results:
            return None

        # 予測: total_scoreでソート済み
        predicted_1st = predictions[0]['pit_number']
        predicted_top3 = set([p['pit_number'] for p in predictions[:3]])

        # 実際の結果
        actual_1st = actual_results[0]['pit_number']
        actual_top3 = set([r['pit_number'] for r in actual_results[:3]])

        # 的中判定
        hit_1st = (predicted_1st == actual_1st)
        hit_top3 = len(predicted_top3 & actual_top3) == 3

        # スコア精度 (順位の相関)
        score_accuracy = self._calculate_score_accuracy(predictions, actual_results)

        return {
            'hit_1st': hit_1st,
            'hit_top3': hit_top3,
            'score_accuracy': score_accuracy,
        }

    def _calculate_score_accuracy(
        self,
        predictions: List[Dict],
        actual_results: List[Dict]
    ) -> float:
        """スコアと実際の順位の相関を計算"""
        # 実際の順位を辞書化
        actual_ranks = {r['pit_number']: r['rank'] for r in actual_results}

        # 予測順位と実際の順位の差を計算
        total_diff = 0
        count = 0

        for pred_rank, pred in enumerate(predictions, 1):
            pit_number = pred['pit_number']
            if pit_number in actual_ranks:
                actual_rank = actual_ranks[pit_number]
                total_diff += abs(pred_rank - actual_rank)
                count += 1

        if count == 0:
            return 0.0

        # 精度を0-1の範囲に正規化 (差が小さいほど高精度)
        max_diff = 5 * count  # 最大差分
        accuracy = 1.0 - (total_diff / max_diff)

        return max(0.0, accuracy)

    def _calculate_summary(self, results: List[Dict]) -> Dict:
        """全ステップの統計サマリーを計算"""
        if not results:
            return {
                'total_steps': 0,
                'total_races': 0,
                'overall_hit_rate_1st': 0.0,
                'overall_hit_rate_top3': 0.0,
                'overall_score_accuracy': 0.0,
                'step_stats': {
                    'avg_hit_rate_1st': 0.0,
                    'avg_hit_rate_top3': 0.0,
                    'avg_score_accuracy': 0.0,
                }
            }

        total_races = sum(r.get('evaluated_races', 0) for r in results)
        total_hits_1st = sum(
            sum(1 for race in r['races'] if race['hit_1st'])
            for r in results
        )
        total_hits_top3 = sum(
            sum(1 for race in r['races'] if race['hit_top3'])
            for r in results
        )
        total_score_accuracy = sum(
            sum(race['score_accuracy'] for race in r['races'])
            for r in results
        )

        return {
            'total_steps': len(results),
            'total_races': total_races,
            'overall_hit_rate_1st': total_hits_1st / total_races if total_races > 0 else 0.0,
            'overall_hit_rate_top3': total_hits_top3 / total_races if total_races > 0 else 0.0,
            'overall_score_accuracy': total_score_accuracy / total_races if total_races > 0 else 0.0,
            'step_stats': {
                'avg_hit_rate_1st': sum(r['hit_rate_1st'] for r in results) / len(results),
                'avg_hit_rate_top3': sum(r['hit_rate_top3'] for r in results) / len(results),
                'avg_score_accuracy': sum(r['avg_score_accuracy'] for r in results) / len(results),
            }
        }

    def _save_results(self, results: List[Dict], summary: Dict, output_path: Path):
        """結果をファイルに保存"""
        # JSON形式で保存
        output_file = output_path / 'walkforward_results.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'steps': results,
                'summary': summary,
            }, f, ensure_ascii=False, indent=2)

        # テキストレポートを保存
        report_file = output_path / 'walkforward_report.txt'
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("Walk-forward Backtest結果レポート\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"総ステップ数: {summary['total_steps']}\n")
            f.write(f"総評価レース数: {summary['total_races']}\n\n")

            f.write("【全体統計】\n")
            f.write(f"  1着的中率: {summary['overall_hit_rate_1st']:.2%}\n")
            f.write(f"  3連単的中率: {summary['overall_hit_rate_top3']:.2%}\n")
            f.write(f"  平均スコア精度: {summary['overall_score_accuracy']:.4f}\n\n")

            if 'step_stats' in summary and summary['step_stats']:
                f.write("【ステップ平均】\n")
                f.write(f"  平均1着的中率: {summary['step_stats']['avg_hit_rate_1st']:.2%}\n")
                f.write(f"  平均3連単的中率: {summary['step_stats']['avg_hit_rate_top3']:.2%}\n")
                f.write(f"  平均スコア精度: {summary['step_stats']['avg_score_accuracy']:.4f}\n\n")

            f.write("【ステップ詳細】\n")
            for i, step in enumerate(results, 1):
                f.write(f"\nStep {i}:\n")
                f.write(f"  訓練期間: {step['train_period'][0]} ~ {step['train_period'][1]}\n")
                f.write(f"  テスト期間: {step['test_period'][0]} ~ {step['test_period'][1]}\n")
                f.write(f"  評価レース数: {step.get('evaluated_races', 0)}\n")
                f.write(f"  1着的中率: {step['hit_rate_1st']:.2%}\n")
                f.write(f"  3連単的中率: {step['hit_rate_top3']:.2%}\n")
                f.write(f"  スコア精度: {step['avg_score_accuracy']:.4f}\n")

        print(f"結果を保存しました: {output_path}")
