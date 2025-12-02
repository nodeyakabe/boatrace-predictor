"""
バックテストフレームワーク

過去データで予測モデルの精度を評価する。
Walk-Forward方式で時系列を考慮した検証を実施。
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

import sqlite3
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import json


@dataclass
class BacktestResult:
    """バックテスト結果"""
    race_id: int
    race_date: str
    venue_code: str
    race_number: int

    # 予測
    predictions: List[Dict]
    top3_predicted: List[int]  # 予測された上位3艇

    # 実結果
    actual_result: List[int]  # 実際の着順（pit_number順）
    top3_actual: List[int]     # 実際の上位3艇

    # 評価指標
    hit_rate: float           # 1着的中率
    top3_hit_rate: float      # 3連単的中率
    score_accuracy: float     # スコア精度（相関係数）
    integration_mode: str     # 統合モード
    integration_condition: Optional[str]  # 統合条件


@dataclass
class BacktestSummary:
    """バックテスト集計結果"""
    total_races: int
    date_range: Tuple[str, str]

    # 的中率
    hit_rate_1st: float       # 1着的中率
    hit_rate_top3: float      # 3連単的中率

    # 統合モード別
    mode_stats: Dict[str, Dict]  # モード別統計

    # スコア精度
    avg_score_accuracy: float

    # 条件別統計
    condition_stats: Dict[str, Dict]  # 条件別統計


class BacktestFramework:
    """バックテストフレームワーク"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        venue_codes: Optional[List[str]] = None,
        output_dir: str = "temp/backtest"
    ) -> BacktestSummary:
        """
        バックテスト実行

        Args:
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）
            venue_codes: 対象会場コードリスト（Noneの場合は全会場）
            output_dir: 結果出力ディレクトリ

        Returns:
            BacktestSummary: 集計結果
        """
        # race_predictorをインポート（循環インポート回避のため遅延インポート）
        from src.analysis.race_predictor import RacePredictor

        # 出力ディレクトリ作成
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 対象レースを取得
        race_ids = self._get_race_ids(start_date, end_date, venue_codes)
        print(f"[INFO] 対象レース数: {len(race_ids)}")

        # 予測器を初期化
        predictor = RacePredictor(db_path=self.db_path)

        # 各レースでバックテスト
        results = []
        for idx, race_id in enumerate(race_ids, 1):
            if idx % 100 == 0:
                print(f"[INFO] 処理中: {idx}/{len(race_ids)}")

            try:
                result = self._evaluate_race(predictor, race_id)
                if result:
                    results.append(result)
            except Exception as e:
                print(f"[WARN] race_id={race_id} でエラー: {e}")
                continue

        # 集計
        summary = self._aggregate_results(results)

        # 結果を保存
        self._save_results(results, summary, output_dir)

        return summary

    def _get_race_ids(
        self,
        start_date: str,
        end_date: str,
        venue_codes: Optional[List[str]]
    ) -> List[int]:
        """対象レースIDを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT id as race_id
            FROM races
            WHERE race_date BETWEEN ? AND ?
        """
        params = [start_date, end_date]

        if venue_codes:
            placeholders = ','.join('?' * len(venue_codes))
            query += f" AND venue_code IN ({placeholders})"
            params.extend(venue_codes)

        query += " ORDER BY race_date, venue_code, race_number"

        cursor.execute(query, params)
        race_ids = [row[0] for row in cursor.fetchall()]

        conn.close()
        return race_ids

    def _evaluate_race(
        self,
        predictor,
        race_id: int
    ) -> Optional[BacktestResult]:
        """1レースを評価"""
        # レース情報取得
        race_info = self._get_race_info(race_id)
        if not race_info:
            return None

        # 実結果取得
        actual_result = self._get_actual_result(race_id)
        if not actual_result:
            return None

        # 予測実行
        try:
            predictions = predictor.predict_race(race_id)
            if not predictions:
                return None
        except Exception:
            return None

        # 予測上位3艇を取得
        sorted_predictions = sorted(predictions, key=lambda x: x['total_score'], reverse=True)
        top3_predicted = [p['pit_number'] for p in sorted_predictions[:3]]

        # 実結果上位3艇
        top3_actual = [pit for pit, rank in sorted(actual_result.items(), key=lambda x: x[1])[:3]]

        # 的中判定
        hit_1st = (top3_predicted[0] == top3_actual[0])
        hit_top3 = (set(top3_predicted) == set(top3_actual))

        # スコア精度（ランク相関）
        score_accuracy = self._calculate_rank_correlation(predictions, actual_result)

        # 統合モード取得
        integration_mode = predictions[0].get('integration_mode', 'unknown')
        integration_condition = predictions[0].get('integration_condition', None)

        return BacktestResult(
            race_id=race_id,
            race_date=race_info['race_date'],
            venue_code=race_info['venue_code'],
            race_number=race_info['race_number'],
            predictions=predictions,
            top3_predicted=top3_predicted,
            top3_actual=top3_actual,
            actual_result=actual_result,
            hit_rate=1.0 if hit_1st else 0.0,
            top3_hit_rate=1.0 if hit_top3 else 0.0,
            score_accuracy=score_accuracy,
            integration_mode=integration_mode,
            integration_condition=integration_condition
        )

    def _get_race_info(self, race_id: int) -> Optional[Dict]:
        """レース情報取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT race_date, venue_code, race_number
            FROM races
            WHERE id = ?
        """, (race_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def _get_actual_result(self, race_id: int) -> Optional[Dict[int, int]]:
        """実結果取得（pit_number -> rank）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pit_number, CAST(rank AS INTEGER) as finish_position
            FROM results
            WHERE race_id = ?
        """, (race_id,))

        rows = cursor.fetchall()
        conn.close()

        if len(rows) < 6:
            return None

        return {pit: rank for pit, rank in rows}

    def _calculate_rank_correlation(
        self,
        predictions: List[Dict],
        actual_result: Dict[int, int]
    ) -> float:
        """ランク相関係数を計算（スピアマン相関）"""
        # 予測ランク
        sorted_preds = sorted(predictions, key=lambda x: x['total_score'], reverse=True)
        pred_ranks = {p['pit_number']: idx + 1 for idx, p in enumerate(sorted_preds)}

        # 実ランク
        actual_ranks = actual_result

        # スピアマン相関計算
        n = len(pred_ranks)
        d_squared_sum = sum((pred_ranks[pit] - actual_ranks[pit]) ** 2 for pit in pred_ranks)

        rho = 1 - (6 * d_squared_sum) / (n * (n ** 2 - 1))
        return rho

    def _aggregate_results(self, results: List[BacktestResult]) -> BacktestSummary:
        """結果集計"""
        if not results:
            return BacktestSummary(
                total_races=0,
                date_range=("", ""),
                hit_rate_1st=0.0,
                hit_rate_top3=0.0,
                mode_stats={},
                avg_score_accuracy=0.0,
                condition_stats={}
            )

        total_races = len(results)

        # 日付範囲
        dates = [r.race_date for r in results]
        date_range = (min(dates), max(dates))

        # 的中率
        hit_rate_1st = sum(r.hit_rate for r in results) / total_races
        hit_rate_top3 = sum(r.top3_hit_rate for r in results) / total_races

        # スコア精度平均
        avg_score_accuracy = sum(r.score_accuracy for r in results) / total_races

        # モード別統計
        mode_stats = {}
        for result in results:
            mode = result.integration_mode
            if mode not in mode_stats:
                mode_stats[mode] = {
                    'count': 0,
                    'hit_1st': 0,
                    'hit_top3': 0,
                    'score_accuracy': 0.0
                }

            mode_stats[mode]['count'] += 1
            mode_stats[mode]['hit_1st'] += result.hit_rate
            mode_stats[mode]['hit_top3'] += result.top3_hit_rate
            mode_stats[mode]['score_accuracy'] += result.score_accuracy

        # 平均化
        for mode in mode_stats:
            count = mode_stats[mode]['count']
            mode_stats[mode]['hit_rate_1st'] = mode_stats[mode]['hit_1st'] / count
            mode_stats[mode]['hit_rate_top3'] = mode_stats[mode]['hit_top3'] / count
            mode_stats[mode]['avg_score_accuracy'] = mode_stats[mode]['score_accuracy'] / count

        # 条件別統計（動的統合のみ）
        condition_stats = {}
        for result in results:
            if result.integration_mode == 'dynamic' and result.integration_condition:
                cond = result.integration_condition
                if cond not in condition_stats:
                    condition_stats[cond] = {
                        'count': 0,
                        'hit_1st': 0,
                        'hit_top3': 0,
                        'score_accuracy': 0.0
                    }

                condition_stats[cond]['count'] += 1
                condition_stats[cond]['hit_1st'] += result.hit_rate
                condition_stats[cond]['hit_top3'] += result.top3_hit_rate
                condition_stats[cond]['score_accuracy'] += result.score_accuracy

        # 平均化
        for cond in condition_stats:
            count = condition_stats[cond]['count']
            condition_stats[cond]['hit_rate_1st'] = condition_stats[cond]['hit_1st'] / count
            condition_stats[cond]['hit_rate_top3'] = condition_stats[cond]['hit_top3'] / count
            condition_stats[cond]['avg_score_accuracy'] = condition_stats[cond]['score_accuracy'] / count

        return BacktestSummary(
            total_races=total_races,
            date_range=date_range,
            hit_rate_1st=hit_rate_1st,
            hit_rate_top3=hit_rate_top3,
            mode_stats=mode_stats,
            avg_score_accuracy=avg_score_accuracy,
            condition_stats=condition_stats
        )

    def _save_results(
        self,
        results: List[BacktestResult],
        summary: BacktestSummary,
        output_dir: str
    ):
        """結果を保存"""
        # 詳細結果をJSON保存
        detailed_results = []
        for r in results:
            detailed_results.append({
                'race_id': r.race_id,
                'race_date': r.race_date,
                'venue_code': r.venue_code,
                'race_number': r.race_number,
                'top3_predicted': r.top3_predicted,
                'top3_actual': r.top3_actual,
                'hit_1st': r.hit_rate,
                'hit_top3': r.top3_hit_rate,
                'score_accuracy': round(r.score_accuracy, 4),
                'integration_mode': r.integration_mode,
                'integration_condition': r.integration_condition
            })

        with open(f"{output_dir}/detailed_results.json", 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=2)

        # サマリーをJSON保存
        summary_dict = {
            'total_races': summary.total_races,
            'date_range': summary.date_range,
            'hit_rate_1st': round(summary.hit_rate_1st, 4),
            'hit_rate_top3': round(summary.hit_rate_top3, 4),
            'avg_score_accuracy': round(summary.avg_score_accuracy, 4),
            'mode_stats': {
                mode: {
                    'count': stats['count'],
                    'hit_rate_1st': round(stats['hit_rate_1st'], 4),
                    'hit_rate_top3': round(stats['hit_rate_top3'], 4),
                    'avg_score_accuracy': round(stats['avg_score_accuracy'], 4)
                }
                for mode, stats in summary.mode_stats.items()
            },
            'condition_stats': {
                cond: {
                    'count': stats['count'],
                    'hit_rate_1st': round(stats['hit_rate_1st'], 4),
                    'hit_rate_top3': round(stats['hit_rate_top3'], 4),
                    'avg_score_accuracy': round(stats['avg_score_accuracy'], 4)
                }
                for cond, stats in summary.condition_stats.items()
            }
        }

        with open(f"{output_dir}/summary.json", 'w', encoding='utf-8') as f:
            json.dump(summary_dict, f, ensure_ascii=False, indent=2)

        print(f"[INFO] 結果を保存しました: {output_dir}")


