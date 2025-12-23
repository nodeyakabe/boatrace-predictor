"""
プリセット値最適化スクリプト V2

新予測システム（PreInfoScorer, ScoreIntegrator, AdjustmentManager）と連携して
グリッドサーチ/ベイズ最適化でプリセットの補正値を最適化する。

使用方法:
    python scripts/optimize_preset_values_v2.py --mode grid --target venue
    python scripts/optimize_preset_values_v2.py --mode bayesian --target weather --iterations 100
    python scripts/optimize_preset_values_v2.py --mode grid --target all --save

作成日: 2025-12-15
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from itertools import product
import yaml

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH
from src.analysis.backtest_evaluator import (
    BacktestEvaluatorV2,
    BacktestConfig,
    BacktestResult,
    ObjectiveFunction
)


# ============================================================
# 設定クラス
# ============================================================

@dataclass
class OptimizationConfigV2:
    """最適化設定 V2"""
    mode: str = "grid"              # "grid" or "bayesian"
    target: str = "venue"           # "venue", "weather", "tide", "compound", "integration", "all"
    iterations: int = 50            # ベイズ最適化のイテレーション数
    test_period_days: int = 90      # テスト期間（日数）
    min_hit_rate: float = 0.55      # 最低的中率制約
    recovery_weight: float = 0.7    # 回収率の重み
    hit_rate_weight: float = 0.3    # 的中率の重み
    verbose: bool = True
    parallel: bool = True           # グリッドサーチの並列実行


@dataclass
class OptimizationResultV2:
    """最適化結果 V2"""
    target: str
    mode: str
    best_params: Dict[str, float]
    best_objective: float
    hit_rate: float
    recovery_rate: float
    profit_loss: float
    sample_size: int
    constraint_satisfied: bool
    started_at: str
    completed_at: str
    iterations_run: int
    all_results: List[Dict[str, Any]] = None  # 全結果（オプション）


# ============================================================
# パラメータ定義ローダー
# ============================================================

class ParameterDefinitionLoader:
    """optimization_targets.yamlからパラメータ定義を読み込む"""

    def __init__(self, config_path: Path = None):
        self.config_path = config_path or (
            PROJECT_ROOT / "config" / "presets" / "optimization_targets.yaml"
        )
        self._definitions = None

    def load(self) -> Dict[str, Any]:
        """パラメータ定義を読み込む"""
        if self._definitions is not None:
            return self._definitions

        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._definitions = yaml.safe_load(f)
        else:
            # デフォルト定義
            self._definitions = self._get_default_definitions()

        return self._definitions

    def get_param_ranges(self, target: str) -> Dict[str, Dict[str, Any]]:
        """
        指定ターゲットのパラメータ範囲を取得

        Args:
            target: venue, weather, tide, compound, integration

        Returns:
            パラメータ名 -> {min, max, step, default}
        """
        definitions = self.load()

        target_map = {
            'venue': 'venue_adjustments',
            'weather': 'weather_adjustments',
            'tide': 'tide_adjustments',
            'compound': 'compound_rules',
            'integration': 'integration_weights'
        }

        if target == 'all':
            # 全パラメータを結合
            all_params = {}
            for key in target_map.values():
                if key in definitions and 'parameters' in definitions[key]:
                    all_params.update(definitions[key]['parameters'])
            return all_params

        section_key = target_map.get(target)
        if not section_key or section_key not in definitions:
            return {}

        return definitions.get(section_key, {}).get('parameters', {})

    def get_optimization_config(self) -> Dict[str, Any]:
        """最適化設定を取得"""
        definitions = self.load()
        return definitions.get('optimization_config', {})

    def get_constraints(self) -> Dict[str, float]:
        """制約設定を取得"""
        definitions = self.load()
        return definitions.get('constraints', {})

    def _get_default_definitions(self) -> Dict[str, Any]:
        """デフォルトのパラメータ定義"""
        return {
            'venue_adjustments': {
                'parameters': {
                    'course_1_base_bonus': {'min': -5.0, 'max': 15.0, 'step': 1.0, 'default': 5.0},
                    'in_strong_venue_bonus': {'min': 5.0, 'max': 15.0, 'step': 1.0, 'default': 10.0},
                    'in_weak_venue_penalty': {'min': -10.0, 'max': 0.0, 'step': 1.0, 'default': -5.0},
                }
            },
            'weather_adjustments': {
                'parameters': {
                    'wind_threshold_strong': {'min': 4.0, 'max': 8.0, 'step': 1.0, 'default': 6.0},
                    'strong_wind_course_1_penalty': {'min': -15.0, 'max': 0.0, 'step': 1.0, 'default': -5.0},
                }
            },
            'optimization_config': {
                'min_hit_rate_constraint': 0.55,
                'target_recovery_rate': 0.85,
            }
        }


# ============================================================
# 最適化エンジン V2
# ============================================================

class ParameterOptimizerV2:
    """パラメータ最適化エンジン V2"""

    def __init__(self, config: OptimizationConfigV2):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # パラメータ定義ローダー
        self.param_loader = ParameterDefinitionLoader()

        # バックテスト評価器
        backtest_config = BacktestConfig(
            period_days=config.test_period_days
        )
        self.evaluator = BacktestEvaluatorV2(config=backtest_config)

        # 目的関数
        self.objective_func = ObjectiveFunction(
            evaluator=self.evaluator,
            min_hit_rate=config.min_hit_rate,
            recovery_weight=config.recovery_weight,
            hit_rate_weight=config.hit_rate_weight
        )

        # パラメータ範囲
        self.param_ranges = self.param_loader.get_param_ranges(config.target)

    def optimize(self) -> OptimizationResultV2:
        """最適化を実行"""
        started_at = datetime.now().isoformat()

        # データ読み込み
        self.logger.info("Loading backtest data...")
        race_count = self.evaluator.load_test_data()
        self.logger.info(f"Loaded {race_count} races for evaluation")

        if race_count < self.evaluator.config.min_races:
            self.logger.warning(
                f"Insufficient data: {race_count} races < {self.evaluator.config.min_races} minimum"
            )

        # 最適化実行
        if self.config.mode == "grid":
            best_params, best_objective, iterations, all_results = self._grid_search()
        elif self.config.mode == "bayesian":
            best_params, best_objective, iterations, all_results = self._bayesian_optimization()
        else:
            raise ValueError(f"Unknown mode: {self.config.mode}")

        completed_at = datetime.now().isoformat()

        # 最終評価
        final_eval = self.objective_func.evaluate_detailed(best_params)

        return OptimizationResultV2(
            target=self.config.target,
            mode=self.config.mode,
            best_params=best_params,
            best_objective=best_objective,
            hit_rate=final_eval['hit_rate'],
            recovery_rate=final_eval['recovery_rate'],
            profit_loss=final_eval['profit_loss'],
            sample_size=final_eval['sample_size'],
            constraint_satisfied=final_eval['constraint_satisfied'],
            started_at=started_at,
            completed_at=completed_at,
            iterations_run=iterations,
            all_results=all_results if self.config.verbose else None
        )

    def _grid_search(self) -> Tuple[Dict[str, float], float, int, List[Dict]]:
        """グリッドサーチによる最適化"""
        self.logger.info("Starting grid search optimization...")
        self.logger.info(f"Target: {self.config.target}")
        self.logger.info(f"Parameters: {list(self.param_ranges.keys())}")

        # パラメータの全組み合わせを生成
        param_names = list(self.param_ranges.keys())
        param_values = []

        for name in param_names:
            spec = self.param_ranges[name]
            import numpy as np
            min_val = spec.get('min', 0)
            max_val = spec.get('max', 10)
            step = spec.get('step', 1.0)
            values = np.arange(min_val, max_val + step/2, step).tolist()
            param_values.append(values)
            self.logger.info(f"  {name}: {min_val} to {max_val} (step={step}, {len(values)} values)")

        total_combinations = 1
        for v in param_values:
            total_combinations *= len(v)

        self.logger.info(f"Total combinations: {total_combinations}")

        best_objective = -float('inf')
        best_params = {}
        iterations = 0
        all_results = []

        # 進捗表示の間隔
        report_interval = max(1, total_combinations // 20)

        for values in product(*param_values):
            params = dict(zip(param_names, values))
            iterations += 1

            # 評価
            eval_result = self.objective_func.evaluate_detailed(params)
            objective = eval_result['objective']

            all_results.append({
                'params': params.copy(),
                'objective': objective,
                'hit_rate': eval_result['hit_rate'],
                'recovery_rate': eval_result['recovery_rate'],
                'constraint_satisfied': eval_result['constraint_satisfied']
            })

            if objective > best_objective:
                best_objective = objective
                best_params = params.copy()
                if self.config.verbose:
                    self.logger.info(
                        f"New best: obj={objective:.4f}, "
                        f"hit={eval_result['hit_rate']:.2%}, "
                        f"rec={eval_result['recovery_rate']:.2%}, "
                        f"constraint={'OK' if eval_result['constraint_satisfied'] else 'NG'}"
                    )

            # 進捗表示
            if iterations % report_interval == 0:
                progress = iterations / total_combinations * 100
                self.logger.info(f"Progress: {iterations}/{total_combinations} ({progress:.1f}%)")

        # 結果をソート（objective降順）
        all_results.sort(key=lambda x: x['objective'], reverse=True)

        return best_params, best_objective, iterations, all_results[:100]  # 上位100件のみ保存

    def _bayesian_optimization(self) -> Tuple[Dict[str, float], float, int, List[Dict]]:
        """ベイズ最適化による最適化"""
        self.logger.info("Starting Bayesian optimization...")

        try:
            from bayes_opt import BayesianOptimization
        except ImportError:
            self.logger.error(
                "bayesian-optimization package is required. "
                "Install with: pip install bayesian-optimization"
            )
            # フォールバック: グリッドサーチ
            self.logger.info("Falling back to grid search...")
            return self._grid_search()

        # パラメータ境界を設定
        pbounds = {}
        for name, spec in self.param_ranges.items():
            pbounds[name] = (spec.get('min', 0), spec.get('max', 10))

        all_results = []

        def objective(**params):
            eval_result = self.objective_func.evaluate_detailed(params)

            all_results.append({
                'params': params.copy(),
                'objective': eval_result['objective'],
                'hit_rate': eval_result['hit_rate'],
                'recovery_rate': eval_result['recovery_rate'],
                'constraint_satisfied': eval_result['constraint_satisfied']
            })

            return eval_result['objective']

        # 最適化設定
        opt_config = self.param_loader.get_optimization_config()
        init_points = opt_config.get('bayesian', {}).get('init_points', 5)
        random_state = opt_config.get('bayesian', {}).get('random_state', 42)

        optimizer = BayesianOptimization(
            f=objective,
            pbounds=pbounds,
            random_state=random_state,
            verbose=2 if self.config.verbose else 0
        )

        optimizer.maximize(
            init_points=init_points,
            n_iter=self.config.iterations
        )

        best_params = optimizer.max['params']
        best_objective = optimizer.max['target']

        # 結果をソート
        all_results.sort(key=lambda x: x['objective'], reverse=True)

        return best_params, best_objective, self.config.iterations + init_points, all_results


# ============================================================
# 結果保存
# ============================================================

def save_optimization_result(
    result: OptimizationResultV2,
    output_dir: Path = None
) -> Path:
    """最適化結果を保存"""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "config" / "presets" / "optimization_history"

    output_dir.mkdir(parents=True, exist_ok=True)

    # ファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{result.target}_{result.mode}_{timestamp}.json"
    filepath = output_dir / filename

    # JSON形式で保存
    result_dict = asdict(result)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)

    print(f"Result saved to: {filepath}")
    return filepath


def apply_to_preset(
    result: OptimizationResultV2,
    preset_dir: Path = None
) -> bool:
    """最適化結果をプリセットYAMLに適用"""
    if preset_dir is None:
        preset_dir = PROJECT_ROOT / "config" / "presets"

    target_map = {
        'venue': 'venue_characteristics.yaml',
        'weather': 'weather_rules.yaml',
        'tide': 'tide_adjustments.yaml',
    }

    if result.target not in target_map:
        print(f"Target '{result.target}' does not have a direct preset file")
        return False

    preset_file = preset_dir / target_map[result.target]

    if not preset_file.exists():
        print(f"Preset file not found: {preset_file}")
        return False

    # 現在のプリセットを読み込み
    with open(preset_file, 'r', encoding='utf-8') as f:
        preset_data = yaml.safe_load(f)

    # パラメータを更新
    # 注: 実際の更新ロジックはプリセット構造に依存
    print(f"Would update {preset_file} with:")
    for name, value in result.best_params.items():
        print(f"  {name}: {value}")

    # 確認なしでは更新しない
    print("\nTo apply these changes, manually update the preset file or use --apply-confirm flag")
    return False


def print_result_summary(result: OptimizationResultV2):
    """結果サマリーを表示"""
    print("\n" + "=" * 60)
    print("最適化結果サマリー")
    print("=" * 60)
    print(f"対象: {result.target}")
    print(f"モード: {result.mode}")
    print(f"実行回数: {result.iterations_run}")
    print(f"開始: {result.started_at}")
    print(f"完了: {result.completed_at}")
    print("-" * 60)
    print(f"最高目的関数値: {result.best_objective:.4f}")
    print(f"的中率: {result.hit_rate:.2%}")
    print(f"回収率: {result.recovery_rate:.2%}")
    print(f"収支: ¥{result.profit_loss:,.0f}")
    print(f"サンプル数: {result.sample_size}")
    print(f"制約充足: {'OK' if result.constraint_satisfied else 'NG'}")
    print("-" * 60)
    print("最適パラメータ:")
    for name, value in result.best_params.items():
        print(f"  {name}: {value:.2f}")

    if result.all_results:
        print("-" * 60)
        print("上位5結果:")
        for i, r in enumerate(result.all_results[:5], 1):
            print(f"  {i}. obj={r['objective']:.4f}, "
                  f"hit={r['hit_rate']:.2%}, "
                  f"rec={r['recovery_rate']:.2%}")


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="プリセット値最適化スクリプト V2"
    )
    parser.add_argument(
        "--mode",
        choices=["grid", "bayesian"],
        default="grid",
        help="最適化モード (default: grid)"
    )
    parser.add_argument(
        "--target",
        choices=["venue", "weather", "tide", "compound", "integration", "all"],
        default="venue",
        help="最適化対象 (default: venue)"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=50,
        help="ベイズ最適化のイテレーション数 (default: 50)"
    )
    parser.add_argument(
        "--test-days",
        type=int,
        default=90,
        help="テスト期間（日数） (default: 90)"
    )
    parser.add_argument(
        "--min-hit-rate",
        type=float,
        default=0.55,
        help="最低的中率制約 (default: 0.55)"
    )
    parser.add_argument(
        "--recovery-weight",
        type=float,
        default=0.7,
        help="回収率の重み (default: 0.7)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細出力"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="結果をJSONで保存"
    )
    parser.add_argument(
        "--apply-confirm",
        action="store_true",
        help="最適化結果をプリセットに適用（確認あり）"
    )

    args = parser.parse_args()

    # ログ設定
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # 設定
    config = OptimizationConfigV2(
        mode=args.mode,
        target=args.target,
        iterations=args.iterations,
        test_period_days=args.test_days,
        min_hit_rate=args.min_hit_rate,
        recovery_weight=args.recovery_weight,
        hit_rate_weight=1.0 - args.recovery_weight,
        verbose=args.verbose
    )

    print("\n" + "=" * 60)
    print("プリセット最適化 V2")
    print("=" * 60)
    print(f"モード: {config.mode}")
    print(f"対象: {config.target}")
    print(f"テスト期間: {config.test_period_days}日")
    print(f"最低的中率: {config.min_hit_rate:.0%}")
    print(f"重み: 回収率={config.recovery_weight:.0%}, 的中率={config.hit_rate_weight:.0%}")
    print()

    # 最適化実行
    optimizer = ParameterOptimizerV2(config)
    result = optimizer.optimize()

    # 結果表示
    print_result_summary(result)

    # 結果保存
    if args.save:
        save_optimization_result(result)

    # プリセット適用
    if args.apply_confirm:
        apply_to_preset(result)

    return result


if __name__ == "__main__":
    main()
