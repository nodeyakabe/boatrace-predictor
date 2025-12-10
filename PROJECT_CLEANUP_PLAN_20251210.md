# プロジェクト整理計画

**作成日**: 2025年12月10日
**目的**: スクリプトとドキュメントの過剰な蓄積を整理し、プロジェクトの見通しを改善

---

## 📊 現状分析サマリー

### 現在のファイル数

| カテゴリ | ファイル数 | 主な問題 |
|---------|----------|---------|
| **Pythonスクリプト** | **132個** | 重複・古いバージョン多数 |
| **Markdownドキュメント** | **352個** | 作業ログの蓄積、重複ガイド |
| - ルートディレクトリ | 164個 | 73%がアーカイブ可能 |
| - docs/ | 94個 | 古い作業ログ多数 |
| - docs/archive/ | 31個 | ✅ 既に整理済み |

### 整理の必要性

1. **ルートディレクトリの肥大化**: 164個のMDファイルは多すぎて管理困難
2. **スクリプトの重複**: 類似機能のスクリプトが複数存在（例: backtest_final_strategy × 3バージョン）
3. **古い作業ログの蓄積**: 2025年11月の作業ログが60件以上残存
4. **必要なファイルの埋没**: 重要なREADME.mdや残タスク一覧.mdが見つけにくい

---

## 🎯 整理の目標

### 削減目標

| カテゴリ | 現在 | 目標 | 削減数 | 削減率 |
|---------|------|------|--------|--------|
| **Pythonスクリプト** | 132 | **40-50** | 82-92 | **62-70%** |
| **ルートMD** | 164 | **15** | 149 | **91%** |
| **docs/MD** | 94 | **20-25** | 69-74 | **73-79%** |
| **合計MD** | 352 | **66-71** | 281-286 | **80-81%** |

### 整理後のディレクトリ構造（予定）

```
BoatRace_package_20251115_172032/
├── README.md                        # プロジェクト概要
├── START_HERE.md                    # 作業開始時の必読
├── CLAUDE.md                        # AI設定
├── DOCS_INDEX.md                    # ドキュメント索引
├──
├── scripts/                         # 40-50個（現役スクリプトのみ）
│   ├── data_collection/            # データ収集（4個）
│   ├── model_training/             # モデル学習（2個）
│   ├── backtest/                   # バックテスト（10個）
│   ├── prediction/                 # 予測生成（2個）
│   ├── analysis/                   # 分析（10-15個、最重要のみ）
│   └── utils/                      # ユーティリティ（8個）
│
├── scripts_archive/                # 古いスクリプト
│   ├── analyze_archived/           # 分析スクリプト（50個）
│   ├── backtest_archived/          # 古いバックテスト（12個）
│   ├── test_debug_archived/        # テスト・デバッグ（15個）
│   └── duplicate_archived/         # 重複スクリプト（15個）
│
├── docs/                           # 20-25個（有効ドキュメントのみ）
│   ├── 残タスク一覧.md
│   ├── betting_implementation_status.md
│   ├── QUICKSTART.md
│   ├── DATABASE_SCHEMA.md
│   └── ...
│
└── docs/archive/                   # アーカイブ
    ├── archive_2025_11_work_logs/  # 作業ログ（60件）
    ├── archive_2025_11_reports/    # レポート（30件）
    ├── archive_2025_11_13/         # ✅ 既存
    ├── archive_quickstart_duplicates/ # ✅ 既存
    ├── archive_experiments/        # ✅ 既存
    ├── archive_old_reports/        # ✅ 既存
    └── archive_old_guides/         # 古いガイド（30件）
```

---

## 📋 Phase 1: スクリプト整理（優先度: 🔴 高）

### 1-1. 削除推奨スクリプト（29個）

#### 空ファイル・特定月専用（6個）

```bash
scripts/generate_october_predictions.py         # 空ファイル
scripts/generate_november_predictions.py        # 特定月専用
scripts/compare_november_predictions.py         # 特定月専用
scripts/backtest_november_strategy.py           # 特定月専用
scripts/november_backtest_detailed.py           # 特定月専用
scripts/november_backtest_ui_strategy.py        # 特定月専用
```

**アクション**: 削除（backupディレクトリに移動後）

#### 明らかな重複（8個）