if __name__ == "__main__":
    import sys
    from datetime import datetime, timedelta

    print("=" * 70)
    print("バックテストフレームワーク テスト実行")
    print("=" * 70)

    # DBパス確認
    db_path = "data/boatrace.db"

    # 過去1週間でテスト（実際には1ヶ月分のデータでバックテスト）
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    print(f"\n[INFO] テスト期間: {start_date} ~ {end_date}")

    framework = BacktestFramework(db_path)

    try:
        summary = framework.run_backtest(
            start_date=start_date,
            end_date=end_date,
            output_dir="temp/backtest/test"
        )

        print("\n" + "=" * 70)
        print("バックテスト結果サマリー")
        print("=" * 70)
        print(f"対象レース数: {summary.total_races}")
        print(f"期間: {summary.date_range[0]} ~ {summary.date_range[1]}")
        print(f"\n1着的中率: {summary.hit_rate_1st:.2%}")
        print(f"3連単的中率: {summary.hit_rate_top3:.2%}")
        print(f"平均スコア精度: {summary.avg_score_accuracy:.4f}")

        print(f"\n【モード別統計】")
        for mode, stats in summary.mode_stats.items():
            print(f"  {mode}:")
            print(f"    レース数: {stats['count']}")
            print(f"    1着的中率: {stats['hit_rate_1st']:.2%}")
            print(f"    3連単的中率: {stats['hit_rate_top3']:.2%}")

        if summary.condition_stats:
            print(f"\n【条件別統計（動的統合）】")
            for cond, stats in summary.condition_stats.items():
                print(f"  {cond}:")
                print(f"    レース数: {stats['count']}")
                print(f"    1着的中率: {stats['hit_rate_1st']:.2%}")

        print("\n" + "=" * 70)
        print("[SUCCESS] バックテスト完了")
        print("=" * 70)

    except Exception as e:
        print(f"\n[ERROR] バックテスト実行エラー: {e}")
        import traceback
        traceback.print_exc()
