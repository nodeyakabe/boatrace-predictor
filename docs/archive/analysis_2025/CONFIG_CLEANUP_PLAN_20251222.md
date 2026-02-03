# 設定ファイル・アーカイブフラグ整理計画

**作成日**: 2025-12-22
**目的**: 不要な設定ファイル・アーカイブフラグを安全に削除し、システムをクリーンに保つ

---

## 📋 目次

1. [アーカイブフラグの整理](#1-アーカイブフラグの整理)
2. [設定ファイルの整理](#2-設定ファイルの整理)
3. [実施計画](#3-実施計画)
4. [バックアップ・ロールバック手順](#4-バックアップロールバック手順)

---

## 1. アーカイブフラグの整理

### 🔴 削除対象フラグ（21個）

すべて `ARCHIVED_FLAGS` に含まれ、検証結果で**効果なし・悪化**が確認済み。

| フラグ名 | 使用箇所 | 検証結果 | 削除可否 |
|---------|---------|---------|---------|
| **beforeinfo_flag_adjustment** | race_predictor.py (1箇所) | **-3.65%悪化** | ✅ 削除可 |
| **hierarchical_before_prediction** | race_predictor.py (1箇所) | **-0.5%悪化** | ✅ 削除可 |
| **normalized_before_integration** | race_predictor.py (1箇所) | **-0.5%悪化** | ✅ 削除可 |
| **dynamic_integration** | - | 逆相関 | ✅ 削除可 |
| **gated_before_integration** | race_predictor.py (1箇所) | 効果なし | ✅ 削除可 |
| **before_safe_integration** | - | 効果なし | ✅ 削除可 |
| **before_safe_st_exhibition** | - | 悪化 | ✅ 削除可 |
| **optimized_pattern_multipliers** | race_predictor.py, pattern_scorer.py | 効果なし | ✅ 削除可 |
| **confidence_refinement** | - | 未実装 | ✅ 削除可 |
| **kelly_betting** | - | 未実装 | ✅ 削除可 |
| **optuna_optimization** | - | 予測時不要 | ✅ 削除可 |
| **auto_buff_learning** | - | 未実装 | ✅ 削除可 |
| **probability_calibration** | - | 未実装 | ✅ 削除可 |
| **venue_specific_models** | - | 未実装 | ✅ 削除可 |
| **shap_explainability** | - | 予測時不要 | ✅ 削除可 |
| **bayesian_hierarchical** | - | 未実装 | ✅ 削除可 |
| **reinforcement_learning** | - | 未実装 | ✅ 削除可 |
| **prediction_engine_v2** | - | 実験的 | ✅ 削除可 |
| **preset_based_adjustment** | - | 実験的 | ✅ 削除可 |
| **adjustment_tracing** | - | 実験的 | ✅ 削除可 |
| **validation_mode** | - | デバッグ用 | ✅ 削除可 |

### 検証結果の根拠

**docs/BEFOREINFO_OPTIMIZATION_ANALYSIS_20251217.md** より:

```
beforeinfo_flag_adjustment: False  # -3.65%悪化
hierarchical_before_prediction: False  # -0.5%悪化
normalized_before_integration: False  # -0.5%悪化
dynamic_integration: False  # 逆相関
gated_before_integration: False  # 効果なし
before_safe_integration: False  # 効果なし
```

**結論**: すべて削除して問題なし。検証結果で明確に悪化または効果なしが確認済み。

---

## 2. 設定ファイルの整理

### 📊 全設定ファイル一覧（17個）

| ファイル名 | サイズ | 使用状況 | 削除可否 | 理由 |
|-----------|-------|---------|---------|------|
| **feature_flags.py** | 18K | ✅ 使用中 | ❌ 保持 | コアシステム |
| **settings.py** | 13K | ✅ 使用中 | ❌ 保持 | コアシステム |
| **model_config.py** | 11K | ✅ 使用中 | ❌ 保持 | モデル設定 |
| **venue_course_win_rates.py** | 21K | ✅ 使用中 | ❌ 保持 | 会場特性 |
| **venue_wind_adjustments.py** | 15K | ✅ 使用中 | ❌ 保持 | 風速補正 |
| **venue_characteristics.py** | 7.8K | ✅ 使用中 | ❌ 保持 | 会場特性 |
| **venue_course_adjustments.py** | 4.8K | ✅ 使用中 | ❌ 保持 | コース調整 |
| **environmental_penalty_rules.yaml** | 9.3K | ✅ 使用中 | ❌ 保持 | 環境ペナルティ |
| **prediction_strategy.yaml** | 3.5K | ✅ 使用中 | ❌ 保持 | 予測戦略 |
| **venue_filter.yaml** | 3.0K | ✅ 使用中 | ❌ 保持 | 会場フィルター |
| **forward_movers.json** | 3.1K | ✅ 使用中 | ❌ 保持 | 前付け常習者（フラグOFFでも定義は保持） |
| **weather_rules.json** | 6.5K | ✅ 使用中 | ❌ 保持 | 天候ルール（WeatherAdjuster使用） |
| **prediction_improvements.json** | 1.6K | ✅ 使用中 | ❌ 保持 | 4モジュールで参照 |
| **monitoring_config.json** | 2.3K | ❓ 要確認 | 🟡 保留 | 使用箇所なし→要確認 |
| **rollout_config.json** | 399B | ✅ 使用中 | ❌ 保持 | gradual_rollout.py使用 |
| **optimized_pattern_multipliers.py** | 2.1K | ❌ フラグOFF | ✅ 削除可 | `optimized_pattern_multipliers: False` |
| **scoring_weights_*.json** (3ファイル) | 計931B | ✅ 使用中 | ❌ 保持 | scoring_config.py使用 |

### 🔴 削除対象ファイル（2個）

#### 1. optimized_pattern_multipliers.py

**理由**:
- フィーチャーフラグ `optimized_pattern_multipliers: False` で無効化
- コード内で3箇所から参照されているが、すべてフラグチェック後のみ使用
- 検証結果: 効果なし

**使用箇所**:
```python
# src/analysis/race_predictor.py
if is_feature_enabled('optimized_pattern_multipliers'):
    multiplier = get_optimized_multiplier(...)

# src/analysis/scorers/pattern_scorer.py
if is_feature_enabled('optimized_pattern_multipliers'):
    multiplier = get_optimized_multiplier(...)
```

**削除手順**:
1. `config/optimized_pattern_multipliers.py` を削除
2. import文を削除（race_predictor.py, pattern_scorer.py）
3. 該当の `if is_feature_enabled('optimized_pattern_multipliers'):` ブロックを削除

#### 2. monitoring_config.json（要確認）

**理由**:
- grep検索で使用箇所が見つからない
- 2.3KBのファイルサイズ

**削除手順**:
1. まず中身を確認
2. 本当に使用されていないことを再確認
3. 使用されていなければ削除

### 🟢 保持すべきファイル（15個）

すべて実際にコード内で使用されていることを確認済み。

---

## 3. 実施計画

### Phase 1: アーカイブフラグの削除（優先度高）

#### Step 1: feature_flags.py の整理

```python
# config/feature_flags.py

# ✅ ARCHIVED_FLAGS 全体を削除
# ❌ 削除前
ARCHIVED_FLAGS = {
    'beforeinfo_flag_adjustment': False,
    ...（21個）
}

# ✅ 削除後
# ARCHIVED_FLAGS は完全削除
```

**影響範囲**: なし（すべて `False` で未使用）

#### Step 2: コード内のアーカイブフラグ参照を削除

**修正対象ファイル**: `src/analysis/race_predictor.py`

```python
# ❌ 削除対象コード
use_flag_adjustment = is_feature_enabled('beforeinfo_flag_adjustment')
use_gated_integration = is_feature_enabled('gated_before_integration')
use_hierarchical_prediction = is_feature_enabled('hierarchical_before_prediction')

if use_flag_adjustment:
    # ... 該当処理ブロック削除

if use_gated_integration:
    # ... 該当処理ブロック削除

if use_hierarchical_prediction:
    # ... 該当処理ブロック削除
```

**工数**: 30分

---

### Phase 2: optimized_pattern_multipliers.py の削除

#### Step 1: import文の削除

**修正対象ファイル**:
- `src/analysis/race_predictor.py`
- `src/analysis/scorers/pattern_scorer.py`

```python
# ❌ 削除
from config.optimized_pattern_multipliers import get_optimized_multiplier
```

#### Step 2: 使用箇所の削除

```python
# ❌ 削除
if is_feature_enabled('optimized_pattern_multipliers'):
    multiplier = get_optimized_multiplier(pattern_name, default_multiplier)
```

#### Step 3: ファイル本体の削除

```bash
rm config/optimized_pattern_multipliers.py
```

#### Step 4: フィーチャーフラグから削除

```python
# config/feature_flags.py
# ❌ 削除
'optimized_pattern_multipliers': False,
```

**工数**: 15分

---

### Phase 3: monitoring_config.json の確認・削除（保留）

#### Step 1: 内容確認

```bash
cat config/monitoring_config.json
```

#### Step 2: 使用箇所の再確認

```bash
grep -r "monitoring_config" . --include="*.py" --include="*.md"
```

#### Step 3: 削除判断

- 使用されていない → 削除
- 使用されている → 保持

**工数**: 10分

---

### Phase 4: 設定ファイル統合（長期タスク）

**現在の問題**:
- `venue_characteristics.py` と `venue_course_win_rates.py` が重複気味
- `venue_wind_adjustments.py` に会場別係数が複数定義されている

**提案**:
1. 会場関連設定を1ファイルに統合（`venue_master_config.py`）
2. スコアリング関連を1ファイルに統合（`scoring_config.py`）

**工数**: 2-3時間（Phase 4は長期タスクとして保留）

---

## 4. バックアップ・ロールバック手順

### 事前バックアップ

```bash
# バックアップディレクトリ作成
mkdir -p backups/config_cleanup_20251222

# 削除対象ファイルのバックアップ
cp config/feature_flags.py backups/config_cleanup_20251222/
cp config/optimized_pattern_multipliers.py backups/config_cleanup_20251222/
cp config/monitoring_config.json backups/config_cleanup_20251222/
cp src/analysis/race_predictor.py backups/config_cleanup_20251222/
cp src/analysis/scorers/pattern_scorer.py backups/config_cleanup_20251222/
```

### ロールバック手順

問題が発生した場合:

```bash
# バックアップから復元
cp backups/config_cleanup_20251222/* config/
cp backups/config_cleanup_20251222/race_predictor.py src/analysis/
cp backups/config_cleanup_20251222/pattern_scorer.py src/analysis/scorers/
```

### 検証手順

削除後の動作確認:

```bash
# 1. 予測スクリプトの動作確認
python scripts/quick_validation_test.py

# 2. バックテストの動作確認
python scripts/backtest_final_strategy_correct.py --limit 100

# 3. UI起動確認
cd ui && python -m streamlit run app.py
```

---

## 📊 削除サマリー

### 削除対象

| カテゴリ | 削除数 | 削減量 |
|---------|-------|--------|
| アーカイブフラグ | 21個 | feature_flags.py内の約50行 |
| 設定ファイル | 1-2個 | 約2-4KB |
| コード参照箇所 | 約10箇所 | 約100行 |

### 期待効果

1. **コード可読性向上**: 使用されていないフラグチェックが削除され、コードが読みやすくなる
2. **保守性向上**: 不要な設定ファイルが減り、どれが本当に使われているか明確になる
3. **混乱防止**: アーカイブフラグが削除され、誤って有効化するリスクがなくなる

### リスク

- **低リスク**: すべて `False` で検証済みのため、削除による影響はほぼゼロ
- **バックアップあり**: 問題発生時は即座にロールバック可能

---

## 🎯 実施スケジュール

### 即座実施（30分）

- [x] バックアップ作成
- [ ] Phase 1: アーカイブフラグ削除（15分）
- [ ] Phase 2: optimized_pattern_multipliers削除（10分）
- [ ] 動作確認（5分）

### 短期（1-2日以内）

- [ ] Phase 3: monitoring_config.json確認・削除（10分）
- [ ] Git commit & push

### 長期（1ヶ月以降）

- [ ] Phase 4: 設定ファイル統合（保留）

---

**次のアクション**: Phase 1からの実施承認を待つ

