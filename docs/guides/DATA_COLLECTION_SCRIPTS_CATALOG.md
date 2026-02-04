# データ収集スクリプト完全カタログ

**最終更新**: 2026-01-15
**対象**: scripts/data_collection/ ディレクトリの全44スクリプト

---

## 📋 目次

1. [推奨スクリプト（現役）](#推奨スクリプト現役)
2. [旧版・非推奨（アーカイブ候補）](#旧版非推奨アーカイブ候補)
3. [スクリプト詳細](#スクリプト詳細)
4. [整理方針](#整理方針)

---

## 推奨スクリプト（現役）

### 過去データバルク収集（6スクリプト）

| ファイル名 | 用途 | 特徴 | 優先度 |
|-----------|------|------|--------|
| `auto_fetch_2020_2025.py` | 2020-2025年マスター自動収集 | 複数タスク順次実行、15-25時間 | ⭐⭐⭐ |
| `fetch_historical_data_parallel.py` | 過去データ高速並列収集 | 10-15倍高速、8-12ワーカー | ⭐⭐⭐ |
| `collect_beforeinfo_2020_2023_optimized.py` | 直前情報収集（最適化版） | 12ワーカー、バッチ処理、再開機能 | ⭐⭐⭐ |
| `bulk_missing_data_fetch_parallel.py` | 不足データ並列バルク収集 | 並列処理 | ⭐⭐ |
| `collect_race_conditions_2024_optimized.py` | 気象・レース条件収集（最適化版） | 12並列ワーカー | ⭐⭐ |
| `master_automation_2020_2025.py` | マスター自動化スクリプト | ログ付き順次実行 | ⭐⭐ |

---

### CSV方式（DB非依存）（3スクリプト）

| ファイル名 | 用途 | 特徴 | 優先度 |
|-----------|------|------|--------|
| `fetch_to_csv_parallel_improved.py` | CSV並列出力（改善版） | スケジュール最適化、50%削減 | ⭐⭐⭐ |
| `fetch_to_csv_parallel_optimized.py` | CSV並列出力（最適化版） | さらなる改善 | ⭐⭐⭐ |
| `fetch_to_csv_parallel.py` | CSV並列出力（基本版） | ProcessPoolExecutor、12ワーカー | ⭐ |

**推奨順**: improved版 > optimized版 > 基本版

---

### 補完スクリプト（10スクリプト）

| ファイル名 | 用途 | 特徴 | 優先度 |
|-----------|------|------|--------|
| `補完_決まり手データ_改善版.py` | 決まり手補完（改善版） | 16ワーカー、バッチ更新、リトライ | ⭐⭐⭐ |
| `補完_レース詳細データ_改善版v4.py` | レース詳細補完 | ST時間、実走コース、チルト | ⭐⭐⭐ |
| `補完_払戻金データ.py` | 払戻金補完 | ProcessPoolExecutor | ⭐⭐⭐ |
| `fill_missing_weather_data.py` | 気象データ補完（汎用） | 天候、風、水温 | ⭐⭐⭐ |
| `collect_parts_exchange.py` | 部品交換データ収集 | CSV出力、レポート生成 | ⭐⭐ |
| `import_missing_data_fixed.py` | 不足データインポート（修正版） | バグ修正済み | ⭐⭐ |
| `import_remaining_data.py` | 残りデータインポート | - | ⭐ |
| `import_final_diff.py` | 最終差分インポート | - | ⭐ |
| `worker_missing_data.py` | 不足データ補完ワーカー | - | ⭐ |
| `complement_2020_2023_beforeinfo_and_predictions.py` | 直前情報と予測補完 | マスタースクリプト | ⭐ |

---

### オッズ収集（7スクリプト）

| ファイル名 | 用途 | 特徴 | 優先度 |
|-----------|------|------|--------|
| `fetch_odds_parallel_safe.py` | 並列オッズ収集（安全版） | エラー処理強化 | ⭐⭐⭐ |
| `fetch_exacta_odds.py` | 2連単オッズ収集 | Selenium使用、3秒間隔 | ⭐⭐⭐ |
| `update_historical_odds.py` | 過去オッズ更新 | - | ⭐⭐ |
| `fetch_odds_fast.py` | 高速オッズ収集 | - | ⭐ |
| `fetch_historical_odds.py` | 過去オッズ収集 | - | ⭐ |
| `fetch_historical_odds_simple.py` | 過去オッズ収集（シンプル版） | - | ⭐ |
| `fetch_odds_2020_2024_background.py` | 2020-2024年オッズ収集 | バックグラウンド実行 | ⭐ |

**推奨**: safe版とexacta_odds.pyを使用

---

### 日次・特殊用途（9スクリプト）

| ファイル名 | 用途 | 特徴 | 優先度 |
|-----------|------|------|--------|
| `fetch_today_beforeinfo.py` | 本日の直前情報 | 日次実行用 | ⭐⭐⭐ |
| `build_indicator_stats.py` | 統計指標生成 | 逃げ率、攻め率等 | ⭐⭐⭐ |
| `update_racer_master.py` | 選手マスタ更新 | 月次実行推奨 | ⭐⭐⭐ |
| `fetch_original_tenji_daily.py` | 日次展示情報収集 | - | ⭐⭐ |
| `worker_tenji_collection.py` | 展示データ収集ワーカー | - | ⭐⭐ |
| `auto_collect_beforeinfo_after_advance.py` | advance予測後自動収集 | 監視機能付き | ⭐⭐ |
| `update_database.py` | データベース更新 | - | ⭐ |
| `収集_潮位データ_最新.py` | 潮位データ収集（最新版） | 海水面9場対象 | ⭐⭐ |
| `test_kimarite_fetch.py` | 決まり手取得テスト | テストスクリプト | ⭐ |

---

## 旧版・非推奨（アーカイブ候補）

### 並列化前の旧版（使用非推奨）

| ファイル名 | 理由 | 代替スクリプト |
|-----------|------|---------------|
| `fetch_historical_data.py` | 並列化なし（遅い） | `fetch_historical_data_parallel.py` |
| `collect_beforeinfo_2020_2023.py` | 最適化前（8ワーカー） | `collect_beforeinfo_2020_2023_optimized.py` |

---

### 改善版が存在する旧版

| ファイル名 | 理由 | 代替スクリプト |
|-----------|------|---------------|
| `補完_決まり手データ_シンプル版.py` | 逐次処理（遅い） | `補完_決まり手データ_改善版.py` |
| `補完_決まり手データ_v2.py` | LIMIT 100制限、テスト用 | `補完_決まり手データ_改善版.py` |
| `fetch_odds_parallel.py` | エラー処理不足 | `fetch_odds_parallel_safe.py` |
| `import_missing_data.py` | バグあり | `import_missing_data_fixed.py` |
| `fill_missing_weather_2022.py` | 特定年度専用 | `fill_missing_weather_data.py` |

---

### 特定用途・一時的スクリプト

| ファイル名 | 理由 | 備考 |
|-----------|------|------|
| `collect_2024_all_data.py` | 2024年専用ラッパー | 特定年度のみ |
| `collect_2024_missing_data.py` | 2024年不足データ専用 | 特定年度のみ |
| `fetch_historical_data_2024.py` | 2024年専用ラッパー | 単純呼び出し |

---

## スクリプト詳細

### 推奨スクリプトの詳細仕様

#### fetch_historical_data_parallel.py

**機能**:
- 過去データの高速並列収集
- レース基本情報、選手情報、結果、オッズを一括取得

**技術仕様**:
- ThreadPoolExecutor使用
- 8-12ワーカー（デフォルト: 8）
- 1日あたり30秒-1分
- 従来版の10-15倍高速

**使用例**:
```bash
python scripts/data_collection/fetch_historical_data_parallel.py \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --workers 12
```

**パラメータ**:
- `--start`: 開始日（YYYY-MM-DD）
- `--end`: 終了日（YYYY-MM-DD）
- `--workers`: 並列ワーカー数

**出力**: 直接DBに保存

---

#### fetch_to_csv_parallel_improved.py

**機能**:
- CSV経由の大量データ収集（DB負荷なし）
- 事前にレーススケジュール取得（タスク数50%削減）
- 50タスクごとに自動保存

**技術仕様**:
- ProcessPoolExecutor使用
- 12ワーカー（デフォルト）
- CSV出力のみ（DB非依存）
- スケジュール事前取得による最適化

**使用例**:
```bash
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --output data/csv/2020 \
  --workers 12
```

**パラメータ**:
- `--start`: 開始日（YYYY-MM-DD）
- `--end`: 終了日（YYYY-MM-DD）
- `--output`: CSV出力ディレクトリ
- `--workers`: 並列ワーカー数

**出力ファイル**:
- `races.csv`: レース基本情報
- `entries.csv`: 出走表
- `race_conditions.csv`: レース条件
- `race_details.csv`: 展示情報
- `results.csv`: レース結果
- `payouts.csv`: 払戻金

**次のステップ**: CSV→DB投入

```bash
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020 \
  --dry-run  # 検証

python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020  # 本番投入
```

---

#### 補完_決まり手データ_改善版.py

**機能**:
- 決まり手データの高速補完
- ThreadPoolExecutor 16ワーカー
- セッション再利用による高速化

**技術仕様**:
- バッチDB更新（100件単位）
- リトライ機能（最大3回）
- セッション再利用（HTTP接続の効率化）

**使用例**:
```bash
python scripts/data_collection/補完_決まり手データ_改善版.py
```

**処理内容**:
1. `kimarite IS NULL` のレースを検索
2. 並列で公式サイトから取得
3. バッチでDB更新

**所要時間**: 1万レース約20-30分

---

#### 補完_レース詳細データ_改善版v4.py

**機能**:
- ST時間、実走コース、チルト角度を補完
- ThreadPoolExecutor 12ワーカー

**技術仕様**:
- バッチサイズ200
- 15秒タイムアウト
- スレッドローカルスクレイパー

**使用例**:
```bash
python scripts/data_collection/補完_レース詳細データ_改善版v4.py
```

**処理内容**:
1. `start_timing IS NULL` のレースを検索
2. 並列で公式サイトから取得
3. バッチでDB更新

---

#### fetch_odds_parallel_safe.py

**機能**:
- 3連単オッズの並列収集（安全版）
- エラー処理強化

**技術仕様**:
- 8-12ワーカー推奨
- リトライ機能
- タイムアウト対応

**使用例**:
```bash
python scripts/data_collection/fetch_odds_parallel_safe.py \
  --start 2024-01-01 \
  --end 2024-12-31
```

**注意**:
- オッズ収集はAPI負荷が高い
- 並列数は8-12推奨
- 3秒間隔の待機必須

---

#### fetch_exacta_odds.py

**機能**:
- 2連単オッズ収集
- Selenium使用

**技術仕様**:
- 3秒間隔待機
- ヘッドレスブラウザ

**使用例**:
```bash
python scripts/data_collection/fetch_exacta_odds.py \
  --start 2024-01-01 \
  --end 2024-12-31
```

---

#### build_indicator_stats.py

**機能**:
- 統計指標の生成（逃げ率、攻め率等）
- 年度別・カスタム期間対応

**使用例**:
```bash
# 2024年の統計指標生成
python scripts/data_collection/build_indicator_stats.py --year 2024

# 全年度
for year in {2020..2025}; do
  python scripts/data_collection/build_indicator_stats.py --year $year
done
```

**出力**:
- `indicator_stats` テーブルに保存
- 逃げ率、攻め率、差し率等

---

## 整理方針

### アーカイブディレクトリ作成案

```
scripts/data_collection/
├── (現役スクリプト) - 推奨17スクリプト
└── archive/
    ├── deprecated/     # 旧版（非推奨）
    │   ├── fetch_historical_data.py
    │   ├── collect_beforeinfo_2020_2023.py
    │   ├── 補完_決まり手データ_シンプル版.py
    │   └── ...
    └── year_specific/  # 特定年度専用
        ├── collect_2024_all_data.py
        ├── fetch_historical_data_2024.py
        └── ...
```

### 推奨スクリプトのみ残す案（17スクリプト）

#### 過去データバルク収集（6）
1. `auto_fetch_2020_2025.py`
2. `fetch_historical_data_parallel.py`
3. `collect_beforeinfo_2020_2023_optimized.py`
4. `bulk_missing_data_fetch_parallel.py`
5. `collect_race_conditions_2024_optimized.py`
6. `master_automation_2020_2025.py`

#### CSV方式（2）
7. `fetch_to_csv_parallel_improved.py`
8. `fetch_to_csv_parallel_optimized.py`

#### 補完（4）
9. `補完_決まり手データ_改善版.py`
10. `補完_レース詳細データ_改善版v4.py`
11. `補完_払戻金データ.py`
12. `fill_missing_weather_data.py`

#### オッズ（2）
13. `fetch_odds_parallel_safe.py`
14. `fetch_exacta_odds.py`

#### 日次・特殊（3）
15. `fetch_today_beforeinfo.py`
16. `build_indicator_stats.py`
17. `update_racer_master.py`

---

### アーカイブ対象（27スクリプト）

#### 旧版・非推奨（10）
- `fetch_historical_data.py`
- `collect_beforeinfo_2020_2023.py`
- `fetch_to_csv_parallel.py`
- `補完_決まり手データ_シンプル版.py`
- `補完_決まり手データ_v2.py`
- `fetch_odds_parallel.py`
- `import_missing_data.py`
- `fill_missing_weather_2022.py`
- `fetch_historical_odds.py`
- `fetch_historical_odds_simple.py`

#### 特定用途・一時的（17）
- `collect_2024_all_data.py`
- `collect_2024_missing_data.py`
- `fetch_historical_data_2024.py`
- `collect_parts_exchange.py`
- `auto_collect_beforeinfo_after_advance.py`
- `complement_2020_2023_beforeinfo_and_predictions.py`
- `fetch_odds_2020_2024_background.py`
- `fetch_odds_fast.py`
- `update_historical_odds.py`
- `fetch_original_tenji_daily.py`
- `worker_tenji_collection.py`
- `worker_missing_data.py`
- `import_missing_data_fixed.py`
- `import_remaining_data.py`
- `import_final_diff.py`
- `update_database.py`
- `test_kimarite_fetch.py`

---

## まとめ

### Claude Code向けガイドライン

**ユーザーから「データ収集」を依頼されたら**:

1. **まずこのカタログを参照**
2. **推奨スクリプト一覧から選択**
3. **旧版・非推奨は使用しない**
4. **詳細は DATA_COLLECTION_MASTER.md を参照**

### クイック判断表

| やりたいこと | 推奨スクリプト |
|-------------|---------------|
| 過去全データ | `auto_fetch_2020_2025.py` |
| 特定期間データ | `fetch_historical_data_parallel.py` |
| CSV出力 | `fetch_to_csv_parallel_improved.py` |
| 決まり手補完 | `補完_決まり手データ_改善版.py` |
| レース詳細補完 | `補完_レース詳細データ_改善版v4.py` |
| オッズ収集 | `fetch_odds_parallel_safe.py` |
| 本日の直前情報 | `fetch_today_beforeinfo.py` |
| 統計指標 | `build_indicator_stats.py` |

---

**関連ドキュメント**:
- [DATA_COLLECTION_OPTIMIZATION_GUIDE.md](DATA_COLLECTION_OPTIMIZATION_GUIDE.md) - 最適化ガイド **(推奨)**
- [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) - マスターガイド
- [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md) - CSV方式の詳細

**最終更新**: 2026-02-04
