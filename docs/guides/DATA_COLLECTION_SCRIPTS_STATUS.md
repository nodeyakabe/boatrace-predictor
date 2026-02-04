# データ収集スクリプト 状態一覧

**最終更新**: 2026-02-04
**目的**: 各スクリプトの状態と推奨度を明確化

---

## 凡例

| 状態 | 意味 |
|------|------|
| **推奨** | ベストプラクティス準拠、積極的に使用可 |
| **使用可** | 基本機能は問題なし、改善の余地あり |
| **要注意** | 特定の問題あり、使用時は注意 |
| **非推奨** | 旧版または問題あり、改善版を使用 |
| **アーカイブ** | 使用禁止、参照のみ |

---

## 過去データ収集スクリプト

### マスタースクリプト

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `auto_fetch_2020_2025.py` | **推奨** | 2020-2025年全データ自動収集 | 完成度高い |
| `master_automation_2020_2025.py` | **使用可** | 完全自動化マスター | 複数タスクの連携 |

### 並列データ収集

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `fetch_historical_data_parallel.py` | **要注意** | 特定期間並列収集 | 開催スケジュール未使用 |
| `fetch_to_csv_parallel_improved.py` | **推奨** | CSV並列出力（改善版） | スケジュール最適化済み |
| `fetch_to_csv_parallel_optimized.py` | **推奨** | CSV並列出力（最適化版） | さらなる改善 |
| `fetch_to_csv_parallel.py` | **非推奨** | CSV並列出力（旧版） | improved版を使用 |

### 直前情報収集

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `collect_beforeinfo_2020_2023_optimized.py` | **要注意** | 直前情報収集（最適化版） | DELETE+INSERT使用 |
| `fetch_today_beforeinfo.py` | **要注意** | 本日の直前情報 | 開催スケジュール未確認 |

### オッズ収集

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `fetch_odds_parallel_safe.py` | **推奨** | 3連単オッズ並列収集 | WALモード、安全設計 |
| `fetch_exacta_odds.py` | **使用可** | 2連単オッズ収集 | Selenium使用 |

---

## 補完スクリプト

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `補完_決まり手データ_改善版.py` | **推奨** | 決まり手補完 | 16並列、バッチ処理 |
| `補完_レース詳細データ_改善版v4.py` | **推奨** | レース詳細補完 | エラー分類あり |
| `補完_払戻金データ.py` | **使用可** | 払戻金補完 | 基本機能OK |
| `fill_missing_weather_data.py` | **使用可** | 気象データ補完 | 8並列 |
| `補完_決まり手データ_v3.py` | **非推奨** | 決まり手補完（旧版） | 改善版を使用 |
| `補完_wave_height_2024.py` | **使用可** | 波高補完（2024特化） | 期間限定用 |
| `補完_race_conditions_2020_2023.py` | **使用可** | レース条件補完 | 期間限定用 |
| `補完_2021_2023_欠損データ.py` | **使用可** | 欠損データ一括補完 | 期間限定用 |
| `補完_2021_2023_一括実行.py` | **使用可** | 一括実行 | 複数補完の連携 |
| `補完_未処理月のみ実行.py` | **使用可** | 未処理月のみ | 再開機能 |
| `補完_順次実行_簡易版.py` | **使用可** | 順次実行 | シンプル版 |
| `補完_順次実行_スキップ機能付き.py` | **使用可** | 順次実行 | スキップ機能 |

---

## 特殊データ収集

### 潮位データ

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `収集_潮位データ_最新.py` | **使用可** | 潮位データ収集 | ブラウザ自動化 |

### 統計指標

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `build_indicator_stats.py` | **推奨** | 統計指標生成 | 年度別対応 |

### 選手マスタ

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `update_racer_master.py` | **使用可** | 選手マスタ更新 | 月次推奨 |

