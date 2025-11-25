# BoatRaceプロジェクト ファイル整理分析レポート
**作成日**: 2025-11-13  

## 目次
1. 削除すべきファイル
2. 更新すべき古い資料
3. 整理すべきディレクトリ
4. 保持すべき重要ファイル
5. 推奨アクション
6. 実装チェックリスト

---

## 1. 削除すべきファイル

### 1.1 バックアップファイル（削除: 約428MB）

#### 大規模バックアップZIP
- BoatRace_backup_20251109_205755.zip (214MB) - 削除
- BoatRace_backup_20251109_205946.zip (214MB) - 削除
- BoatRace_Transfer_Package.zip (5.8MB) - 削除

削除理由: 重複バックアップ。受け渡し/フォルダに統一

#### データベースバックアップ
- data/boatrace_backup_20251101_005920.db - 削除（古い）
- 受け渡し/内の重複DB - 確認後削除

### 1.2 バックアップディレクトリ（削除: 354KB）

削除対象:
- backup/analyzer_backup_20251103/ 
- backup/scraper_backup_20251103/ 
内容はsrc/に統合済み

### 1.3 不要なテストスクリプト（削除: 約50個）

重複・旧バージョンテスト:
- test_improved_v2.py, v3.py (v4が最新)
- test_v3_multiple.py (v4が最新)
- test_v4_scraper.py (src/scraper内で統合)
- verify_v3_data.py (v4検証で統合)

実験用・検証済みスクリプト:
- debug_race_result.py (デバッグ完了)
- debug_st_scraping.py (デバッグ完了)
- test_basic_scraper.py (基本テスト完了)
- test_improved_scraper.py (改善版テスト完了)
- その他debug_*.py (デバッグ完了)

### 1.4 一時ファイル・ログファイル（削除: 約80MB）

大規模ログファイル:
- v6_output.log (18MB) - 完了ログ
- v5_fixed_output.log (6.4MB) - 完了ログ
- v5_output.log (6.5MB) - 完了ログ
- rdmdb_tide_collection.log (28KB) - テストログ
- rdmdb_tide_improved_production.log (44KB) - テストログ

デバッグ出力ファイル:
- debug_fresh.log, debug_output.txt, debug_st_output.txt

### 1.5 デバッグHTML・出力ファイル（削除: 約300KB）

削除対象:
- debug_output.html (68KB) - デバッグ完了
- beforeinfo_1028_5r.html (52KB) - テストデータ
- beforeinfo_debug.html (52KB) - テストデータ
- raceresult_1028_5r.html (60KB) - テストデータ
- raceresult_sample.html (60KB) - テストデータ
- result_20241026.html (60KB) - テストデータ
- その他debug_*.html

### 1.6 一時データディレクトリ（削除: ~1.5GB）

削除対象:
- rdmdb_tide_data_test/ (732MB) - テスト用
- rdmdb_test_debug/ (空) - テスト用
- rdmdb_test_single/ (空) - テスト用
- rdmdb_downloads/ (2.4MB) - 一時ダウンロード

削除理由: テスト用の一時ディレクトリ

### 1.7 Python キャッシュディレクトリ（自動再生成）

削除対象: 全__pycache__/
削除後、.gitignore確認

---

## 2. 更新すべき古い資料

### 2.1 README・メインドキュメント（更新優先度: 高）

README.md
問題点:
  - セットアップ手順が不完全（venvアクティベーション記述エラー）
  - 最新機能の説明不足
  - データベーススキーマ説明なし
  - 運用手順の説明なし

推奨更新:
  - 正確なセットアップ手順（venv activate修正）
  - 最新モジュール構成の説明
  - データベーススキーマの概要
  - 主要スクリプト実行方法
  - トラブルシューティングセクション

### 2.2 古い計画書・提案書（削除・統合推奨）

