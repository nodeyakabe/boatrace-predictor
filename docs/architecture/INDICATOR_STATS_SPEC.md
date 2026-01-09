# 指標データ仕様書（逃げ率・まくり率・差し率）

**作成日**: 2026-01-08
**目的**: B信頼度×50-100倍条件の購入件数削減・ROI維持のための展開系指標

---

## 概要

### 作成した指標

| 指標 | 定義 | 集計単位 | 母数制限 |
|------|------|---------|---------|
| **逃げ率** | 1コース出走時の1着率 | 選手別×全国/当地 | 全国30走、当地15走 |
| **まくり率** | (3C+4C)の1着率 | 会場別 | なし |
| **差し率** | (2C+5C)の1着率 | 会場別 | なし |

### 設計方針

1. **コースベース定義** - 公式の決まり手分類は使用せず、コースのみで判定（再現性重視）
2. **1着率のみ** - 2着・3着はカウントしない（展開の主導権を測る）
3. **母数チェック必須** - サンプル不足の高率値は使用禁止（NULL扱い）
4. **独立保持** - 合成スコアは作らない（判定ロジック側でAND条件に使用）

---

## テーブル構造

### player_escape_stats（選手別逃げ率）

```sql
CREATE TABLE player_escape_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,           -- 選手ID (racer_number)
    stadium_id TEXT,                    -- 会場ID (NULL=全国)
    races_1course INTEGER NOT NULL,     -- 1コース出走数
    wins_1course INTEGER NOT NULL,      -- 1コース1着数
    escape_rate REAL,                   -- 逃げ率 (NULL=母数不足)
    period_start DATE NOT NULL,         -- 集計開始日
    period_end DATE NOT NULL,           -- 集計終了日
    updated_at TIMESTAMP,
    UNIQUE(player_id, stadium_id, period_start, period_end)
);
```

**インデックス**:
- `idx_player_escape_player` (player_id)
- `idx_player_escape_stadium` (stadium_id)
- `idx_player_escape_period` (period_start, period_end)

### stadium_attack_stats（会場別まくり率・差し率）

```sql
CREATE TABLE stadium_attack_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stadium_id TEXT NOT NULL,           -- 会場ID
    total_races INTEGER NOT NULL,       -- 総レース数
    course2_wins INTEGER NOT NULL,      -- 2コース1着数
    course3_wins INTEGER NOT NULL,      -- 3コース1着数
    course4_wins INTEGER NOT NULL,      -- 4コース1着数
    course5_wins INTEGER NOT NULL,      -- 5コース1着数
    makuri_rate REAL NOT NULL,          -- まくり率 (3C+4C)/全
    sashi_rate REAL NOT NULL,           -- 差し率 (2C+5C)/全
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    updated_at TIMESTAMP,
    UNIQUE(stadium_id, period_start, period_end)
);
```

---

## 現在のデータ量（2026-01-08生成）

| テーブル | 件数 | 内訳 |
|---------|------|------|
| player_escape_stats | 104,757件 | 全国+当地、全期間+年別 |
| stadium_attack_stats | 168件 | 24会場×7期間 |

### 母数充足率

| 期間 | 全国逃げ率 | 当地逃げ率 |
|------|-----------|-----------|
| 全期間 | 1,446/2,005 (72%) | 920/34,036 (2.7%) |
| 2022年 | 430/1,518 (28%) | 7/15,262 (0.05%) |
| 2025年 | 12/1,538 (0.8%) | 0/13,284 (0%) |

**注意**: 単年データでは母数不足になりやすい。全期間データの使用を推奨。

---

## 会場別指標サマリー（全期間）

### まくり率が高い会場（荒れやすい）

| 順位 | 会場 | まくり率 | レース数 |
|-----|------|---------|---------|
| 1 | 戸田 | 29.6% | 6,500 |
| 2 | 江戸川 | 26.2% | 5,415 |
| 3 | 平和島 | 25.6% | 5,469 |
| 4 | 桐生 | 25.2% | 5,541 |
| 5 | 多摩川 | 24.5% | 5,812 |

### 差し率が高い会場（逃げ崩壊しやすい）