### 展示データ

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `collect_exhibition_2020_2024.py` | **使用可** | 展示データ月別収集 | 進捗保存機能 |
| `fetch_exhibition_data_to_csv.py` | **使用可** | 展示データCSV出力 | 単体使用 |
| `collect_race_conditions_2024_optimized.py` | **使用可** | レース条件収集 | 2024特化 |
| `fetch_race_conditions_to_csv.py` | **使用可** | レース条件CSV出力 | 単体使用 |
| `fetch_race_details_to_csv.py` | **使用可** | レース詳細CSV出力 | 単体使用 |

---

## バルク処理スクリプト

| スクリプト | 状態 | 説明 | 改善点 |
|-----------|------|------|--------|
| `bulk_missing_data_fetch_parallel.py` | **使用可** | 欠損データ一括取得 | 並列処理 |

---

## テスト・デバッグ用

| スクリプト | 状態 | 説明 | 備考 |
|-----------|------|------|------|
| `debug_kimarite.py` | テスト | 決まり手デバッグ | 開発用 |
| `debug_boatcast.py` | テスト | Boatcastデバッグ | 開発用 |
| `debug_boaters.py` | テスト | Boatersデバッグ | 開発用 |
| `test_venue_scraper.py` | テスト | 会場スクレイパーテスト | 開発用 |
| `test_all_venues.py` | テスト | 全会場テスト | 開発用 |
| `test_official_tenji.py` | テスト | 公式展示テスト | 開発用 |
| `test_boatcast_scraping.py` | テスト | Boatcastテスト | 開発用 |
| `test_naruto_tide_html.py` | テスト | 鳴門潮位テスト | 開発用 |
| `simple_test.py` | テスト | シンプルテスト | 開発用 |
| `investigate_boatcast.py` | 調査 | Boatcast調査 | 開発用 |
| `investigate_boatcast_detail.py` | 調査 | Boatcast詳細調査 | 開発用 |

---

## 展示データ収集（試験的）

| スクリプト | 状態 | 説明 | 備考 |
|-----------|------|------|------|
| `fetch_boatcast_tenji.py` | 試験的 | Boatcast展示取得 | 外部サイト依存 |
| `fetch_boaters_tenji.py` | 試験的 | Boaters展示取得 | 外部サイト依存 |
| `fetch_boaters_tenji_v2.py` | 試験的 | Boaters展示取得v2 | 外部サイト依存 |
| `collect_original_tenji.py` | 試験的 | オリジナル展示収集 | 前日のみ取得可 |
| `collect_and_save_tenji.py` | 試験的 | 展示収集・保存 | 組み合わせ |
| `save_tenji_to_db.py` | 試験的 | 展示DB保存 | 単体機能 |
| `fetch_venue_specific_data.py` | 試験的 | 会場独自データ | 会場依存 |

---

## アーカイブ済み（使用禁止）

以下のスクリプトは `archive/deprecated/` に移動済みです。

| スクリプト | 理由 | 代替 |
|-----------|------|------|
| `fetch_historical_data.py` | 旧版 | `fetch_historical_data_parallel.py` |
| `fetch_historical_odds.py` | 旧版 | `fetch_odds_parallel_safe.py` |
| `fetch_historical_odds_simple.py` | 旧版 | `fetch_odds_parallel_safe.py` |
| `fetch_odds_parallel.py` | 旧版 | `fetch_odds_parallel_safe.py` |
| `fetch_odds_fast.py` | 旧版 | `fetch_odds_parallel_safe.py` |
| `fetch_odds_2020_2024_background.py` | 旧版 | `fetch_odds_parallel_safe.py` |
| `collect_beforeinfo_2020_2023.py` | 旧版 | `collect_beforeinfo_2020_2023_optimized.py` |
| `補完_決まり手データ_シンプル版.py` | 旧版 | `補完_決まり手データ_改善版.py` |
| `補完_決まり手データ_v2.py` | 旧版 | `補完_決まり手データ_改善版.py` |
| `test_kimarite_fetch.py` | テスト | 開発用 |
| `auto_collect_beforeinfo_after_advance.py` | 旧版 | 新方式に移行 |
| `collect_parts_exchange.py` | 旧版 | 別方式に統合 |
| `complement_2020_2023_beforeinfo_and_predictions.py` | 旧版 | 分離実行に変更 |
| `fetch_original_tenji_daily.py` | 旧版 | 新方式に移行 |
| `fill_missing_weather_2022.py` | 年度特化 | `fill_missing_weather_data.py` |
| `import_final_diff.py` | 一時的 | 完了済み |
| `import_missing_data.py` | 一時的 | 完了済み |
| `import_missing_data_fixed.py` | 一時的 | 完了済み |
| `import_remaining_data.py` | 一時的 | 完了済み |
| `update_database.py` | 旧版 | マイグレーションに移行 |
| `update_historical_odds.py` | 旧版 | `fetch_odds_parallel_safe.py` |
| `worker_missing_data.py` | 旧版 | 新方式に移行 |
| `worker_tenji_collection.py` | 旧版 | 新方式に移行 |

