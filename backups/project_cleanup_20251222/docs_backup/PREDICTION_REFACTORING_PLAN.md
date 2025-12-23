# 予測システム リファクタリング実装計画書

**作成日**: 2025-12-15
**バージョン**: 1.0
**関連ドキュメント**: PREDICTION_REFACTORING_ANALYSIS.md

---

## 概要

本計画書は、予測システムを「加算・減算方式」に統一し、プリセット管理と最適化を体系化するための段階的実装計画を定義する。

### 目標

1. **スコア統合方式の統一**: 乗算・パーセントを加算・減算に変換
2. **事前/直前情報の明確な分離**: 重複を排除し、境界を明確化
3. **プリセット管理の体系化**: YAML形式で一元管理
4. **最適化システムの構築**: バックテスト連携の自動パラメータ最適化

### 成功基準

- 既存の回収率（約75%）を維持または改善
- 1着的中率55%以上を維持
- 全プリセットがYAMLファイルで管理される
- 最適化スクリプトで自動チューニング可能

---

## Phase 1: プリセット管理の体系化

**期間**: 3日間
**リスク**: 低
**既存システムへの影響**: 最小

### 1.1 タスク一覧

| # | タスク | 詳細 | 想定工数 |
|---|--------|------|---------|
| 1.1 | プリセット形式の設計 | YAML構造の定義 | 2h |
| 1.2 | 会場特性プリセット移行 | venue_characteristics.py → YAML | 3h |
| 1.3 | 天候ルール移行 | weather_rules.json → YAML統合 | 2h |
| 1.4 | 潮位補正プリセット移行 | tide_adjuster.py内定義 → YAML | 2h |
| 1.5 | プリセットローダー実装 | preset_loader.py 新規作成 | 4h |
| 1.6 | 既存コードの接続 | 旧システムとの互換性確保 | 4h |
| 1.7 | テスト・検証 | 回帰テスト実施 | 3h |

### 1.2 成果物

- `config/presets/venue_characteristics.yaml`
- `config/presets/weather_rules.yaml`
- `config/presets/tide_adjustments.yaml`
- `src/utils/preset_loader.py`

### 1.3 YAMLスキーマ設計

```yaml
# config/presets/venue_characteristics.yaml
version: "1.0"
updated_at: "2025-12-15"
data_source: "2020-2025年実績データ"

venues:
  "01":  # 桐生
    name: "桐生"
    water_type: "freshwater"
    characteristics:
      - "標準的"
    course_win_rates:
      1: 0.572
      2: 0.110
      3: 0.126
      4: 0.115
      5: 0.066
      6: 0.020
    adjustments:
      course_1_multiplier: 1.0
      strong_wind_penalty: -0.05
      high_wave_penalty: -0.03

  "24":  # 大村
    name: "大村"
    water_type: "seawater"
    characteristics:
      - "インが非常に強い"
      - "静水面"
    course_win_rates:
      1: 0.681
      2: 0.112
      3: 0.094
      4: 0.066
      5: 0.046
      6: 0.013
    adjustments:
      course_1_multiplier: 1.10
      strong_wind_penalty: -0.08
      high_wave_penalty: -0.05
```

---

## Phase 2: スコア統合方式の統一

**期間**: 5日間
**リスク**: 中
**既存システムへの影響**: 中（コアロジック変更）

### 2.1 タスク一覧

| # | タスク | 詳細 | 想定工数 |
|---|--------|------|---------|
| 2.1 | 加算・減算変換ルール定義 | 乗算→加算の変換式策定 | 4h |
| 2.2 | ベーススコア計算見直し | calculate_course_rank_score改修 | 6h |
| 2.3 | 補正モジュールの統一 | weather/tide/compound を加算方式に | 8h |
| 2.4 | 新統合関数の実装 | apply_adjustments() 統一インターフェース | 6h |
| 2.5 | 補正値の正規化 | 各補正のスケールを統一（-10〜+10点） | 4h |
| 2.6 | テスト・検証 | 新旧比較バックテスト | 6h |
| 2.7 | ドキュメント更新 | 変換ルール・補正値一覧 | 2h |

### 2.2 変換ルール

**乗算 → 加算 変換式:**

```python
# 旧方式（乗算）
score = base_score * multiplier  # multiplier = 1.05 など

# 新方式（加算）
# multiplier 1.05 = +5%相当 → base_scoreの5%を加算
adjustment = base_score * (multiplier - 1.0)
score = base_score + adjustment

# 例: base_score=50, multiplier=1.10
# 旧: 50 * 1.10 = 55
# 新: 50 + 50 * 0.10 = 55（同値だが、adjustmentが可視化される）
```

**パーセント → 加算 変換式:**

```python
# 旧方式（パーセント）
adjustment_percent = 0.05  # 5%
score = original_score * (1 + adjustment_percent)

# 新方式（直接加算）
# 基準スコア（例: 50点）に対する影響を固定化
BASE_REFERENCE = 50.0
adjustment = BASE_REFERENCE * adjustment_percent
score = original_score + adjustment

# 例: original_score=70, adjustment_percent=0.05
# 旧: 70 * 1.05 = 73.5
# 新: 70 + 2.5 = 72.5（スコアに依存しない固定加算）
```