```bash
# 最終戦略バックテスト重複（正確版を残す）
scripts/backtest_final_strategy.py             # 削除候補
scripts/backtest_final_strategy_historical.py  # 削除候補
# → backtest_final_strategy_correct.py を残す

# イン強会場バックテスト重複
scripts/backtest_high_in_venues_no_filter.py   # 削除候補
# → backtest_high_in_venues.py を残す

# 信頼度B分析重複（v2を残す）
scripts/analyze_confidence_b.py                # 削除候補
scripts/analyze_confidence_b_comprehensive.py  # 削除候補
scripts/analyze_confidence_b_detail.py         # 削除候補
scripts/analyze_confidence_b_from_csv.py       # 削除候補
# → analyze_confidence_b_v2.py を残す

# 予測生成重複（並列版を残す）
scripts/generate_predictions_batch.py          # 削除候補
# → regenerate_predictions_2025_parallel.py を残す
```

**アクション**: scripts_archive/duplicate_archived/ に移動

#### デバッグ・テスト用（15個）

```bash
scripts/debug_final_strategy.py
scripts/debug_high_in_venues.py
scripts/test_evaluator.py
scripts/test_flag_adjuster.py
scripts/test_phase_integration.py
scripts/test_confidence_specific_hybrid.py
scripts/test_hybrid_scoring_confidence_b.py
scripts/test_top3_scoring.py
scripts/quick_test.py
scripts/quick_test_hybrid.py
scripts/quick_test_v2_model.py
scripts/test_prediction_types.py
scripts/migrate_prediction_unique_constraint.py  # マイグレーション完了後
scripts/night_auto_collection.py                # 自動化設定後
scripts/ev_bet_tool.py                           # 機能統合済み
```

**アクション**: scripts_archive/test_debug_archived/ に移動

---

### 1-2. アーカイブ推奨スクリプト（53個）

#### 分析スクリプト（50個）

以下のパターンをすべて scripts_archive/analyze_archived/ に移動:

```bash
# 信頼度B関連（5個、v2を除く）
scripts/check_confidence_b.py
scripts/show_confidence_b_summary.py
scripts/analyze_confidence_c_conditions.py
scripts/analyze_confidence_issues.py
scripts/confidence_c_conditions.py

# BEFORE情報関連（8個）
scripts/analyze_before_element_correlation.py
scripts/analyze_before_rank_bonus.py
scripts/analyze_beforeinfo_comprehensive.py
scripts/analyze_beforeinfo_correlation.py
scripts/analyze_beforeinfo_correlation_lite.py
scripts/check_beforeinfo_status.py
scripts/analyze_pre_before_correlation.py
scripts/validate_before_patterns.py

# パターン抽出（3個）
scripts/extract_before_patterns.py
scripts/extract_2nd_3rd_presets.py
scripts/extract_environmental_presets.py

# 年度別・期間別（7個）
scripts/analyze_2024_performance.py
scripts/analyze_2025_fast.py
scripts/analyze_2025_full_year.py
scripts/analyze_2025_with_bet_filter.py
scripts/monthly_performance_analysis.py
scripts/analyze_monthly_and_confidence_b.py
scripts/analyze_changed_races.py

# その他分析（27個）
scripts/analyze_all_confidence_levels.py
scripts/analyze_entry_change_impact.py
scripts/analyze_hit_races.py
scripts/analyze_pattern_application.py
scripts/analyze_phases_detail.py
scripts/analyze_rank23_accuracy.py
scripts/analyze_top3_coverage.py
scripts/analyze_venue_patterns.py
scripts/check_db_basic.py
scripts/check_db_structure.py
scripts/compare_before_after_hybrid.py
scripts/compare_prediction_methods.py
scripts/compare_strategy_vs_current.py
scripts/discover_high_roi_conditions.py
scripts/evaluate_conditional_v1_comprehensive.py
scripts/evaluate_top3_scoring_confidence_b.py
scripts/evaluate_unused_6_conditions.py
scripts/evaluate_v2_performance.py
scripts/find_improvement_opportunities.py
scripts/quick_condition_scan.py
scripts/verify_st_correlation.py
scripts/validate_flag_adjustment.py
scripts/validate_gated_integration.py
scripts/validate_hierarchical_prediction.py
scripts/validate_normalized_integration.py
scripts/validate_stage2_training_data.py
scripts/clean_hybrid_evaluation.py
scripts/comprehensive_hybrid_evaluation.py
```

**アクション**: 一括でscripts_archive/analyze_archived/ に移動

#### バックテストスクリプト（12個）

以下をscripts_archive/backtest_archived/ に移動:

