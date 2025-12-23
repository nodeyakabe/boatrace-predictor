# 不要ファイル削除レポート

**実行日時**: 2025-12-18 11:48

## 📊 削除結果サマリー

### 削減容量

**合計削減: 1.73GB**

### カテゴリ別削除内容

#### 1. 大容量ディレクトリ (1.68GB)

| ディレクトリ | サイズ | 内容 |
|-------------|--------|------|
| temp_extract | 1.29GB | 一時展開ファイル |
| rdmdb_tide_data | 375.23MB | 潮汐生データ |
| cleanup_20251210 | 4.03MB | 古いバックアップ |
| temp | 3.52MB | 一時ファイル |

#### 2. ログファイル (64.54MB)

| ファイル | サイズ |
|---------|--------|
| backtest_output.txt | 31.79MB |
| conditional_v1_eval.txt | 14.63MB |
| top3_coverage.txt | 14.63MB |
| v2_eval_output.txt | 2.96MB |
| log_oct_2024.txt | 537.73KB |
| その他ログファイル | 20KB |

#### 3. HTMLファイル (515KB)

| ファイル | サイズ |
|---------|--------|
| debug_odds_*.html | 176.51KB |
| page_source.html | 148.12KB |
| race_schedule_page.html | 47.62KB |
| rdmdb_download_page.html | 52.07KB |
| その他HTMLファイル | 90KB |

#### 4. その他 (558KB)

| ファイル | サイズ |
|---------|--------|
| archive_20251118_165053.zip | 490.37KB |
| missing_data_log.txt | 67.08KB |
| missing_races.txt | 1.04KB |

---

## 📈 削除前後の比較

| 項目 | 削除前 | 削除後 | 削減 |
|------|--------|--------|------|
| プロジェクト総容量 | 約17GB | 15GB | **1.73GB** |
| 最大ディレクトリ | rdmdb_tide_data (376MB) | data (15GB) | - |
| バックアップ容量 | 5.4MB | 392KB | 5.0MB |

---

## 🎯 削除されたファイル一覧

### 大容量ディレクトリ (4件)
- ✅ 受け渡し/temp_extract/
- ✅ rdmdb_tide_data/
- ✅ backups/cleanup_20251210/
- ✅ temp/

### ログファイル (11件)
- ✅ backtest_output.txt
- ✅ conditional_v1_eval.txt
- ✅ top3_coverage.txt
- ✅ v2_eval_output.txt
- ✅ log_oct_2024.txt
- ✅ cfc743_output.txt
- ✅ error_traceback.txt
- ✅ output.txt
- ✅ output_weather_impact.txt
- ✅ output_weather_patterns.txt
- ✅ nov_dec_analysis.txt

### HTMLファイル (10件)
- ✅ debug_odds_02_20251117_1.html
- ✅ debug_odds_02_20251118_1.html
- ✅ page_source.html
- ✅ exhibition_table3.html
- ✅ jodc_top_page.html
- ✅ race_schedule_page.html
- ✅ rdmdb_download_page.html
- ✅ rdmdb_new_page.html
- ✅ monthly_schedule.html
- ✅ first_row.html

### その他 (3件)
- ✅ archive_20251118_165053.zip
- ✅ missing_data_log.txt
- ✅ missing_races.txt

---

## 📂 現在の主要ディレクトリサイズ

| ディレクトリ | サイズ | 説明 |
|-------------|--------|------|
| data/ | 15GB | データベース（保持） |
| results/ | 82MB | 結果データ（保持） |
| models/ | 67MB | 学習済みモデル（保持） |
| logs/ | 22MB | 最新ログ（保持） |
| src/ | 5.5MB | ソースコード（保持） |
| docs/ | 3.9MB | ドキュメント（保持） |
| scripts/ | 3.6MB | スクリプト（保持） |
| _archive/ | 2.5MB | アーカイブ（保持） |
| ui/ | 1.4MB | UI（保持） |
| scripts_archive/ | 1.1MB | スクリプトアーカイブ（保持） |
| backups/ | 392KB | バックアップ（削減済み） |

---

## ✅ 削除の安全性確認

### 削除が安全だった理由

1. **temp_extract** (1.29GB)
   - 受け渡し完了済みの一時ファイル
   - 元データはGitに保存済み

2. **rdmdb_tide_data** (375MB)
   - 潮汐データはDBに取り込み済み（7,844件確認）
   - 生データファイルは不要

3. **バックアップ** (5.0MB)
   - 1週間以上前のバックアップ
   - Gitに履歴が残っている

4. **ログファイル** (64MB)
   - 一時的な分析結果
   - 必要なら再生成可能

5. **HTMLファイル** (515KB)
   - デバッグ用の一時ファイル
   - 再取得可能

---

## 🔍 今後の推奨事項

### さらなる容量削減の可能性

1. **_archive/** (2.5MB)
   - 内容を確認して不要なら削除

2. **scripts_archive/** (1.1MB)
   - 使用していないスクリプトなら削除

3. **logs/** (22MB)
   - 古いログファイルを定期的にクリーンアップ

### 定期クリーンアップの推奨

- **月次**: temp/, logs/内の古いファイル
- **四半期**: バックアップディレクトリの整理
- **年次**: アーカイブディレクトリの見直し

---

**実行スクリプト**: cleanup_auto.py
**計画書**: cleanup_plan.md
