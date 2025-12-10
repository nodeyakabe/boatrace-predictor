# プロジェクト整理レポート

作成日: 2025-11-02
バックアップ先: `C:\Users\seizo\Desktop\BoatRace_backup_20251102`

## 目次

1. [削除推奨スクリプト一覧](#削除推奨スクリプト一覧)
2. [保持すべきスクリプト](#保持すべきスクリプト)
3. [失敗事例と改善点](#失敗事例と改善点)
4. [現在の運用スクリプト](#現在の運用スクリプト)

---

## 削除推奨スクリプト一覧

### 1. テスト・デバッグスクリプト (Test/Debug Scripts)

以下は開発中のテスト・デバッグ用で、本番環境では不要:

**テストスクリプト:**
- `test_2020_data_availability.py` - 2020年データ可用性テスト
- `test_data_fetchers.py` - データフェッチャーテスト
- `test_db_sync.py` - DB同期テスト
- `test_environment.py` - 環境テスト
- `test_exhibition_save.py` - 展示データ保存テスト
- `test_exhibition_time_save.py` - 展示タイムテスト
- `test_kimarite_fast.py` - 決まり手高速テスト
- `test_kimarite_v2.py` - 決まり手v2テスト
- `test_ml_system.py` - 機械学習システムテスト
- `test_parser_format_detection.py` - パーサーフォーマット検出テスト
- `test_parser_with_sample.py` - サンプルパーサーテスト
- `test_rdmdb_access.py` - RDMDB アクセステスト
- `test_rdmdb_collection.py` - RDMDB 収集テスト
- `test_rdmdb_download.py` - RDMDB ダウンロードテスト
- `test_rdmdb_parser_3files.py` - RDMDB パーサー3ファイルテスト
- `test_rdmdb_parser_single.py` - RDMDB パーサー単一テスト
- `test_rdmdb_search.py` - RDMDB 検索テスト
- `test_rule_integration.py` - ルール統合テスト
- `test_single_failing_file.py` - 失敗ファイルテスト
- `test_single_race_v5.py` - レース単体v5テスト
- `test_two_phase_save.py` - 2フェーズ保存テスト
- `test_ui_integration.py` - UI統合テスト
- `test_v4_quick.py` - v4クイックテスト
- `test_wind_direction.py` - 風向テスト
- `test_wind_extraction.py` - 風データ抽出テスト
- `test_収集_RDMDB潮位_単一.py` - RDMDB潮位単一テスト
- `test_新URL_1ファイル.py` - 新URL1ファイルテスト
- `test_結果イベント抽出.py` - 結果イベント抽出テスト
- `test_結果イベント抽出v2.py` - 結果イベント抽出v2テスト
- `test_結果イベント抽出v3.py` - 結果イベント抽出v3テスト
- `test_補完_決まり手_単一.py` - 決まり手単一補完テスト

**デバッグスクリプト:**
- `debug_checkbox_ids.py` - チェックボックスIDデバッグ
- `debug_failed_hiroshima.py` - 広島失敗デバッグ
- `debug_hiroshima_detailed.py` - 広島詳細デバッグ
- `debug_racer_query.py` - レーサークエリデバッグ
- `debug_rdmdb_options.py` - RDMDB オプションデバッグ
- `debug_rdmdb_parser.py` - RDMDB パーサーデバッグ
- `debug_result_page_exhibition.py` - 結果ページ展示デバッグ
- `debug_tide_extraction.py` - 潮位抽出デバッグ
- `debug_tide_html.py` - 潮位HTMLデバッグ
- `debug_wind_html.py` - 風HTMLデバッグ

### 2. 旧バージョン・試行版スクリプト (Old Versions/Trial Scripts)

以下は改善版が存在するため、削除可能:

**旧バージョン:**
- `補完_決まり手データ.py` → 最新版: `補完_決まり手データ_改善版.py`
- `補完_決まり手データ_高速版.py` → 最新版: `補完_決まり手データ_改善版.py`
- `補完_結果データ.py` → 最新版あり
- `補完_レース詳細データ.py` → 最新版: `補完_レース詳細データ_改善版v4.py`
- `補完_レース詳細データ_改善版.py` → 最新版: v4
- `補完_レース詳細データ_改善版v2.py` → 最新版: v4
- `補完_レース詳細データ_改善版v3.py` → 最新版: v4
- `補完_天候データ取得.py` → 最新版: `補完_天候データ_改善版.py`
- `収集_RDMDB潮位データ.py` → 最新版: `収集_RDMDB潮位データ_改善版.py`
- `収集_RDMDB潮位データ_単一.py` - 単一テスト版
- `収集_RDMDB潮位データ_新URL対応.py` → 最新版に統合済み
- `fetch_parallel_v4.py` → v5, v6がある
- `fetch_parallel_v5.py` → v6がある
- `fetch_parallel_v5_fixed.py` → v6がある
- `analyze_demei_probability.py` → fixed版がある
- `analyze_demei_probability_fixed.py` - fixed版
- `analyze_prediction_patterns.py` → fixed版がある
- `analyze_prediction_patterns_fixed.py` - fixed版
- `comprehensive_bug_check.py` → fixed版がある
- `comprehensive_bug_check_fixed.py` - fixed版
- `check_coverage_fixed.py` - fixed版

### 3. 一時的な調査・分析スクリプト (Temporary Investigation Scripts)

開発中の調査目的で作成されたもの:

**HTML抽出・調査:**
- `extract_all_boats_tilt.py` - チルト抽出試行
- `extract_exhibition_table3.py` - 展示テーブル抽出試行
- `extract_first_row_html.py` - 最初の行HTML抽出
- `extract_start_info_html.py` - スタート情報抽出
- `extract_start_table.py` - スタートテーブル抽出
- `find_all_start_tables.py` - スタートテーブル検索
- `find_all_tbodies.py` - tbody検索
- `find_exhibition_time.py` - 展示タイム検索
- `find_rdmdb_new_url.py` - RDMDB新URL検索
- `count_tbody_rows.py` - tbody行数カウント

**調査スクリプト:**
- `investigate_exhibition_details.py` - 展示詳細調査
- `investigate_jcg_tide.py` - JCG潮位調査
- `investigate_rdmdb_flow.py` - RDMDBフロー調査
- `investigate_schedule.py` - スケジュール調査
- `investigate_tide_url.py` - 潮位URL調査

**分析スクリプト (開発用):**
- `analyze_endpoints.py` - エンドポイント分析
- `analyze_further_optimization.py` - 追加最適化分析
- `analyze_payout_data.py` - 払戻データ分析
- `analyze_schedule_structure.py` - スケジュール構造分析
- `analyze_st_time.py` - スタートタイム分析
- `analyze_tilt_structure.py` - チルト構造分析
- `analyze_v4_speed.py` - v4速度分析
- `analyze_venue_patterns.py` - 会場パターン分析
- `analyze_wakamatsu.py` - 若松分析

**チェックスクリプト (一時的):**
- `check_2023_data.py` - 2023データチェック
- `check_data_completeness.py` - データ完全性チェック
- `check_data_coverage_detail.py` - データカバレッジ詳細
- `check_data_gaps.py` - データギャップチェック
- `check_data_integrity.py` - データ整合性チェック
- `check_exhibition_coverage.py` - 展示データカバレッジ
- `check_exhibition_time_html.py` - 展示タイムHTMLチェック
- `check_latest_wind_data.py` - 最新風データチェック
- `check_logs.py` - ログチェック
- `check_missing_data.py` - 欠損データチェック
- `check_missing_weather.py` - 欠損天候チェック
- `check_new_rdmdb_url.py` - 新RDMDBURLチェック
- `check_rdmdb_page.py` - RDMDBページチェック
- `check_tide_coverage.py` - 潮位カバレッジチェック
- `check_tide_data.py` - 潮位データチェック
- `check_v5_data_quality.py` - v5データ品質チェック
- `30日確認.py` - 30日確認

### 4. マイグレーション・初期セットアップスクリプト (Migration Scripts)

既に実行済みで再実行不要:

- `migrate_rank_column.py` - rank列マイグレーション
- `migrate_add_weather_columns.py` - 天候列追加
- `migrate_add_race_details.py` - レース詳細追加
- `migrate_add_payouts_table.py` - 払戻テーブル追加
- `migrate_add_kimarite_column.py` - 決まり手列追加
- `migrate_add_winning_technique.py` - 勝利技術追加
- `register_all_venues.py` - 全会場登録 (初回のみ)
- `register_wakamatsu_rules.py` - 若松ルール登録 (初回のみ)
- `register_top_racer_rules.py` - トップレーサールール登録 (初回のみ)
- `create_racer_rules_table.py` - レーサールールテーブル作成
- `create_rules_table.py` - ルールテーブル作成
- `create_test_db.py` - テストDB作成
- `add_weather_columns.py` - 天候列追加 (マイグレーション)
- `add_payout_methods.py` - 払戻メソッド追加 (初回のみ)
- `add_rule_validation_tab.py` - ルール検証タブ追加 (UI更新済み)

### 5. 廃止された機能のスクリプト (Deprecated Features)

使わなくなった機能:

- `train_model.py` - 機械学習モデル (現在未使用)
- `uiapp.py` - 旧UIアプリ (ui/app.pyに移行済み)
- `continuous_auto_collect.py` - 連続自動収集 (現在未使用)
- `auto_collect_next_month.py` - 自動翌月収集 (現在未使用)
- `merge_databases.py` - DB統合 (初回のみ)
- `convert_to_readonly_db.py` - 読み取り専用DB変換 (不要)
- `enable_wal_mode.py` - WALモード有効化 (既に実行済み)
- `fix_pyarrow.py` - PyArrow修正 (一時的な修正)
- `fix_tabs.py` - タブ修正 (UI修正済み)
- `create_package.py` - パッケージ作成 (開発用)

### 6. 再処理・バックフィルスクリプト (One-time Reprocessing Scripts)

一度実行すれば不要:

- `再パース_RDMDB潮位_既存ファイル.py` - 既存ファイル再パース
- `再パース_Hiroshima_2ファイル.py` - Hiroshima再パース
- `再収集_RDMDB潮位_10ファイルテスト.py` - 10ファイル再収集テスト
- `削除_結果イベント_tide直行.py` - tide直行イベント削除
- `削除_結果イベント_追加3候補.py` - 追加3候補イベント削除
- `補完_決まり手_全件.py` - 全件決まり手補完 (一度実行済み)
- `補完_決まり手_全件_並列.py` - 並列全件補完 (一度実行済み)
- `補完_決まり手_全件_並列後.py` - 並列後補完 (一度実行済み)
- `補完_過去天候データ.py` - 過去天候補完 (一度実行済み)
- `fill_weather_data.py` - 天候データ補完 (一度実行済み)
- `fetch_missing_race_details.py` - 欠損レース詳細取得 (一度実行済み)
- `fetch_missing_weather.py` - 欠損天候取得 (一度実行済み)
- `fetch_historical_data_bulk.py` - 過去データ一括取得 (一度実行済み)
- `update_results_table.py` - 結果テーブル更新 (一度実行済み)
- `過去データ一括取得_並列版.py` - 並列過去データ取得 (一度実行済み)

### 7. サンプル・ダウンロードファイル (Sample/Download Files)

- `download_rdmdb_sample.py` - RDMDBサンプルダウンロード
- `save_result_html.py` - 結果HTML保存 (調査用)
- `解凍_RDMDB潮位ZIP.py` - ZIP解凍 (手動作業用)

---

## 保持すべきスクリプト

### 現在運用中のスクリプト

以下は現在のシステムで使用中のため保持:

**コアシステム:**
- `init_database.py` - データベース初期化
- `update_database.py` - データベース更新
- `backtest_prediction.py` - 予想バックテスト
- `場攻略情報インポート.py` - 場攻略情報インポート

**最新版データ補完スクリプト:**
- `補完_レース詳細データ_改善版v4.py` - レース詳細補完 (最新版)
- `補完_決まり手データ_改善版.py` - 決まり手補完 (最新版)
- `補完_天候データ_改善版.py` - 天候データ補完 (最新版)
- `収集_RDMDB潮位データ_改善版.py` - RDMDB潮位データ収集 (最新版)
- `収集_オリジナル展示_自動実行.py` - オリジナル展示自動実行
- `収集_オリジナル展示_最新.py` - オリジナル展示最新
- `収集_結果データ_最新.py` - 結果データ最新
- `収集_2020年結果データ.py` - 2020年結果データ

**最新版フェッチャー:**
- `fetch_parallel_v6.py` - 並列フェッチv6 (最新版)
- `fetch_upcoming_races.py` - 今後のレース取得

**ユーティリティ:**
- `check_settings.py` - 設定チェック
- `check_venues.py` - 会場チェック
- `check_schema.py` - スキーマチェック
- `check_db_structure.py` - DB構造チェック
- `check_weather_data.py` - 天候データチェック
- `backup_project.py` - プロジェクトバックアップ (今回作成)

**分析ツール:**
- `analyze_collected_data.py` - 収集データ分析
- `analyze_missing_data.py` - 欠損データ分析
- `analyze_top_racers.py` - トップレーサー分析
- `analyze_win_rate.py` - 勝率分析

**進捗監視:**
- `check_collection_progress.py` - 収集進捗チェック
- `check_data_dates.py` - データ日付チェック
- `check_data_progress.py` - データ進捗チェック
- `check_db_status.py` - DBステータスチェック
- `check_db_quick.py` - DB クイックチェック
- `check_monthly_data.py` - 月次データチェック
- `check_progress.py` - 進捗チェック
- `check_system_status.py` - システムステータスチェック
- `monitor_parallel.py` - 並列処理監視
- `monitor_progress.py` - 進捗監視

**品質管理:**
- `comprehensive_logic_check.py` - 総合ロジックチェック
- `generate_data_quality_report.py` - データ品質レポート生成
- `measure_bottleneck.py` - ボトルネック計測

**その他:**
- `estimate_storage.py` - ストレージ推定
- `reanalyze_all.py` - 全再分析

---

## 失敗事例と改善点

### 1. RDMDB潮位データ収集の失敗

**問題:**
- 当初、RDMDBサイトから潮位データを取得する際、URLの仕様を正しく理解していなかった
- CSVパース処理が不完全で、データ形式の違いに対応できなかった
- エラーハンドリングが不十分で、一部のファイルが失敗すると全体が止まった

**試行錯誤:**
1. `収集_RDMDB潮位データ.py` - 初期版 (URL取得失敗)
2. `収集_RDMDB潮位データ_新URL対応.py` - URL修正版 (パース失敗)
3. `test_rdmdb_parser_single.py` - 単一ファイルテスト
4. `test_rdmdb_parser_3files.py` - 3ファイルテスト
5. `debug_rdmdb_parser.py` - パーサーデバッグ
6. `収集_RDMDB潮位データ_改善版.py` - **最終成功版**

**改善策:**
- URLパターンを正しく解析し、正規表現で抽出
- 複数のCSV形式に対応するパーサー実装
- エラー時も処理を継続し、失敗したファイルをログに記録
- リトライ機構の実装

**教訓:**
- 外部サイトのスクレイピングは仕様変更に脆弱
- まず小規模テストで検証してから本番実行
- エラーハンドリングは必須

### 2. 決まり手データ補完の試行錯誤

**問題:**
- 決まり手データが大量のレースに欠損していた
- 単純な逐次処理では完了までに数日かかる見込み
- データベースロックが頻発

**試行錯誤:**
1. `補完_決まり手データ.py` - 初期版 (遅い)
2. `補完_決まり手データ_高速版.py` - 高速化試行 (ロック問題)
3. `test_kimarite_v2.py` - v2テスト
4. `test_kimarite_fast.py` - 高速版テスト
5. `補完_決まり手データ_改善版.py` - **最終成功版**

**改善策:**
- バッチ処理でDBアクセスを削減
- トランザクション管理の最適化
- プログレス表示で進捗を可視化
- 並列処理の適切な制御

**教訓:**
- 大量データ処理は最初から性能を考慮すべき
- データベースアクセスパターンの最適化が重要
- プログレス表示でユーザー体験向上

### 3. レース詳細データ補完の段階的改善

**問題:**
- レース詳細データに複数種類の欠損があった
- 展示タイム、スタートタイミングなど多様なデータ
- APIレスポンスの形式が微妙に異なる

**試行錯誤:**
1. `補完_レース詳細データ.py` - 初期版
2. `補完_レース詳細データ_改善版.py` - 改善版v1
3. `補完_レース詳細データ_改善版v2.py` - 改善版v2
4. `補完_レース詳細データ_改善版v3.py` - 改善版v3
5. `補完_レース詳細データ_改善版v4.py` - **最終版**

**改善策:**
- 各種データタイプに対応する汎用パーサー
- NULL値のハンドリング強化
- レスポンスキャッシュで API負荷軽減
- エラー時の詳細ログ

**教訓:**
- 複雑な処理は段階的に改善
- バージョン管理で進化を追跡
- 最終版以外は削除してOK

### 4. 広島会場データ取得の失敗

**問題:**
- 広島会場のデータだけ取得失敗が頻発
- HTML構造が他の会場と微妙に異なっていた

**試行錯誤:**
1. `debug_failed_hiroshima.py` - 失敗原因調査
2. `debug_hiroshima_detailed.py` - 詳細デバッグ
3. `再パース_Hiroshima_2ファイル.py` - 再パース試行
4. 最終的に汎用パーサーで対応

**改善策:**
- 会場ごとの HTML 差異を吸収するロバストなパーサー
- 失敗時に HTML をダンプしてデバッグ
- 特定会場だけ特殊処理を追加

**教訓:**
- 公式サイトでも会場によってHTMLが違う
- エッジケースへの対応が重要
- デバッグ情報の出力は必須

### 5. 展示データ保存の2フェーズアプローチ失敗

**問題:**
- 展示データを2段階で保存しようとした
- Phase 1: 基本情報、Phase 2: 詳細情報
- フェーズ間の整合性が取れない

**試行錯誤:**
1. `test_exhibition_save.py` - 展示保存テスト
2. `test_two_phase_save.py` - 2フェーズ保存テスト
3. `test_exhibition_time_save.py` - タイム保存テスト
4. 最終的に1フェーズで全保存に変更

**改善策:**
- データ取得と保存を1トランザクションで実行
- 部分的な保存を避ける
- 失敗時は全ロールバック

**教訓:**
- 複雑な設計は失敗しやすい
- シンプルなアプローチの方が堅牢
- トランザクションの境界を明確に

---

## 現在の運用スクリプト

### データ収集パイプライン

1. **レース結果収集:** `収集_結果データ_最新.py`
2. **レース詳細補完:** `補完_レース詳細データ_改善版v4.py`
3. **決まり手補完:** `補完_決まり手データ_改善版.py`
4. **天候データ補完:** `補完_天候データ_改善版.py`
5. **潮位データ収集:** `収集_RDMDB潮位データ_改善版.py`
6. **展示データ収集:** `収集_オリジナル展示_最新.py`

### 監視・分析

- **進捗確認:** `check_progress.py`, `check_system_status.py`
- **データ品質:** `generate_data_quality_report.py`
- **欠損チェック:** `analyze_missing_data.py`

### バックテスト・予想

- **予想精度検証:** `backtest_prediction.py`

### UI

- **Streamlit UI:** `ui/app.py`

---

## 削除実行計画

### ステップ1: バックアップ確認

- [x] バックアップ作成完了: `C:\Users\seizo\Desktop\BoatRace_backup_20251102`
- [x] バックアップサイズ: 1,204.69 MB (397ファイル)

### ステップ2: テスト・デバッグスクリプト削除

合計約50ファイルを削除予定

### ステップ3: 旧バージョンスクリプト削除

合計約30ファイルを削除予定

### ステップ4: 一時調査スクリプト削除

合計約40ファイルを削除予定

### ステップ5: マイグレーション・初期化スクリプト削除

合計約15ファイルを削除予定

### 推定削減量

- 削除予定ファイル数: 約135ファイル
- 保持ファイル数: 約60ファイル
- ディスク削減: 推定50-100MB

---

## 注意事項

1. **必ずバックアップを確認してから削除**
2. **削除は段階的に実施** (カテゴリ別に)
3. **削除後は動作確認**を実施
4. **疑わしい場合は保留**して後で再検討

---

## 次のアクション

1. このレポートを確認
2. 削除対象の承認
3. 段階的な削除実行
4. 動作確認
5. ドキュメント更新
