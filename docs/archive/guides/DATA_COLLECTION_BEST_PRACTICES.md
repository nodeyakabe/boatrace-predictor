# データ収集 ベストプラクティス集

**最終更新**: 2026-02-04
**目的**: 新規スクリプト作成時の参考となるベストプラクティス集

---

## 目次

1. [必須パターン](#必須パターン)
2. [開催スケジュール確認](#開催スケジュール確認)
3. [既存データチェック](#既存データチェック)
4. [エラーハンドリング](#エラーハンドリング)
5. [UPSERT（INSERT OR REPLACE）](#upsertinsert-or-replace)
6. [バッチ処理](#バッチ処理)
7. [進捗表示とログ](#進捗表示とログ)
8. [並列処理](#並列処理)
9. [DB設定](#db設定)
10. [シグナルハンドリング](#シグナルハンドリング)

---

## 必須パターン

新規データ収集スクリプトを作成する際は、以下のパターンを必ず実装してください。

### チェックリスト

- [ ] 開催スケジュールを事前取得（全会場アクセスを回避）
- [ ] 既存データをチェック（重複取得を回避）
- [ ] エラー種別を分類（データなし vs エラー）
- [ ] リトライ機能（指数バックオフ）
- [ ] UPSERT使用（DELETE+INSERT禁止）
- [ ] バッチ処理（100件程度）
- [ ] 進捗表示（100件ごと）
- [ ] ログファイル出力
- [ ] WALモード有効化
- [ ] シグナルハンドラ（優雅な終了）

---

## 開催スケジュール確認

### 問題

全24会場×全日付にアクセスすると、開催していない会場への無駄なリクエストが発生します。
約50%のリクエストが無駄になり、処理時間とサーバー負荷が増大します。

### 解決策

`ScheduleScraper`を使用して、開催日のみを対象にします。

### 実装例

**良い例（fetch_to_csv_parallel_improved.py より）**:

```python
from src.scraper.schedule_scraper import ScheduleScraper

def get_schedule_for_period(start_date: str, end_date: str):
    """
    期間内の開催スケジュールを取得

    Returns:
        dict: {
            '20240101': ['01', '05', '10', ...],  # その日に開催している会場
            '20240102': ['02', '06', '12', ...],
            ...
        }
    """
    scraper = ScheduleScraper()
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    print("\n=== 開催スケジュール取得中 ===")
    venue_schedule = scraper.get_schedule_for_period(start_dt, end_dt)
    scraper.close()

    # 会場→日付 を 日付→会場 に変換
    date_schedule = {}
    for venue_code, dates in venue_schedule.items():
        for date_str in dates:
            if date_str not in date_schedule:
                date_schedule[date_str] = []
            date_schedule[date_str].append(venue_code)

    # 各日付の会場リストをソート
    for date_str in date_schedule:
        date_schedule[date_str].sort()

    # 統計表示
    total_venue_days = sum(len(venues) for venues in date_schedule.values())
    days_count = len(date_schedule)
    avg_venues = total_venue_days / days_count if days_count > 0 else 0

    print(f"  期間: {start_date} - {end_date}")
    print(f"  開催日数: {days_count}日")
    print(f"  総会場日数: {total_venue_days} (平均 {avg_venues:.1f}会場/日)")

    return date_schedule
```

### 効果

- タスク数: 50%削減
- 処理時間: 約半分
- サーバー負荷: 大幅軽減

---

## 既存データチェック

### 問題

既に収集済みのデータを再度取得すると、処理時間の浪費とサーバー負荷になります。

### 解決策

収集前に既存データを確認し、未収集のみを対象にします。

### 実装例

**良い例（collect_beforeinfo_2020_2023_optimized.py より）**:

```python
def get_already_collected_races(db_path):
    """既に収集済みのレースIDを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # exhibition_timeが入っているレースは収集済みとみなす
    cursor.execute("""
        SELECT DISTINCT race_id FROM race_details
        WHERE exhibition_time IS NOT NULL
    """)
    collected = set(row[0] for row in cursor.fetchall())
    conn.close()

    return collected

# 使用例
collected = get_already_collected_races(str(db_path))
races = [r for r in all_races if r[0] not in collected]
print(f"全レース数: {len(all_races):,}件")
print(f"収集済み: {len(collected):,}件")
print(f"残り: {len(races):,}件")
```

**良い例（fetch_odds_parallel_safe.py より）**:

```python
def get_races_to_fetch(self, start_date, end_date):
    """未取得レースを取得"""
    conn = sqlite3.connect(self.db_path, timeout=30.0)
    cursor = conn.cursor()

    query = """
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    """
    cursor.execute(query, (start_date, end_date))
    races = cursor.fetchall()
    conn.close()
    return races
```

### 効果

- 2回目以降の実行が高速化
- サーバー負荷軽減
- 再開機能の実現

---

## エラーハンドリング

### 問題

「データなし」と「取得エラー」を区別しないと、本来取得すべきデータを見逃す可能性があります。

### 解決策

エラー種別を明確に分類し、リトライ対象を区別します。

### 実装例

**良い例（補完_レース詳細データ_改善版v4.py より）**:

```python
def fetch_race_details(race_id, venue_code, race_date, race_number):
    """
    レース詳細データを取得

    Returns:
        tuple: (race_id, details_data, status)
               status: 'success', 'error', 'skip', 'timeout'
    """
    date_str = race_date.replace('-', '')
    scraper = get_scraper()

    max_retries = 2
    base_wait = 0.5

    for attempt in range(max_retries):
        try:
            result = scraper.get_race_result_complete(venue_code, date_str, race_number)

            if result and 'race_details' in result and result['race_details']:
                return (race_id, result['race_details'], 'success')
            else:
                # レースデータが存在しない（正常なデータなし）
                return (race_id, None, 'skip')

        except Exception as e:
            error_str = str(e).lower()

            # タイムアウトは即座に諦める（サーバー負荷軽減）
            if 'timeout' in error_str or 'timed out' in error_str:
                return (race_id, None, 'timeout')

            # その他のエラーはリトライ
            if attempt < max_retries - 1:
                wait_time = base_wait * (2 ** attempt) + random.uniform(0, 0.3)
                time.sleep(wait_time)
                continue
            else:
                return (race_id, None, 'error')

    return (race_id, None, 'error')
```

**推奨: Enumによる分類**:

```python
from enum import Enum

class FetchResult(Enum):
    SUCCESS = "success"           # 成功
    NO_DATA = "no_data"           # データなし（正常）
    NETWORK_ERROR = "network"     # ネットワークエラー（要リトライ）
    TIMEOUT = "timeout"           # タイムアウト（要リトライ）
    SERVER_ERROR = "server"       # サーバーエラー（要リトライ）
    PARSE_ERROR = "parse"         # パースエラー
```

### 効果

- 正確なエラー統計
- 適切なリトライ判断
- 欠損データの特定

---

## UPSERT（INSERT OR REPLACE）

### 問題

`DELETE` + `INSERT` パターンは以下の問題があります:
- 外部キー制約違反
- トランザクション失敗時のデータ消失
- 競合条件

### 解決策

SQLiteの `INSERT OR REPLACE` または `ON CONFLICT` を使用します。

### 実装例

**良い例（fetch_odds_parallel_safe.py より）**:

```python
def save_batch_to_db(self, batch_data):
    """バッチデータをDBに保存（UPSERT使用）"""
    if not batch_data:
        return

    cursor = self.db_conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        for race_id, odds_data in batch_data:
            for combination, odds_value in odds_data.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO trifecta_odds
                    (race_id, combination, odds, fetched_at)
                    VALUES (?, ?, ?, datetime('now'))
                """, (race_id, combination, odds_value))

        self.db_conn.commit()

    except Exception as e:
        self.logger.error(f"DB保存エラー: {e}")
        self.db_conn.rollback()
```

**良い例（補完_レース詳細データ_改善版v4.py より）**:

```python
# COALESCEで既存値を保持しつつ更新
cursor.execute("""
    UPDATE race_details
    SET exhibition_time = COALESCE(?, exhibition_time),
        tilt_angle = COALESCE(?, tilt_angle),
        st_time = COALESCE(?, st_time)
    WHERE id = ?
""", (exhibition_time, tilt_angle, st_time, detail_id))
```

**悪い例（避けるべき）**:

```python
# NG: DELETE + INSERT
cursor.execute('DELETE FROM race_conditions WHERE race_id = ?', (race_id,))
cursor.execute('''
    INSERT INTO race_conditions (race_id, temperature, ...)
    VALUES (?, ?, ...)
''', (race_id, temp, ...))
```

### 効果

- データ整合性の維持
- トランザクション安全性
- 外部キー制約との整合

---

## バッチ処理

### 問題

1件ずつコミットすると:
- 処理速度低下
- DBロックの頻発
- トランザクションオーバーヘッド

### 解決策

100件程度のバッチでまとめて処理します。

### 実装例

**良い例（補完_決まり手データ_改善版.py より）**:

```python
batch = []
batch_size = 100

conn = sqlite3.connect(DB_PATH)

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(fetch_kimarite_fast, race): race for race in races}

    for i, future in enumerate(as_completed(futures), 1):
        try:
            result = future.result()

            if result:
                batch.append(result)

                # バッチサイズに達したら保存
                if len(batch) >= batch_size:
                    update_kimarite_batch(conn, batch)
                    print(f"[{i}/{len(races)}] 保存完了: {len(batch)}件")
                    batch = []

        except Exception as e:
            error_count += 1

# 残りのバッチを保存
if batch:
    update_kimarite_batch(conn, batch)
    print(f"最終バッチ保存完了: {len(batch)}件")

conn.close()
```

### 効果

- 処理速度向上
- DB負荷軽減
- トランザクション効率化

---

## 進捗表示とログ

### 問題

長時間処理で進捗が見えないと:
- 状態把握困難
- エラー原因特定困難
- 再開位置不明

### 解決策

詳細な進捗表示とファイルログを実装します。

### 実装例

**良い例（fetch_odds_parallel_safe.py より）**:

```python
def setup_logging(self, log_file):
    """ロギング設定"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8', mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    self.logger = logging.getLogger(__name__)
    return self.logger

# 進捗表示（100件ごと）
if processed % 100 == 0 or processed == total:
    elapsed = time.time() - start_time
    rate = processed / elapsed if elapsed > 0 else 0
    remaining = (total - processed) / rate if rate > 0 else 0
    progress_pct = (processed / total) * 100

    self.logger.info(
        f"進捗: {processed:,}/{total:,} ({progress_pct:.1f}%) | "
        f"成功: {self.success_count:,}, エラー: {self.error_count:,} | "
        f"速度: {rate:.2f}件/秒 | 残り: {remaining/3600:.1f}時間"
    )
```

### 効果

- リアルタイム状態把握
- トラブルシューティング支援
- 処理履歴の記録

---

## 並列処理

### 問題

シングルスレッドでは:
- I/O待ち時間が無駄
- 処理時間が長い

### 解決策

`ThreadPoolExecutor`で並列化（I/Oバウンド向け）。

### 実装例

**良い例（補完_決まり手データ_改善版.py より）**:

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# スレッドローカルセッション
thread_local = threading.local()

def get_session():
    """スレッドローカルなセッションを取得"""
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update({
            'User-Agent': 'Mozilla/5.0 ...'
        })
    return thread_local.session

# 並列処理
max_workers = 16

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(fetch_kimarite_fast, race): race for race in races}

    for i, future in enumerate(as_completed(futures), 1):
        result = future.result()
        # 処理...
```

### 推奨ワーカー数

| 処理タイプ | 推奨ワーカー数 |
|-----------|---------------|
| 軽量API | 12-16 |
| 重いページ | 6-8 |
| Selenium | 4-6 |
| オッズ（負荷制限） | 8-10 |

---

## DB設定

### 問題

デフォルト設定では:
- 並列書き込みでロック
- タイムアウトエラー

### 解決策

WALモードとタイムアウト設定を行います。

### 実装例

**良い例（fetch_odds_parallel_safe.py より）**:

```python
def setup_database(self):
    """データベース設定（WALモード有効化）"""
    self.db_conn = sqlite3.connect(
        self.db_path,
        check_same_thread=False,
        timeout=30.0
    )

    # WALモード有効化（並列書き込み改善）
    self.db_conn.execute("PRAGMA journal_mode=WAL")

    # パフォーマンスと安全性のバランス
    self.db_conn.execute("PRAGMA synchronous=NORMAL")

    # タイムアウト設定
    self.db_conn.execute("PRAGMA busy_timeout=30000")

    self.logger.info("データベース設定完了（WALモード有効）")
```

### 効果

- 並列読み書き対応
- ロック競合削減
- クラッシュ耐性向上

---

## シグナルハンドリング

### 問題

Ctrl+Cで強制終了すると:
- バッファ内データ消失
- トランザクション中断
- DB破損リスク

### 解決策

シグナルハンドラで優雅に終了します。

### 実装例

**良い例（fetch_odds_parallel_safe.py より）**:

```python
import signal
from threading import Event

class SafeParallelOddsFetcher:
    def __init__(self, ...):
        self.shutdown_event = Event()
        self.is_shutting_down = False

    def setup_signal_handlers(self):
        """シグナルハンドラ設定"""
        def signal_handler(signum, frame):
            if not self.is_shutting_down:
                self.logger.warning("\n" + "=" * 80)
                self.logger.warning("終了シグナル受信。優雅にシャットダウン...")
                self.logger.warning("データを保存中。強制終了しないでください。")
                self.logger.warning("=" * 80)
                self.is_shutting_down = True
                self.shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def run(self, ...):
        # メインループ内でチェック
        for future in as_completed(futures):
            if self.shutdown_event.is_set():
                self.logger.warning("シャットダウン処理を開始")
                break

            # 通常処理...

        # 終了処理
        finally:
            # 残りのバッファを保存
            if self.batch_buffer:
                self.save_batch_to_db(self.batch_buffer)
                self.logger.info("バッファデータ保存完了")

            # DB接続クローズ
            if self.db_conn:
                self.db_conn.close()
```

### 効果

- データ損失防止
- クリーンシャットダウン
- ユーザーフレンドリー

---

## まとめ

### 新規スクリプト作成時のテンプレート

`scripts/templates/data_collection_template.py` をベースに作成してください。

### 参照すべき良いスクリプト

| パターン | 参照スクリプト |
|---------|---------------|
| 開催スケジュール | `fetch_to_csv_parallel_improved.py` |
| 既存データチェック | `collect_beforeinfo_2020_2023_optimized.py` |
| エラー分類 | `補完_レース詳細データ_改善版v4.py` |
| UPSERT | `fetch_odds_parallel_safe.py` |
| バッチ処理 | `補完_決まり手データ_改善版.py` |
| ログ・進捗 | `fetch_odds_parallel_safe.py` |
| シグナルハンドラ | `fetch_odds_parallel_safe.py` |

---

## 関連ドキュメント

- [DATA_COLLECTION_TROUBLESHOOTING.md](DATA_COLLECTION_TROUBLESHOOTING.md) - トラブルシューティング
- [DATA_COLLECTION_SCRIPTS_STATUS.md](DATA_COLLECTION_SCRIPTS_STATUS.md) - スクリプト状態一覧
- [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) - マスターガイド

---

**最終更新**: 2026-02-04
