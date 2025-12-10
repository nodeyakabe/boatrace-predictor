# 🔒 システム制約・ルール定義

**目的**: システムの不変条件・制約を明文化し、誤った変更を防ぐ

**重要**: コード変更前に必ず確認してください

---

## 📊 データベース制約

### 1. テーブル間の関係

```
races (親)
  ├── entries (子) - FOREIGN KEY: race_id
  ├── race_details (子) - FOREIGN KEY: race_id
  ├── results (子) - FOREIGN KEY: race_id
  └── recommendations (子) - FOREIGN KEY: race_id

venues (親)
  ├── races (子) - FOREIGN KEY: venue_code
  ├── weather (子) - FOREIGN KEY: venue_code
  └── tide (子) - FOREIGN KEY: venue_code
```

**制約**: 子テーブルのレコード挿入前に、親テーブルのレコードが存在すること

### 2. 必須制約（NOT NULL）

#### races テーブル
- `venue_code` (TEXT, NOT NULL) - 会場コード
- `race_date` (DATE, NOT NULL) - レース日
- `race_number` (INTEGER, NOT NULL) - レース番号

#### entries テーブル
- `race_id` (INTEGER, NOT NULL)
- `pit_number` (INTEGER, NOT NULL)

#### results テーブル
- `race_id` (INTEGER, NOT NULL)
- `pit_number` (INTEGER, NOT NULL)
- `rank` (TEXT, NOT NULL)

### 3. UNIQUE制約

```sql
-- 1レース1回のみ
UNIQUE(venue_code, race_date, race_number)  -- races

-- 1レース1艇1エントリー
UNIQUE(race_id, pit_number)  -- entries, race_details, results

-- 1会場1日1気象データ
UNIQUE(venue_code, weather_date)  -- weather
```

**制約**: 重複挿入を試みるとエラーになる

### 4. 値の範囲制約

| カラム | 最小値 | 最大値 | 許可値 |
|--------|--------|--------|--------|
| `venue_code` | '01' | '24' | 24会場 |
| `race_number` | 1 | 12 | 1日最大12レース |
| `pit_number` | 1 | 6 | 6艇固定 |
| `racer_rank` | - | - | A1, A2, B1, B2 |
| `rank` | - | - | 1, 2, 3, 4, 5, 6, F, L, K, S |
| `winning_technique` | 1 | 6 | 逃げ(1), 差し(2), まくり(3), まくり差し(4), 抜き(5), 恵まれ(6) |

### 5. ビジネスロジック制約

#### ⚠️ 最重要：1レース = 6艇

```python
# 必ず検証
entries_count = len(entries_for_race)
assert entries_count == 6, f"1レースは6艇固定（実際: {entries_count}艇）"
```

**理由**: 競艇は必ず6艇で行われる。これが崩れるとすべての計算が破綻する。

#### レース結果の整合性

```python
# 着順は1-6またはF/L/K/S
valid_ranks = ['1', '2', '3', '4', '5', '6', 'F', 'L', 'K', 'S']

# 決まり手は1着のみ（2着以降はNULL）
if rank == '1':
    assert winning_technique in [1, 2, 3, 4, 5, 6]
else:
    assert winning_technique is None
```

---

## 🧮 計算ロジックの制約

### 1. 確率の制約

#### 確率の基本原則
```python
# 1. 確率は0-1の範囲
0 <= probability <= 1

# 2. 確率の合計は1（または100%）
sum(probabilities) == 1.0  # 許容誤差: ±0.01

# 3. 負の確率は存在しない
probability >= 0
```

**検証方法**:
```python
def validate_probabilities(probs):
    assert all(0 <= p <= 1 for p in probs), "確率が0-1範囲外"
    assert abs(sum(probs) - 1.0) < 0.01, f"確率の合計が1でない: {sum(probs)}"
```

### 2. Kelly基準の制約

#### 期待値の計算
```python
# 期待値 = 予測確率 × オッズ - 1
EV = pred_prob * odds - 1

# 正の期待値のみ賭ける
if EV <= 0:
    kelly_fraction = 0.0
    bet_amount = 0.0
```

