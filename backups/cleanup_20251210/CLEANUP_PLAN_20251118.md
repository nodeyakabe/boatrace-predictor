# プロジェクトクリーンアップ計画 - 2025年11月18日

## 現状

- **Pythonファイル**: 233個
- **Markdownファイル**: 153個
- **問題**: 古いスクリプト・ドキュメントが大量に残存

---

## クリーンアップ方針

### 基本原則
1. **削除しない** - すべてarchiveフォルダに移動
2. **慎重に選別** - 本当に使用中のもののみ残す
3. **ドキュメント作成** - 何を残したか明記

---

## Phase 1: アーカイブ対象の特定

### 移動対象スクリプト（test/debug/check系）

#### test_*.py (テストスクリプト)
```
test_補完_決まり手_改善版.py
test_収集_RDMDB潮位_改善版.py
test_潮位イベント抽出.py
test_潮位イベント抽出v2.py
test_潮位イベント抽出v3.py
test_kimarite_fix.py
test_historical_data_access.py
test_single_race.py
test_scraper.py
test_improved_scraper.py
test_improved_simple.py
test_basic_scraper.py
test_v4_scraper.py
test_v4_multiple_races.py
test_odds_fetcher.py
test_new_modules.py
test_racer_features.py
test_dataset_with_racer_features.py
※ 例外: 最近作成した test_original_tenji_data.py, test_beforeinfo_direct.py は残す
```

#### check_*.py (確認スクリプト)
```
check_all_data_completeness.py
check_cancelled_races.py
check_collection_progress.py
check_collection_status.py
check_columns.py
check_data_dates.py
check_data_progress.py
check_db_20251113.py
check_db_20251113_final.py
check_db_20251113_v2.py
check_db_quick.py
check_db_schema.py
check_db_schema_v2.py
check_db_structure.py
check_db_tables.py
check_missing_data.py
check_missing_data_simple.py
check_missing_final.py
check_missing_correct.py
check_monthly_data.py
check_pit3_pattern.py
check_progress.py
check_recent_st.py
check_settings.py
check_st_coverage.py
check_system_status.py
check_venues.py
check_venue_count.py
check_weather_data.py
check_yesterday_st.py
※ 例外: check_db_status.py は残す（汎用的に使用）
```

#### debug_*.py, analyze_*.py, verify_*.py, monitor_*.py
```
debug_odds_fetch.py
debug_race_result.py
debug_table_structure.py
analyze_* (12個程度)
verify_*.py
monitor_*.py
count_*.py
measure_*.py
※ 例外: analyze_model_bias.py は残す（最近作成、重要）
```

### 移動対象スクリプト（古い補完・収集系）

#### 補完_*.py（古いバージョン）
```
補完_風向データ.py → 改善版あり
補完_風向データ_全件.py → 改善版あり
補完_風向データ_全件_自動.py → 改善版あり
補完_展示タイム_全件_自動.py → 並列版あり
補完_展示タイム_全件_高速化.py → 並列版あり
補完_払戻金データ.py → 古い
補完_決まり手データ_改善版.py → 古い
※ 残すもの:
- 補完_race_details_INSERT対応_高速版.py （最新・推奨）
- 補完_風向データ_改善版.py
- 補完_天候データ_改善版.py
- 補完_レース詳細データ_改善版v4.py
```

#### 収集_*.py（古いバージョン）
```
収集_オリジナル展示_最新.py → 日付指定版あり
収集_潮位データ_最新.py → 古い
収集_2020年潮位データ.py → 古い
※ 残すもの:
- 収集_オリジナル展示_日付指定.py（UI向け・最新）
- 収集_オリジナル展示_手動実行.py（相対日付用）
- 収集_RDMDB潮位データ_改善版.py
```

### 移動対象スクリプト（fetch系の古いバージョン）
```
fetch_historical_data_backup.py
fetch_venue_data.py
fetch_parallel_improved.py
fetch_improved_v2.py
fetch_missing_data.py
※ 残すもの:
- fetch_historical_data.py（最新）
- fetch_original_tenji_daily.py
- fetch_all_data_comprehensive.py
- fetch_improved_v3.py
- fetch_parallel_v6.py
```

### 移動対象ドキュメント（古いサマリー・レポート）

#### 作業サマリー系（重複）
```
SESSION_REPORT.md
PROGRESS_REPORT.md
PROGRESS_SUMMARY.md
STATUS_REPORT.md
STATUS_SUMMARY_20251113.md
CURRENT_SESSION_SUMMARY.md
CURRENT_SESSION_SUMMARY_UPDATED.md
SESSION_FINAL_REPORT.md
SESSION_COMPLETION_REPORT.md
FINAL_SUMMARY.md
WORK_SUMMARY.md
WORK_SUMMARY_20251113.md
※ 残すもの:
- docs/work_summary_20251118.md（最新）
- FINAL_WORK_SUMMARY_20251113.md（重要なマイルストーン）
```

#### 分析・計画系レポート（古い）
```
EFFICIENCY_IMPROVEMENT.md
EFFICIENCY_ANALYSIS.md
SPEED_COMPARISON.md
OPTIMIZATION_COMPLETE.md
FURTHER_OPTIMIZATION_ANALYSIS.md
TIMING_ANALYSIS.md
TURBO_EDITION_COMPLETE.md
TURBO_PERFORMANCE_VALIDATION.md
BOTTLENECK_ANALYSIS_AND_IMPROVEMENTS.md
REAL_BOTTLENECK_ANALYSIS.md
ALTERNATIVE_DATA_SOURCES.md
DOWNLOAD_SOLUTION_SUMMARY.md
HTML_DOWNLOAD_ANALYSIS.md
SELECTOLAX_TEST_RESULTS.md
ULTRA_OPTIMIZATION_PLAN.md
PARALLEL_RISK_ANALYSIS.md
```

