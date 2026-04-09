# 予測システム現状ステータス

**最終更新**: 2025-12-22
**更新方法**: `python scripts/maintenance/extract_current_config.py`

---

## 1. 現在の性能指標

### 測定条件

| 項目 | 値 |
|------|-----|
| **データセット** | 2025年 before予測 |
| **期間** | 2025-01-01 〜 2025-12-18 |
| **対象レース数** | 17,459 レース |
| **prediction_type** | before |

### 1着的中率（信頼度別）

| 信頼度 | 的中 | 総数 | 的中率 |
|--------|------|------|--------|
| **A** | 654 | 896 | **72.99%** |
| **B** | 3,739 | 5,700 | **65.60%** |
| **C** | 3,971 | 8,630 | **46.01%** |
| **D** | 712 | 2,162 | **32.93%** |
| **E** | 25 | 77 | **32.47%** |

### 2着的中率（信頼度別）

| 信頼度 | 的中 | 総数 | 的中率 |
|--------|------|------|--------|
| **A** | 266 | 896 | **29.69%** |
| **B** | 1,552 | 5,698 | **27.24%** |
| **C** | 2,013 | 8,628 | **23.33%** |
| **D** | 485 | 2,162 | **22.43%** |
| **E** | 17 | 77 | **22.08%** |

### 3着的中率（信頼度別）

| 信頼度 | 的中 | 総数 | 的中率 |
|--------|------|------|--------|
| **A** | 207 | 896 | **23.10%** |
| **B** | 1,283 | 5,700 | **22.51%** |
| **C** | 1,745 | 8,629 | **20.22%** |
| **D** | 412 | 2,162 | **19.06%** |
| **E** | 11 | 77 | **14.29%** |

### 三連単的中率（信頼度別）

| 信頼度 | 的中 | 総数 | 的中率 |
|--------|------|------|--------|
| **A** | 91 | 894 | **10.18%** |
| **B** | 511 | 5,633 | **9.07%** |
| **C** | 494 | 8,435 | **5.86%** |
| **D** | 81 | 2,068 | **3.92%** |
| **E** | 3 | 72 | **4.17%** |

---

## 2. 有効なフィーチャーフラグ

**更新日**: 2025-12-22
**ソース**: `config/feature_flags.py`

### 有効なフラグ一覧

| フラグ名 | 状態 | テスト結果 |
|----------|------|------------|
| `ab_rank_special_betting` | ON | - |
| `before_pattern_bonus` | ON | - |
| `confidence_based_switching` | ON | 検証中（アプローチ1: 信頼度ベース戦略切り替え） |
| `entry_prediction_model` | ON | - |
| `hierarchical_predictor` | ON | - |
| `interaction_features` | ON | - |
| `kimarite_flow_prediction` | ON | - |
| `lightgbm_ranking` | ON | - |
| `makuri_risk_adjustment` | ON | 検証中（P-6-2タスク） |
| `motor_capsizing_penalty` | ON | 検証中 |
| `negative_pattern_filter` | ON | 
            Opus分析結果（2022-2025年4年間）:
         ... |
| `negative_patterns` | ON | +2.0%改善（50レーステスト 2025-12-11） |
| `pairwise_scoring` | ON | 2着+7.3pt, 3着+3.9pt, ROI+1.7pt（482レース検証 2025-12-... |
| `second_place_specialized` | ON | +6.8pt（432レース検証 2025-12-18）AUC=0.6819 |
| `st_course_interaction` | ON | - |
| `upset_pattern_filter` | ON | 
            Opus分析結果（2022-2025年4年間）:
         ... |

### 無効化中のフラグ

| フラグ名 | 状態 | 理由 |
|----------|------|------|
| `apply_pattern_to_confidence_d` | OFF | - |
| `compound_pattern_bonus` | OFF | - |
| `condition_factor` | OFF | - |
| `forward_mover_filter` | OFF | - |
| `legacy_exhibition_adjustment` | OFF | - |
| `monte_carlo_simulation` | OFF | - |
| `odds_calibration` | OFF | 保留中 |
| `rank23_odds_calibration` | OFF | 不採用 - 2025年データで効果なし |
| `third_place_specialized_scorer` | OFF | - |
| `venue_pattern_optimization` | OFF | - |
| `verbose_logging` | OFF | - |

---

## 3. ベンチマーク実行方法

### 標準ベンチマーク

```bash
# 2025年before予測で性能測定
python scripts/benchmark_prediction_system.py
```

### 前回比較

```bash
# 前回の結果と比較
python scripts/benchmark_prediction_system.py --compare
```

### 設定抽出

```bash
# 現在のフラグ・設定をこのファイルに反映
python scripts/maintenance/extract_current_config.py
```

### 変更追跡

```bash
# 変更前後の性能差分を記録
python scripts/benchmark_prediction_system.py --save-baseline
# （フラグ変更後）
python scripts/benchmark_prediction_system.py --compare
python scripts/maintenance/track_performance_change.py --description "変更内容"
```

---

## 4. 関連ファイル

| ファイル | 説明 |
|----------|------|
| [config/feature_flags.py](../../config/feature_flags.py) | フィーチャーフラグ定義 |
| [config/settings.py](../../config/settings.py) | スコアリング重み設定 |
| [scripts/benchmark_prediction_system.py](../../scripts/benchmark_prediction_system.py) | ベンチマークスクリプト |
| [data/benchmark_results/](../../data/benchmark_results/) | ベンチマーク結果保存先 |

---

**自動更新**: `python scripts/maintenance/extract_current_config.py` で最新状態に更新