### 2.3 統一インターフェース設計

```python
# src/analysis/adjustment_manager.py
class AdjustmentManager:
    """補正値の統一管理"""

    def apply_all_adjustments(
        self,
        base_score: float,
        race_context: RaceContext
    ) -> Tuple[float, List[AdjustmentRecord]]:
        """
        全補正を適用

        Returns:
            (final_score, adjustment_records)
        """
        adjustments = []
        score = base_score

        # 1. 会場特性補正
        venue_adj = self._apply_venue_adjustment(race_context)
        adjustments.append(AdjustmentRecord("venue", venue_adj, score))
        score += venue_adj

        # 2. 天候補正
        weather_adj = self._apply_weather_adjustment(race_context)
        adjustments.append(AdjustmentRecord("weather", weather_adj, score))
        score += weather_adj

        # 3. 潮位補正
        tide_adj = self._apply_tide_adjustment(race_context)
        adjustments.append(AdjustmentRecord("tide", tide_adj, score))
        score += tide_adj

        # 4. 複合条件補正
        compound_adj = self._apply_compound_adjustment(race_context)
        adjustments.append(AdjustmentRecord("compound", compound_adj, score))
        score += compound_adj

        # スコア範囲を制限
        score = max(0.0, min(100.0, score))

        return score, adjustments
```

---

## Phase 3: 事前/直前情報の明確な分離

**期間**: 4日間
**リスク**: 中
**既存システムへの影響**: 中（データフロー変更）

### 3.1 タスク一覧

| # | タスク | 詳細 | 想定工数 |
|---|--------|------|---------|
| 3.1 | 情報カテゴリの再定義 | 事前/直前の境界を明確化 | 2h |
| 3.2 | PreInfoScorer実装 | 事前情報専用スコアラー | 6h |
| 3.3 | BeforeInfoScorer改修 | 直前情報に特化（重複排除） | 4h |
| 3.4 | 統合ロジックの見直し | 動的重み調整の改善 | 6h |
| 3.5 | データフロー整理 | キャッシュ戦略の最適化 | 4h |
| 3.6 | テスト・検証 | 新旧比較バックテスト | 6h |

### 3.2 情報カテゴリの再定義

**事前情報（Pre-Information）**

```yaml
pre_information:
  racer:
    - overall_stats         # 全国成績
    - course_stats          # コース別成績
    - venue_stats           # 当地成績
    - grade_affinity        # グレード適性
    - kimarite_affinity     # 決まり手適性
    - recent_form           # 直近成績（過去5走）
  motor:
    - win_rate              # モーター勝率
    - second_rate           # 2連率
    - boat_stats            # ボート成績
  static:
    - racer_rank            # 級別（A1/A2/B1/B2）
    - f_count               # F持ち
    - l_count               # L持ち
    - avg_st                # 平均ST（過去実績）
```

**直前情報（Before-Information）**

```yaml
before_information:
  exhibition:
    - exhibition_time       # 展示タイム
    - exhibition_st         # 展示ST
    - exhibition_course     # 展示進入コース
    - tilt_angle            # チルト角度
  race_day:
    - prev_race_result      # 前走成績（当日）
    - parts_replacement     # 部品交換
    - adjusted_weight       # 調整重量
  environment:
    - wind_speed            # 風速
    - wind_direction        # 風向
    - wave_height           # 波高
    - temperature           # 気温
    - water_temperature     # 水温
    - tide_phase            # 潮位フェーズ
```

### 3.3 統合ロジックの見直し

```python
# 現状
FINAL_SCORE = PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4

# 新方式（動的重み + 加算分離）
class ScoreIntegrator:
    def integrate(
        self,
        pre_score: float,
        before_score: float,
        context: RaceContext
    ) -> Tuple[float, IntegrationDetail]:
        # 1. 動的重みを決定
        weights = self._determine_weights(context)

        # 2. 事前スコアをベースとして設定
        base_score = pre_score

        # 3. 直前情報による補正を加算
        # BEFORE_SCOREは「ベースからの差分」として扱う
        before_adjustment = (before_score - 50.0) * weights.before_factor

        # 4. 統合
        final_score = base_score + before_adjustment

        return final_score, IntegrationDetail(
            base_score=base_score,
            before_adjustment=before_adjustment,
            weights=weights,
            final_score=final_score
        )
```

---

## Phase 4: 最適化システムの構築

**期間**: 5日間
**リスク**: 低（新規機能）
**既存システムへの影響**: なし

### 4.1 タスク一覧

| # | タスク | 詳細 | 想定工数 |
|---|--------|------|---------|
| 4.1 | 最適化フレームワーク設計 | グリッドサーチ/ベイズ最適化 | 4h |
| 4.2 | 評価関数の実装 | 回収率/的中率の最大化 | 4h |
| 4.3 | バックテスト連携 | backtest.pyとの統合 | 6h |
| 4.4 | 最適化スクリプト実装 | optimize_preset_values.py | 8h |
| 4.5 | 結果保存・適用機能 | YAMLへの自動反映 | 4h |
| 4.6 | ドキュメント・ガイド作成 | 最適化実行手順 | 4h |

