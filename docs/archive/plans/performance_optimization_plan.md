# パフォーマンス最適化計画

**作成日**: 2025-12-03
**目的**: 予測精度を維持したまま、処理速度を大幅に改善

---

## 現状の問題

### パフォーマンスの劣化

| 状態 | 1レースあたり処理時間 | 有効化機能 |
|------|----------------------|-----------|
| **初期** | 1-2秒 | dynamic_integration, entry_prediction_model のみ |
| **現在** | 3-5秒 | 全Phase有効化（LightGBM、階層モデル、SHAP等） |

### 影響範囲

1. **UIでの予測生成**: ユーザーが待つ時間が2-3倍に
2. **バックテスト**: 100レースで30分以上（以前は3-5分）
3. **A/Bテスト**: 大規模テストが現実的でない

---

## 最適化戦略

### 原則

✅ **精度は犠牲にしない**
✅ **キャッシュと遅延ロードを活用**
✅ **不要な計算を削減**
✅ **並列処理で高速化**

---

## 1. モデルキャッシング

### 現状の問題

```python
# 毎回モデルをロードしている
def predict_race(self, race_id):
    model = load_lightgbm_model()  # ← 重い！
    venue_model = load_venue_model(venue)  # ← 重い！
    predictions = model.predict(features)
```

### 改善案

```python
class RacePredictor:
    def __init__(self):
        # モデルを初回のみロード
        self._lightgbm_model = None
        self._venue_models = {}
        self._hierarchical_model = None

    @property
    def lightgbm_model(self):
        """遅延ロード: 使用時に1回だけ読み込み"""
        if self._lightgbm_model is None:
            self._lightgbm_model = self._load_lightgbm()
        return self._lightgbm_model

    def get_venue_model(self, venue_code):
        """会場別モデルをキャッシュ"""
        if venue_code not in self._venue_models:
            self._venue_models[venue_code] = self._load_venue_model(venue_code)
        return self._venue_models[venue_code]
```

**期待効果**: モデルロード時間を90%削減（毎回0.5秒 → 初回のみ）

---

## 2. 特徴量計算の最適化

### 現状の問題

```python
# 同じ特徴量を複数回計算
def predict_race(self, race_id):
    features1 = calculate_features(race_id)  # 1回目
    features2 = calculate_features(race_id)  # 2回目（重複！）
```

### 改善案: 特徴量キャッシュ

```python
class FeatureCache:
    def __init__(self):
        self.cache = {}

    def get_or_compute(self, key, compute_func):
        if key not in self.cache:
            self.cache[key] = compute_func()
        return self.cache[key]

# 使用例
feature_cache = FeatureCache()

def predict_race(self, race_id):
    features = feature_cache.get_or_compute(
        f'race_{race_id}',
        lambda: self._calculate_features(race_id)
    )
```

**期待効果**: 特徴量計算時間を50%削減

---

## 3. SHAP計算の条件付き無効化

### 現状の問題

SHAP（説明可能性）は**予測精度に影響しない**が、計算コストが高い。

```python
# 毎回SHAP値を計算（重い！）
if is_feature_enabled('shap_explainability'):
    shap_values = calculate_shap(model, features)  # ← 1秒以上かかる
```

### 改善案: モード別制御

```python
# config/feature_flags.py
FEATURE_FLAGS = {
    # 通常予測（高速）
    'shap_explainability': False,

    # 詳細分析モード（UIで明示的に要求された時のみ）
    'analysis_mode': False,
}

# race_predictor.py
def predict_race(self, race_id, explain=False):
    predictions = self._basic_predict(race_id)

    # 説明が必要な時のみSHAP計算
    if explain and is_feature_enabled('shap_explainability'):
        predictions['shap_values'] = self._calculate_shap(race_id)

    return predictions
```

**期待効果**: SHAP無効化で1レースあたり1-2秒削減

---

## 4. データベース接続プーリング

### 現状の問題

```python
# 毎回DB接続を作成
def predict_race(self, race_id):
    conn = sqlite3.connect('data/boatrace.db')  # ← 毎回接続
    cursor.execute(...)
    conn.close()
```

### 改善案: 接続プール

