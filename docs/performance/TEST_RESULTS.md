# テスト結果・構成

**最終更新**: 2025-12-25

---

## テスト構成

### 標準バックテスト

**スクリプト**: `scripts/backtest/standard_backtest.py`

```bash
# 実行方法
python scripts/backtest/standard_backtest.py
```

**テスト内容**:
- 購入条件（BET_CONDITIONS）に基づく全条件のバックテスト
- 年度指定可能（デフォルト: 2025年）
- before予測を使用
- 1-2-3全的中を的中と判定

### ベンチマークテスト

**スクリプト**: `scripts/benchmark_prediction_system.py`

```bash
# ベースライン保存
python scripts/benchmark_prediction_system.py --save-baseline

# 変更後の比較
python scripts/benchmark_prediction_system.py --compare
```

**テスト内容**:
- 予測精度（1着/2着/3着）の測定
- 信頼度別の成績測定
- 結果を `data/benchmark_results/` に自動保存

---

## 検証方法の違い（重要）

| 検証方法 | 的中定義 | 用途 | 信頼性 |
|:---------|:---------|:-----|:------:|
| **バックテスト** | 1-2-3全的中 | **最終判断** | **高** |
| 6年間データ分析 | 1着予測が1着 | 参考値 | 中 |
| 単純サンプリング | ランダム100件 | 参考値 | 低 |

**教訓**:
- 新条件追加時は**必ずバックテスト**で検証
- 6年間データ分析のROIはバックテストで大幅に変わることがある
  - 例: A×B1×モーター40%+ → 6年間: 2692% → バックテスト: 196.6%

---

## 最新テスト結果（2025-12-25）

### 購入条件別バックテスト

| 条件 | 件数 | 的中 | ROI | 収支 | 判定 |
|:-----|:----:|:----:|:---:|:----:|:----:|
| A×A1×10-12 | 199 | 21 | 115.1% | +3,010円 | PASS |
| A×A1×14-16 | 86 | 8 | 137.0% | +3,180円 | PASS |
| A×B1×モーター40%+ | 80 | - | 196.6% | +7,730円 | PASS |
| B×50-100 | 52 | 2 | 289.2% | +9,840円 | PASS |
| B×30-50×B1+会場 | 20 | 3 | 552.0% | +9,040円 | PASS |
| C×20-30×B1+会場 | 132 | 9 | 161.5% | +8,120円 | PASS |
| 鳴門×C×A2×30-80 | 19 | 1 | 225.8% | +2,390円 | PASS |
| D×40-50×B1 | 110 | 4 | 171.9% | +7,910円 | PASS |
| D×30-60 | 508 | 15 | 136.2% | +18,390円 | PASS |
| **合計** | **1,126** | - | **155.0%** | **+61,880円** | **PASS** |

### 機能フラグ別効果測定

| フラグ | テスト方法 | サンプル数 | 効果 | 判定 |
|-------|-----------|:----------:|:----:|:----:|
| ab_rank_special_betting | 全件バックテスト | 1,105件 | +17.2pt | PASS |
| kimarite_flow_prediction | 全件バックテスト | 28,089件 | +4.1pt | PASS |
| makuri_risk_adjustment | 全件バックテスト | 28,089件 | +4.1pt | PASS |
| pairwise_scoring | 482レース検証 | 482件 | +1.7pt | PASS |
| monte_carlo_simulation | 300レース検証 | 300件 | **-8.5pt** | **FAIL** |
| rank23_odds_calibration | 100レース検証 | 100件 | ±0pt | FAIL |
| condition_factor | 1000レース検証 | 1,000件 | **-9.5pt** | **FAIL** |

---

## テストスクリプト一覧

### バックテスト系

| スクリプト | 用途 |
|-----------|------|
| `scripts/backtest/standard_backtest.py` | 標準バックテスト |
| `scripts/backtest/verify_feature_flags_4years.py` | 4年間フラグ検証 |
| `scripts/backtest/verify_adjustment_full.py` | 調整効果全件検証 |
| `scripts/backtest/backtest_motor_conditions.py` | モーター条件検証 |
| `scripts/backtest/simulate_2025_full_year.py` | 2025年通年シミュレーション |

