# Phase 4 実装サマリー

**作成日**: 2025-12-15
**ステータス**: 完了

---

## 概要

Phase 4では、パラメータ最適化システムを構築しました。新予測システム（PreInfoScorer, ScoreIntegrator, AdjustmentManager）と連携し、グリッドサーチ/ベイズ最適化でプリセット補正値の最適化を実現します。

---

## 実装モジュール

### 1. BacktestEvaluatorV2 (`src/analysis/backtest_evaluator.py`)

**目的**: 新予測システムと連携したバックテスト評価

**主要クラス**:

| クラス | 説明 |
|--------|------|
| BacktestConfig | バックテスト設定（期間、会場フィルター等） |
| BacktestResult | バックテスト結果（的中率、回収率、会場別等） |
| RaceEvaluationData | レース評価用データ構造 |
| BacktestEvaluatorV2 | 評価器本体 |
| ObjectiveFunction | 最適化用目的関数 |

**評価方法**:

```python
# 1. 予測関数を指定して評価
result = evaluator.evaluate_with_predictor(predict_func)

# 2. スコア関数を指定して評価
result = evaluator.evaluate_with_scores(score_func)

# 3. パラメータ直接指定で評価
result = evaluator.evaluate_params(params_dict)
```

**出力統計**:
- 的中率（hit_rate）
- 回収率（recovery_rate）
- 収支（profit_loss）
- 会場別統計（by_venue）
- グレード別統計（by_grade）

### 2. optimization_targets.yaml (`config/presets/optimization_targets.yaml`)

**目的**: 最適化対象パラメータの一元管理

**セクション構成**:

| セクション | パラメータ数 | 説明 |
|------------|-------------|------|
| venue_adjustments | 6 | 会場特性補正 |
| weather_adjustments | 6 | 天候補正 |
| tide_adjustments | 5 | 潮位補正 |
| integration_weights | 4 | スコア統合 |
| compound_rules | 4 | 複合条件 |

**パラメータ定義形式**:

```yaml
course_1_base_bonus:
  description: "1コース基本ボーナス"
  default: 5.0
  min: -5.0
  max: 15.0
  step: 1.0
```

### 3. optimize_preset_values_v2.py (`scripts/optimize_preset_values_v2.py`)

**目的**: V2システム対応の最適化スクリプト

**使用方法**:

```bash
# グリッドサーチ（会場パラメータ）
python scripts/optimize_preset_values_v2.py --mode grid --target venue --verbose

# ベイズ最適化（天候パラメータ、100イテレーション）
python scripts/optimize_preset_values_v2.py --mode bayesian --target weather --iterations 100

# 全パラメータ最適化（結果保存）
python scripts/optimize_preset_values_v2.py --mode grid --target all --save

# 短期テスト（30日）
python scripts/optimize_preset_values_v2.py --mode grid --target venue --test-days 30
```

**オプション**:

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| --mode | grid | 最適化モード (grid/bayesian) |
| --target | venue | 対象 (venue/weather/tide/compound/integration/all) |
| --iterations | 50 | ベイズ最適化イテレーション数 |
| --test-days | 90 | テスト期間（日数） |
| --min-hit-rate | 0.55 | 最低的中率制約 |
| --recovery-weight | 0.7 | 回収率の重み |
| --verbose | false | 詳細出力 |
| --save | false | 結果をJSONで保存 |

---

## 評価関数（目的関数）

```
目的関数 = recovery_weight × 回収率 + hit_rate_weight × 的中率 - ペナルティ

ペナルティ = {
  0                                    (的中率 >= min_hit_rate の場合)
  (min_hit_rate - 的中率) × 100        (制約違反の場合)
}
```

**デフォルト設定**:
- 回収率の重み: 0.7
- 的中率の重み: 0.3
- 最低的中率制約: 55%

---

## モジュール間の関係

