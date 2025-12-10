# V3 最適化分析と改善案

## 現在のボトルネック (V2/V3共通)

### 1. **Database Locked問題** (最大のボトルネック)

**現象**:
- 6並列ワーカーが同時にSQLiteへ書き込み
- SQLiteは1つの書き込みトランザクションのみ許可
- 大量の`database is locked`エラーが発生
- エラーが出たレースはスキップされる → 5.6%の欠損

**処理時間への影響**:
```
理想: 6並列 × 2レース/分 = 12レース/分
実際: database locked多発で約8レース/分に低下 (33%の性能低下)
```

**現在のV3の問題点**:
```python
# fetch_parallel_v3.py 58行目
success = db.save_race_data(race_data)
if not success:
    result['error'] = 'データ保存失敗'
    return result  # ← エラーで即終了、リトライなし
```

### 2. **1レースあたり3回のHTTP通信**

**V3の処理フロー**:
```python
def fetch_single_race(args):
    # HTTP通信1: 出走表取得 (0.5秒)
    race_data = race_scraper.get_race_card(venue_code, date_str, race_number)
    db.save_race_data(race_data)  # ← DB書き込み1

    # HTTP通信2: 事前情報取得 (0.5秒)
    beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)
    db.save_race_details(race_id, detail_updates)  # ← DB書き込み2

    # HTTP通信3: 結果完全版取得 (0.5秒)
    complete_result = result_scraper.get_race_result_complete(venue_code, date_str, race_number)
    db.save_race_result(result_data_for_save)  # ← DB書き込み3
    db.save_race_details(race_id, detail_updates)  # ← DB書き込み4
    db.save_weather_data(...)  # ← DB書き込み5
```

**時間内訳** (1レースあたり):
```
HTTP通信: 1.5秒
DB書き込み: 5回 × 0.1秒 = 0.5秒 (lock待ち含む)
合計: 約2.0秒/レース
```

### 3. **各プロセスで独立したDB接続**

```python
# 各ワーカープロセスで毎回初期化
db = DataManager()  # ← 6プロセス全てが同じDBに書き込み
```

**問題**:
- 6プロセスが1つのSQLiteファイルに同時書き込み
- ロック競合が頻発
- 各プロセスがリトライせずにエラーを返す

---

## 改善案: V4の設計

### **改善1: バッチ書き込み方式 (最重要)**

**概要**: HTTP通信と DB書き込みを分離

```python
# 処理フロー
1. 全ワーカーがHTTP通信のみ実行 (並列)
2. 取得したデータをキューに追加
3. 専用のDBライタースレッドが1つずつ書き込み (直列)
```

**実装イメージ**:
```python
from multiprocessing import Queue
from threading import Thread

# グローバルキュー
data_queue = Queue()

def fetch_worker(args):
    """HTTP通信のみ実行（DB書き込みなし）"""
    venue_code, date_str, race_number = args

    # 1. HTTP通信: 出走表
    race_data = race_scraper.get_race_card(venue_code, date_str, race_number)

    # 2. HTTP通信: 事前情報
    beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)

    # 3. HTTP通信: 結果
    complete_result = result_scraper.get_race_result_complete(venue_code, date_str, race_number)

    # キューに追加（DB書き込みは別スレッドで）
    data_queue.put({
        'race_data': race_data,
        'beforeinfo': beforeinfo,
        'result': complete_result
    })

def db_writer_thread():
    """専用DBライタースレッド"""
    db = DataManager()

    while True:
        data = data_queue.get()
        if data is None:  # 終了シグナル
            break

        # DB書き込みを直列実行（lockなし）
        race_id = db.save_race_data(data['race_data'])
        db.save_race_details(race_id, data['beforeinfo'])
        db.save_race_result(data['result'])
        db.save_weather_data(data['result']['weather_data'])
```

**期待効果**:
```
現在: 6ワーカー × DB書き込み直接 → lock多発
改善後: 6ワーカー (HTTP) + 1ライター (DB) → lock解消

処理速度:
- HTTP: 1.5秒/レース (6並列 = 0.25秒/レース)
- DB書き込み: 0.5秒/レース (1スレッド直列)
→ ボトルネックはDB書き込み (0.5秒/レース)

理論値: 2レース/秒 = 120レース/分 (現在の10倍)
実際: 約60レース/分 (現在の5倍)

残り675件 → 約11分で完了 (現在56分 → 11分)
```

---

### **改善2: リトライ機構の追加**

**現在の問題**:
```python
success = db.save_race_data(race_data)
if not success:
    result['error'] = 'データ保存失敗'
    return result  # ← 1回失敗で終了
```

**改善案**:
```python
import time

def save_with_retry(func, *args, max_retries=3, delay=0.5):
    """リトライ機能付き保存"""
    for attempt in range(max_retries):
        try:
            return func(*args)
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))  # 指数バックオフ
                continue
            else:
                raise
    return None

# 使用例
race_id = save_with_retry(db.save_race_data, race_data)
```