```bash
# 11月関連（既に削除推奨に含まれる）
# その他古いバックテスト
scripts/backtest_combined_strategy.py
scripts/backtest_exacta_only_optimized.py
scripts/backtest_exacta_optimized.py
scripts/backtest_integrated_strategy.py
scripts/backtest_multi_month.py
scripts/backtest_optimized_v2.py
scripts/backtest_strategy.py
scripts/backtest_v1_moderate.py
scripts/backtest_conditional_models_v2.py  # 新しいモデル学習後は不要
scripts/comprehensive_backtest_correct.py
scripts/comprehensive_backtest_v1_v2.py
scripts/comprehensive_strategy_analysis.py
```

**アクション**: scripts_archive/backtest_archived/ に移動

---

### 1-3. 残すスクリプト（40-50個）

#### データ収集系（4個）

```bash
scripts/bulk_missing_data_fetch_parallel.py      # ✅ README推奨
scripts/background_data_collection.py            # ✅ 現役
scripts/background_today_prediction.py           # ✅ 現役
scripts/collect_parts_exchange.py                # ✅ 現役
```

#### モデル学習系（2個）

```bash
scripts/train_all_models.py                      # ✅ 現役
scripts/retrain_conditional_models_v2.py         # ✅ 現役
```

#### バックテスト系（10個）

```bash
scripts/backtest_v2_edge_test.py                 # ✅ 残タスク最優先
scripts/backtest_all_modes.py                    # ✅ 残タスク最優先
scripts/backtest_v2_venue_test.py                # ✅ 残タスクPhase B
scripts/backtest_v2_strategy.py                  # ✅ 現役
scripts/validate_strategy_a.py                   # ✅ 戦略A検証
scripts/backtest_final_strategy_correct.py       # ✅ 正確な払戻版
scripts/backtest_high_in_venues.py               # ✅ イン強会場
scripts/walkforward_backtest.py                  # ✅ ウォークフォワード
scripts/optimize_betting_strategy.py             # ✅ 現役
scripts/monitor_live_performance.py              # ✅ 現役
```

#### 予測生成系（2個）

```bash
scripts/regenerate_predictions_2025_parallel.py  # ✅ 最新並列版
scripts/regenerate_predictions_2025.py           # ✅ 通常版
```

#### データベース管理系（3個）

```bash
scripts/add_attack_pattern_indexes.py            # ✅ DB最適化
scripts/generate_db_documentation.py             # ✅ 現役
scripts/verify_db_documentation.py               # ✅ 現役
```

#### 分析スクリプト（10-15個、最重要のみ）

```bash
scripts/analyze_confidence_b_v2.py               # ✅ 最新v2版
scripts/backup_old_predictions.py                # ✅ ユーティリティ
scripts/fast_prediction_generator.py             # ✅ 高速生成
scripts/generate_predictions_parallel.py         # ✅ 汎用並列版

# オッズ関連（3個）
scripts/fetch_exacta_odds.py
scripts/fetch_historical_odds.py
scripts/fetch_odds_fast.py
scripts/update_historical_odds.py

# UI・調査（3個）
scripts/ui_workflow_simulation.py
scripts/investigate_tide_tables.py
scripts/investigate_ui_components.py
```

#### ユーティリティ系（8個）

```bash
scripts/worker_tenji_collection.py               # ✅ 現役
scripts/worker_missing_data.py                   # ✅ 現役
scripts/update_racer_master.py                   # ✅ 現役
scripts/create_performance_indexes.py            # ✅ 現役
scripts/cleanup_unused_ui_components.py
scripts/patch_extended_scorer_cache.py
scripts/simplify_extended_scorer.py
scripts/train_optimized_models.py
```

---

## 📋 Phase 2: ドキュメント整理（優先度: 🔴 高）

### 2-1. ルートディレクトリの整理

#### 残すべきドキュメント（15個）

**必須（9個）**:
```
START_HERE.md                    # 作業開始時の必読
CLAUDE.md                        # AI設定
README.md                        # プロジェクト概要
DOCS_INDEX.md                    # ドキュメント索引
SYSTEM_CONSTRAINTS.md            # システム制約
WORK_CHECKLIST.md                # 作業前チェックリスト
TESTING_GUIDE.md                 # テストガイド
QUALITY_ASSURANCE.md             # 品質保証
SYSTEM_LOGIC_ANALYSIS.md         # システムロジック分析
```