#### Kelly分数の制約
```python
# 1. 理論値は (bp - q) / b
# 2. 実用上は1/4 Kelly（リスク調整）
kelly_fraction = theoretical_kelly * 0.25

# 3. 最大20%まで（資金保護）
kelly_fraction = min(kelly_fraction, 0.2)

# 4. 負の場合は0
kelly_fraction = max(kelly_fraction, 0.0)
```

**重要**: Kelly基準を破ると資金破綻のリスク

### 3. オッズの制約

```python
# オッズは1.0以上（払い戻しは元金以上）
odds >= 1.0

# 三連単オッズの実用範囲
1.0 <= trifecta_odds <= 100000.0  # 現実的な範囲
```

---

## 📐 特徴量の制約

### 1. 必須特徴量

**これらは必ず存在すること**:
- `pit_number` (1-6)
- `win_rate` (0-10)
- `motor_number` (1-100程度)

### 2. 特徴量の値範囲

| 特徴量 | 型 | 最小値 | 最大値 | 備考 |
|--------|---|--------|--------|------|
| `pit_number` | int | 1 | 6 | 枠番 |
| `win_rate` | float | 0.0 | 10.0 | 勝率 |
| `racer_age` | int | 18 | 70 | 年齢 |
| `racer_weight` | float | 40.0 | 75.0 | 体重（kg） |
| `wind_speed` | float | 0.0 | 30.0 | 風速（m/s） |
| `wave_height` | float | 0.0 | 50.0 | 波高（cm） |
| `temperature` | float | -20.0 | 50.0 | 気温（℃） |
| `water_temperature` | float | 0.0 | 40.0 | 水温（℃） |
| `humidity` | int | 0 | 100 | 湿度（%） |
| `motor_2ren_rate` | float | 0.0 | 1.0 | モーター2連対率 |
| `exhibition_time` | float | 6.0 | 8.0 | 展示タイム（秒） |
| `st_time` | float | -0.5 | 1.0 | STタイミング（秒） |
| `tilt_angle` | float | -3.0 | 3.0 | チルト角（度） |

### 3. 特徴量の欠損値処理

```python
# 数値特徴量: 0または平均値で補完
numeric_features.fillna(0, inplace=True)
# または
numeric_features.fillna(numeric_features.mean(), inplace=True)

# カテゴリ特徴量: 'unknown'で補完
categorical_features.fillna('unknown', inplace=True)
```

**禁止事項**:
- ❌ NaNやInfを含む特徴量で予測を実行
- ❌ 範囲外の値を含む特徴量で予測を実行

---

## 🔢 データ型の制約

### 1. データベースのデータ型

```python
# 数値型
INTEGER  # race_number, pit_number, motor_number, etc.
REAL     # win_rate, temperature, odds, etc.

# 文字列型
TEXT     # venue_code, racer_name, rank, etc.

# 日付型
DATE     # race_date (YYYY-MM-DD)
TIMESTAMP  # created_at
```

### 2. Pythonのデータ型対応

```python
# DBからの読み込み時
race_number: int
pit_number: int
win_rate: float
venue_code: str
race_date: str (YYYY-MM-DD) → datetime.date に変換

# 型変換の検証
def validate_type(value, expected_type):
    if not isinstance(value, expected_type):
        raise TypeError(f"型不一致: {type(value)} (期待: {expected_type})")
```

### 3. DataFrameのデータ型

```python
# 特徴量DataFrame
features_df = pd.DataFrame({
    'pit_number': pd.Int64Dtype(),      # 整数
    'win_rate': pd.Float64Dtype(),      # 浮動小数点
    'racer_name': pd.StringDtype(),     # 文字列
})

# 型チェック
assert features_df['pit_number'].dtype == 'int64'
assert features_df['win_rate'].dtype == 'float64'
```

---

## 🚫 禁止事項

### 1. データベース操作の禁止事項

#### ❌ 外部キー制約を無視した削除
```python
# 悪い例：子レコードを残したまま親を削除
cursor.execute("DELETE FROM races WHERE id = ?", (race_id,))
# → entries, results などが孤立する

# 良い例：子レコードから先に削除
cursor.execute("DELETE FROM entries WHERE race_id = ?", (race_id,))
cursor.execute("DELETE FROM results WHERE race_id = ?", (race_id,))
cursor.execute("DELETE FROM races WHERE id = ?", (race_id,))
```

