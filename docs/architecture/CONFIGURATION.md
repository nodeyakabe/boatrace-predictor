# 設定ファイル一覧

**作成日**: 2025-12-15
**目的**: 全設定ファイルの概要と用途を整理

---

## ディレクトリ構成

```
config/
├── settings.py              # グローバル設定（DB接続、パス等）
├── feature_flags.py         # 機能フラグ管理
├── model_config.py          # 機械学習モデル設定
├── venue_characteristics.py # 会場特性マスタ
├── venue_course_adjustments.py    # 会場別コース調整
├── venue_course_win_rates.py      # 会場別コース勝率
├── venue_wind_adjustments.py      # 会場別風向き調整
├── optimized_pattern_multipliers.py # 最適化済みパターン乗数
│
├── presets/                 # YAML設定（新規）
│   ├── scoring_weights.yaml       # スコアリング重み
│   ├── venue_characteristics.yaml # 会場特性
│   ├── weather_rules.yaml         # 天候ルール
│   ├── tide_adjustments.yaml      # 潮汐調整
│   ├── optimization_targets.yaml  # 最適化ターゲット
│   └── loader.py                  # YAML読み込みユーティリティ
│
├── *.json                   # JSON設定（レガシー/参照用）
│   ├── scoring_weights.json
│   ├── scoring_weights_accuracy.json
│   ├── scoring_weights_value.json
│   ├── weather_rules.json
│   ├── prediction_improvements.json
│   ├── rollout_config.json
│   └── monitoring_config.json
│
└── environmental_penalty_rules.yaml  # 環境ペナルティルール
```

---

## 主要設定ファイル

### 1. settings.py

**役割**: グローバル設定（データベース接続、ファイルパス等）

**主要定数**:
```python
DATABASE_PATH = 'data/boatrace.db'
LOG_DIR = 'logs/'
CACHE_DIR = 'cache/'
MODEL_DIR = 'models/'
```

**スコアリング重み読み込み**:
- `EXTENDED_SCORE_WEIGHTS`: YAML から動的読み込み
- フォールバック: ハードコードされたデフォルト値

---

### 2. feature_flags.py

**役割**: 機能のオン/オフ制御

**アクティブフラグ（12個）**:

| フラグ名 | デフォルト | 用途 |
|----------|------------|------|
| `before_pattern_bonus` | True | パターンボーナス適用 |
| `negative_patterns` | True | ネガティブパターン (+2.0%改善) |
| `entry_prediction_model` | True | 進入予測モデル |
| `hierarchical_predictor` | True | 階層的条件確率モデル |
| `lightgbm_ranking` | True | LightGBMランキング |
| `interaction_features` | True | 交互作用特徴量 |
| `st_course_interaction` | True | ST×course交互作用 |
| `legacy_exhibition_adjustment` | **False** | 旧展示補正（重複回避） |
| `apply_pattern_to_confidence_d` | False | 信頼度Dパターン適用 |
| `venue_pattern_optimization` | False | 会場別パターン最適化 |
| `compound_pattern_bonus` | False | 複合パターンボーナス |
| `verbose_logging` | False | 詳細ログ |

**API**:
```python
from config.feature_flags import is_feature_enabled, enable_feature, disable_feature

if is_feature_enabled('negative_patterns'):
    # 機能有効時の処理
```

---

### 3. presets/scoring_weights.yaml

**役割**: スコアリングパラメータの一元管理

**セクション構成**:

#### extended_scorer（拡張スコア重み）
```yaml
extended_scorer:
  class_score: 10        # 級別スコア
  fl_penalty_max: -10    # F/Lペナルティ
  session: 5             # 節間成績
  prev_race: 5           # 前走レベル
  course_entry: 5        # 進入傾向
  matchup: 5             # 選手間相性
  motor: 5               # モーター特性
  start_timing: 8        # 平均ST
  exhibition: 10         # 展示タイム（重要）
  tilt: 3                # チルト角度
  recent_form: 8         # 直近成績
  venue_affinity: 3      # 会場別勝率
```

#### before_patterns（パターン乗数）
```yaml
before_patterns:
  first_place:           # 1着予測パターン
    pre1_st1:
      multiplier: 1.411  # PRE1位 & ST1位
  second_place:          # 2着予測パターン
  third_place:           # 3着予測パターン
  top3:                  # 3着以内予測パターン
```

