# アーカイブ索引（ARCHIVE_INDEX）

**最終更新**: 2026-05-11  
**目的**: archive/ 配下のファイルを検索・参照できるようにする。過去の知見・調査結果は削除せずここに保存している。  
**注意**: 内容は過去時点のスナップショット。現在の状態はDB・コード・HANDOVER.mdで確認すること。

---

## 2026-05-11 整理内容

| 対象 | 移動ファイル数 | 移動先 |
|------|:---:|------|
| scripts/analysis/ 旧版・一時分析 | 36 | scripts/analysis/_deprecated/ |
| scripts/maintenance/ 旧版・一時タスク | 36 | scripts/maintenance/_deprecated/ |
| scripts/validation/ デバッグ系 | 13 | scripts/validation/_deprecated/（新規作成） |
| logs/ 完了済み一時作業ログ | 62 | logs/archive/（新規作成） |
| ui/components/*.tmp.* | 16 | 削除 |
| ルート直下 temp_* | 15 | 削除 |
| temp/ 内 一時ファイル | 29 | 削除 |

---

## ディレクトリ構成一覧

| ディレクトリ | ファイル数 | 内容 |
|---|---|---|
| [archive直下](#archive直下) | 12 | 単発レポート・分析JSON・バージョン履歴 |
| [analysis/](#analysis90ファイル) | 90 | 2026年初頭の詳細分析レポート |
| [analysis_2025/](#analysis_202551ファイル) | 51 | 2025年12月の分析レポート |
| [implementation/](#implementation36ファイル) | 36 | 実装完了レポート・フェーズ報告 |
| [reports_2025/](#reports_20254ファイル) | 4 | 2025年末〜2026年初のその他レポート |
| [reports_2026/](#reports_202614ファイル) | 14 | 2026年前半のデータ品質・改善計画レポート |
| [performance_old/](#performance_old4ファイル) | 4 | 旧ベースライン・補完完了レポート |
| [archive_2025_11_13/](#archive_2025_11_133ファイル) | 3 | プロジェクト初期の分析メモ（txt） |
| [guides/](#guides46ファイル) | 46 | 旧ガイド類（2024-12〜2025-02） |
| [improvement_attempts/](#improvement_attempts5ファイル) | 5 | 不採用案の詳細調査メモ（REJECTED_IDEAS.mdに要約済み） |
| [architecture_old/](#architecture_old4ファイル) | 4 | 旧アーキテクチャ文書・設計メモ |
| [knowledge/](#knowledge6ファイル) | 6 | 旧知見ベース・ロジック解説書（2024-12） |

### scripts/_deprecated/ （2026-05-11追加）

| ディレクトリ | 移動数 | 主な内容 |
|---|---|---|
| scripts/analysis/_deprecated/ | +36 | tj系分析・旧p1/p2分析・一時スキャン・ML評価旧版など |
| scripts/maintenance/_deprecated/ | +36 | 旧学習モデル（v4以前）・create_*系テーブル作成・cleanup_*系・監視旧版など |
| scripts/validation/_deprecated/ | 13（新規） | debug_*系・analyze_tier*系・check_overlap系・compare_tier系 |

### logs/archive/ （2026-05-11新規作成）

| 内容 | ファイル数 |
|---|---|
| regen_*系（前日・年度データ再生成ログ） | 約25 |
| test_*系（各種テスト実行ログ） | 約7 |
| 一時作業ログ（brute_force・overnight・auto_plan等） | 約30 |

---

## archive直下（12ファイル）

| ファイル | 概要 |
|---|---|
| `version_history.md` | バージョン履歴メモ |
| `DATA_QUALITY_REVIEW_REPORT_20260206.md` | 2026-02-06 データ品質レビュー報告 |
| `MARKET_EFFICIENCY_LESSONS_20260216.md` | 2026-02-16 市場効率性に関する教訓まとめ |
| `MISTAKE_ANALYSIS_20260206.md` | 2026-02-06 ミス分析・原因調査 |
| `TROUBLE_ANALYSIS_20260209.md` | 2026-02-09 トラブル分析 |
| `purchase_condition_c20-30_investigation_20260209.md` | C条件20-30オッズの検討調査 |
| `purchase_condition_optimization_report.md` | 購入条件最適化レポート |
| `purchase_condition_optimization_summary.md` | 購入条件最適化サマリー |
| `venue_wind_direction_table.py` | 会場別風向テーブル（Pythonスクリプト） |
| `beforeinfo_analysis_results.json` | 直前情報分析結果（JSON） |
| `comprehensive_analysis_2025.json` | 2025年包括分析結果（JSON） |
| `exhibition_detailed_results.json` | 展示タイム詳細分析結果（JSON） |

---

## analysis/（90ファイル）

2026年初頭（2026-01〜02）の詳細分析レポート群。主要なものを以下に記載。

| ファイル | 概要 |
|---|---|
| `2020_09_DATE_FIX_COMPLETION_REPORT.md` | 2020-09日付修正完了報告 |
| `2020_09_DATE_FORMAT_INVESTIGATION.md` | 2020-09日付フォーマット調査 |
| `20251223_6YEAR_STABLE_CONDITIONS_ANALYSIS.md` | 6年間安定条件分析 |
| `20251224_BEFORE_PREDICTION_ANALYSIS_SUMMARY.md` | before予測分析サマリー |
| `20251224_BEFORE_PREDICTION_CONDITION_ANALYSIS.md` | before予測条件分析 |
| `20251224_BEFORE_PREDICTION_MISS_PATTERN_ANALYSIS.md` | before予測外れパターン分析 |
| `20251224_COMPREHENSIVE_ANALYSIS_REPORT.md` | 包括分析レポート |
| `20251224_MOTOR_CONDITION_ANALYSIS_SUMMARY.md` | モーター条件分析サマリー |
| `20251224_MOTOR_CONDITION_FINAL_RECOMMENDATION.md` | モーター条件最終推奨 |
| `20251224_VENUE_COMPLETE_ANALYSIS.md` | 会場別完全分析 |
| `20260105_D_COURSE5_ANALYSIS.md` | D条件5コース分析 |
| `20260106_BEFOREINFO_EXCLUSION_ANALYSIS.md` | 直前情報除外条件分析 |
| `ACCURATE_VENUE_FILTER_ANALYSIS_20260213.md` | 会場フィルター精度分析 |
| `B2_CONDITIONS_YEARLY_STABILITY_20260212.md` | B2条件の年度安定性分析 |
| `BEFOREINFO_UTILIZATION_REPORT.md` | 直前情報活用状況レポート |
| （他75ファイル） | 各種条件・会場・指標の詳細分析 |

> **検索ヒント**: `python scripts/search_knowledge.py "キーワード"` で横断検索可能

---

## analysis_2025/（51ファイル）

2025年12月の分析レポート群。条件検討・バックテスト結果・モデル評価が中心。

| ファイル | 概要 |
|---|---|
| `AB_RANK_ANALYSIS_REPORT_20251219.md` | ABランク分析 |
| `ACCURATE_BACKTEST_RESULTS_2025.md` | 精度確認済みバックテスト結果 |
| `ALL_CONDITIONS_MATRIX_2025.md` | 全条件マトリクス |
| `BACKTEST_RELIABILITY_REPORT_20251215.md` | バックテスト信頼性レポート |
| `BASELINE_CLARIFICATION_20251220.md` | ベースライン定義の明確化 |
| `BEFOREINFO_OPTIMIZATION_ANALYSIS_20251217.md` | 直前情報最適化分析 |
| （他45ファイル） | 条件テスト・指標評価等 |

---

## implementation/（36ファイル）

完了済み実装フェーズのレポート。施策の実装経緯を確認したい場合に参照。

| ファイル | 概要 |
|---|---|
| `PHASE1_VENUE_FILTER_IMPLEMENTATION_20260213.md` | Phase1 会場フィルター実装 |
| `PHASE2_VERIFICATION_REPORT_20251217.md` | Phase2 検証レポート |
| `PHASE3_IMPLEMENTATION_SUMMARY.md` | Phase3 実装サマリー |
| `PHASE4_IMPLEMENTATION_SUMMARY.md` | Phase4 実装サマリー |
| `PREDICTION_UNIFICATION_LIGHTWEIGHT_20260213.md` | 予測統一化・軽量化実装 |
| `PRODUCTION_DEPLOYMENT_REPORT.md` | 本番デプロイレポート |
| `REJECTED_INITIATIVES_SUMMARY_20260213.md` | 不採用施策サマリー |
| `SYSTEM_IMPROVEMENT_PROPOSAL_20260212.md` | システム改善提案 |
| `TJ06_WAVE_HEIGHT_FILTER_VERIFICATION_20260216.md` | 波高フィルター検証 |
| `TJ09_EXHIBITION_RELIABILITY_VERIFICATION_20260216.md` | 展示タイム信頼性検証 |
| （他26ファイル） | 各種実装完了報告 |

---

## reports_2025/（4ファイル）

| ファイル | 概要 |
|---|---|
| `DATA_BACKFILL_PROGRESS_20260128.md` | データ補完進捗報告 |
| `DOCUMENT_CLEANUP_PROPOSAL_20260114.md` | ドキュメント整理提案（過去版） |
| `JAN_2026_ANALYSIS_REPORT.md` | 2026年1月分析レポート |
| `PROJECT_CLEANUP_LOG_20251222.md` | 2025-12-22 プロジェクト整理ログ |

---

## reports_2026/（14ファイル）

2026年前半のデータ収集品質・改善計画レポート群。

| ファイル | 概要 |
|---|---|
| `DATA_COLLECTION_IMPROVEMENT_PLAN.md` | データ収集改善計画 |
| `DATA_COMPLETION_REVIEW_ITEMS.md` | データ補完レビュー項目 |
| `DATA_COVERAGE_REALITY_REPORT.md` | データカバレッジ実態報告 |
| `DATA_QUALITY_IMPROVEMENT_FINAL_REPORT.md` | データ品質改善最終報告 |
| `DATA_STRUCTURE_CONFUSION_ANALYSIS.md` | データ構造混乱分析 |
| `REDUNDANT_COLUMNS_PROPOSAL.md` | 冗長カラム整理提案 |
| `SCHEDULER_INVESTIGATION_REPORT.md` | スケジューラー調査報告 |
| `WAVE_HEIGHT_COMPLETION_REPORT.md` | 波高データ補完完了報告 |
| `COMPREHENSIVE_LOGIC_REVIEW_ITEMS.md` | ロジック総合レビュー項目 |
| `COMPREHENSIVE_REVIEW_PREP.md` | 総合レビュー準備資料 |
| `DATA_ENHANCEMENT_ACTION_PLAN.md` | データ拡充アクションプラン |
| `DATA_UTILIZATION_AND_IMPROVEMENT_PLAN.md` | データ活用・改善計画 |
| `REVIEW_READY_SUMMARY.md` | レビュー準備サマリー |
| `DATA_COMPLETION_PREPARATION_CHECKLIST.md` | データ補完準備チェックリスト |

---

## performance_old/（4ファイル）

旧ベースライン時代のパフォーマンスレポート。

| ファイル | 概要 |
|---|---|
| `BASELINE_DETAIL_20260216.md` | 2026-02-16時点のベースライン詳細 |
| `MONTHLY_BASELINE_20260216.md` | 2026-02-16時点の月次ベースライン |
| `DATA_COMPLETION_PRIORITY_REPORT_20260206.md` | データ補完優先度レポート |
| `DATA_COVERAGE_REPORT_20260206.md` | データカバレッジレポート |

---

## archive_2025_11_13/（3ファイル）

プロジェクト初期（2025-11-13）のコード分析メモ。

| ファイル | 概要 |
|---|---|
| `COMPREHENSIVE_CODE_ANALYSIS_20251113.txt` | 初期コード包括分析 |
| `VENUE_ANALYZER_FIX_SUMMARY.txt` | 会場アナライザー修正サマリー |
| `復元完了_次回起動時の確認事項.txt` | 初期セットアップ確認事項 |

---

## guides/（46ファイル）

2024-12〜2025-02 作成の旧ガイド群。現役版は `docs/guides/` に10ファイルが残っている。

### セットアップ・運用系

| ファイル | 概要 |
|---|---|
| `QUICKSTART.md` | クイックスタートガイド（旧） |
| `PROJECT_SETUP_GUIDE.md` | プロジェクトセットアップ（旧） |
| `DEVELOPMENT_WORKFLOW.md` | 開発ワークフロー（旧） |
| `OPERATIONS_GUIDE.md` | 運用ガイド（旧） |
| `SYSTEM_UPDATE_GUIDE.md` | システム更新ガイド（旧） |
| `AUTOMATION_SETUP.md` | 自動化セットアップ |
| `DUAL_PC_SETUP_GUIDE.md` / `dual_pc_setup.md` | デュアルPC構成ガイド |
| `PC_RESTART_PREVENTION.md` | PC再起動防止（旧、現在は再起動耐性実装済み） |
| `DISCORD_WEBHOOK_SETUP.md` | Discord Webhook設定 |
| `LINE_NOTIFY_SETUP.md` | LINE通知設定 |
| `SCHEDULER_USAGE.md` | スケジューラー使い方 |
| `UI起動ガイド.md` | Streamlit UI起動手順 |

### データ収集系（旧版）

| ファイル | 概要 |
|---|---|
| `DATA_COLLECTION_README.md` | データ収集README（旧） |
| `DATA_COLLECTION_CHECKLIST.md` | データ収集チェックリスト（旧、現役版はDATA_ANALYSIS_CHECKLIST.md） |
| `DATA_COLLECTION_BEST_PRACTICES.md` | データ収集ベストプラクティス（旧） |
| `DATA_COLLECTION_CONSTRAINTS.md` | データ収集制約事項（旧） |
| `DATA_COLLECTION_QUALITY_REPORT.md` | データ収集品質レポート（旧） |
| `DATA_COLLECTION_SCRIPTS_STATUS.md` | スクリプト状態一覧（旧、現役版はDATA_COLLECTION_SCRIPTS_CATALOG.md） |
| `DATA_COLLECTION_TROUBLESHOOTING.md` | データ収集トラブルシューティング（旧） |
| `DATA_COMPLETION_ERROR_RECOVERY.md` | データ補完エラーリカバリー手順 |
| `DATA_COMPLETION_REVIEW_WORKFLOW.md` | データ補完レビューワークフロー（旧） |
| `DATA_SOURCE_INVESTIGATION_REPORT.md` | データソース調査レポート |
| `odds_data_collection.md` | オッズデータ収集（旧） |
| `夜間オッズ収集実行手順.md` | 夜間オッズ収集手順（旧） |
| `2021_2023_DATA_RECOVERY_GUIDE.md` | 2021-2023年データリカバリーガイド（一時タスク） |
| `2021_2023_DATA_RECOVERY_README.md` | 同README |

### 予測・モデル系（旧版）

| ファイル | 概要 |
|---|---|
| `PREDICTION_WORKFLOW.md` | 予測ワークフロー（旧） |
| `PREDICTION_SYSTEM_STATUS.md` | 予測システム状態（旧） |
| `prediction_efficiency_guide.md` / `prediction_efficiency_guide_v2.md` | 予測効率化ガイド（旧） |
| `MODEL_MANAGEMENT.md` | モデル管理（旧） |
| `model_training_guide.md` | モデル学習ガイド（旧） |
| `setup_beforeinfo_enhancement.md` | 直前情報強化セットアップ（旧） |
| `PATTERN_H_IMPLEMENTATION_GUIDE.md` | パターンH実装ガイド（旧） |
| `BETTING_CONDITIONS_TEST_GUIDE.md` | 購入条件テストガイド（旧、現役版はVALIDATION_WORKFLOW.md） |
| `backtest_guide.md` | バックテストガイド（旧） |
| `night_batch_execution_guide.md` / `夜間バッチ実行手順.md` | 夜間バッチ手順（旧） |
| `期待値予想機能_使い方.md` | 期待値予想機能の使い方 |

### 展示タイム・会場系（旧版）

| ファイル | 概要 |
|---|---|
| `ORIGINAL_TENJI_COLLECTION.md` | オリジナル展示収集（旧） |
| `VENUE_TENJI_DATA_AVAILABILITY.md` | 会場別展示データ可用性（旧） |
| `オリジナル展示収集_UI連携ガイド.md` | 展示収集UIガイド（旧） |

### その他

| ファイル | 概要 |
|---|---|
| `PROJECT_CLEANUP_DETAIL.md` | プロジェクト整理詳細ログ |
| `UI_SCRIPT_REFERENCE_FIX_REPORT.md` | UIスクリプト参照修正レポート（一時タスク完了済み） |
| `TROUBLESHOOTING_GUIDE.md` | トラブルシューティング（旧） |
| `PROJECT_CLEANUP_DETAIL.md` | プロジェクト整理詳細 |

---

## improvement_attempts/（5ファイル）

不採用案の調査詳細メモ。要約は `docs/improvement_attempts/REJECTED_IDEAS.md` に記載済み。

| ファイル | 概要 |
|---|---|
| `REJECTED_IDEAS.md` の要約エントリ対応 | ↓ |
| `2025-12_v2_strategy_test.md` | v2戦略テスト詳細（2025-12） |
| `monte_carlo_rejection_20251219.md` | モンテカルロ法不採用の調査詳細 |
| `rank23_odds_calibration_rejection_20251218.md` | ランク2/3オッズ補正不採用の詳細 |
| `DATA_COLLECTION_CLEANUP_20260205.md` | 2026-02-05 データ収集整理レポート |
| `DATA_COLLECTION_ISSUE_20260205.md` | 2026-02-05 データ収集問題報告 |

---

## architecture_old/（4ファイル）

旧・重複アーキテクチャ文書。現役版は `docs/architecture/` に残っている。

| ファイル | 概要 | 現役代替 |
|---|---|---|
| `DATABASE_SCHEMA.md` との重複 | `DB_SCHEMA_REFERENCE.md` | `docs/architecture/DATABASE_SCHEMA.md`（73K・最新） |
| `PREDICTION_LOGIC.md` との重複 | `prediction_system_spec.md` | `docs/architecture/PREDICTION_LOGIC.md`（92K・最新） |
| 設計段階メモ | `hole_prediction_model_design.md` | 実装済みのため不要 |
| 外部レビュー用 | `SYSTEM_OVERVIEW_FOR_EXTERNAL_REVIEW.md` | 一時利用目的だったため |

---

## knowledge/（6ファイル）

2024-12 作成の旧知見ベース。現在の予測ロジックは `docs/architecture/PREDICTION_LOGIC.md` が正。

| ファイル | 概要 |
|---|---|
| `prediction_logic_knowledge_base.md` | 予測ロジック知見ベース（旧） |
| `prediction_logic_summary.md` | 予測ロジックサマリー（旧） |
| `weather_preset_rules.md` | 天気プリセットルール（旧） |
| `exclusion_rules_pending_20251225.md` | 除外ルール検討メモ（2025-12-25、未実装） |
| `オリジナル展示収集_知見とトラブルシューティング.md` | 展示収集トラブルシューティング（旧） |
| `予想ロジック解説書_非エンジニア向け.md` | 非エンジニア向けロジック解説（2024-12・旧） |