#### ❌ UNIQUE制約を無視した挿入
```python
# 悪い例：重複チェックなし
cursor.execute("INSERT INTO races VALUES (?, ?, ?)", (venue, date, number))
# → UNIQUE制約エラー

# 良い例：INSERT OR IGNORE または事前チェック
cursor.execute("INSERT OR IGNORE INTO races VALUES (?, ?, ?)", (...))
```

#### ❌ 6艇以外のレースデータ
```python
# 悪い例：5艇のデータを挿入
entries = [...]  # 5件のみ
for entry in entries:
    cursor.execute("INSERT INTO entries VALUES (...)")
# → 予測エンジンが破綻

# 良い例：6艇であることを検証
assert len(entries) == 6, "1レースは6艇固定"
```

### 2. 計算ロジックの禁止事項

#### ❌ 確率の合計が1でない
```python
# 悪い例
probs = [0.35, 0.25, 0.20, 0.10, 0.05]  # 合計0.95

# 良い例：正規化
probs = np.array([0.35, 0.25, 0.20, 0.10, 0.05, 0.05])
probs = probs / probs.sum()  # 合計1.0に正規化
```

#### ❌ 負の期待値で賭ける
```python
# 悪い例
ev = -0.1
bet_amount = bankroll * 0.05  # 負の期待値でも賭ける

# 良い例
if ev <= 0:
    bet_amount = 0.0  # 賭けない
```

#### ❌ Kelly分数が1を超える
```python
# 悪い例
kelly_f = 1.5  # 資金の150%を賭ける（破綻）

# 良い例
kelly_f = min(kelly_f, 0.2)  # 最大20%まで制限
```

### 3. 特徴量処理の禁止事項

#### ❌ NaN/Infを含むまま予測
```python
# 悪い例
predictions = model.predict(features_with_nan)  # エラーまたは異常な予測

# 良い例
assert not features.isna().any().any(), "NaN値が存在"
assert not np.isinf(features).any().any(), "Inf値が存在"
predictions = model.predict(features)
```

#### ❌ 範囲外の値を含むまま予測
```python
# 悪い例
features['win_rate'] = 15.0  # 範囲外（0-10）
predictions = model.predict(features)

# 良い例
assert 0 <= features['win_rate'].max() <= 10, "勝率が範囲外"
```

---

## ✅ 推奨事項

### 1. 防御的プログラミング

```python
def calculate_something(value):
    # 1. 入力検証
    if value is None:
        raise ValueError("値がNone")
    if value < 0:
        raise ValueError(f"値が負数: {value}")

    # 2. 計算
    result = value * 2

    # 3. 出力検証
    if result > 100:
        raise ValueError(f"計算結果が異常: {result}")

    return result
```

### 2. 早期エラー検出

```python
# データ挿入前に検証
from src.validation.data_validator import DataValidator

is_valid, errors = DataValidator.validate_race(race_data)
if not is_valid:
    raise ValueError(f"検証エラー: {errors}")

# 検証OKなら挿入
cursor.execute("INSERT INTO races VALUES (...)")
```

### 3. ログ出力

```python
import logging

logger = logging.getLogger(__name__)

# 重要な計算ではログを残す
logger.info(f"Kelly分数: {kelly_f:.4f}, 賭け金: {bet_amount:.0f}円")
logger.warning(f"確率の合計が1でない: {sum(probs):.4f}")
```

---

## 📝 まとめ

### 絶対に守るべき制約（TOP 5）

1. **1レース = 6艇** - これが崩れると全システムが破綻
2. **確率の合計 = 1.0** - 確率計算の基本原則
3. **Kelly分数 ≤ 0.2** - 資金保護のため
4. **外部キー制約** - データベース整合性の維持
5. **特徴量の値範囲** - 予測精度の保証

### チェック方法

```bash
# データベース整合性
python -m pytest tests/test_integration.py::TestDataFlow::test_database_integrity -v

# 計算ロジック
python -m pytest tests/test_core_logic.py -v

# 特徴量検証
python -m pytest tests/test_integration.py::TestDataFlow::test_feature_generation_pipeline -v
```

---

**最終更新**: 2025-11-14

**重要**: この制約を破ると、システムが正常に動作しなくなります！
