# 不要ファイル削除計画

## 📊 現在の容量状況

| ディレクトリ/ファイル | サイズ | 削除候補 | 理由 |
|----------------------|--------|----------|------|
| **受け渡し/temp_extract/** | 1.3GB | ✅ | 一時展開ファイル（受け渡し完了済み） |
| **rdmdb_tide_data/** | 376MB | ✅ | 潮汐生データ（DBに取り込み済みなら不要） |
| **backups/cleanup_20251210/** | 5.0MB | ✅ | 古いクリーンアップバックアップ |
| **temp/** | 3.8MB | ✅ | 一時ファイル |
| **_archive/** | 2.5MB | ⚠️ | アーカイブ（内容確認後） |
| **scripts_archive/** | 1.1MB | ⚠️ | スクリプトアーカイブ（内容確認後） |
| **backtest_output.txt** | 32MB | ✅ | バックテスト出力ログ |
| **conditional_v1_eval.txt** | 15MB | ✅ | 評価ログ |
| **top3_coverage.txt** | 15MB | ✅ | カバレッジログ |
| **v2_eval_output.txt** | 3.0MB | ✅ | 評価ログ |
| **HTMLファイル群** | ~500KB | ✅ | デバッグ用HTML |
| **画像ファイル** | ~500KB | ⚠️ | スクリーンショット（必要なら残す） |
| **archive_20251118_165053.zip** | 492KB | ✅ | 古いアーカイブ |

### 削除による削減見込み

- **確実に削除可能**: 約1.75GB
- **内容確認後削除**: 約3.6MB
- **合計削減見込み**: 約1.75GB

---

## 🗑️ 削除対象の詳細

### 優先度: 高（即削除推奨）

#### 1. 受け渡し/temp_extract/ (1.3GB)
```
理由: 一時展開ディレクトリ、受け渡し完了済み
```

#### 2. rdmdb_tide_data/ (376MB)
```
理由: 潮汐の生データ、DBに取り込み済みなら不要
確認: race_tide_dataテーブルにデータがあるか
```

#### 3. backtest_output.txt (32MB)
```
理由: バックテスト出力ログ、古い評価結果
```

#### 4. conditional_v1_eval.txt (15MB)
```
理由: 評価ログ、古いバージョン
```

#### 5. top3_coverage.txt (15MB)
```
理由: カバレッジログ、一時的な分析結果
```

#### 6. backups/cleanup_20251210/ (5.0MB)
```
理由: 12月10日のクリーンアップバックアップ、1週間以上経過
```

#### 7. temp/ (3.8MB)
```
理由: 一時ファイルディレクトリ
```

#### 8. v2_eval_output.txt (3.0MB)
```
理由: V2評価ログ
```

---

### 優先度: 中（内容確認後削除）

#### 9. _archive/ (2.5MB)
```
理由: アーカイブディレクトリ
確認: 必要なファイルがないか確認
```

#### 10. scripts_archive/ (1.1MB)
```
理由: スクリプトアーカイブ
確認: 現在使っていないスクリプトか確認
```

#### 11. HTMLファイル群
```
- debug_odds_*.html
- page_source.html
- exhibition_table3.html
- jodc_top_page.html
- race_schedule_page.html
など
理由: デバッグ用の一時ファイル
```

#### 12. archive_20251118_165053.zip (492KB)
```
理由: 11月のアーカイブ、1ヶ月以上経過
```

---

### 優先度: 低（保留）

#### 画像ファイル
```
- jodc_top_page.png (237KB)
- rdmdb_new_page.png (96KB)
理由: ドキュメント用の可能性、サイズ小
→ 必要なら残す
```

#### 小さいCSVファイル
```
- missing_*.csv
理由: 欠損データ分析結果、サイズ小
→ 参考資料として残す
```

---

## ✅ 実行手順

### ステップ1: 潮汐データの確認

潮汐データがDBに取り込まれているか確認:
```bash
python -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); print('潮汐データ件数:', conn.execute('SELECT COUNT(*) FROM race_tide_data').fetchone()[0]); conn.close()"
```

件数が多ければ（10,000件以上）、rdmdb_tide_data/は削除OK

### ステップ2: アーカイブ内容の確認

```bash
# _archiveの内容確認
ls -lh _archive/

# scripts_archiveの内容確認
ls -lh scripts_archive/
```

### ステップ3: 削除実行

確認後、以下のコマンドで削除:

```bash
# 大容量ディレクトリの削除
rm -rf 受け渡し/temp_extract/
rm -rf rdmdb_tide_data/  # 潮汐データ確認後
rm -rf backups/cleanup_20251210/
rm -rf temp/

# ログファイルの削除
rm -f backtest_output.txt
rm -f conditional_v1_eval.txt
rm -f top3_coverage.txt
rm -f v2_eval_output.txt

# HTMLファイルの削除
rm -f debug_odds_*.html
rm -f page_source.html
rm -f exhibition_table3.html
rm -f jodc_top_page.html
rm -f race_schedule_page.html
rm -f rdmdb_download_page.html
rm -f rdmdb_new_page.html
rm -f monthly_schedule.html
rm -f first_row.html

# アーカイブの削除（内容確認後）
rm -f archive_20251118_165053.zip

# 小さいログファイル
rm -f log_oct_2024.txt
rm -f cfc743_output.txt
rm -f error_traceback.txt
rm -f output.txt
rm -f output_weather_*.txt
```

### ステップ4: 削減効果の確認

```bash
du -sh .
```

---

## ⚠️ 削除前の注意事項

1. **重要なファイルは削除しない**
   - data/ (データベース)
   - src/ (ソースコード)
   - models/ (学習済みモデル)
   - docs/ (ドキュメント)

2. **バックアップ確認**
   - Gitにコミット済みか確認
   - 重要なファイルは別途バックアップ

3. **段階的に削除**
   - まず小さいファイルから
   - 大容量ディレクトリは確認後に削除

---

**作成日**: 2025-12-18