| 順位 | 会場 | 差し率 | レース数 |
|-----|------|--------|---------|
| 1 | 平和島 | 25.0% | 5,469 |
| 2 | 江戸川 | 24.7% | 5,415 |
| 3 | 戸田 | 22.9% | 6,500 |
| 4 | 桐生 | 22.0% | 5,541 |
| 5 | 多摩川 | 21.8% | 5,812 |

### まくり率・差し率が低い会場（固い）

| 会場 | まくり率 | 差し率 | 特徴 |
|------|---------|--------|------|
| 大村 | 17.8% | 15.2% | イン天国 |
| 徳山 | 18.5% | 16.3% | 固め |
| 芦屋 | 19.2% | 16.8% | 固め |

---

## 利用方法

### データ取得API

```python
from src.analysis.escape_rate_calculator import EscapeRateCalculator
from src.analysis.attack_rate_calculator import AttackRateCalculator

# 逃げ率取得
escape_calc = EscapeRateCalculator()
rate = escape_calc.get_escape_rate(
    player_id='4444',      # 選手ID
    stadium_id='06',       # 会場ID（None=全国）
    period_start=None,     # 期間指定（None=最新）
    period_end=None
)

# まくり率・差し率取得
attack_calc = AttackRateCalculator()
rates = attack_calc.get_attack_rates(
    stadium_id='02',       # 会場ID
    period_start=None,
    period_end=None
)
# rates = {'makuri_rate': 0.296, 'sashi_rate': 0.229, ...}
```

### SQLクエリ例

```sql
-- 選手の全国逃げ率を取得
SELECT player_id, escape_rate, races_1course, wins_1course
FROM player_escape_stats
WHERE player_id = '4444'
  AND stadium_id IS NULL
  AND period_start = '2000-01-01'
ORDER BY updated_at DESC
LIMIT 1;

-- 会場のまくり率・差し率を取得
SELECT stadium_id, makuri_rate, sashi_rate, total_races
FROM stadium_attack_stats
WHERE stadium_id = '02'
  AND period_start = '2000-01-01';

-- 逃げ率トップ選手（母数30走以上）
SELECT player_id, escape_rate, races_1course
FROM player_escape_stats
WHERE stadium_id IS NULL
  AND escape_rate IS NOT NULL
  AND period_start = '2000-01-01'
ORDER BY escape_rate DESC
LIMIT 20;
```

---

## 購入判定での活用案（参考）

### 案1: 逃げ率による1コース信頼度調整

```python
# 1コース選手の逃げ率が低い場合、購入を控える
if course == 1 and player_escape_rate < 0.50:
    skip_purchase = True
```

### 案2: 会場特性によるフィルター

```python
# まくり率が高い会場（戸田、江戸川等）では高オッズを期待
if stadium_makuri_rate > 0.25:
    min_odds_threshold = 30  # オッズ下限を上げる

# 固い会場（大村、徳山等）では低オッズでも購入
if stadium_makuri_rate < 0.20:
    min_odds_threshold = 10
```

### 案3: 複合条件

```python
# 逃げ率高い選手が1コースで、まくり率低い会場
if (player_escape_rate > 0.60
    and course == 1
    and stadium_makuri_rate < 0.22):
    confidence_boost = True
```

---

## データ再生成

```bash
# 全期間データのみ
python scripts/data_collection/build_indicator_stats.py

# 全期間 + 年別データ
python scripts/data_collection/build_indicator_stats.py --yearly

# 特定期間
python scripts/data_collection/build_indicator_stats.py --start 2024-01-01 --end 2024-12-31

# テーブル再作成
python scripts/data_collection/build_indicator_stats.py --recreate

# サマリー表示のみ
python scripts/data_collection/build_indicator_stats.py --summary
```

---

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `src/database/indicator_tables.py` | テーブル定義・管理 |
| `src/analysis/escape_rate_calculator.py` | 逃げ率計算 |
| `src/analysis/attack_rate_calculator.py` | まくり率・差し率計算 |
| `scripts/data_collection/build_indicator_stats.py` | データ生成スクリプト |

---

## 注意事項

1. **コースの定義**: `actual_course`（実進入コース）優先、なければ`pit_number`（枠番）を使用
2. **母数不足**: escape_rateがNULLの場合は使用しない
3. **期間指定**: 全期間（2000-01-01〜今日）と年別データの両方を生成済み
4. **閾値設定**: 本仕様の範囲外（購入判定ロジック側で検討）

---

*最終更新: 2026-01-08*