削除対象:
- ALTERNATIVE_DATA_SOURCES.md (3.5KB) - v1仕様
- DEPLOYMENT_PLAN_V3.md (8.6KB) - v3計画
- DOWNLOAD_SOLUTION_SUMMARY.md - 古い解決案
- EFFICIENCY_IMPROVEMENT.md - 古い提案
- LUNCH_BREAK_PLAN.md - 期間限定メモ
- PHASE3_PREPARATION.md - フェーズ完了済み

### 2.3 実装完了済みドキュメント（アーカイブ化推奨）

アーカイブ対象（docs/reference/completed_features/ へ）:
- CALIBRATION_VALIDATION_COMPLETED.md
- MODULE_CONSOLIDATION_COMPLETED.md
- SCRAPER_CONSOLIDATION_COMPLETED.md
- STAGE1_IMPROVEMENT_COMPLETED.md
- STAGE2_MODEL_COMPLETED.md
- PURCHASE_HISTORY_TRACKING_COMPLETED.md
- RACER_FEATURES_COMPLETED.md
- VENUE_RACER_ANALYSIS_UI_COMPLETED.md

### 2.4 ワークレポート・分析レポート（アーカイブ化推奨）

アーカイブ対象（docs/reports/2025-11-13/ へ）:
- CURRENT_SESSION_SUMMARY.md - 過去セッション
- SESSION_COMPLETION_REPORT.md - 過去セッション
- SESSION_FINAL_REPORT.md - 過去セッション
- WORK_SUMMARY_20251113.md - 本日作業
- FINAL_WORK_SUMMARY_20251113.md - 本日最終

### 2.5 高速化・最適化ドキュメント（参考資料へ）

参考資料化対象（docs/reference/optimization/ へ）:
- BOTTLENECK_ANALYSIS_AND_IMPROVEMENTS.md
- EFFICIENCY_ANALYSIS.md
- FURTHER_OPTIMIZATION_ANALYSIS.md
- OPTIMIZATION_COMPLETE.md
- REAL_BOTTLENECK_ANALYSIS.md
- TURBO_EDITION_COMPLETE.md
- その他最適化関連

### 2.6 コード分析ドキュメント（統合または削除）

削除対象:
- CODE_ANALYSIS_REPORT.md (24KB) - 古い分析
- COMPREHENSIVE_CODE_ANALYSIS_20251113.txt
- 改善アドバイス20251103.txt

---

## 3. 整理すべきディレクトリ

### 3.1 受け渡し/ フォルダ（整理: 2.6GB）

現状:
- BoatRace_backup_20251109_205946/
- original_tenji_fix_20251111/

問題点:
  - プロジェクト総容量の40%を占める
  - 重複バックアップ
  - 明確な用途不明

推奨:
1. 内容確認（本当に転送用？）
2. 1つのマスターバージョンのみ保持
3. それ以外は削除またはクラウドストレージに移行

### 3.2 docs/ フォルダ（整理: 72KB → 構造化）

推奨新構成:
docs/
├── README.md (ドキュメント索引)
├── ARCHITECTURE.md (全体設計)
├── DATABASE_SCHEMA.md (DB設計)
├── guides/ (実行ガイド)
├── design/ (設計書)
├── reference/ (参考資料)
│   ├── optimization/ (最適化参考)
│   └── completed_features/ (完成済み)
└── reports/ (セッション報告)

### 3.3 tests/ フォルダ（整理: 137KB）

推奨構成:
tests/
├── unit/ (単体テスト)
├── integration/ (統合テスト)
├── validation/ (検証)
└── training/ (訓練スクリプト)

### 3.4 models/ フォルダ（整理: 4KB）

推奨構成:
models/
├── stage1/
│   ├── latest/
│   └── archive/
├── stage2/
│   ├── latest/
│   └── archive/
└── metrics/

### 3.5 logs/ フォルダ（整理: 1.9MB）

推奨構成:
logs/
├── YYYY-MM-DD/
│   ├── collection_HHMM.log
│   ├── prediction_HHMM.log
│   └── errors_HHMM.log
└── archive/

### 3.6 data/ フォルダ（整理: 2.6GB）

推奨構成:
data/
├── boatrace.db (メインDB)
├── backups/
│   ├── daily/
│   └── weekly/
├── exports/
├── temp/ (一時)
└── archive/ (古いデータ)