#### 実装・仕様系（古い）
```
FEATURE_DESIGN.md
DEPLOYMENT_PLAN_V3.md
DATA_COLLECTION_ISSUES.md
V3_OPTIMIZATION_ANALYSIS.md
REORGANIZATION_SUMMARY.md
MODULE_CONSOLIDATION_PLAN.md
SCRAPER_CONSOLIDATION_PLAN.md
MODULE_CONSOLIDATION_COMPLETED.md
SCRAPER_CONSOLIDATION_COMPLETED.md
```

---

## Phase 2: 残すファイルリスト

### 必須Pythonスクリプト（コア機能）

#### UI関連
```
ui/app.py
ui/pages/*.py（すべて）
```

#### データ収集（推奨版のみ）
```
fetch_historical_data.py
fetch_original_tenji_daily.py
fetch_all_data_comprehensive.py
fetch_improved_v3.py
fetch_parallel_v6.py
```

#### オリジナル展示収集（最新）
```
収集_オリジナル展示_日付指定.py
収集_オリジナル展示_手動実行.py
収集_RDMDB潮位データ_改善版.py
```

#### 補完（推奨版のみ）
```
補完_race_details_INSERT対応_高速版.py
補完_風向データ_改善版.py
補完_天候データ_改善版.py
補完_レース詳細データ_改善版v4.py
```

#### 統合・実用スクリプト
```
過去データ一括取得_統合版.py
過去データ収集_完全版.py
fix_st_times.py
```

#### モデル学習・予測
```
train_conditional_model.py
run_backtest.py
predict_today.py
backtest_prediction.py
```

#### 最近作成の重要スクリプト
```
analyze_model_bias.py
test_probability_adjustment.py
test_full_prediction_yesterday.py
test_original_tenji_data.py
test_beforeinfo_direct.py
```

#### ユーティリティ
```
init_database.py
update_database.py
check_db_status.py
cleanup_project.py
backup_project.py
create_zip_package.py
```

### 必須ドキュメント

#### プロジェクト基本
```
README.md
START_HERE.md
DOCS_INDEX.md
README_WORK_GUIDE.md
README_QUICK_START.md
```

#### システム仕様・ガイド
```
COMPREHENSIVE_DATA_COLLECTION_README.md
DAILY_COLLECTION_SETUP.md
DATA_COLLECTION_GUIDE.md
オリジナル展示収集_UI連携ガイド.md
SYSTEM_CONSTRAINTS.md
WORK_CHECKLIST.md
QUALITY_ASSURANCE.md
TESTING_GUIDE.md
```

#### 重要な技術ドキュメント
```
SYSTEM_LOGIC_ANALYSIS.md
IMPORTANT_KNOW_HOW.md
SAFE_SCRAPING_GUIDELINES.md
```

#### 最新の作業記録
```
docs/work_summary_20251118.md
docs/model_bias_analysis_20251118.md
docs/オリジナル展示データ利用可能期間_調査報告.md
docs/プロジェクト全体レビュー_20251118.md
FINAL_WORK_SUMMARY_20251113.md
HANDOVER_REPORT_20251111.md
```

#### 分析・提案（重要）
```
docs/new_features_proposal.md
docs/API_STRUCTURE.md
docs/RACER_ANALYSIS_DESIGN.md
docs/PREDICTION_LOGIC_INSIGHTS.md
docs/kimarite_prediction_system.md
```

---

## Phase 3: 実行計画

### ステップ1: バックアップ
```bash
# 念のためプロジェクト全体をバックアップ
python backup_project.py
```

### ステップ2: アーカイブフォルダへ移動
```bash
# test_*.py（例外除く）
mv test_補完*.py archive/scripts_old/
mv test_収集*.py archive/scripts_old/
# ... (リストに基づいて移動)

# check_*.py（例外除く）
mv check_all*.py archive/scripts_old/
# ... (リストに基づいて移動)

# 古いドキュメント
mv SESSION_REPORT.md archive/docs_old/
# ... (リストに基づいて移動)
```

### ステップ3: README_SCRIPTS.md作成
残したスクリプトの用途を明記した一覧を作成

### ステップ4: 動作確認
```bash
# UI起動確認
streamlit run ui/app.py

# データ収集確認
python check_db_status.py
```

---

## Phase 4: クリーンアップ後の状態

### 期待される結果
- Pythonファイル: 233個 → **約60個**（75%削減）
- Markdownファイル: 153個 → **約40個**（74%削減）
- プロジェクト見通し: **大幅改善**

### メリット
1. 新規メンバーが理解しやすい
2. 推奨スクリプトが明確
3. メンテナンス負荷削減
4. Git履歴は保持（削除ではなく移動）

---

## 実行判断

**実行前の確認事項**:
- [ ] バックアップ完了
- [ ] 移動対象リストの確認
- [ ] 残すファイルリストの確認
- [ ] ユーザーの承認

**実行コマンド**: 別途作成する `cleanup_execute.py` で一括実行

---

**作成日**: 2025年11月18日
**実行予定**: ユーザー承認後
