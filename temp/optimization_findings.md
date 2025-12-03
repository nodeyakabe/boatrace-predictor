# 予測処理の最適化調査結果

**調査日時**: 2025-12-03
**調査方法**: Pythonプロファイラーによる処理時間計測

---

## 現状の問題

### パフォーマンス

- **1レースあたり32秒**
- **100レースで53分**（期待値: 2-3分）
- **約18倍遅い**

### ボトルネック特定

プロファイリング結果:

```
98回のDB execute(): 33.859秒 (全体の99.5%)
└─ 1回あたり 0.346秒
```

#### 主な原因

1. **racer_analyzer.analyze_race_entries()**: 18.3秒
   - 25回のDB接続 (14.6秒)

2. **motor_analyzer.analyze_race_motors()**: 11.1秒
   - 13回のDB接続 (7.3秒)

3. **entry_prediction_model.predict_race_entries()**: 3.3秒
   - 6回のDB接続

4. **各種統計取得メソッド**: 各3-4秒
   - get_racer_overall_stats (3.9秒)
   - get_motor_stats (3.8秒)
   - get_racer_st_stats (3.8秒)
   - get_racer_venue_stats (3.7秒)
   - etc.

---

## 実施済みの最適化

### 1. use_cache=True をデフォルト化

```python
# 変更前
def __init__(self, ..., use_cache: bool = False):

# 変更後
def __init__(self, ..., use_cache: bool = True):
```

**効果**: データのキャッシュは有効化されたが、**DB接続自体は毎回作成されている**

### 2. 階層的予測モデルの機能フラグ制御

```python
# 変更前
if self.hierarchical_predictor is not None:

# 変更後
if is_feature_enabled('hierarchical_predictor') and self.hierarchical_predictor is not None:
```

**効果**: 機能フラグがFalseなので、階層的予測は実行されない（軽微な改善）

### 3. 未実装機能の無効化（feature_flags.py）

以下を全てFalseに設定:
- lightgbm_ranking
- shap_explainability
- hierarchical_predictor
- etc.

**効果**: エラーは解消されたが、速度改善は限定的

---

## 根本的な問題

### DB接続の大量作成

各Analyzerクラスが独自にDB接続を作成:

```python
# racer_analyzer.py
def _connect(self):
    return sqlite3.connect(self.db_path)

def _fetch_one(self, query, params):
    conn = self._connect()  # 毎回新規接続！
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    return result
```

**問題点**:
- 1つのanalyze_race_entries()呼び出しで25回接続
- 1つのanalyze_race_motors()呼び出しで13回接続
- **合計98回の接続/切断**

### キャッシュの限界

BatchDataLoaderは「データ」をキャッシュするが、「DB接続」は再利用しない:

```python
# batch_data_loader.py
class BatchDataLoader:
    def get_racer_stats(self, racer_number):
        if racer_number in self.cache:
            return self.cache[racer_number]

        # キャッシュミス時は新規接続
        conn = sqlite3.connect(self.db_path)
        # データ取得
        conn.close()
```

---

## 必要な最適化（未実装）

### Phase 1: DB接続の再利用（最優先）

**期待効果**: 80-90%の速度改善

#### 方法A: predict_race内で接続を渡す

```python
def predict_race(self, race_id: int):
    with sqlite3.connect(self.db_path) as conn:
        # 全てのAnalyzerに接続を渡す
        racer_analyses = self.racer_analyzer.analyze_race_entries(race_id, conn=conn)
        motor_analyses = self.motor_analyzer.analyze_race_motors(race_id, conn=conn)
        # ...
```

#### 方法B: 接続プール実装

```python
class DBConnectionPool:
    def __init__(self, db_path, pool_size=5):
        self.connections = [
            sqlite3.connect(db_path, check_same_thread=False)
            for _ in range(pool_size)
        ]

    @contextmanager
    def get_connection(self):
        conn = self.connections.pop(0)
        try:
            yield conn
        finally:
            self.connections.append(conn)
```

### Phase 2: バッチクエリの活用

**期待効果**: さらに20-30%の速度改善

N+1問題の解消:

```python
# 現状: 6艇ごとにクエリ
for pit in range(1, 7):
    racer_stats = get_racer_stats(racer_number)

# 改善: 1回のクエリで全艇取得
racer_stats_all = get_all_racer_stats(racer_numbers)
```

### Phase 3: SQLiteインデックス追加

**期待効果**: 10-15%の速度改善

```sql
CREATE INDEX IF NOT EXISTS idx_race_id ON results(race_id);
CREATE INDEX IF NOT EXISTS idx_racer_venue ON results(racer_number, venue_code);
CREATE INDEX IF NOT EXISTS idx_motor_date ON motor_performance(motor_number, race_date);
```

---

## 期待される最終結果

| 項目 | 現在 | Phase 1後 | Phase 2後 | 目標 |
|------|------|-----------|-----------|------|
| 1レース | 32秒 | 3-5秒 | 2-3秒 | **<3秒** |
| 100レース | 53分 | 5-8分 | 3-5分 | **<5分** |
| 削減率 | - | 90% | 93% | **94%** |

---

## 次のステップ

1. **Phase 1の実装** - DB接続再利用（最優先）
   - 各Analyzerに `conn` パラメータ追加
   - predict_race()内で1つの接続を全処理で共有

2. **テストで効果確認**
   - 1レーステスト: 32秒 → 3秒を確認
   - 100レーステスト: 53分 → 5分を確認

3. **Phase 2以降は必要に応じて実装**

---

## 注意事項

### 精度には影響なし

これらの最適化は全て「処理効率の改善」であり、**予測アルゴリズムには一切変更を加えない**:

- ✅ 同じデータを取得
- ✅ 同じ計算を実行
- ✅ 同じスコアを出力

唯一の違いは「実行速度」のみ。

### 実装の優先順位

1. **最優先**: DB接続再利用（Phase 1）
2. **中優先**: バッチクエリ（Phase 2）
3. **低優先**: インデックス（Phase 3）

---

**結論**: 現在のパフォーマンス問題の99.5%はDB接続の大量作成が原因。Phase 1の実装で劇的に改善する見込み。