```python
from contextlib import contextmanager
import sqlite3

class DBConnectionPool:
    def __init__(self, db_path, pool_size=5):
        self.db_path = db_path
        self.connections = []
        for _ in range(pool_size):
            self.connections.append(sqlite3.connect(db_path, check_same_thread=False))

    @contextmanager
    def get_connection(self):
        conn = self.connections.pop(0)
        try:
            yield conn
        finally:
            self.connections.append(conn)

# 使用例
db_pool = DBConnectionPool('data/boatrace.db')

def predict_race(self, race_id):
    with db_pool.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(...)
```

**期待効果**: DB接続時間を80%削減（毎回50ms → 10ms）

---

## 5. クエリ最適化

### 現状の問題

```python
# N+1問題: 艇ごとにクエリを発行
for pit in range(1, 7):
    cursor.execute("SELECT * FROM entries WHERE race_id=? AND pit_number=?", (race_id, pit))
```

### 改善案: バッチクエリ

```python
# 1回のクエリで全艇取得
cursor.execute("""
    SELECT * FROM entries
    WHERE race_id = ?
    ORDER BY pit_number
""", (race_id,))
entries = cursor.fetchall()
```

**期待効果**: クエリ実行時間を60%削減

---

## 6. 並列処理

### バッチ予測の並列化

```python
from multiprocessing import Pool
import concurrent.futures

class BatchPredictor:
    def __init__(self, predictor):
        self.predictor = predictor

    def predict_batch(self, race_ids, n_workers=4):
        """複数レースを並列予測"""
        with concurrent.futures.ProcessPoolExecutor(max_workers=n_workers) as executor:
            results = list(executor.map(self.predictor.predict_race, race_ids))
        return results

# 使用例（バックテスト）
batch_predictor = BatchPredictor(predictor)
results = batch_predictor.predict_batch(race_ids[:100], n_workers=4)
```

**期待効果**: 4コア使用で処理時間を70%削減

---

## 7. 軽量モードの実装

### モード別機能セット

```python
# config/feature_flags.py

# 通常予測モード（高速・本番用）
FAST_MODE_FLAGS = {
    'dynamic_integration': True,
    'entry_prediction_model': True,
    'lightgbm_ranking': True,
    'interaction_features': True,

    # 重い機能は無効化
    'shap_explainability': False,
    'optuna_optimization': False,  # 予測時は不要（学習時のみ）
}

# 詳細分析モード（低速・分析用）
ANALYSIS_MODE_FLAGS = {
    # 全機能有効
    'shap_explainability': True,
    'venue_specific_models': True,
    'hierarchical_predictor': True,
}

# 切り替え
def set_prediction_mode(mode='fast'):
    global FEATURE_FLAGS
    if mode == 'fast':
        FEATURE_FLAGS.update(FAST_MODE_FLAGS)
    elif mode == 'analysis':
        FEATURE_FLAGS.update(ANALYSIS_MODE_FLAGS)
```

### UI側での制御

```python
# Streamlit UI
mode = st.radio("予測モード", ["高速", "詳細分析"])

if mode == "高速":
    set_prediction_mode('fast')
    predictions = predictor.predict_race(race_id)
else:
    set_prediction_mode('analysis')
    predictions = predictor.predict_race(race_id, explain=True)
```

**期待効果**: 高速モードで処理時間を50%削減

---

## 8. インデックスの追加

### 現状の問題

```sql
-- インデックスなし → フルスキャン
SELECT * FROM race_details WHERE race_id = ?
```

### 改善案: 適切なインデックス

```sql
-- 頻繁に使うカラムにインデックス
CREATE INDEX IF NOT EXISTS idx_race_details_race_id ON race_details(race_id);
CREATE INDEX IF NOT EXISTS idx_entries_race_id ON entries(race_id);
CREATE INDEX IF NOT EXISTS idx_results_race_id ON results(race_id);
CREATE INDEX IF NOT EXISTS idx_races_date ON races(race_date);
CREATE INDEX IF NOT EXISTS idx_races_venue_date ON races(venue_code, race_date);
```

**期待効果**: クエリ実行時間を40%削減

---

## 9. Optunaの適切な使用

### 現状の問題

Optunaは**パラメータ最適化用**であり、予測時に実行する必要はない。

```python
# 毎回最適化（誤り）
if is_feature_enabled('optuna_optimization'):
    best_params = optimize_with_optuna()  # ← 不要！
```

