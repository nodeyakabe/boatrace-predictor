"""
プリセット値最適化スクリプト

グリッドサーチ、ベイズ最適化等を用いてプリセットの補正値を最適化する。
バックテストと連携して、回収率・的中率を最大化するパラメータを探索。

使用方法:
    python scripts/optimize_preset_values.py --mode grid --target venue
    python scripts/optimize_preset_values.py --mode bayesian --target weather --iterations 100
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass, asdict
from itertools import product
import sqlite3

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH
from src.utils.db_connection_pool import get_connection


# ============================================================
# 設定クラス
# ============================================================

@dataclass
class OptimizationConfig:
    """最適化設定"""
    mode: str = "grid"          # "grid" or "bayesian"
    target: str = "venue"       # "venue", "weather", "tide", "compound"
    iterations: int = 50        # ベイズ最適化のイテレーション数
    test_period_days: int = 90  # テスト期間（日数）
    min_hit_rate: float = 0.55  # 最低的中率制約
    verbose: bool = True


@dataclass
class OptimizationResult:
    """最適化結果"""
    target: str
    mode: str
    best_params: Dict[str, float]
    best_score: float
    hit_rate: float
    recovery_rate: float
    sample_size: int
    started_at: str
    completed_at: str
    iterations_run: int


# ============================================================
# 評価関数
# ============================================================

class BacktestEvaluator:
    """バックテスト評価器"""

    def __init__(self, db_path: str = None, test_period_days: int = 90):
        self.db_path = db_path or DATABASE_PATH
        self.test_period_days = test_period_days
        self.logger = logging.getLogger(__name__)

        # テストデータを事前に読み込む
        self._load_test_data()

    def _load_test_data(self):
        """テストデータを読み込む"""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # 直近90日のレース結果を取得
            cursor.execute("""
                SELECT
                    r.id as race_id,
                    r.venue_code,
                    r.race_date,
                    r.race_grade,
                    rc.wind_speed,
                    rc.wind_direction,
                    rc.wave_height,
                    res.pit_number as winner_pit,
                    res.rank
                FROM races r
                JOIN results res ON r.id = res.race_id
                LEFT JOIN race_conditions rc ON r.id = rc.race_id
                WHERE r.race_date >= date('now', ?)
                  AND res.rank = 1
                ORDER BY r.race_date, r.race_number
            """, (f'-{self.test_period_days} days',))

            self.test_races = cursor.fetchall()
            self.logger.info(f"Loaded {len(self.test_races)} test races")

        finally:
            cursor.close()

    def evaluate(
        self,
        params: Dict[str, float],
        param_applier: Callable[[Dict[str, float]], None]
    ) -> Dict[str, float]:
        """
        パラメータを評価

        Args:
            params: 評価するパラメータ
            param_applier: パラメータを適用する関数

        Returns:
            評価結果（hit_rate, recovery_rate等）
        """
        # パラメータを適用
        param_applier(params)

        # 簡易評価（実際のバックテストの代わり）
        # 本番では predict_race() を呼び出して評価
        correct = 0
        total = len(self.test_races)

        if total == 0:
            return {
                'hit_rate': 0.0,
                'recovery_rate': 0.0,
                'sample_size': 0
            }

        for race in self.test_races:
            race_id, venue_code, race_date, grade, wind, wind_dir, wave, winner_pit, rank = race

            # パラメータに基づく簡易予測
            # 実際にはPredictionEngineV2を使用
            predicted_winner = self._simple_predict(
                venue_code,
                wind,
                wave,
                params
            )

            if predicted_winner == winner_pit:
                correct += 1

        hit_rate = correct / total
        # 簡易回収率計算（実際にはオッズを考慮）
        recovery_rate = hit_rate * 1.5  # 仮の計算

        return {
            'hit_rate': hit_rate,
            'recovery_rate': recovery_rate,
            'sample_size': total
        }

    def _simple_predict(
        self,
        venue_code: str,
        wind_speed: Optional[float],
        wave_height: Optional[float],
        params: Dict[str, float]
    ) -> int:
        """簡易予測（プロトタイプ）"""
        # イン強会場リスト
        IN_STRONG = ['24', '18', '17', '19', '13', '07', '16', '12', '08', '09']

        # 基本は1号艇（イン）を予測
        predicted = 1

        # 強風時は外を予測
        wind_threshold = params.get('wind_threshold', 6.0)
        if wind_speed and wind_speed >= wind_threshold:
            course_1_penalty = params.get('strong_wind_course1_penalty', -5.0)
            if course_1_penalty < -3.0:
                # 大きなペナルティなら2号艇を予測
                predicted = 2

        # イン弱会場は2号艇を予測しやすい
        if venue_code not in IN_STRONG:
            in_weak_threshold = params.get('in_weak_threshold', 0.0)
            if in_weak_threshold > 0:
                predicted = 2

        return predicted


# ============================================================
# 最適化エンジン
# ============================================================

class ParameterOptimizer:
    """パラメータ最適化エンジン"""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.evaluator = BacktestEvaluator(test_period_days=config.test_period_days)

        # 最適化対象のパラメータ範囲を定義
        self.param_ranges = self._get_param_ranges(config.target)

    def _get_param_ranges(self, target: str) -> Dict[str, Dict[str, Any]]:
        """最適化対象のパラメータ範囲を取得"""
        if target == "venue":
            return {
                'course_1_base_bonus': {
                    'type': 'continuous',
                    'min': -5.0,
                    'max': 10.0,
                    'step': 1.0
                },
                'in_strong_bonus': {
                    'type': 'continuous',
                    'min': 0.0,
                    'max': 10.0,
                    'step': 1.0
                },
                'in_weak_penalty': {
                    'type': 'continuous',
                    'min': -10.0,
                    'max': 0.0,
                    'step': 1.0
                }
            }
        elif target == "weather":
            return {
                'wind_threshold': {
                    'type': 'continuous',
                    'min': 4.0,
                    'max': 8.0,
                    'step': 1.0
                },
                'strong_wind_course1_penalty': {
                    'type': 'continuous',
                    'min': -15.0,
                    'max': 0.0,
                    'step': 1.0
                },
                'outer_course_bonus': {
                    'type': 'continuous',
                    'min': 0.0,
                    'max': 5.0,
                    'step': 0.5
                }
            }
        elif target == "tide":
            return {
                'high_tide_in_bonus': {
                    'type': 'continuous',
                    'min': 0.0,
                    'max': 5.0,
                    'step': 0.5
                },
                'low_tide_in_penalty': {
                    'type': 'continuous',
                    'min': -5.0,
                    'max': 0.0,
                    'step': 0.5
                },
                'low_tide_outer_bonus': {
                    'type': 'continuous',
                    'min': 0.0,
                    'max': 3.0,
                    'step': 0.5
                }
            }
        elif target == "compound":
            return {
                'tokuyama_a1_bonus': {
                    'type': 'continuous',
                    'min': 5.0,
                    'max': 15.0,
                    'step': 1.0
                },
                'omura_in_bonus': {
                    'type': 'continuous',
                    'min': 3.0,
                    'max': 10.0,
                    'step': 1.0
                },
                'toda_b_in_penalty': {
                    'type': 'continuous',
                    'min': -10.0,
                    'max': 0.0,
                    'step': 1.0
                }
            }
        else:
            raise ValueError(f"Unknown target: {target}")

    def optimize(self) -> OptimizationResult:
        """最適化を実行"""
        started_at = datetime.now().isoformat()

        if self.config.mode == "grid":
            best_params, best_score, iterations = self._grid_search()
        elif self.config.mode == "bayesian":
            best_params, best_score, iterations = self._bayesian_optimization()
        else:
            raise ValueError(f"Unknown mode: {self.config.mode}")

        completed_at = datetime.now().isoformat()

        # 最終評価
        final_result = self.evaluator.evaluate(
            best_params,
            lambda p: None  # パラメータ適用（実際には実装が必要）
        )

        return OptimizationResult(
            target=self.config.target,
            mode=self.config.mode,
            best_params=best_params,
            best_score=best_score,
            hit_rate=final_result['hit_rate'],
            recovery_rate=final_result['recovery_rate'],
            sample_size=final_result['sample_size'],
            started_at=started_at,
            completed_at=completed_at,
            iterations_run=iterations
        )

    def _grid_search(self) -> Tuple[Dict[str, float], float, int]:
        """グリッドサーチによる最適化"""
        self.logger.info("Starting grid search optimization...")

        # パラメータの全組み合わせを生成
        param_names = list(self.param_ranges.keys())
        param_values = []

        for name in param_names:
            spec = self.param_ranges[name]
            import numpy as np
            values = np.arange(spec['min'], spec['max'] + spec['step'], spec['step']).tolist()
            param_values.append(values)

        total_combinations = 1
        for v in param_values:
            total_combinations *= len(v)

        self.logger.info(f"Total combinations to evaluate: {total_combinations}")

        best_score = -float('inf')
        best_params = {}
        iterations = 0

        for values in product(*param_values):
            params = dict(zip(param_names, values))
            iterations += 1

            # 評価
            result = self.evaluator.evaluate(params, lambda p: None)

            # 制約チェック
            if result['hit_rate'] < self.config.min_hit_rate:
                continue

            # 目標関数：回収率を最大化
            score = result['recovery_rate']

            if score > best_score:
                best_score = score
                best_params = params.copy()
                if self.config.verbose:
                    self.logger.info(
                        f"New best: score={score:.4f}, "
                        f"hit_rate={result['hit_rate']:.2%}, "
                        f"params={params}"
                    )

            # 進捗表示
            if iterations % 100 == 0:
                self.logger.info(f"Progress: {iterations}/{total_combinations}")

        return best_params, best_score, iterations

    def _bayesian_optimization(self) -> Tuple[Dict[str, float], float, int]:
        """ベイズ最適化による最適化"""
        self.logger.info("Starting Bayesian optimization...")

        try:
            from bayes_opt import BayesianOptimization
        except ImportError:
            self.logger.error(
                "bayesian-optimization package is required. "
                "Install with: pip install bayesian-optimization"
            )
            return {}, 0.0, 0

        # パラメータ境界を設定
        pbounds = {}
        for name, spec in self.param_ranges.items():
            pbounds[name] = (spec['min'], spec['max'])

        def objective(**params):
            result = self.evaluator.evaluate(params, lambda p: None)

            # 制約ペナルティ
            penalty = 0.0
            if result['hit_rate'] < self.config.min_hit_rate:
                penalty = (self.config.min_hit_rate - result['hit_rate']) * 10

            return result['recovery_rate'] - penalty

        optimizer = BayesianOptimization(
            f=objective,
            pbounds=pbounds,
            random_state=42,
            verbose=2 if self.config.verbose else 0
        )

        optimizer.maximize(
            init_points=5,
            n_iter=self.config.iterations
        )

        best_params = optimizer.max['params']
        best_score = optimizer.max['target']

        return best_params, best_score, self.config.iterations + 5


# ============================================================
# 結果保存
# ============================================================

def save_optimization_result(
    result: OptimizationResult,
    output_dir: Path = None
):
    """最適化結果を保存"""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "config" / "presets" / "optimization_history"

    output_dir.mkdir(parents=True, exist_ok=True)

    # ファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{result.target}_{result.mode}_{timestamp}.json"
    filepath = output_dir / filename

    # JSON形式で保存
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(asdict(result), f, indent=2, ensure_ascii=False)

    print(f"Result saved to: {filepath}")
    return filepath


def apply_optimization_result(
    result: OptimizationResult,
    preset_file: Path = None
):
    """最適化結果をプリセットファイルに適用"""
    # 実際のYAMLファイルへの適用は実装が必要
    # ここではログ出力のみ
    print("\n=== 最適化結果 ===")
    print(f"対象: {result.target}")
    print(f"モード: {result.mode}")
    print(f"最高スコア: {result.best_score:.4f}")
    print(f"的中率: {result.hit_rate:.2%}")
    print(f"回収率: {result.recovery_rate:.2%}")
    print(f"サンプル数: {result.sample_size}")
    print("\n最適パラメータ:")
    for name, value in result.best_params.items():
        print(f"  {name}: {value:.2f}")


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="プリセット値最適化スクリプト"
    )
    parser.add_argument(
        "--mode",
        choices=["grid", "bayesian"],
        default="grid",
        help="最適化モード"
    )
    parser.add_argument(
        "--target",
        choices=["venue", "weather", "tide", "compound"],
        default="venue",
        help="最適化対象"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=50,
        help="ベイズ最適化のイテレーション数"
    )
    parser.add_argument(
        "--test-days",
        type=int,
        default=90,
        help="テスト期間（日数）"
    )
    parser.add_argument(
        "--min-hit-rate",
        type=float,
        default=0.55,
        help="最低的中率制約"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細出力"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="結果を保存"
    )

    args = parser.parse_args()

    # ログ設定
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # 設定
    config = OptimizationConfig(
        mode=args.mode,
        target=args.target,
        iterations=args.iterations,
        test_period_days=args.test_days,
        min_hit_rate=args.min_hit_rate,
        verbose=args.verbose
    )

    print(f"\n=== プリセット最適化 ===")
    print(f"モード: {config.mode}")
    print(f"対象: {config.target}")
    print(f"テスト期間: {config.test_period_days}日")
    print(f"最低的中率: {config.min_hit_rate:.0%}")
    print()

    # 最適化実行
    optimizer = ParameterOptimizer(config)
    result = optimizer.optimize()

    # 結果表示
    apply_optimization_result(result)

    # 結果保存
    if args.save:
        save_optimization_result(result)


if __name__ == "__main__":
    main()
