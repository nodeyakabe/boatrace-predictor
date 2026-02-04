# データ収集スクリプト トラブルシューティングガイド

**最終更新**: 2026-02-04
**目的**: データ収集スクリプトでよくある問題と予防策・対処法

---

## 目次

1. [よくあるトラブルパターン](#よくあるトラブルパターン)
2. [トラブル検出チェックリスト](#トラブル検出チェックリスト)
3. [予防策とベストプラクティス](#予防策とベストプラクティス)
4. [トラブル別対処法](#トラブル別対処法)
5. [スクリプト実装時のチェックリスト](#スクリプト実装時のチェックリスト)

---

## よくあるトラブルパターン

### 1. 開催スケジュール未確認で全会場にアクセス

**症状**:
- 処理時間が異常に長い
- 大量の「データなし」ログが出力される
- サーバーへの不要なリクエスト発生

**原因**:
```python
# 悪い例: 全24会場×全日付にアクセス
ALL_VENUES = ['01', '02', '03', ... , '24']
for date in date_range:
    for venue in ALL_VENUES:
        fetch_data(venue, date)  # 開催していない会場にもアクセス
```

**影響**:
- 処理時間: 本来の2-3倍
- サーバー負荷: 約50%が無駄なリクエスト
- エラー判定困難: 「データなし」と「取得失敗」の区別がつかない

**正しい実装**:
```python
# 良い例: 開催スケジュールを事前取得
from src.scraper.schedule_scraper import ScheduleScraper

schedule_scraper = ScheduleScraper()
schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)

for venue_code, dates in schedule.items():
    for date_str in dates:
        fetch_data(venue_code, date_str)  # 開催日のみ
```

**該当スクリプト（良い例）**:
- `fetch_to_csv_parallel_improved.py` - ScheduleScraperを使用

**該当スクリプト（要改善）**:
- `fetch_historical_data_parallel.py` - 全会場にアクセス

---

### 2. 取得失敗を「開催なし」と誤判定

**症状**:
- 一部の日付・会場でデータが欠損
- エラーログが少ない（エラーを見逃している）
- 後から補完しても埋まらないデータがある

**原因**:
```python
# 悪い例: 例外をすべて無視
try:
    data = fetch_data(venue, date)
    if not data:
        continue  # データなし扱い
except Exception:
    pass  # エラーも無視
```

**問題点**:
- ネットワークエラーを「データなし」と誤認
- タイムアウトを「データなし」と誤認
- サーバー5xxエラーを「データなし」と誤認

**正しい実装**:
```python
# 良い例: エラー種別を明確に分類
from enum import Enum

class FetchResult(Enum):
    SUCCESS = "success"
    NO_DATA = "no_data"          # 開催なし（正常）
    NETWORK_ERROR = "network"    # ネットワークエラー（要リトライ）
    TIMEOUT = "timeout"          # タイムアウト（要リトライ）
    SERVER_ERROR = "server"      # サーバーエラー（要リトライ）
    PARSE_ERROR = "parse"        # パースエラー（データ形式問題）

def fetch_with_classification(venue_code, date):
    try:
        response = session.get(url, timeout=15)

        if response.status_code == 404:
            return FetchResult.NO_DATA, None

        response.raise_for_status()

        data = parse_response(response)
        if not data or not data.get('entries'):
            return FetchResult.NO_DATA, None

        return FetchResult.SUCCESS, data

    except requests.Timeout:
        return FetchResult.TIMEOUT, None
    except requests.ConnectionError:
        return FetchResult.NETWORK_ERROR, None
    except requests.HTTPError as e:
        if e.response.status_code >= 500:
            return FetchResult.SERVER_ERROR, None
        return FetchResult.NO_DATA, None
    except Exception as e:
        return FetchResult.PARSE_ERROR, None
```

**該当スクリプト（良い例）**:
- `補完_レース詳細データ_改善版v4.py` - status分類あり（success/error/skip/timeout）

---

### 3. 既存データの重複取得

**症状**:
- 2回目以降の実行でも初回と同じ時間がかかる
- DBに重複レコードが発生（UNIQUEエラーまたは上書き）
- 無駄なサーバーリクエスト

**原因**:
```python
# 悪い例: 既存チェックなし
for date in date_range:
    for venue in venues:
        data = fetch_data(venue, date)
        save_to_db(data)  # 毎回上書き
```

**正しい実装**:
```python
# 良い例: 既存データをスキップ
def get_already_collected(db_path, start_date, end_date):
    """既に収集済みのrace_idを取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM races
        WHERE race_date BETWEEN ? AND ?
    """, (start_date, end_date))
    collected = set(row[0] for row in cursor.fetchall())
    conn.close()
    return collected

# 使用例
collected = get_already_collected(db_path, start_date, end_date)
for race in races_to_fetch:
    if race['id'] in collected:
        continue  # スキップ
    fetch_and_save(race)
```

**該当スクリプト（良い例）**:
- `collect_beforeinfo_2020_2023_optimized.py` - `get_already_collected_races()` 関数あり
- `fetch_odds_parallel_safe.py` - 未取得レースのみ対象

---

### 4. DELETE + INSERT による更新

**症状**:
- 外部キー制約違反エラー
- トランザクション失敗時にデータ消失
- 複数プロセスでの競合

**原因**:
```python
# 悪い例: DELETE→INSERT
cursor.execute('DELETE FROM race_conditions WHERE race_id = ?', (race_id,))
cursor.execute('''
    INSERT INTO race_conditions (race_id, temperature, ...)
    VALUES (?, ?, ...)
''', (race_id, temp, ...))
```

**問題点**:
- DELETEとINSERTの間で他プロセスが参照すると不整合
- トランザクション失敗時に元データも消失
- 外部キーが設定されていると制約違反

**正しい実装**:
```python
# 良い例1: INSERT OR REPLACE（SQLite）
cursor.execute('''
    INSERT OR REPLACE INTO race_conditions (race_id, temperature, ...)
    VALUES (?, ?, ...)
''', (race_id, temp, ...))

# 良い例2: ON CONFLICT（PostgreSQL/SQLite 3.24+）
cursor.execute('''
    INSERT INTO trifecta_odds (race_id, combination, odds, fetched_at)
    VALUES (?, ?, ?, datetime('now'))
    ON CONFLICT (race_id, combination)
    DO UPDATE SET odds = excluded.odds, fetched_at = excluded.fetched_at
''', (race_id, combination, odds_value))

# 良い例3: UPDATE + INSERT（確実な方法）
cursor.execute('''
    UPDATE race_details
    SET exhibition_time = COALESCE(?, exhibition_time),
        tilt_angle = COALESCE(?, tilt_angle)
    WHERE race_id = ? AND pit_number = ?
''', (exhibition_time, tilt_angle, race_id, pit_number))

if cursor.rowcount == 0:  # 更新対象がなければINSERT
    cursor.execute('''
        INSERT INTO race_details (race_id, pit_number, exhibition_time, tilt_angle)
        VALUES (?, ?, ?, ?)
    ''', (race_id, pit_number, exhibition_time, tilt_angle))
```

**該当スクリプト（良い例）**:
- `fetch_odds_parallel_safe.py` - `INSERT OR REPLACE` 使用
- `補完_レース詳細データ_改善版v4.py` - UPDATE文でCOALESCE使用

**該当スクリプト（要改善）**:
- `collect_beforeinfo_2020_2023_optimized.py` - race_conditionsで `DELETE→INSERT` 使用

---

### 5. バッチ処理なしの逐次DB書き込み

**症状**:
- 処理速度が遅い
- DBがロック状態になりやすい
- 途中失敗時に一貫性が保てない

**原因**:
```python
# 悪い例: 1件ずつコミット
for data in all_data:
    cursor.execute('INSERT INTO ...', data)
    conn.commit()  # 毎回コミット
```

**正しい実装**:
```python
# 良い例: バッチ処理
BATCH_SIZE = 100
batch = []

for data in all_data:
    batch.append(data)

    if len(batch) >= BATCH_SIZE:
        save_batch(batch)
        batch = []

# 残りを保存
if batch:
    save_batch(batch)

def save_batch(batch):
    cursor.execute("BEGIN IMMEDIATE")
    for data in batch:
        cursor.execute('INSERT INTO ...', data)
    conn.commit()
```

**該当スクリプト（良い例）**:
- `補完_決まり手データ_改善版.py` - バッチサイズ100
- `fetch_odds_parallel_safe.py` - バッチサイズ50

---

### 6. 進捗表示・ログ不足

**症状**:
- 長時間実行時に状態が不明
- エラー発生時の原因特定困難
- 再開時にどこまで完了したか不明

**正しい実装**:
```python
# 良い例: 詳細なログと進捗表示
import logging
from datetime import datetime

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f'logs/collection_{datetime.now():%Y%m%d_%H%M%S}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 進捗表示
total = len(tasks)
for i, task in enumerate(tasks, 1):
    result = process_task(task)

    if i % 100 == 0 or i == total:
        elapsed = time.time() - start_time
        rate = i / elapsed if elapsed > 0 else 0
        remaining = (total - i) / rate if rate > 0 else 0

        logger.info(
            f"進捗: {i}/{total} ({i/total*100:.1f}%) | "
            f"成功: {success_count} | エラー: {error_count} | "
            f"速度: {rate:.1f}件/秒 | 残り: {remaining/60:.1f}分"
        )
```

**該当スクリプト（良い例）**:
- `fetch_odds_parallel_safe.py` - ファイル+コンソールログ、詳細進捗
- `collect_beforeinfo_2020_2023_optimized.py` - 100件ごとの進捗表示

---

## トラブル検出チェックリスト

スクリプト実行後に以下を確認:

### 1. 処理効率チェック
```sql
-- 期間内のレース数を確認
SELECT COUNT(*) FROM races WHERE race_date BETWEEN '2024-01-01' AND '2024-01-31';

-- 1日あたりのレース数（約120-150件が正常）
SELECT race_date, COUNT(*) FROM races
WHERE race_date BETWEEN '2024-01-01' AND '2024-01-31'
GROUP BY race_date;
```

### 2. データ品質チェック
```sql
-- NULL値の確認
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN kimarite IS NULL THEN 1 END) as null_kimarite,
    COUNT(CASE WHEN st_time IS NULL THEN 1 END) as null_st_time
FROM race_details;

-- 外部キー整合性
SELECT r.id FROM races r
LEFT JOIN results res ON r.id = res.race_id
WHERE res.race_id IS NULL AND r.race_date < date('now', '-1 day');
```

### 3. エラー率チェック
```python
# ログからエラー率を計算
error_rate = error_count / total_count
if error_rate > 0.05:  # 5%以上はNG
    print(f"警告: エラー率が高い ({error_rate*100:.1f}%)")
```

---

## 予防策とベストプラクティス

### 必須実装項目

1. **開催スケジュール取得**
   ```python
   from src.scraper.schedule_scraper import ScheduleScraper
   ```

2. **既存データチェック**
   ```python
   def get_uncollected_races(db_path, start_date, end_date):
       ...
   ```

3. **エラー分類**
   ```python
   class FetchResult(Enum):
       SUCCESS = "success"
       NO_DATA = "no_data"
       NETWORK_ERROR = "network"
       ...
   ```

4. **リトライ機能**
   ```python
   max_retries = 3
   for attempt in range(max_retries):
       try:
           result = fetch()
           break
       except RetryableError:
           time.sleep(2 ** attempt)  # 指数バックオフ
   ```

5. **UPSERT使用**
   ```python
   cursor.execute('INSERT OR REPLACE INTO ...')
   ```

6. **バッチ処理**
   ```python
   BATCH_SIZE = 100
   ```

7. **詳細ログ**
   ```python
   logging.basicConfig(...)
   ```

---

## トラブル別対処法

### ネットワークエラーが多発

1. **原因特定**
   - サーバー側の問題か確認（ブラウザで手動アクセス）
   - 自身のネットワーク環境確認

2. **対処**
   - ワーカー数を減らす（12→6）
   - リクエスト間隔を増やす（0.5秒→1.0秒）
   - リトライ回数を増やす

### DBロックエラー

1. **原因**
   - 複数プロセスの同時書き込み
   - 長時間トランザクション

2. **対処**
   ```python
   # WALモード有効化
   conn.execute("PRAGMA journal_mode=WAL")
   conn.execute("PRAGMA busy_timeout=30000")
   ```

### メモリ不足

1. **原因**
   - 大量データを一度にメモリ保持
   - ジェネレータ未使用

2. **対処**
   ```python
   # ジェネレータを使用
   def fetch_races():
       for date in dates:
           for race in fetch_day(date):
               yield race

   # バッチ処理
   for batch in batched(fetch_races(), 100):
       process_batch(batch)
   ```

---

## スクリプト実装時のチェックリスト

新しいデータ収集スクリプトを作成する際のチェックリスト:

- [ ] 開催スケジュールを事前取得している
- [ ] 既存データをチェックしてスキップしている
- [ ] エラー種別を明確に分類している（データなし vs エラー）
- [ ] リトライ機能を実装している（指数バックオフ推奨）
- [ ] UPSERT（INSERT OR REPLACE）を使用している
- [ ] バッチ処理を実装している（100件程度）
- [ ] 進捗表示を実装している（100件ごと推奨）
- [ ] ログをファイルに出力している
- [ ] WALモードを有効化している
- [ ] シグナルハンドラで優雅に終了できる

---

## 関連ドキュメント

- [DATA_COLLECTION_BEST_PRACTICES.md](DATA_COLLECTION_BEST_PRACTICES.md) - ベストプラクティス集
- [DATA_COLLECTION_SCRIPTS_STATUS.md](DATA_COLLECTION_SCRIPTS_STATUS.md) - スクリプト状態一覧
- [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) - マスターガイド

---

**最終更新**: 2026-02-04