### 効果測定系

| スクリプト | 用途 |
|-----------|------|
| `scripts/quick_compare_odds_calibration.py` | オッズ校正効果比較 |
| `scripts/quick_monte_carlo_test.py` | モンテカルロ効果測定 |
| `scripts/evaluate_condition_factor.py` | 調子係数効果測定 |

### ベンチマーク系

| スクリプト | 用途 |
|-----------|------|
| `scripts/benchmark_prediction_system.py` | 予測精度ベンチマーク |
| `scripts/maintenance/track_performance_change.py` | 性能変更追跡 |
| `scripts/maintenance/extract_current_config.py` | 現在設定抽出 |

---

## 標準テストワークフロー

### 新機能追加時

```bash
# 1. ベースライン保存
python scripts/benchmark_prediction_system.py --save-baseline

# 2. 機能フラグ変更（config/feature_flags.py編集）

# 3. 効果測定
python scripts/benchmark_prediction_system.py --compare

# 4. バックテスト
python scripts/backtest/standard_backtest.py

# 5. 履歴記録
python scripts/maintenance/track_performance_change.py \
    --description "変更内容の説明"
```

### 新条件追加時

```bash
# 1. 6年間データ分析（参考値）
# → 高ROIパターンを抽出

# 2. バックテスト（最終判断）
python scripts/backtest/standard_backtest.py

# 3. 年度別安定性確認
# → 2022-2025年で連続黒字か確認

# 4. 本番条件に追加
# → src/betting/bet_target_evaluator.py 編集
```

---

## 採用基準

### 機能フラグ

| 基準 | 条件 |
|------|------|
| 効果 | ROI +2pt以上 または 収支改善 |
| サンプル | 100件以上で検証 |
| 安定性 | 年度間で効果が一貫 |
| 計算コスト | 許容範囲内（+50%以下） |

### 購入条件

| 基準 | 条件 |
|------|------|
| ROI | 100%以上（黒字） |
| サンプル | 100件以上 |
| 年度安定性 | 直近4年で3年以上黒字 |
| 月別安定性 | 極端な偏りがないこと |

---

## 過去のテスト履歴

### 2025-12-25

| テスト | 結果 |
|--------|------|
| 鳴門×C×A2×30-80 | ROI 225.8%, +2,390円 → **採用** |

### 2025-12-24

| テスト | 結果 |
|--------|------|
| A×B1×モーター40%+ | ROI 196.6%, +7,730円 → **採用** |
| A×A2×モーター40%+ | ROI 70.3%, -3,500円 → **不採用** |
| D×A1×モーター40%+ | 32件、サンプル不足 → **保留** |
| D×A2×モーター40%+ | 32件、サンプル不足 → **保留** |

### 2025-12-20

| テスト | 結果 |
|--------|------|
| 決まり手展開予測（5%調整） | ROI +4.1pt → **採用** |
| 決まり手展開予測（10%調整） | ROI -10.4pt → 不採用 |
| 選手調子係数 | 精度-9.5pt → **不採用** |
| 前付け常習者フィルター | ab_rank ONで-7.6pt → **不採用** |

### 2025-12-19

| テスト | 結果 |
|--------|------|
| モンテカルロシミュレーション | 1着-8.5pt → **不採用** |
| ペアワイズスコアリング | 2着+7.3pt, 3着+3.9pt → **採用** |

### 2025-12-18

| テスト | 結果 |
|--------|------|
| rank23オッズ校正（2024年） | +2.04pt → 一時採用 |
| rank23オッズ校正（2025年） | ±0pt → **不採用（ドリフト）** |

---

## 関連ドキュメント

- [REJECTED_IDEAS.md](../improvement_attempts/REJECTED_IDEAS.md) - 不採用案詳細
- [YEARLY_PERFORMANCE.md](YEARLY_PERFORMANCE.md) - 年度別成績
- [PREDICTION_LOGIC.md](../architecture/PREDICTION_LOGIC.md) - 予測ロジック

---

*最終更新: 2025-12-25*