### 改善案: オフライン最適化

```python
# 1. パラメータ最適化（事前に1回だけ実行）
# scripts/optimize_parameters.py
best_params = optimize_with_optuna(n_trials=100)
save_params('config/optimized_params.json', best_params)

# 2. 予測時は最適化済みパラメータを使用
# src/analysis/race_predictor.py
def __init__(self):
    self.params = load_params('config/optimized_params.json')
```

**期待効果**: Optuna無効化で処理時間を大幅削減

---

## 10. プロファイリングで真のボトルネック特定

### ツール使用

```python
import cProfile
import pstats

# プロファイリング実行
profiler = cProfile.Profile()
profiler.enable()

predictions = predictor.predict_race(race_id)

profiler.disable()

# 結果を表示
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # 上位20関数
```

**期待される発見**:
- どの関数が最も時間を消費しているか
- 予想外の重複計算
- 最適化すべき優先順位

---

## 実装優先順位

### Phase 1: 即効性の高い最適化（1-2時間）

1. ✅ **SHAP無効化**: 通常予測時はFalse
2. ✅ **Optuna除去**: 予測時には使わない
3. ✅ **モデルキャッシング**: 初回のみロード
4. ✅ **クエリ最適化**: N+1問題解消

**期待効果**: 3-5秒 → 1.5-2秒（40-50%削減）

### Phase 2: 中期的最適化（1-2日）

5. ✅ **特徴量キャッシュ**: 重複計算削減
6. ✅ **DB接続プール**: 接続オーバーヘッド削減
7. ✅ **インデックス追加**: クエリ高速化
8. ✅ **軽量モード実装**: モード切り替え

**期待効果**: 1.5-2秒 → 0.8-1.2秒（さらに40%削減）

### Phase 3: 長期的最適化（1週間）

9. ✅ **並列処理**: バッチ予測の高速化
10. ✅ **プロファイリング**: 継続的な最適化

**期待効果**: バックテストが実用的な時間で完了

---

## 期待される最終結果

| 項目 | 現在 | Phase 1後 | Phase 2後 | 目標 |
|------|------|-----------|-----------|------|
| 1レース予測 | 3-5秒 | 1.5-2秒 | 0.8-1.2秒 | **<1秒** |
| 100レース | 30-40分 | 15-20分 | 8-12分 | **<10分** |
| UI体感 | 遅い | 許容範囲 | 快適 | **高速** |

---

## 注意点

### やってはいけないこと

❌ **精度を犠牲にする最適化**
- モデルの簡略化
- 特徴量の削減
- アンサンブルの省略

✅ **やるべきこと**
- 無駄な計算の削減
- キャッシュの活用
- 効率的なアルゴリズム

---

## 測定方法

### ベンチマークスクリプト

```python
import time

def benchmark_prediction(race_id, n_runs=10):
    """予測速度をベンチマーク"""
    times = []

    for i in range(n_runs):
        start = time.time()
        predictor.predict_race(race_id)
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    print(f"平均予測時間: {avg_time:.2f}秒")
    print(f"最速: {min(times):.2f}秒")
    print(f"最遅: {max(times):.2f}秒")

# 実行
benchmark_prediction(132724, n_runs=10)
```

### 継続的な監視

```python
# src/monitoring/performance_tracker.py
class PerformanceTracker:
    def track_prediction_time(self, race_id, elapsed_time):
        """予測時間をログ記録"""
        with open('logs/prediction_times.csv', 'a') as f:
            f.write(f"{race_id},{elapsed_time},{datetime.now()}\n")

    def get_average_time(self, days=7):
        """過去N日間の平均予測時間"""
        # CSVから集計
        pass
```

---

## 次のステップ

1. **現在実行中のテスト完了を待つ**
2. **Phase 1の最適化を実装**（SHAP無効化、Optuna除去等）
3. **ベンチマークで効果測定**
4. **Phase 2へ進む**

---

## まとめ

現在の処理速度の問題は、多数の高度な機能を同時有効化したことが原因です。

**解決策**:
- 予測時に不要な機能を無効化（SHAP、Optuna）
- モデルと特徴量のキャッシング
- データベースクエリの最適化
- モード別の機能セット

これらの最適化により、**精度を維持したまま処理時間を60-70%削減**できる見込みです。