**期待効果**:
```
現在: 1回失敗で5.6%欠損
改善後: 3回リトライで0.5%未満に削減
```

---

### **改善3: SQLite設定の最適化**

**現在の問題**: デフォルトのSQLite設定では並列書き込みに弱い

**改善案**:
```python
# src/database/data_manager.py に追加
import sqlite3

conn = sqlite3.connect('data/boatrace.db', timeout=30.0)

# WALモード有効化（並列書き込み対応）
conn.execute('PRAGMA journal_mode=WAL')

# 同期モードを調整（速度優先）
conn.execute('PRAGMA synchronous=NORMAL')

# キャッシュサイズ増加
conn.execute('PRAGMA cache_size=-64000')  # 64MB
```

**WAL (Write-Ahead Logging) モードの効果**:
```
通常モード: 書き込み時に読み取りもブロック
WALモード: 書き込み中も読み取り可能、並列性が向上

期待効果: database locked エラーを50%削減
```

---

### **改善4: 並列数の最適化**

**現在**: 6並列 → database lock多発

**最適化案**:
```
パターンA: バッチ書き込み方式
  - HTTPワーカー: 10～12並列
  - DBライター: 1スレッド
  → lock解消、HTTP並列度向上

パターンB: WALモード + リトライ
  - 並列数: 4並列
  → lock頻度削減、リトライで回復

パターンC: ハイブリッド
  - HTTPワーカー: 8並列
  - DBライター: 2スレッド (WALモード)
  → 最高速度
```

---

### **改善5: HTTP通信の最適化**

**現在**: 各レースで3回HTTP通信

**改善案**: HTTP/2セッション再利用
```python
import httpx

# HTTP/2対応クライアント
client = httpx.Client(http2=True)

# セッション再利用で通信時間30%削減
# 1.5秒 → 1.0秒/レース
```

---

## V4実装の優先度

### **優先度1: バッチ書き込み方式** (必須)
- database locked問題を根本解決
- 実装時間: 約1時間
- 効果: 処理速度5倍、欠損率0.5%未満

### **優先度2: WALモード有効化** (推奨)
- 既存コードへの影響最小
- 実装時間: 10分
- 効果: lock頻度50%削減

### **優先度3: リトライ機構** (推奨)
- バッチ方式との併用で完璧
- 実装時間: 30分
- 効果: 欠損率0.1%未満

### **優先度4: 並列数調整** (オプション)
- 環境依存性が高い
- 実装時間: 5分
- 効果: 環境により10～30%向上

### **優先度5: HTTP/2対応** (オプション)
- 効果は限定的
- 実装時間: 30分
- 効果: 通信時間20～30%削減

---

## V4実装プラン (1時間以内)

### **Step 1: WALモード有効化 (10分)**
```python
# src/database/data_manager.py に追加
def __init__(self):
    self.db_path = DATABASE_PATH
    # WALモード有効化
    conn = sqlite3.connect(self.db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.close()
```

### **Step 2: バッチ書き込み方式の実装 (40分)**
```python
# fetch_parallel_v4.py
- fetch_worker(): HTTP通信のみ
- db_writer_thread(): DB書き込み専用
- Queue経由でデータ受け渡し
```

### **Step 3: テスト (10分)**
```bash
# テスト用DB使用
python create_test_db.py
python test_v4_with_testdb.py

# 実データで1日分テスト
python fetch_parallel_v4.py --start 2025-10-01 --end 2025-10-01 --workers 10
```

---

## 期待される改善結果

### **処理速度**
```
現在 (V2): 12レース/分 (理論値) → 8レース/分 (実際)
V3: 12レース/分 (lock問題は未解決)
V4: 60～120レース/分 (5～10倍)

残り675件の処理時間:
- 現在: 約56分
- V4: 約6～11分
```

### **データ完全性**
```
現在 (V2):
  - 出走表: 94.4%
  - 結果: 85.5%
  - 進入コース: 58.8%

V3:
  - 出走表: 94.4% (lock問題で変わらず)
  - 結果: 85.5%
  - 進入コース: 100% (取得はできる)

V4:
  - 出走表: 99.9%
  - 結果: 99.9%
  - 進入コース: 100%
  - STタイム: 95%+
  - 天気: 100%
```

---

## まとめ

### **最大のボトルネック**
Database Locked問題 → バッチ書き込み方式で解決

### **V4で実装すべき機能**
1. **バッチ書き込み方式** (必須)
2. **WALモード** (推奨)
3. **リトライ機構** (推奨)

### **実装時間**
約1時間 (現在のデータ収集完了を待つ時間で実装可能)

### **期待効果**
- 処理速度: **5～10倍**
- 欠損率: **5.6% → 0.1%未満**
- 1ヶ月のデータ収集: **3時間 → 20分**

---

**作成日時**: 2025-10-30 21:00
**ステータス**: 設計完了 → V4実装準備