---

## 4. 保持すべき重要ファイル

### 4.1 ソースコード（必須保持）
- src/ ディレクトリ全体 (1.7MB)
- result_scraper_improved_v4.py (最新版)
- odds_scraper.py, beforeinfo_fetcher.py
- 全分析モジュール

### 4.2 UIコンポーネント（必須保持）
- ui/ ディレクトリ (520KB)
- ui/app.py (メインアプリ)
- ui/components/ (再利用コンポーネント)

### 4.3 設定ファイル（必須保持）
- config/settings.py
- config/scoring_weights.json
- requirements.txt
- .env, .env.example
- .gitignore

### 4.4 メインデータベース（必須保持）
- boatrace.db (最新版)
- 日次バックアップは別途自動化

### 4.5 実行スクリプト（選別保持）

保持:
- fetch_historical_data.py
- collect_environmental_data.py
- analyze_data_quality.py
- check_collection_status.py (最新)
- check_db_status.py (最新)

削除（旧版):
- check_collection_progress.py
- check_data_progress.py
- check_db_quick.py

### 4.6 README & ドキュメント（選別保持）

保持:
- README.md (メイン説明)
- docs/ARCHITECTURE.md
- docs/DATABASE_SCHEMA.md
- docs/SETUP_GUIDE.md

---

## 推奨アクション

### フェーズ1: 快速クリーンアップ（1-2時間）

削除コマンド:
```
rm BoatRace_backup_20251109_205755.zip
rm BoatRace_backup_20251109_205946.zip
rm BoatRace_Transfer_Package.zip
rm data/boatrace_backup_20251101_005920.db
rm -rf rdmdb_tide_data_test/
rm -rf rdmdb_test_debug/
rm -rf rdmdb_test_single/
rm -rf rdmdb_downloads/
rm -rf backup/
```

削減: 約2.2GB

### フェーズ2: ドキュメント整理（2-3時間）

- docs/ディレクトリ構造化
- 古い計画書をarchivedへ移動
- セッションレポートを日付フォルダへ
- README.md更新

### フェーズ3: ファイル整理（1時間）

- テスト関連をv4に統一
- デバッグファイル削除
- 実行ログ削除
- テストHTML削除

削減: 約80MB

### フェーズ4: ソースコード統一（1-2時間）

- スクレーパーを最新版に統一
- チェックスクリプトを最新版に統一
- __pycache__クリーンアップ

### フェーズ5: 受け渡し/フォルダ整理（1時間、事前確認必須）

- 内容確認
- 必要に応じて保持/削除
- またはクラウドストレージに移行

---

## 実装チェックリスト

### 即座に実施（フェーズ1）
- [ ] BoatRace_backup_20251109_205755.zip 削除
- [ ] BoatRace_backup_20251109_205946.zip 削除
- [ ] BoatRace_Transfer_Package.zip 削除
- [ ] rdmdb_tide_data_test/ 削除
- [ ] rdmdb_downloads/ 削除
- [ ] backup/ 削除

### 本週中に実施（フェーズ2-4）
- [ ] README.md 更新
- [ ] docs/ 構造化
- [ ] 古い計画書をアーカイブ
- [ ] セッションレポートを日付フォルダへ
- [ ] テスト統一
- [ ] デバッグファイル削除
- [ ] __pycache__ クリーンアップ

### 確認後実施（フェーズ5）
- [ ] 受け渡し/ 確認
- [ ] 必要に応じて整理

### 最適化
- [ ] .gitignore 更新
- [ ] logs統一スクリプト修正
- [ ] 自動バックアップスクリプト作成

---

## 期待効果

### ストレージ削減
- 削減容量: 約2.3-2.7GB (6.5GB → 約4GB)
- 削減率: 35-40%

### 保守性向上
- ディレクトリ構造の明確化
- ドキュメントの体系化
- 重複排除

### セキュリティ向上
- 不要な個人情報削除
- バージョン管理の明確化
- .gitignore 強化

---

作成: 2025-11-13