### 4.2 最適化対象パラメータ

```yaml
# config/optimization_targets.yaml
optimization_targets:
  venue_adjustments:
    - course_1_multiplier
    - strong_wind_penalty
    - high_wave_penalty

  weather_adjustments:
    - tailwind_bonus
    - headwind_penalty
    - wind_threshold

  tide_adjustments:
    - rising_bonus
    - falling_penalty

  integration_weights:
    - pre_weight
    - before_weight
    - confidence_threshold

  constraints:
    min_value: -20.0
    max_value: 20.0
    total_adjustment_limit: 30.0
```

### 4.3 評価関数

```python
# scripts/optimize_preset_values.py
def objective_function(params: Dict, backtest_data: DataFrame) -> float:
    """
    最適化の評価関数

    目標: 回収率の最大化（制約: 的中率55%以上）
    """
    # 1. パラメータを適用
    apply_params(params)

    # 2. バックテスト実行
    results = run_backtest(backtest_data)

    # 3. 評価値計算
    recovery_rate = results['total_return'] / results['total_bet']
    hit_rate = results['hit_count'] / results['total_races']

    # 4. 制約違反ペナルティ
    penalty = 0.0
    if hit_rate < 0.55:
        penalty = (0.55 - hit_rate) * 100  # 的中率55%未満はペナルティ

    # 5. 目標関数（回収率最大化）
    return recovery_rate - penalty
```

---

## 実装スケジュール

```
Week 1 (Day 1-5):
  Mon: Phase 1.1-1.2 (プリセット形式設計、会場特性移行)
  Tue: Phase 1.3-1.4 (天候/潮位プリセット移行)
  Wed: Phase 1.5-1.6 (プリセットローダー実装)
  Thu: Phase 1.7 (テスト・検証)
  Fri: Phase 2.1-2.2 (変換ルール定義、ベーススコア見直し)

Week 2 (Day 6-10):
  Mon: Phase 2.3 (補正モジュール統一)
  Tue: Phase 2.4-2.5 (統合関数実装、正規化)
  Wed: Phase 2.6-2.7 (テスト・ドキュメント)
  Thu: Phase 3.1-3.2 (情報カテゴリ再定義、PreInfoScorer)
  Fri: Phase 3.3-3.4 (BeforeInfoScorer改修、統合ロジック)

Week 3 (Day 11-15):
  Mon: Phase 3.5-3.6 (データフロー整理、テスト)
  Tue: Phase 4.1-4.2 (最適化フレームワーク、評価関数)
  Wed: Phase 4.3 (バックテスト連携)
  Thu: Phase 4.4 (最適化スクリプト)
  Fri: Phase 4.5-4.6 (結果保存、ドキュメント)
```

---

## リスクと対策

| リスク | 影響度 | 発生確率 | 対策 |
|--------|--------|----------|------|
| 回収率低下 | 高 | 中 | 旧システムとの並行運用、段階的移行 |
| バグ混入 | 中 | 中 | 単体テスト充実、回帰テスト自動化 |
| 工数超過 | 中 | 中 | バッファ確保、スコープ調整の柔軟性 |
| 既存機能への影響 | 高 | 低 | インターフェース互換性維持 |

### ロールバック手順

1. 機能フラグ `use_prediction_engine_v2` を `False` に設定
2. 旧エンジンが自動的に使用される
3. 問題の特定・修正後、フラグを `True` に戻す

---

## 付録: 新規作成ファイル一覧

| ファイル | 役割 | Phase |
|---------|------|-------|
| config/presets/venue_characteristics.yaml | 会場特性プリセット | 1 |
| config/presets/weather_rules.yaml | 天候ルールプリセット | 1 |
| config/presets/tide_adjustments.yaml | 潮位補正プリセット | 1 |
| config/presets/compound_rules.yaml | 複合条件ルールプリセット | 1 |
| src/utils/preset_loader.py | プリセットローダー | 1 |
| src/analysis/adjustment_manager.py | 補正値統一管理 | 2 |
| src/analysis/pre_info_scorer.py | 事前情報スコアラー | 3 |
| src/analysis/score_integrator.py | スコア統合モジュール | 3 |
| src/analysis/prediction_engine_v2.py | 新予測エンジン | 3 |
| scripts/optimize_preset_values.py | 最適化スクリプト | 4 |
| config/optimization_targets.yaml | 最適化対象定義 | 4 |

---

## 付録: 修正対象ファイル一覧

| ファイル | 修正内容 | Phase |
|---------|---------|-------|
| src/analysis/race_predictor.py | V2エンジン呼び出し追加 | 3 |
| src/analysis/beforeinfo_scorer.py | 重複排除、純粋化 | 3 |
| src/analysis/weather_adjuster.py | 加算方式への変換 | 2 |
| src/analysis/tide_adjuster.py | 加算方式への変換、YAML読込 | 2 |
| src/analysis/compound_buff_system.py | YAML読込対応 | 1 |
| config/feature_flags.py | V2フラグ追加 | 3 |

---

*本計画書はプロジェクト進行に応じて更新される*
