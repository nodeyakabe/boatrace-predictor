# データ収集マスターガイド

**最終更新**: 2026-02-19
**対象**: Claude Codeがデータ収集タスクを実行する際の完全リファレンス

---

## ⭐ 重要：データ収集の依存関係チェーン

**パイプライン設計時・データ補完後は必ず確認すること:**

→ **[DATA_DEPENDENCY_CHAIN.md](DATA_DEPENDENCY_CHAIN.md)** ⭐

**entries/resultsを追加したら、以下も必要:**
```
entries/results 追加
  → kimarite 補完が必要（補完_決まり手データ_改善版.py）
  → race_details 補完が必要（補完_レース詳細データ_改善版v4.py）
  → trifecta_odds 収集が必要（fetch_odds_parallel_safe.py）★バックテスト必須
  → indicator_stats 再生成が必要（build_indicator_stats.py）
  → advance 予測再生成が必要（generate_advance_fast.py）
```

**この依存関係を見落とすと → 後続データが欠損したままバックテストが動く**

---

## 📋 目次

1. [概要](#概要)
2. [クイックリファレンス](#クイックリファレンス)
3. [シナリオ別ガイド](#シナリオ別ガイド)
4. [推奨スクリプト一覧](#推奨スクリプト一覧)
5. [スクリプト詳細](#スクリプト詳細)
6. [トラブルシューティング](#トラブルシューティング)
7. [CSV収集方式の詳細](#csv収集方式の詳細)
8. [競艇場独自データ](#競艇場独自データ)

---

## 概要

### データ収集の3つの方式

| 方式 | 特徴 | 推奨用途 |
|------|------|---------|
| **DB直接投入** | リアルタイムでDB保存 | 日次収集、少量データ |
| **CSV経由** | CSV保存→後で一括投入 | 大量過去データ、長時間収集 |
| **補完実行** | 欠損データを追加 | データ品質改善 |

### データ種別

- **レース基本情報**: races, entries, results, payouts
- **直前情報**: beforeinfo（展示タイム、チルト、部品交換、気象）
- **レース条件**: race_conditions（天候、風、水温）
- **オッズ**: trifecta_odds, exacta_odds
- **統計指標**: indicator_stats（逃げ率、攻め率）
- **特殊データ**: 決まり手、潮位データ

---

## ⚠️ 重要な制約事項（必読）

### 1. オリジナル展示データの時間制約

**最重要**: オリジナル展示は**昨日までのデータしか収集できない**

```
✅ 前日のレース: 取得可能
   例: 1月15日に1月14日のデータを取得

❌ 当日以前の過去レース: データ削除済み（会場による）
   例: 1月15日に1月13日以前のデータを取得しようとする

❌ 未来のレース: データ未公開
   例: 1月15日に1月16日のデータを取得しようとする
```

**運用への影響**:
1. **毎日の自動収集が必須** - 一度逃すと二度と取得できない
2. **過去データの補完は不可能** - 欠損したら永久に欠損
3. **最適な収集タイミング**: 前日夜23:00に翌日分のデータを収集

**詳細**: [docs/knowledge/オリジナル展示収集_知見とトラブルシューティング.md](../knowledge/オリジナル展示収集_知見とトラブルシューティング.md)

---

### 2. 公式データは数年前も公開されている

**重要**: 公式API（レース基本情報、結果、オッズ等）は**過去数年分のデータが常時公開**

```
✅ 過去データ取得可能:
- レース基本情報（races, entries）
- レース結果（results）
- 払戻金（payouts）
- オッズ（trifecta_odds, exacta_odds）
- レース条件（race_conditions）

期間: 2020年以降のデータは常時取得可能
```

**Claude Codeへの注意**:
- 「過去データが取れない」と判断しない
- 「公式APIは最新データのみ」と思い込まない
- 過去の補完は通常問題なく実行可能

**例外**: オリジナル展示のみ時間制約あり（上記参照）

---

### 3. データ取得可能期間の整理

| データ種別 | 取得可能期間 | 補完可否 | 注意事項 |
|-----------|-------------|---------|---------|
| レース基本情報 | 2020年～ | ✅ 可能 | 公式APIで常時公開 |
| レース結果 | 2020年～ | ✅ 可能 | 公式APIで常時公開 |
| オッズ | 2020年～ | ✅ 可能 | 公式APIで常時公開 |
| 直前情報（標準） | 2020年～ | ✅ 可能 | 公式APIで常時公開 |
| **オリジナル展示** | **前日のみ** | **❌ 不可** | **Boatersサイト限定** |
| 潮位データ | 数年分 | ✅ 可能 | 競艇場公式サイト |

---

## クイックリファレンス

### よくあるタスクと対応スクリプト

| やりたいこと | 使うスクリプト | コマンド例 |
|-------------|---------------|-----------|
| **過去全データ収集（2020-2025）** | `auto_fetch_2020_2025.py` | `python scripts/data_collection/auto_fetch_2020_2025.py` |
| **特定期間のデータ収集** | `fetch_historical_data_parallel.py` | `python scripts/data_collection/fetch_historical_data_parallel.py --start 2024-01-01 --end 2024-12-31` |
| **CSV方式で大量収集** | `fetch_to_csv_parallel_improved.py` | `python scripts/data_collection/fetch_to_csv_parallel_improved.py --start 2020-01-01 --end 2020-12-31 --output data/csv/2020` |
| **決まり手＋レース詳細一括補完** ⭐ | `補完_統合版_決まり手_レース詳細.py` | `python scripts/data_collection/補完_統合版_決まり手_レース詳細.py --years 2024 2025` |
| **決まり手データ補完（個別）** | `補完_決まり手データ_改善版.py` | `python scripts/data_collection/補完_決まり手データ_改善版.py` |
| **レース詳細補完（個別）** | `補完_レース詳細データ_改善版v4.py` | `python scripts/data_collection/補完_レース詳細データ_改善版v4.py` |
| **オッズ収集** | `fetch_odds_parallel_safe.py` | `python scripts/data_collection/fetch_odds_parallel_safe.py --start 2024-01-01 --end 2024-12-31` |
| **本日の直前情報** | `fetch_today_beforeinfo.py` | `python scripts/data_collection/fetch_today_beforeinfo.py` |
| **統計指標生成** | `build_indicator_stats.py` | `python scripts/data_collection/build_indicator_stats.py --year 2024` |

---

## シナリオ別ガイド

### シナリオ1: 初回セットアップ（2020-2025年全データ）

**状況**: 空のDBから全データを構築

**推奨手順**:

```bash
# ステップ1: マスター自動収集（15-25時間）
python scripts/data_collection/auto_fetch_2020_2025.py

# ステップ2: 決まり手＋レース詳細補完（統合版、推奨）
python scripts/data_collection/補完_統合版_決まり手_レース詳細.py --years 2020 2021 2022 2023 2024 2025

# または個別実行
# python scripts/data_collection/補完_決まり手データ_改善版.py
# python scripts/data_collection/補完_レース詳細データ_改善版v4.py

# ステップ4: 統計指標生成
python scripts/data_collection/build_indicator_stats.py --year 2020
python scripts/data_collection/build_indicator_stats.py --year 2021
python scripts/data_collection/build_indicator_stats.py --year 2022
python scripts/data_collection/build_indicator_stats.py --year 2023
python scripts/data_collection/build_indicator_stats.py --year 2024
python scripts/data_collection/build_indicator_stats.py --year 2025
```

**所要時間**: 合計 20-30時間

---

### シナリオ2: 大量過去データ収集（DB負荷回避）

**状況**: 長期間のデータ収集中も他の作業を続けたい

**推奨手順**:

```bash
# ステップ1: CSV収集（DB不使用、4-8時間）
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --output data/csv/2020 \
  --workers 12

# ステップ2: 検証（dry-run）
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020 \
  --dry-run

# ステップ3: DB一括投入（5-10分）
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020
```

**メリット**:
- CSV収集中もDB操作可能
- 50タスクごとに自動保存（途中で止まってもデータ残る）
- 一括投入が高速

**詳細**: [CSV収集方式の詳細](#csv収集方式の詳細)

---

### シナリオ3: 日次データ更新

**状況**: 毎日の新しいレースデータを収集

**推奨手順**:

```bash
# 方法A: 自動スケジューラー（推奨）
# scripts/automation/daily_scheduler.py が自動実行

# 方法B: 手動実行
python scripts/data_collection/fetch_today_beforeinfo.py
```

**自動化設定**: [AUTOMATION_SETUP.md](AUTOMATION_SETUP.md)

---

### シナリオ4: データ品質改善（補完実行）

**状況**: 既存データに欠損がある

**補完スクリプト一覧**:

| データ種別 | スクリプト | 対象 | 備考 |
|-----------|-----------|------|------|
| **決まり手＋レース詳細** ⭐ | `補完_統合版_決まり手_レース詳細.py` | 決まり手、ST時間、実走コース、チルト | **最優先推奨**（2026-02-10） |
| 決まり手（個別） | `補完_決まり手データ_改善版.py` | 全レース | 統合版がない場合のみ |
| レース詳細（個別） | `補完_レース詳細データ_改善版v4.py` | ST時間、実走コース、チルト | 統合版がない場合のみ |
| 払戻金 | `補完_払戻金データ.py` | 全払戻種別 | - |
| 気象データ | `fill_missing_weather_data.py` | 天候、風、水温 | - |

**実行例**:

```bash
# 【推奨】統合版（決まり手＋レース詳細を一括補完）
python scripts/data_collection/補完_統合版_決まり手_レース詳細.py --years 2024 2025

# Phase 1: 決まり手補完（16並列、高速）
# Phase 2: レース詳細補完（6並列、安定性重視）
# 2フェーズを自動実行、ログ出力あり

# 個別実行（統合版がない環境の場合のみ）
python scripts/data_collection/補完_決まり手データ_改善版.py
python scripts/data_collection/補完_レース詳細データ_改善版v4.py
```

---

### シナリオ5: オッズデータ収集

**状況**: 3連単・2連単オッズを追加取得

**推奨手順**:

```bash
# 3連単オッズ（並列・安全版）
python scripts/data_collection/fetch_odds_parallel_safe.py \
  --start 2024-01-01 \
  --end 2024-12-31

# 2連単オッズ（Selenium使用）
python scripts/data_collection/fetch_exacta_odds.py \
  --start 2024-01-01 \
  --end 2024-12-31
```

**注意**:
- オッズ収集はAPI負荷が高い
- 並列数は8-12推奨
- 3秒間隔の待機必須

---

### シナリオ6: 特定月のみ収集

**状況**: 一部期間のデータが欠けている

**推奨手順**:

```bash
# 月別に分割実行
python scripts/data_collection/fetch_historical_data_parallel.py \
  --start 2024-03-01 \
  --end 2024-03-31 \
  --workers 12

# または CSV方式
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2024-03-01 \
  --end 2024-03-31 \
  --output data/csv/2024_03
```

---

## 推奨スクリプト一覧

### 🥇 最優先（現役・推奨）

#### 過去データバルク収集

| スクリプト | 用途 | 特徴 |
|-----------|------|------|
| `auto_fetch_2020_2025.py` | 2020-2025年全データ自動収集 | マスタースクリプト、15-25時間 |
| `fetch_historical_data_parallel.py` | 特定期間データ並列収集 | 10-15倍高速、8-12ワーカー |
| `collect_beforeinfo_2020_2023_optimized.py` | 直前情報収集（最適化版） | 12ワーカー、バッチ処理、再開機能 |

#### CSV方式（DB負荷なし）

| スクリプト | 用途 | 特徴 |
|-----------|------|------|
| `fetch_to_csv_parallel_improved.py` | CSV並列出力（改善版） | スケジュール最適化、50%タスク削減 |
| `fetch_to_csv_parallel_optimized.py` | CSV並列出力（最適化版） | さらなる改善版 |

#### 補完スクリプト

| スクリプト | 用途 | 特徴 |
|-----------|------|------|
| `補完_統合版_決まり手_レース詳細.py` ⭐ | **決まり手＋レース詳細一括補完** | **Phase 1: 決まり手（16並列）+ Phase 2: レース詳細（6並列）、2026-02-10作成、最優先推奨** |
| `補完_決まり手データ_改善版.py` | 決まり手補完（個別） | 16並列、セッション再利用、バッチ更新 |
| `補完_レース詳細データ_改善版v4.py` | レース詳細補完（個別） | ST時間、実走コース、チルト角度 |
| `補完_払戻金データ.py` | 払戻金補完 | 全払戻種別対応 |
| `fill_missing_weather_data.py` | 気象データ補完 | 天候、風、水温 |

#### オッズ収集

| スクリプト | 用途 | 特徴 |
|-----------|------|------|
| `fetch_odds_parallel_safe.py` | 3連単オッズ並列収集 | 安全版、エラー処理強化 |
| `fetch_exacta_odds.py` | 2連単オッズ収集 | Selenium使用、3秒間隔 |

#### 日次・特殊用途

| スクリプト | 用途 | 特徴 |
|-----------|------|------|
| `fetch_today_beforeinfo.py` | 本日の直前情報 | 日次実行用 |
| `build_indicator_stats.py` | 統計指標生成 | 逃げ率、攻め率等 |
| `update_racer_master.py` | 選手マスタ更新 | 月次実行推奨 |

---

### ⚠️ 旧版・非推奨（アーカイブ候補）

以下は改善版が存在するため、使用非推奨:

- `fetch_historical_data.py` → **使用: fetch_historical_data_parallel.py**
- `collect_beforeinfo_2020_2023.py` → **使用: collect_beforeinfo_2020_2023_optimized.py**
- `fetch_to_csv_parallel.py` → **使用: fetch_to_csv_parallel_improved.py**
- `補完_決まり手データ_シンプル版.py` → **使用: 補完_決まり手データ_改善版.py**
- `fetch_odds_parallel.py` → **使用: fetch_odds_parallel_safe.py**

---

## スクリプト詳細

### fetch_historical_data_parallel.py

**目的**: 過去データの高速並列収集

**主な機能**:
- レース基本情報、選手情報、結果、オッズを一括取得
- ThreadPoolExecutor使用（8-12ワーカー）
- 1日あたり30秒-1分（従来版の10-15倍高速）

**使用例**:

```bash
# 2024年全データ収集
python scripts/data_collection/fetch_historical_data_parallel.py \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --workers 12

# 特定月のみ
python scripts/data_collection/fetch_historical_data_parallel.py \
  --start 2024-03-01 \
  --end 2024-03-31
```

**パラメータ**:
- `--start`: 開始日（YYYY-MM-DD）
- `--end`: 終了日（YYYY-MM-DD）
- `--workers`: 並列ワーカー数（デフォルト: 8）

**出力**:
- 直接DBに保存
- 進捗表示あり

---

### fetch_to_csv_parallel_improved.py

**目的**: CSV経由の大量データ収集（DB負荷なし）

**主な機能**:
- 事前にレーススケジュール取得（タスク数50%削減）
- 50タスクごとに自動保存（途中停止でもデータ保護）
- CSV出力のみ（DB非依存）
- ProcessPoolExecutor使用（12ワーカー）

**使用例**:

```bash
# 2020年全データをCSV出力
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --output data/csv/2020 \
  --workers 12

# 特定月
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2024-03-01 \
  --end 2024-03-31 \
  --output data/csv/2024_03
```

**パラメータ**:
- `--start`: 開始日（YYYY-MM-DD）
- `--end`: 終了日（YYYY-MM-DD）
- `--output`: CSV出力ディレクトリ
- `--workers`: 並列ワーカー数（デフォルト: 12）

**出力ファイル**:
```
data/csv/2020/
├── races.csv           # レース基本情報
├── entries.csv         # 出走表
├── race_conditions.csv # レース条件
├── race_details.csv    # 展示情報
├── results.csv         # レース結果
└── payouts.csv         # 払戻金
```

**次のステップ**: CSV→DB投入

```bash
# 検証
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020 \
  --dry-run

# 本番投入
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020
```

**詳細**: [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md)

---

### 補完_統合版_決まり手_レース詳細.py ⭐

**目的**: 決まり手＋レース詳細データの一括補完（統合版）

**主な機能**:
- **Phase 1**: 決まり手補完（16並列、高速）
- **Phase 2**: レース詳細補完（6並列、安定性重視）
- 年度指定可能（複数年一括実行）
- 詳細ログ出力（logs/配下に保存）
- 自動リトライ機能

**使用例**:

```bash
# 2024-2025年のデータを一括補完
python scripts/data_collection/補完_統合版_決まり手_レース詳細.py --years 2024 2025

# 全年度を一括補完
python scripts/data_collection/補完_統合版_決まり手_レース詳細.py --years 2020 2021 2022 2023 2024 2025
```

**処理内容**:
1. 指定年度の欠損データを自動検出
2. Phase 1: 決まり手（kimarite IS NULL）を16並列で取得・更新
3. Phase 2: レース詳細（ST時間、実走コース、チルト）を6並列で取得・更新
4. 詳細ログをタイムスタンプ付きで保存

**所要時間**: 1万レース約30-40分（両フェーズ合計）

**推奨理由**:
- 2026-02-10作成の最新版
- 個別スクリプト2つの機能を統合
- 1回の実行で両方のデータを補完
- フェーズ分けで安定性とパフォーマンスを両立

---

### 補完_決まり手データ_改善版.py（個別版）

**目的**: 決まり手データの高速補完（統合版がない環境用）

**主な機能**:
- ThreadPoolExecutor 16ワーカー
- セッション再利用（高速化）
- バッチDB更新（100件単位）
- リトライ機能（最大3回）

**使用例**:

```bash
# 欠損決まり手データを自動補完
python scripts/data_collection/補完_決まり手データ_改善版.py
```

**処理内容**:
1. `kimarite IS NULL` のレースを検索
2. 並列で公式サイトから取得
3. バッチでDB更新

**所要時間**: 1万レース約20-30分

**注意**: 統合版（`補完_統合版_決まり手_レース詳細.py`）が利用可能な場合はそちらを推奨

---

### 補完_レース詳細データ_改善版v4.py（個別版）

**目的**: レース詳細情報の補完（統合版がない環境用）

**主な機能**:
- ST時間、実走コース、チルト角度を補完
- ThreadPoolExecutor 12ワーカー
- バッチサイズ200
- 15秒タイムアウト

**使用例**:

```bash
# ST時間・実走コース・チルト角度を補完
python scripts/data_collection/補完_レース詳細データ_改善版v4.py
```

**処理内容**:
1. `start_timing IS NULL` のレースを検索
2. 並列で公式サイトから取得
3. バッチでDB更新

**注意**: 統合版（`補完_統合版_決まり手_レース詳細.py`）が利用可能な場合はそちらを推奨

---

### build_indicator_stats.py

**目的**: 統計指標の生成（逃げ率、攻め率等）

**主な機能**:
- 年度別・カスタム期間対応
- 競艇場別・選手別統計

**使用例**:

```bash
# 2024年の統計指標生成
python scripts/data_collection/build_indicator_stats.py --year 2024

# 全年度
python scripts/data_collection/build_indicator_stats.py --year 2020
python scripts/data_collection/build_indicator_stats.py --year 2021
python scripts/data_collection/build_indicator_stats.py --year 2022
python scripts/data_collection/build_indicator_stats.py --year 2023
python scripts/data_collection/build_indicator_stats.py --year 2024
python scripts/data_collection/build_indicator_stats.py --year 2025
```

**出力**:
- `indicator_stats` テーブルに保存
- 逃げ率、攻め率、差し率等

---

## トラブルシューティング

### Q1: データ収集が遅い

**原因**: 並列化していない、ワーカー数が少ない

**対処**:
1. 並列版スクリプトを使用（`_parallel` 付き）
2. ワーカー数を増やす（`--workers 12`）
3. CSV方式を検討（DB負荷回避）

---

### Q2: 途中で止まる

**原因**: ネットワークエラー、タイムアウト

**対処**:
1. CSV方式を使用（50タスクごとに自動保存）
2. 期間を短く分割（月別実行）
3. リトライ機能付きスクリプトを使用

---

### Q3: DBがロックされる

**原因**: 長時間のDB書き込み

**対処**:
1. **CSV方式を使用**（DB非依存）
2. バッチサイズを大きくする
3. トランザクション管理を最適化

**推奨**: 大量データ収集はCSV方式必須

---

### Q4: データが重複する

**原因**: 同じ期間を複数回実行

**対処**:
- スクリプトは自動的に既存データをスキップ
- 上書きしたい場合は `--overwrite` オプション

---

### Q5: 外部キー制約エラー

**原因**: データ投入順序の問題

**対処**:
- CSV投入時は `bulk_insert_from_csv.py` を使用（自動解決）
- dry-run で事前検証

```bash
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020 \
  --dry-run
```

---

### Q6: オッズ収集で403エラー

**原因**: アクセス頻度制限

**対処**:
1. ワーカー数を減らす（8以下）
2. 待機時間を増やす（3秒以上）
3. `fetch_odds_parallel_safe.py` を使用

---

## CSV収集方式の詳細

### なぜCSV方式が必要か？

**従来の問題点**:
- データ収集に4-8日かかる
- その間DBがロック状態
- 他の作業ができない
- 途中で失敗すると最初からやり直し

**CSV方式の利点**:
- ✅ DB負荷なし（収集中はCSVに保存）
- ✅ 並行作業可能（他のDB操作OK）
- ✅ 段階的保存（50タスクごと）
- ✅ リカバリが容易
- ✅ 一括投入が高速（数百万レコード数分）

### 実行手順

#### ステップ1: CSV収集

```bash
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --output data/csv/2020 \
  --workers 12
```

**進捗確認**:
- 50タスクごとにCSV保存
- 途中で止まっても既存データは残る

#### ステップ2: 検証（dry-run）

```bash
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020 \
  --dry-run
```

**確認内容**:
- CSVファイル読み込み
- データ形式検証
- 外部キー制約チェック
- 重複チェック

#### ステップ3: DB投入

```bash
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020
```

**オプション**:
- `--overwrite`: 既存データを上書き
- `--db`: DBファイルパス指定

### パフォーマンス目安

| 期間 | レース数 | CSV収集時間 | DB投入時間 |
|------|---------|-----------|-----------|
| 1日 | 100-150 | 5-10分 | 数秒 |
| 1ヶ月 | 3,000-4,000 | 2-3時間 | 1-2分 |
| 1年 | 40,000-50,000 | 30-40時間 | 5-10分 |

### 推奨ワークフロー

**大量データ収集（2020-2025年）の場合**:

```bash
# 月単位で分割実行
for month in {01..12}; do
  python scripts/data_collection/fetch_to_csv_parallel_improved.py \
    --start 2020-${month}-01 \
    --end 2020-${month}-31 \
    --output data/csv/2020_${month}

  # 検証
  python scripts/maintenance/bulk_insert_from_csv.py \
    --input data/csv/2020_${month} \
    --dry-run

  # DB投入
  python scripts/maintenance/bulk_insert_from_csv.py \
    --input data/csv/2020_${month}
done
```

**メリット**:
- 失敗時のリトライが容易
- ディスク容量節約（投入後にCSV削除可能）
- 進捗管理がしやすい

### 詳細ドキュメント

- [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md)

---

## 競艇場独自データ

### 概要

公式API以外に、各競艇場の公式サイトから収集可能な独自データがあります。

### 優先度：高（予測精度向上に直結）

1. **潮汐表**（海水面の競艇場）
   - 対象: まるがめ、鳴門、宮島、徳山、下関、若松、芦屋、唐津、大村
   - 理由: 満潮・干潮で水面状況が大きく変化

2. **リアルタイム気象データ**（風向・風速）
   - 対象: 全競艇場
   - 理由: レース当日の条件

3. **前検タイムランキング**
   - 対象: 全競艇場
   - 理由: モーターの調子を直接反映

4. **進入コース別データ**（最新傾向）
   - 対象: 全競艇場
   - 理由: 季節・整備による変化を追跡

### 収集スクリプト

| データ | スクリプト | 対象競艇場 |
|--------|-----------|-----------|
| 潮位データ | `収集_潮位データ_最新.py` | 海水面9場 |

### 詳細ドキュメント

- [VENUE_SPECIFIC_DATA_COLLECTION.md](VENUE_SPECIFIC_DATA_COLLECTION.md)

---

## まとめ

### データ収集の基本原則

1. **大量データはCSV方式** - DB負荷回避
2. **並列化を活用** - 高速化（8-12ワーカー）
3. **月別に分割** - リカバリ容易
4. **補完は定期実行** - データ品質維持
5. **dry-run で検証** - 安全確認

### Claude Code向けガイドライン

**ユーザーから「データ収集」を依頼されたら**:

1. まず状況を確認:
   - 期間は？（1日 / 1ヶ月 / 複数年）
   - データ種別は？（レース / オッズ / 補完）
   - 他の作業と並行？（Yes → CSV方式）

2. 適切なスクリプトを選択:
   - 大量データ → CSV方式
   - 特定期間 → 並列版
   - 補完 → 専用スクリプト

3. 実行前に説明:
   - 所要時間
   - DB負荷の有無
   - 出力先

4. 実行後に確認:
   - データ件数
   - エラーの有無
   - 次のステップ

### よくある質問への回答

| 質問 | 回答 |
|------|------|
| 「過去データ全部取得して」 | CSV方式推奨、月別分割実行 |
| 「今日のデータ更新して」 | `fetch_today_beforeinfo.py` |
| 「決まり手が抜けてる」 | `補完_統合版_決まり手_レース詳細.py`（統合版、推奨） |
| 「ST時間がない」 | `補完_統合版_決まり手_レース詳細.py`（統合版、推奨） |
| 「データ補完したい」 | `補完_統合版_決まり手_レース詳細.py --years 2024 2025` |
| 「オッズがない」 | `fetch_odds_parallel_safe.py` |
| 「DBロックされた」 | CSV方式に切り替え |

---

**関連ドキュメント**:
- [DATA_COLLECTION_OPTIMIZATION_GUIDE.md](DATA_COLLECTION_OPTIMIZATION_GUIDE.md) - 最適化ガイド **(推奨)**
- [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md) - CSV方式の詳細
- [VENUE_SPECIFIC_DATA_COLLECTION.md](VENUE_SPECIFIC_DATA_COLLECTION.md) - 競艇場独自データ
- [AUTOMATION_SETUP.md](AUTOMATION_SETUP.md) - 自動化設定

**最終更新**: 2026-02-13