```
┌─────────────────────────────────────────────────────────────────┐
│                   optimize_preset_values_v2.py                   │
│                      (最適化スクリプト)                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ParameterOptimizerV2                            │
│           ┌──────────────┬──────────────────┐                   │
│           │ グリッドサーチ │ ベイズ最適化      │                   │
│           └──────────────┴──────────────────┘                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌────────────────┐ ┌────────────────┐ ┌────────────────────────────┐
│ ObjectiveFunc  │ │ BacktestEval   │ │ ParameterDefinitionLoader  │
│ (目的関数)     │ │ V2 (評価器)    │ │ (パラメータ定義読み込み)   │
└────────┬───────┘ └────────┬───────┘ └─────────────┬──────────────┘
         │                  │                       │
         │                  │                       ▼
         │                  │         ┌────────────────────────────┐
         │                  │         │ optimization_targets.yaml  │
         │                  │         └────────────────────────────┘
         │                  │
         ▼                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                        Database                                   │
│  - races, entries, results, race_conditions, win_odds            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 最適化結果の保存

**保存場所**: `config/presets/optimization_history/`

**ファイル形式**: JSON

**ファイル名**: `{target}_{mode}_{timestamp}.json`

**内容**:

```json
{
  "target": "venue",
  "mode": "grid",
  "best_params": {
    "course_1_base_bonus": 7.0,
    "in_strong_venue_bonus": 12.0,
    "in_weak_venue_penalty": -4.0
  },
  "best_objective": 0.623,
  "hit_rate": 0.587,
  "recovery_rate": 0.812,
  "profit_loss": -18800,
  "sample_size": 1234,
  "constraint_satisfied": true,
  "started_at": "2025-12-15T10:00:00",
  "completed_at": "2025-12-15T10:15:30",
  "iterations_run": 1728
}
```

---

## グリッドサーチの計算量

| ターゲット | パラメータ数 | 推定組み合わせ数 | 推定実行時間 |
|-----------|-------------|----------------|-------------|
| venue | 6 | ~15,000 | 5-10分 |
| weather | 6 | ~10,000 | 3-7分 |
| tide | 5 | ~3,000 | 1-3分 |
| compound | 4 | ~1,500 | 1分未満 |
| integration | 4 | ~1,200 | 1分未満 |
| all | 25 | 膨大 | ベイズ推奨 |

**注**: `--target all` はベイズ最適化を推奨

---

## 今後の拡張

### 1. 並列実行対応

```python
# concurrent.futures を使用した並列グリッドサーチ
from concurrent.futures import ProcessPoolExecutor
```

### 2. 早期終了（Early Stopping）

収束判定を追加して、改善が見られない場合に早期終了

### 3. ハイパーパラメータのチューニング

- ベイズ最適化の取得関数（acquisition function）調整
- 探索/活用のバランス調整

### 4. クロスバリデーション

期間を分割して、過学習を防止

---

## 関連ファイル

| ファイル | 説明 |
|----------|------|
| `src/analysis/backtest_evaluator.py` | バックテスト評価器 V2（NEW） |
| `scripts/optimize_preset_values_v2.py` | 最適化スクリプト V2（NEW） |
| `config/presets/optimization_targets.yaml` | パラメータ定義（NEW） |
| `src/analysis/pre_info_scorer.py` | 事前情報スコアラー（Phase 3） |
| `src/analysis/score_integrator.py` | スコア統合（Phase 3） |
| `src/analysis/adjustment_manager.py` | 補正管理（Phase 2） |
| `config/presets/*.yaml` | プリセット設定（Phase 1） |

---

## 使用例

### 基本的な最適化フロー

```python
from scripts.optimize_preset_values_v2 import (
    ParameterOptimizerV2,
    OptimizationConfigV2,
    print_result_summary,
    save_optimization_result
)

# 1. 設定
config = OptimizationConfigV2(
    mode="grid",
    target="venue",
    test_period_days=90,
    min_hit_rate=0.55,
    verbose=True
)

# 2. 最適化実行
optimizer = ParameterOptimizerV2(config)
result = optimizer.optimize()

# 3. 結果表示
print_result_summary(result)

# 4. 結果保存
save_optimization_result(result)
```

### カスタム評価

```python
from src.analysis.backtest_evaluator import (
    BacktestEvaluatorV2,
    BacktestConfig,
    ObjectiveFunction
)

# カスタム設定で評価
config = BacktestConfig(
    period_days=60,
    venue_codes=['24', '18'],  # 大村・徳山のみ
    min_races=50
)

evaluator = BacktestEvaluatorV2(config=config)
evaluator.load_test_data()

# カスタムパラメータで評価
params = {
    'course_1_base_bonus': 8.0,
    'in_strong_venue_bonus': 15.0,
}

result = evaluator.evaluate_params(params)
print(evaluator.get_summary(result))
```