#### dynamic_weights（動的重み）
```yaml
dynamic_weights:
  base:
    course_weight: 35
    racer_weight: 35
    motor_weight: 20
  high_motor_venues:     # モーター重視会場
  high_in_venues:        # イン強会場
```

#### adjustment_limits（調整上限）
```yaml
adjustment_limits:
  max_exhibition_adjustment: 10.0
  max_weather_adjustment: 8.0
  max_tide_adjustment: 5.0
```

**読み込み方法**:
```python
from config.presets.loader import load_scoring_weights, get_pattern_multiplier

config = load_scoring_weights()
multiplier = get_pattern_multiplier('top3_multiplier')
```

---

### 4. presets/tide_adjustments.yaml

**役割**: 潮汐による調整パラメータ

**内容**:
```yaml
adjustments:
  flood:         # 満潮時
    course_1: 1.5
    course_2: 1.0
    course_6: -1.0
  ebb:           # 干潮時
    course_1: -0.5
    course_5: 0.5
    course_6: 1.0
```

---

### 5. presets/weather_rules.yaml

**役割**: 天候条件による調整ルール

**内容**:
```yaml
wind:
  tailwind:      # 追い風
    strong: { inner_boost: 2.0, outer_penalty: -1.0 }
    moderate: { inner_boost: 1.0 }
  headwind:      # 向かい風
    strong: { outer_boost: 1.5, inner_penalty: -0.5 }
```

---

### 6. venue_characteristics.py

**役割**: 会場特性マスタデータ

**内容例**:
```python
VENUE_CHARACTERISTICS = {
    '01': {  # 桐生
        'name': '桐生',
        'prefecture': '群馬',
        'in_rate': 52.1,
        'motor_impact': 'high',
        'water_type': 'fresh',
        'characteristics': ['モーター重要', '潮位変動なし']
    },
    # ... 全24会場
}
```

---

### 7. venue_course_win_rates.py

**役割**: 会場×コース別勝率マスタ

**内容例**:
```python
VENUE_COURSE_WIN_RATES = {
    '01': {  # 桐生
        1: 0.55,  # 1コース勝率
        2: 0.14,
        3: 0.12,
        4: 0.10,
        5: 0.06,
        6: 0.03
    },
    # ... 全24会場
}
```

---

## JSON設定ファイル（レガシー）

以下のJSONファイルは参照用に残していますが、新規開発ではYAMLを使用してください。

| ファイル | 用途 | 移行先 |
|----------|------|--------|
| `scoring_weights.json` | スコアリング重み | `presets/scoring_weights.yaml` |
| `weather_rules.json` | 天候ルール | `presets/weather_rules.yaml` |
| `prediction_improvements.json` | 改善履歴 | ドキュメント化 |
| `rollout_config.json` | ロールアウト設定 | `feature_flags.py` |
| `monitoring_config.json` | モニタリング設定 | 未移行 |

---

## 設定の優先順位

```
1. 環境変数（未実装）
2. YAML設定ファイル（config/presets/*.yaml）
3. Python定数（config/*.py）
4. ハードコードされたデフォルト値
```

---

## 設定変更手順

### パラメータ調整

1. `config/presets/scoring_weights.yaml` を編集
2. テスト実行: `python -m pytest tests/test_race_predictor.py -v`
3. バックテスト: `python scripts/backtest_expected_value.py`
4. 本番反映: 再起動のみ（キャッシュクリアで即時反映）

### 機能フラグ変更

1. `config/feature_flags.py` の `FEATURE_FLAGS` を編集
2. 変更内容をコメントに記録
3. テスト実行
4. 本番反映

### 新しいYAML設定追加

1. `config/presets/` に新しいYAMLファイル作成
2. `config/presets/loader.py` に読み込み関数を追加
3. 利用側コードで関数を呼び出し

```python
# loader.py に追加
def load_my_config():
    config_path = Path(__file__).parent / 'my_config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
```

---

## 関連ドキュメント

- [ARCHITECTURE.md](ARCHITECTURE.md) - モジュール構成図
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) - データベース構造
- [残タスク一覧.md](残タスク一覧.md) - 未完了タスク

---

*最終更新: 2025-12-15*