**ガイド（4個）**:
```
README_SCRIPTS.md                # スクリプト使い方
SCRIPTS_GUIDE.md                 # 並列化版ガイド
GIT_SETUP_GUIDE.md               # Git設定
UI起動ガイド.md                  # UI起動
```

**仕様・参考（2個）**:
```
boatrace_predictor_spec.md       # 予測システム仕様
SAFE_SCRAPING_GUIDELINES.md      # スクレイピング安全ガイド
```

---

#### アーカイブ対象（約149個）

##### カテゴリA: 作業ログ・セッションレポート（約60件）

→ **docs/archive/archive_2025_11_work_logs/** に移動

```bash
# WORK系（13件）
*WORK_SUMMARY*.md
WORK_CHECKLIST*.md（古いバージョン）
WORKFLOW_*.md

# SESSION系（13件）
*SESSION*.md
CURRENT_SESSION*.md
SESSION_COMPLETION_REPORT.md
SESSION_FINAL_REPORT.md

# 復元作業（7件）
復元*.md
機能比較レポート*.md
欠落機能と復元計画.md
PROJECT_BUG_REPORT_20251113.md
CRITICAL_DISCOVERY_20251113.md
EXECUTION_SUMMARY_20251113.md

# その他作業ログ（27件）
HANDOVER_REPORT*.md
CORRECTED_WORK_REPORT*.md
TEST_COMPLETION_REPORT*.md
DATA_COLLECTION_ISSUES.md
COLLECTION_STATUS_REPORT.md
...
```

##### カテゴリB: 古い実装・改善レポート（約40件）

→ **docs/archive/archive_old_reports/** に移動

```bash
# IMPLEMENTATION系（6件）
IMPLEMENTATION_GUIDE.md
IMPLEMENTATION_SUMMARY*.md
FINAL_IMPLEMENTATION_*.md
IMPROVEMENT_IMPLEMENTATION_SUMMARY.md

# IMPROVEMENT系（13件）
IMPROVEMENT_PLAN*.md
IMPROVEMENTS*.md
FUTURE_IMPROVEMENTS_ANALYSIS.md
IMPROVEMENT_ROADMAP.md
改善点_1118.md（古いバージョン）

# SUMMARY/REPORT系（21件）
FINAL_COMPREHENSIVE_REPORT.md
IMPROVEMENTS_COMPREHENSIVE_REPORT.md
FINAL_SUMMARY_REPORT.md
ULTIMATE_SUMMARY_REPORT.md
COMPREHENSIVE_*.md
BACKTEST_COMPARISON_REPORT.md
CODE_ANALYSIS_REPORT.md
EFFICIENCY_*.md
ANALYSIS_MODULE_GUIDE.md
...
```

##### カテゴリC: 重複ガイド（約10件）

→ **docs/archive/archive_quickstart_duplicates/** に移動（一部は既存）

```bash
# QUICK_START系（4件、ルート）
QUICK_START.md
QUICK_START_GUIDE.md
README_QUICK_START.md
NEXT_SESSION_QUICKSTART.md

# DATA_COLLECTION系（3件、統合済み）
DATA_COLLECTION_GUIDE.md
DATA_FILLING_GUIDE.md
COMPREHENSIVE_DATA_COLLECTION_README.md

# その他重複（3件）
DAILY_COLLECTION_SETUP.md
DEPLOYMENT_PLAN_V3.md
BOTTLENECK_ANALYSIS_AND_IMPROVEMENTS.md
```

##### カテゴリD: 実験レポート（8件）

→ **docs/archive/archive_experiments/** に移動（一部は既存）

```bash
EXPERIMENT_004_REPORT.md
EXPERIMENT_005_REPORT.md
EXPERIMENT_006_REPORT.md
EXPERIMENT_007_REPORT.md
EXPERIMENT_009B_REPORT.md
EXPERIMENTS_FINAL_REPORT.md
EXPERIMENTS_SUMMARY_REPORT.md
```

##### カテゴリE: その他古いドキュメント（約30件）

→ **docs/archive/archive_old_guides/** に移動

```bash
# 古いステータスレポート
PROJECT_STATUS_AND_NEXT_STEPS.md
SYSTEM_OVERVIEW_FINAL.md
CURRENT_STATUS*.md

# 古いガイド
ALTERNATIVE_DATA_SOURCES.md
DATA_RETENTION_DISCOVERY.md
DOWNLOAD_SOLUTION_SUMMARY.md
ERROR_HANDLING_IMPROVEMENT.md
EXCEPTION_HANDLING_IMPROVEMENTS.md

# 古い仕様書
RACER_ANALYSIS_DESIGN.md
API_STRUCTURE.md
REFERENCE_SITES_ANALYSIS.md
database_migration_strategy.md
dual_pc_setup.md

# その他
RESTART_HANDOVER.md
IMPORTANT_KNOW_HOW.md
CLEANUP_PLAN_20251118.md
CLEANUP_REPORT.md
...
```

---

### 2-2. docs/ディレクトリの整理

#### 残すべきドキュメント（20-25個）

**タスク管理（3個）**:
```
docs/残タスク一覧.md
docs/betting_implementation_status.md
docs/current_implementation_status.md
```

**最新分析・レポート（6個、2025-12月）**:
```
docs/confidence_b_analysis_20241209.md
docs/opus_upset_analysis_20251208.md
docs/confidence_analysis_report_20251208.md
docs/DATABASE_SCHEMA.md
docs/DB_VERIFICATION_REPORT.md
docs/hybrid_scoring_implementation.md
```

**ガイド・仕様（8個）**:
```
docs/QUICKSTART.md
docs/betting_system_improvement_plan.md
docs/model_training_guide.md (あれば)
docs/backtest_guide.md (あれば)
docs/prediction_logic_summary.md
docs/v2_implementation_complete.md
docs/model_comparison_v1_vs_v2.md
docs/rank23_prediction_issue_analysis.md
```

**技術ドキュメント（3個）**:
```
docs/new_features_proposal.md
docs/improvement_tasks.md
docs/improvements_summary.md
```

---

#### アーカイブ対象（約70件）

##### 作業ログ（約20件）

→ **docs/archive/archive_2025_11_work_logs/** に移動

```bash
docs/work_summary_2025*.md（全て）
docs/20251*_作業ログ.md（全て）
docs/20251126_スコアリング改善_中間報告.md
docs/20251127_買い目戦略検討.md
docs/model_bias_analysis_20251118.md
docs/technical_insights_20251119.md
docs/プロジェクト全体レビュー_20251118.md
```

##### 古い実装レポート（約15件）

→ **docs/archive/archive_old_reports/** に移動

```bash
docs/IMPLEMENTATION_SUMMARY.md
docs/implementation_summary_20251128.md
docs/implementation_verification_report.md
docs/improvement_implementation_report.md
docs/improvement_implementation_plan.md
docs/phase1_completion_report.md
docs/phase1-3_complete_report.md
docs/phase1-3_implementation_complete.md
docs/COMPLETION_REPORT.md
docs/TEST_RESULTS.md
```

##### その他古いドキュメント（約35件）

→ **docs/archive/archive_old_guides/** に移動

```bash
docs/odds_scraping_guide.md
docs/kimarite_prediction_system.md
docs/model_experiments.md
docs/PREDICTION_LOGIC_INSIGHTS.md
docs/VENUE_RACER_CHARACTERISTICS.md
docs/reprediction_setup_guide.md
docs/ui_improvements_guide.md
docs/オリジナル展示データ利用可能期間_調査報告.md
...
```

---

### 2-3. 改善点/ディレクトリの整理

#### 残すべきドキュメント（3個、最新のみ）

```
改善点/BEFOREパターン抽出検証_総合レポート_20251209.md
改善点/直前情報の活用方法_再整理_20251209.md
改善点/BEFORE統合検証結果まとめ_20251209.md
```

#### アーカイブ対象

古いバージョン（改善点_1118.md など）を docs/archive/archive_old_reports/ に移動

---

## 🛠️ 実行手順

### Step 1: バックアップの作成（必須）

```bash
# プロジェクト全体のバックアップ
mkdir -p backups/cleanup_20251210
cp -r scripts backups/cleanup_20251210/
cp -r docs backups/cleanup_20251210/
cp *.md backups/cleanup_20251210/

# Git コミット（念のため）
git add .
git commit -m "Backup before cleanup: 2025-12-10"
```

---

### Step 2: アーカイブディレクトリの作成

```bash
# スクリプトアーカイブ
mkdir -p scripts_archive/analyze_archived
mkdir -p scripts_archive/backtest_archived
mkdir -p scripts_archive/test_debug_archived
mkdir -p scripts_archive/duplicate_archived

# ドキュメントアーカイブ
mkdir -p docs/archive/archive_2025_11_work_logs
mkdir -p docs/archive/archive_2025_11_reports
mkdir -p docs/archive/archive_old_guides
```

---

### Step 3: スクリプトの整理実行

#### 3-1. 空ファイル・特定月専用を削除

```bash
# バックアップに移動後、削除
mv scripts/generate_october_predictions.py scripts_archive/duplicate_archived/
mv scripts/generate_november_predictions.py scripts_archive/duplicate_archived/
mv scripts/compare_november_predictions.py scripts_archive/duplicate_archived/
mv scripts/backtest_november_strategy.py scripts_archive/duplicate_archived/
mv scripts/november_backtest_detailed.py scripts_archive/duplicate_archived/
mv scripts/november_backtest_ui_strategy.py scripts_archive/duplicate_archived/
```

#### 3-2. 重複スクリプトをアーカイブ

```bash
# 最終戦略重複
mv scripts/backtest_final_strategy.py scripts_archive/duplicate_archived/
mv scripts/backtest_final_strategy_historical.py scripts_archive/duplicate_archived/

# イン強会場重複
mv scripts/backtest_high_in_venues_no_filter.py scripts_archive/duplicate_archived/

# 信頼度B重複
mv scripts/analyze_confidence_b.py scripts_archive/duplicate_archived/
mv scripts/analyze_confidence_b_comprehensive.py scripts_archive/duplicate_archived/
mv scripts/analyze_confidence_b_detail.py scripts_archive/duplicate_archived/
mv scripts/analyze_confidence_b_from_csv.py scripts_archive/duplicate_archived/

# 予測生成重複
mv scripts/generate_predictions_batch.py scripts_archive/duplicate_archived/
```

#### 3-3. デバッグ・テスト用をアーカイブ

```bash
mv scripts/debug_*.py scripts_archive/test_debug_archived/
mv scripts/test_*.py scripts_archive/test_debug_archived/
mv scripts/quick_test*.py scripts_archive/test_debug_archived/
mv scripts/migrate_prediction_unique_constraint.py scripts_archive/test_debug_archived/
mv scripts/night_auto_collection.py scripts_archive/test_debug_archived/
mv scripts/ev_bet_tool.py scripts_archive/test_debug_archived/
```

#### 3-4. 分析スクリプトを一括アーカイブ

```bash
# 信頼度B関連
mv scripts/check_confidence_b.py scripts_archive/analyze_archived/
mv scripts/show_confidence_b_summary.py scripts_archive/analyze_archived/
mv scripts/analyze_confidence_c_conditions.py scripts_archive/analyze_archived/
mv scripts/analyze_confidence_issues.py scripts_archive/analyze_archived/
mv scripts/confidence_c_conditions.py scripts_archive/analyze_archived/

# BEFORE情報関連
mv scripts/analyze_before_*.py scripts_archive/analyze_archived/
mv scripts/analyze_beforeinfo_*.py scripts_archive/analyze_archived/
mv scripts/check_beforeinfo_status.py scripts_archive/analyze_archived/
mv scripts/validate_before_patterns.py scripts_archive/analyze_archived/

# パターン抽出
mv scripts/extract_*.py scripts_archive/analyze_archived/

# 年度別・期間別
mv scripts/analyze_2024_performance.py scripts_archive/analyze_archived/
mv scripts/analyze_2025_*.py scripts_archive/analyze_archived/
mv scripts/monthly_performance_analysis.py scripts_archive/analyze_archived/
mv scripts/analyze_changed_races.py scripts_archive/analyze_archived/

# その他分析（残りのanalyze_*, compare_*, evaluate_*, validate_*）
mv scripts/analyze_*.py scripts_archive/analyze_archived/
mv scripts/compare_*.py scripts_archive/analyze_archived/
mv scripts/evaluate_*.py scripts_archive/analyze_archived/
mv scripts/validate_*.py scripts_archive/analyze_archived/
mv scripts/check_db_*.py scripts_archive/analyze_archived/
mv scripts/verify_st_correlation.py scripts_archive/analyze_archived/
mv scripts/discover_high_roi_conditions.py scripts_archive/analyze_archived/
mv scripts/find_improvement_opportunities.py scripts_archive/analyze_archived/
mv scripts/quick_condition_scan.py scripts_archive/analyze_archived/
mv scripts/clean_hybrid_evaluation.py scripts_archive/analyze_archived/
mv scripts/comprehensive_hybrid_evaluation.py scripts_archive/analyze_archived/
```

#### 3-5. 古いバックテストをアーカイブ

```bash
mv scripts/backtest_combined_strategy.py scripts_archive/backtest_archived/
mv scripts/backtest_exacta_*.py scripts_archive/backtest_archived/
mv scripts/backtest_integrated_strategy.py scripts_archive/backtest_archived/
mv scripts/backtest_multi_month.py scripts_archive/backtest_archived/
mv scripts/backtest_optimized_v2.py scripts_archive/backtest_archived/
mv scripts/backtest_strategy.py scripts_archive/backtest_archived/
mv scripts/backtest_v1_moderate.py scripts_archive/backtest_archived/
mv scripts/backtest_conditional_models_v2.py scripts_archive/backtest_archived/
mv scripts/comprehensive_backtest_*.py scripts_archive/backtest_archived/
mv scripts/comprehensive_strategy_analysis.py scripts_archive/backtest_archived/
```

---

### Step 4: ドキュメントの整理実行

#### 4-1. ルートディレクトリの整理

```bash
# 作業ログ・セッションレポート
mv *WORK*.md docs/archive/archive_2025_11_work_logs/
mv *SESSION*.md docs/archive/archive_2025_11_work_logs/
mv 復元*.md docs/archive/archive_2025_11_work_logs/
mv 機能比較*.md docs/archive/archive_2025_11_work_logs/
mv 欠落*.md docs/archive/archive_2025_11_work_logs/
mv *20251113*.md docs/archive/archive_2025_11_work_logs/
mv HANDOVER_REPORT*.md docs/archive/archive_2025_11_work_logs/
mv CORRECTED_WORK_REPORT*.md docs/archive/archive_2025_11_work_logs/
mv EXECUTION_SUMMARY*.md docs/archive/archive_2025_11_work_logs/

# 古い実装・改善レポート
mv IMPLEMENTATION_*.md docs/archive/archive_old_reports/
mv IMPROVEMENT_*.md docs/archive/archive_old_reports/
mv FINAL_*.md docs/archive/archive_old_reports/
mv ULTIMATE_*.md docs/archive/archive_old_reports/
mv COMPREHENSIVE_*.md docs/archive/archive_old_reports/
mv *REPORT*.md docs/archive/archive_old_reports/  # 必須以外
mv *SUMMARY*.md docs/archive/archive_old_reports/  # 必須以外

# 重複ガイド
mv QUICK_START*.md docs/archive/archive_quickstart_duplicates/
mv README_QUICK_START.md docs/archive/archive_quickstart_duplicates/
mv NEXT_SESSION_QUICKSTART.md docs/archive/archive_quickstart_duplicates/
mv DATA_COLLECTION_GUIDE.md docs/archive/archive_old_guides/
mv DATA_FILLING_GUIDE.md docs/archive/archive_old_guides/
mv COMPREHENSIVE_DATA_COLLECTION_README.md docs/archive/archive_old_guides/
mv DAILY_COLLECTION_SETUP.md docs/archive/archive_old_guides/

# 実験レポート
mv EXPERIMENT_*.md docs/archive/archive_experiments/

# その他古いドキュメント
mv PROJECT_STATUS_AND_NEXT_STEPS.md docs/archive/archive_old_guides/
mv SYSTEM_OVERVIEW_FINAL.md docs/archive/archive_old_guides/
mv ALTERNATIVE_DATA_SOURCES.md docs/archive/archive_old_guides/
mv DATA_RETENTION_DISCOVERY.md docs/archive/archive_old_guides/
mv RACER_ANALYSIS_DESIGN.md docs/archive/archive_old_guides/
mv API_STRUCTURE.md docs/archive/archive_old_guides/
mv database_migration_strategy.md docs/archive/archive_old_guides/
mv dual_pc_setup.md docs/archive/archive_old_guides/
mv RESTART_HANDOVER.md docs/archive/archive_old_guides/
mv IMPORTANT_KNOW_HOW.md docs/archive/archive_old_guides/
mv CLEANUP_PLAN_20251118.md docs/archive/archive_old_guides/
mv CLEANUP_REPORT.md docs/archive/archive_old_guides/
```

#### 4-2. docs/ディレクトリの整理

```bash
# 作業ログ
mv docs/work_summary_*.md docs/archive/archive_2025_11_work_logs/
mv docs/20251*_作業ログ.md docs/archive/archive_2025_11_work_logs/
mv docs/20251*_スコアリング*.md docs/archive/archive_2025_11_work_logs/
mv docs/20251*_買い目*.md docs/archive/archive_2025_11_work_logs/
mv docs/model_bias_analysis_*.md docs/archive/archive_2025_11_work_logs/
mv docs/technical_insights_*.md docs/archive/archive_2025_11_work_logs/
mv docs/プロジェクト全体レビュー_*.md docs/archive/archive_2025_11_work_logs/

# 古い実装レポート
mv docs/IMPLEMENTATION_SUMMARY.md docs/archive/archive_old_reports/
mv docs/implementation_*.md docs/archive/archive_old_reports/
mv docs/improvement_implementation_*.md docs/archive/archive_old_reports/
mv docs/phase*.md docs/archive/archive_old_reports/
mv docs/COMPLETION_REPORT.md docs/archive/archive_old_reports/
mv docs/TEST_RESULTS.md docs/archive/archive_old_reports/

# その他古いドキュメント
mv docs/odds_scraping_guide.md docs/archive/archive_old_guides/
mv docs/kimarite_prediction_system.md docs/archive/archive_old_guides/
mv docs/model_experiments.md docs/archive/archive_old_guides/
mv docs/PREDICTION_LOGIC_INSIGHTS.md docs/archive/archive_old_guides/
mv docs/VENUE_RACER_CHARACTERISTICS.md docs/archive/archive_old_guides/
mv docs/reprediction_setup_guide.md docs/archive/archive_old_guides/
mv docs/ui_improvements_guide.md docs/archive/archive_old_guides/
mv docs/オリジナル展示*.md docs/archive/archive_old_guides/
```

---

### Step 5: 検証

```bash
# スクリプト数の確認
echo "現在のスクリプト数:"
ls -1 scripts/*.py | wc -l
echo "アーカイブされたスクリプト数:"
find scripts_archive -name "*.py" | wc -l

# ドキュメント数の確認
echo "ルートディレクトリのMD数:"
ls -1 *.md | wc -l
echo "docs/のMD数:"
ls -1 docs/*.md | wc -l
echo "アーカイブされたMD数:"
find docs/archive -name "*.md" | wc -l
```

---

### Step 6: DOCS_INDEX.mdの更新

整理後、DOCS_INDEX.mdを更新して最新のドキュメント構造を反映します。

---

## ⚠️ 注意事項

### 安全対策

1. **必ずバックアップを取る**: Step 1を実行してから整理を開始
2. **段階的に実行**: 一度にすべて実行せず、カテゴリごとに確認しながら進める
3. **削除前に確認**: 削除推奨のスクリプトも一旦アーカイブに移動し、1週間問題なければ削除
4. **Gitコミット**: 各ステップ後にコミットして、ロールバック可能にする

### 確認ポイント

- [ ] バックアップが正常に作成されたか
- [ ] 必須ドキュメント（START_HERE.md, README.md, CLAUDE.md）が残っているか
- [ ] 現役スクリプト（残タスク一覧.md記載）が残っているか
- [ ] アーカイブディレクトリが正しく作成されたか
- [ ] 移動後のファイルパスが正しいか

---

## 📊 期待される効果

### ファイル数の削減

| カテゴリ | 削減前 | 削減後 | 削減率 |
|---------|--------|--------|--------|
| scripts/ | 132 | 40-50 | 62-70% |
| ルートMD | 164 | 15 | 91% |
| docs/MD | 94 | 20-25 | 73-79% |

### プロジェクトの見通し改善

- ✅ 必要なドキュメントが見つけやすくなる
- ✅ スクリプトの役割が明確になる
- ✅ 新しいメンバーの理解が容易になる
- ✅ メンテナンス性が向上する

---

## 📝 整理後のメンテナンス

### 定期的な整理ルール

1. **月次**: 作業ログをarchiveに移動（翌月初旬）
2. **四半期**: 使用していないスクリプトをarchiveに移動
3. **半年**: archive内の不要ファイルを削除

### 新規ファイル作成時のルール

1. **スクリプト**: 既存の類似スクリプトがないか確認
2. **ドキュメント**: DOCS_INDEX.mdに登録
3. **作業ログ**: 日付を含めたファイル名にする（YYYYMMDD形式）

---

**作成者**: Claude Code
**最終更新**: 2025年12月10日
**関連ドキュメント**: DOCS_INDEX.md, README.md, START_HERE.md
