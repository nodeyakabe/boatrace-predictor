# データ収集最適化ガイド

**最終更新**: 2026-02-04
**対象**: データ収集作業を行うすべてのユーザーおよびClaude Code

---

## 目次

1. [概要](#1-概要)
2. [データ収集フローチャート](#2-データ収集フローチャート)
3. [スクリプト選択ガイド](#3-スクリプト選択ガイド)
4. [パフォーマンス最適化](#4-パフォーマンス最適化)
5. [エラーハンドリングのベストプラクティス](#5-エラーハンドリングのベストプラクティス)
6. [データ整合性の確保](#6-データ整合性の確保)
7. [トラブルシューティング](#7-トラブルシューティング)
8. [よくある失敗パターンと対策](#8-よくある失敗パターンと対策)
9. [チェックリスト](#9-チェックリスト)
10. [ベストプラクティス集](#10-ベストプラクティス集)

---

## 1. 概要

### 1.1 データ収集の3つの方式

| 方式 | 特徴 | 推奨用途 | DB負荷 |
|------|------|----------|--------|
| **DB直接投入** | リアルタイムでDB保存 | 日次収集、少量データ | 高 |
| **CSV経由** | CSV保存→後で一括投入 | 大量過去データ、長時間収集 | なし |
| **補完実行** | 欠損データを追加 | データ品質改善 | 中 |

### 1.2 重要な制約事項

#### オリジナル展示データの時間制約

| データ種別 | 取得可能期間 | 補完可否 | 注意事項 |
|-----------|-------------|---------|---------|
| レース基本情報 | 2020年～ | 可能 | 公式APIで常時公開 |
| レース結果 | 2020年～ | 可能 | 公式APIで常時公開 |
| オッズ | 2020年～ | 可能 | 公式APIで常時公開 |
| 直前情報（標準） | 2020年～ | 可能 | 公式APIで常時公開 |
| **オリジナル展示** | **前日のみ** | **不可** | **一度逃すと永久欠損** |
| 潮位データ | 数年分 | 可能 | 競艇場公式サイト |

**運用への影響**:
- 毎日の自動収集が必須（オリジナル展示）
- 過去データの補完は不可能（オリジナル展示のみ）
- 公式データは常に補完可能（レース・結果・オッズ）

---

## 2. データ収集フローチャート

### 2.1 収集方式の選択

```
[データ収集タスク開始]
         |
         v
    収集対象は？
    /     |      \
  日次  特定期間  大量過去データ
   |      |           |
   v      v           v
単体   1万レース    CSV方式
スクリプト  未満？    必須
   |      /  \        |
   |    Yes  No       |
   |     |    |       |
   v     v    v       v
[DB直接] [DB直接] [CSV収集]
   |        |        |
   v        v        v
  完了    完了   [DB一括投入]
                     |
                     v
                   完了
```

### 2.2 シナリオ別ガイド

| シナリオ | 推奨手順 | 所要時間 |
|---------|---------|---------|
| 初回セットアップ（2020-2025年全データ） | auto_fetch_2020_2025.py → 補完スクリプト → 統計生成 | 20-30時間 |
| 大量過去データ収集（DB負荷回避） | CSV収集 → dry-run検証 → DB一括投入 | 期間依存 |
| 日次データ更新 | fetch_today_beforeinfo.py（自動化推奨） | 数分 |
| データ品質改善（補完） | 補完スクリプト（決まり手、レース詳細等） | データ量依存 |
| オッズ収集 | fetch_odds_parallel_safe.py（安全版） | 期間依存 |

---

## 3. スクリプト選択ガイド

### 3.1 クイックリファレンス

| やりたいこと | 推奨スクリプト | コマンド例 |
|-------------|---------------|-----------|
| **過去全データ収集（2020-2025）** | `auto_fetch_2020_2025.py` | `python scripts/data_collection/auto_fetch_2020_2025.py` |
| **特定期間のデータ収集** | `fetch_historical_data_parallel.py` | `python scripts/data_collection/fetch_historical_data_parallel.py --start 2024-01-01 --end 2024-12-31` |
| **CSV方式で大量収集** | `fetch_to_csv_parallel_improved.py` | `python scripts/data_collection/fetch_to_csv_parallel_improved.py --start 2020-01-01 --end 2020-12-31 --output data/csv/2020` |
| **決まり手データ補完** | `補完_決まり手データ_改善版.py` | `python scripts/data_collection/補完_決まり手データ_改善版.py` |
| **レース詳細補完** | `補完_レース詳細データ_改善版v4.py` | `python scripts/data_collection/補完_レース詳細データ_改善版v4.py` |
| **オッズ収集** | `fetch_odds_parallel_safe.py` | `python scripts/data_collection/fetch_odds_parallel_safe.py --start 2024-01-01 --end 2024-12-31` |
| **本日の直前情報** | `fetch_today_beforeinfo.py` | `python scripts/data_collection/fetch_today_beforeinfo.py` |
| **統計指標生成** | `build_indicator_stats.py` | `python scripts/data_collection/build_indicator_stats.py --year 2024` |

### 3.2 推奨スクリプト一覧（17スクリプト）

#### 過去データバルク収集（6）
| スクリプト | 用途 | 並列化 | 特徴 |
|-----------|------|--------|------|
| `auto_fetch_2020_2025.py` | 2020-2025年マスター自動収集 | - | 複数タスク順次実行 |
| `fetch_historical_data_parallel.py` | 過去データ高速並列収集 | 8-12スレッド | 10-15倍高速 |
| `collect_beforeinfo_2020_2023_optimized.py` | 直前情報収集（最適化版） | 12ワーカー | バッチ処理、再開機能 |
| `bulk_missing_data_fetch_parallel.py` | 不足データ並列バルク収集 | あり | 並列処理 |
| `collect_race_conditions_2024_optimized.py` | 気象・レース条件収集 | 12並列 | 最適化版 |
| `master_automation_2020_2025.py` | マスター自動化スクリプト | - | ログ付き順次実行 |

#### CSV方式（2）
| スクリプト | 用途 | 特徴 |
|-----------|------|------|
| `fetch_to_csv_parallel_improved.py` | CSV並列出力（改善版） | スケジュール最適化、50%削減 |
| `fetch_to_csv_parallel_optimized.py` | CSV並列出力（最適化版） | さらなる改善 |

#### 補完スクリプト（4）
| スクリプト | 用途 | 並列化 | 特徴 |
|-----------|------|--------|------|
| `補完_決まり手データ_改善版.py` | 決まり手補完 | 16ワーカー | バッチ更新、リトライ |
| `補完_レース詳細データ_改善版v4.py` | レース詳細補完 | 12ワーカー | ST時間、実走コース、チルト |
| `補完_払戻金データ.py` | 払戻金補完 | あり | ProcessPoolExecutor |
| `fill_missing_weather_data.py` | 気象データ補完 | - | 天候、風、水温 |

#### オッズ収集（2）
| スクリプト | 用途 | 特徴 |
|-----------|------|------|
| `fetch_odds_parallel_safe.py` | 3連単オッズ収集（安全版） | WALモード、エラー処理強化 |
| `fetch_exacta_odds.py` | 2連単オッズ収集 | Selenium使用、3秒間隔 |

#### 日次・特殊用途（3）
| スクリプト | 用途 | 実行頻度 |
|-----------|------|---------|
| `fetch_today_beforeinfo.py` | 本日の直前情報 | 日次 |
| `build_indicator_stats.py` | 統計指標生成 | 随時 |
| `update_racer_master.py` | 選手マスタ更新 | 月次 |

### 3.3 非推奨スクリプト（使用しないこと）

| スクリプト | 理由 | 代替 |
|-----------|------|------|
| `fetch_historical_data.py` | 並列化なし（遅い） | `fetch_historical_data_parallel.py` |
| `collect_beforeinfo_2020_2023.py` | 最適化前 | `collect_beforeinfo_2020_2023_optimized.py` |
| `補完_決まり手データ_シンプル版.py` | 逐次処理（遅い） | `補完_決まり手データ_改善版.py` |
| `fetch_odds_parallel.py` | エラー処理不足 | `fetch_odds_parallel_safe.py` |
| `import_missing_data.py` | バグあり | `import_missing_data_fixed.py` |

---

## 4. パフォーマンス最適化

### 4.1 並列化の最適設定

| 処理タイプ | 推奨並列数 | 理由 |
|-----------|-----------|------|
| HTTP I/O（レース取得） | 10-12スレッド | ネットワーク待機時間の有効活用 |
| HTTP I/O（オッズ取得） | 8-10スレッド | API負荷制限を考慮 |
| 補完処理（決まり手） | 16スレッド | 軽量なHTTPリクエスト |
| 補完処理（レース詳細） | 12スレッド | 中程度のデータ量 |
| CSV収集 | 12ワーカー | ProcessPoolExecutor使用 |

### 4.2 スレッドローカルストレージの活用

```python
# 各スレッドでスクレイパーインスタンスを保持
thread_local = threading.local()

def get_scrapers():
    """スレッドローカルなスクレイパーを取得"""
    if not hasattr(thread_local, 'race_scraper'):
        thread_local.race_scraper = RaceScraperV2()
        thread_local.result_scraper = ResultScraper()
    return thread_local.race_scraper, thread_local.result_scraper
```

**効果**:
- セッション再利用による接続コスト削減
- スレッド間の競合回避
- メモリ効率の向上

### 4.3 バッチ処理の最適化

| 処理 | 推奨バッチサイズ | 理由 |
|------|----------------|------|
| DB更新（決まり手） | 100件 | ロック競合回避 |
| DB更新（レース詳細） | 200件 | 処理効率とメモリのバランス |
| CSV保存 | 50タスク | 途中停止時のデータ保護 |
| オッズ保存 | 50件 | トランザクション効率 |

### 4.4 パフォーマンス目安

| 期間 | レース数 | 収集時間（並列12） | DB投入時間 |
|------|---------|-----------------|-----------|
| 1日 | 100-150 | 5-10分 | 数秒 |
| 1ヶ月 | 3,000-4,000 | 2-3時間 | 1-2分 |
| 1年 | 40,000-50,000 | 30-40時間 | 5-10分 |

---

## 5. エラーハンドリングのベストプラクティス

### 5.1 リトライ機能の実装パターン

```python
def fetch_with_retry(args, max_retries=3):
    """指数バックオフ付きリトライ"""
    for attempt in range(max_retries):
        try:
            result = fetch_data(args)
            if result:
                return result
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1秒, 2秒, 4秒
                continue
            else:
                return None
    return None
```

**ポイント**:
- 指数バックオフ: 1秒 → 2秒 → 4秒
- 最大リトライ回数: 3回
- エラー後は必ず待機

### 5.2 シグナルハンドラによる優雅な終了

```python
def setup_signal_handlers(self):
    """Ctrl+Cで優雅に終了"""
    def signal_handler(signum, frame):
        if not self.is_shutting_down:
            self.logger.warning("終了シグナル受信。データを保存中...")
            self.is_shutting_down = True
            self.shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
```

**効果**:
- 強制終了時もデータ保護
- バッファ内のデータを保存
- DB接続を適切にクローズ

### 5.3 タイムアウト設定

| 処理 | 推奨タイムアウト |
|------|----------------|
| HTTPリクエスト | 10秒 |
| レース詳細取得 | 15秒 |
| DB接続 | 30秒 |
| DBビジータイムアウト | 30秒 |

---

## 6. データ整合性の確保

### 6.1 WALモードによるDB保護

```python
def setup_database(self):
    """WALモード有効化"""
    self.db_conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)

    # WALモード有効化（書き込み時のファイル破損を防止）
    self.db_conn.execute("PRAGMA journal_mode=WAL")
    self.db_conn.execute("PRAGMA synchronous=NORMAL")
    self.db_conn.execute("PRAGMA busy_timeout=30000")
```

**効果**:
- 書き込み中の読み取り可能
- クラッシュ時のデータ保護
- 並行アクセスの性能向上

### 6.2 トランザクション管理

```python
try:
    data_manager.begin_batch()

    for item in data:
        data_manager.save_race_data_fast(item)

    data_manager.commit_batch()

except Exception as e:
    data_manager.rollback_batch()
    raise
```

### 6.3 CSV投入時の検証

```bash
# 1. dry-runで検証
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020 \
  --dry-run

# 2. 検証成功後に本番投入
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020
```

**検証内容**:
- CSVファイル読み込み
- データ形式検証
- 外部キー制約チェック
- 重複チェック

---

## 7. トラブルシューティング

### 7.1 よくある問題と解決策

| 問題 | 原因 | 解決策 |
|------|------|--------|
| データ収集が遅い | 並列化していない | `_parallel`付きスクリプトを使用 |
| 途中で止まる | ネットワークエラー | CSV方式に切り替え |
| DBがロックされる | 長時間の書き込み | CSV方式必須 |
| データが重複する | 同じ期間を複数回実行 | `--overwrite`オプション |
| 外部キー制約エラー | データ投入順序の問題 | `bulk_insert_from_csv.py`使用 |
| オッズ収集で403エラー | アクセス頻度制限 | ワーカー数を8以下に |

### 7.2 DBロック時の対処

```bash
# 1. プロセスを確認
lsof data/boatrace.db

# 2. 必要に応じて終了
kill -15 <PID>

# 3. WALチェックポイント実行
sqlite3 data/boatrace.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

### 7.3 CSV保存時の問題

| 問題 | 原因 | 解決策 |
|------|------|--------|
| ディレクトリが作成されない | 親ディレクトリ不在 | `mkdir -p data/csv/2020` |
| 文字化け | エンコーディング | UTF-8を明示指定 |
| 数値型変換エラー | フォーマット | `int(float(value))` |

---

## 8. よくある失敗パターンと対策

### 8.1 失敗パターン一覧

| パターン | 症状 | 原因 | 対策 |
|---------|------|------|------|
| **大量データの直接投入** | DBロック、タイムアウト | 長時間トランザクション | CSV方式を使用 |
| **非推奨スクリプト使用** | 遅い、エラー多発 | 古い実装 | 推奨スクリプトを確認 |
| **並列数過多** | 403エラー、BAN | API制限超過 | ワーカー数を8-12に |
| **検証なしの本番投入** | データ不整合 | 外部キー違反 | dry-run必須 |
| **途中停止でデータ消失** | 収集やり直し | バッファ未保存 | 50タスクごと保存 |
| **オリジナル展示の取り逃し** | 永久欠損 | 時間制約 | 自動化必須 |

### 8.2 成功事例

#### wave_height補完プロジェクト（2026-01-29）

**背景**:
- wave_heightカバレッジ: 51.6%（113,757/220,413レース）
- 補完対象: 2020-2023年（約22万レース）

**実施内容**:
```bash
# CSV収集（年別に分割）
python scripts/data_collection/fetch_race_conditions_to_csv.py \
  --start 2020-01-01 --end 2020-12-31 \
  --output data/csv/race_conditions/2020 \
  --workers 12

# 検証
python scripts/maintenance/import_race_conditions_from_csv.py \
  --input data/csv/race_conditions/2020 \
  --dry-run

# DB投入
python scripts/maintenance/import_race_conditions_from_csv.py \
  --input data/csv/race_conditions/2020
```

**結果**:
- 収集レース数: 220,813件
- 新規投入: 109,595件
- 補完率向上: 51.6% → **97.1%** (+45.5%)
- 所要時間: 約71.4時間
- DB負荷: ゼロ

---

## 9. チェックリスト

### 9.1 収集前チェックリスト

- [ ] 収集対象のデータ種別を確認
- [ ] 期間と予想レース数を確認
- [ ] 適切なスクリプトを選択（推奨スクリプト一覧参照）
- [ ] 1万レース以上ならCSV方式を検討
- [ ] ディスク空き容量を確認（1年分: 約600MB-1.2GB）
- [ ] 並列数を適切に設定（8-12が推奨）

### 9.2 収集中チェックリスト

- [ ] 進捗表示を確認
- [ ] エラー率が高くないか確認
- [ ] Ctrl+Cで止める場合は優雅な終了を待つ

### 9.3 収集後チェックリスト

- [ ] エラー件数を確認
- [ ] CSVの場合はdry-runで検証
- [ ] データ件数を確認
- [ ] 必要に応じて補完スクリプトを実行
- [ ] 統計指標を再生成

### 9.4 CSV方式採用チェックリスト

以下の条件に当てはまる場合、CSV方式を採用:

- [ ] 収集対象が1万レース以上
- [ ] 推定所要時間が2時間以上
- [ ] 収集中も他のDB操作を実行したい
- [ ] ネットワーク障害のリスクがある
- [ ] 投入前にデータ検証したい

---

## 10. ベストプラクティス集

### 10.1 データ収集の基本原則

1. **大量データはCSV方式** - DB負荷回避、途中停止対策
2. **並列化を活用** - 8-12ワーカーで10-15倍高速化
3. **月別に分割** - リカバリ容易、進捗管理しやすい
4. **補完は定期実行** - データ品質維持
5. **dry-runで検証** - 本番投入前の安全確認

### 10.2 効率的なワークフロー

```bash
# 1. 月単位で分割実行
for month in {01..12}; do
  python scripts/data_collection/fetch_to_csv_parallel_improved.py \
    --start 2020-${month}-01 \
    --end 2020-${month}-31 \
    --output data/csv/2020_${month}

  # 2. 検証
  python scripts/maintenance/bulk_insert_from_csv.py \
    --input data/csv/2020_${month} \
    --dry-run

  # 3. DB投入
  python scripts/maintenance/bulk_insert_from_csv.py \
    --input data/csv/2020_${month}
done
```

### 10.3 日次運用のポイント

1. **自動化スケジューラー**: `daily_scheduler.py`で毎日実行
2. **オリジナル展示**: 前日夜23:00に翌日分を収集
3. **監視**: ログを確認し、エラーを早期発見

### 10.4 トラブル発生時の対処

1. **まず停止**: 強制終了せず、優雅な終了を待つ
2. **ログ確認**: エラー内容を特定
3. **期間分割**: 失敗した期間のみ再実行
4. **CSV方式へ切り替え**: DBロックが発生したら

---

## 関連ドキュメント

- [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) - マスターガイド
- [DATA_COLLECTION_SCRIPTS_CATALOG.md](DATA_COLLECTION_SCRIPTS_CATALOG.md) - スクリプトカタログ
- [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md) - CSV方式の詳細
- [VENUE_SPECIFIC_DATA_COLLECTION.md](VENUE_SPECIFIC_DATA_COLLECTION.md) - 競艇場独自データ

---

**最終更新**: 2026-02-04