### 年度特化スクリプト（archive/year_specific/）

| スクリプト | 理由 |
|-----------|------|
| `collect_2024_all_data.py` | 2024年特化、汎用版を使用 |
| `collect_2024_missing_data.py` | 2024年特化、汎用版を使用 |
| `fetch_historical_data_2024.py` | 2024年特化、汎用版を使用 |

---

## 改善優先度

### 高優先度（重大な問題）

| スクリプト | 問題 | 改善提案 |
|-----------|------|----------|
| `fetch_historical_data_parallel.py` | 開催スケジュール未使用 | ScheduleScraper導入 |
| `collect_beforeinfo_2020_2023_optimized.py` | DELETE+INSERT使用 | UPSERT（INSERT OR REPLACE）に変更 |
| `fetch_today_beforeinfo.py` | 開催会場ハードコード | ScheduleScraper使用 |

### 中優先度（改善推奨）

| スクリプト | 問題 | 改善提案 |
|-----------|------|----------|
| `fill_missing_weather_data.py` | 期間ハードコード | コマンドライン引数化 |
| `補完_払戻金データ.py` | ProcessPoolExecutor使用 | ThreadPoolExecutorに変更（I/Oバウンド） |

### 低優先度（軽微）

| スクリプト | 問題 | 改善提案 |
|-----------|------|----------|
| `update_racer_master.py` | ログ不足 | ログファイル出力追加 |

---

## 使用ガイド

### 過去全データ収集

```bash
# 推奨: マスタースクリプト
python scripts/data_collection/auto_fetch_2020_2025.py

# 代替: CSV方式（DB負荷なし）
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2020-01-01 --end 2025-12-31 --output data/csv/all
```

### 特定期間収集

```bash
# CSV方式（推奨）
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2024-01-01 --end 2024-12-31 --output data/csv/2024

# 直接DB投入（要注意：開催スケジュール未使用）
python scripts/data_collection/fetch_historical_data_parallel.py \
  --start 2024-01-01 --end 2024-12-31
```

### 補完処理

```bash
# 決まり手
python scripts/data_collection/補完_決まり手データ_改善版.py

# レース詳細
python scripts/data_collection/補完_レース詳細データ_改善版v4.py

# 払戻金
python scripts/data_collection/補完_払戻金データ.py
```

### オッズ収集

```bash
# 3連単
python scripts/data_collection/fetch_odds_parallel_safe.py \
  --start 2024-01-01 --end 2024-12-31

# 2連単
python scripts/data_collection/fetch_exacta_odds.py \
  --start 2024-01-01 --end 2024-12-31
```

---

## 関連ドキュメント

- [DATA_COLLECTION_TROUBLESHOOTING.md](DATA_COLLECTION_TROUBLESHOOTING.md) - トラブルシューティング
- [DATA_COLLECTION_BEST_PRACTICES.md](DATA_COLLECTION_BEST_PRACTICES.md) - ベストプラクティス
- [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) - マスターガイド

---

**最終更新**: 2026-02-04
