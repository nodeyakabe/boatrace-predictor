# アーキテクチャ概要

**作成日**: 2025-12-15
**目的**: プロジェクトのモジュール構成と設計を理解しやすくする

---

## モジュール構成図

```
BoatRace/
├── config/                     # 設定・構成管理
│   ├── settings.py            # グローバル設定（DB接続、パス等）
│   ├── feature_flags.py       # 機能フラグ管理（12個のアクティブフラグ）
│   └── presets/               # YAML設定ファイル
│       ├── scoring_weights.yaml   # スコアリング重み設定
│       └── loader.py              # YAML読み込みユーティリティ
│
├── src/
│   ├── analysis/              # 予測・分析ロジック
│   │   ├── race_predictor.py      # メイン予測エンジン（2,640行）
│   │   ├── pattern_analyzer.py    # 法則分析
│   │   ├── venue_analyzer.py      # 会場分析
│   │   ├── bet_recommender.py     # 買い目推奨（新規分割）
│   │   ├── scorers/               # スコアリングモジュール（新規）
│   │   │   ├── __init__.py
│   │   │   └── pattern_scorer.py  # パターンスコア計算
│   │   └── adjusters/             # 調整モジュール（新規）
│   │       ├── __init__.py
│   │       └── weather_tide.py    # 天候・潮汐調整
│   │
│   ├── scraper/               # データ収集
│   │   ├── bulk_scraper.py        # 一括スクレイピング
│   │   ├── odds_scraper.py        # オッズ取得
│   │   ├── beforeinfo_scraper.py  # 直前情報取得
│   │   └── result_scraper.py      # レース結果取得
│   │
│   ├── workflow/              # ワークフロー管理
│   │   ├── today_prediction.py        # 今日の予測生成
│   │   ├── missing_data_fetch_parallel.py  # 不足データ並列取得
│   │   └── tenji_collection.py        # オリジナル展示収集
│   │
│   └── database/              # データベース操作
│       ├── connection.py          # DB接続管理
│       └── queries.py             # SQLクエリ
│
├── ui/                        # Streamlit UI
│   ├── app.py                 # メインアプリ
│   └── pages/                 # 各ページコンポーネント
│
├── scripts/                   # ユーティリティスクリプト
│   ├── fast_prediction_generator.py  # 高速予測生成
│   └── master_automation_*.py        # 自動化スクリプト
│
└── data/
    └── boatrace.db            # SQLiteデータベース
```

---

## コア予測システム

### 1. RacePredictor（メイン予測エンジン）

**ファイル**: [src/analysis/race_predictor.py](../src/analysis/race_predictor.py)

```
┌─────────────────────────────────────────────────────────────┐
│                    RacePredictor                            │
├─────────────────────────────────────────────────────────────┤
│ 主要メソッド:                                                │
│  - predict_race(): レース予測のエントリーポイント            │
│  - calculate_extended_scores(): 拡張スコア計算               │
│  - _apply_before_patterns(): 直前パターン適用                │
│  - generate_recommendations(): 買い目生成                    │
├─────────────────────────────────────────────────────────────┤
│ 依存モジュール:                                              │
│  - PatternScorer: パターンスコア計算                         │
│  - WeatherTideAdjuster: 天候・潮汐調整                       │
│  - BetRecommender: 買い目推奨                                │
└─────────────────────────────────────────────────────────────┘
```

### 2. スコアリングフロー

```
入力データ
    │
    ▼
┌──────────────────┐
│ 基本スコア計算    │  ← 選手ランク、勝率、モーター等
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 拡張スコア計算    │  ← コース適性、展示タイム、STデータ
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ パターンボーナス  │  ← PatternScorer
│ 適用             │     BEFORE_PATTERNS (展示1-3位、ST1-3位等)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 環境調整         │  ← WeatherTideAdjuster
│ (天候・潮汐)      │     最大 ±5.0点
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 買い目生成       │  ← BetRecommender
│                  │     3連単、3連複、2連単、2連複
└────────┬─────────┘
         │
         ▼
    予測結果
```

---

## 新規分割モジュール詳細

### PatternScorer

**ファイル**: [src/analysis/scorers/pattern_scorer.py](../src/analysis/scorers/pattern_scorer.py)

**役割**: 直前情報（展示タイム、ST）に基づくパターンボーナス計算

**主要コンポーネント**:
- `BEFORE_PATTERNS_1ST`: 展示1位パターン（17パターン）
- `BEFORE_PATTERNS_2ND`: 展示2位パターン
- `BEFORE_PATTERNS_3RD`: 展示3位パターン
- `BEFORE_PATTERNS_TOP3`: 展示TOP3パターン

**設定連携**:
```python
from config.presets.loader import get_pattern_multiplier

multiplier = get_pattern_multiplier('top3_multiplier')  # YAML から取得
```

### WeatherTideAdjuster

**ファイル**: [src/analysis/adjusters/weather_tide.py](../src/analysis/adjusters/weather_tide.py)

**役割**: 天候と潮汐による選手スコア調整

**調整ルール**:
| 条件 | 影響 | 最大調整 |
|------|------|----------|
| 追い風 | インコース有利 | ±5.0点 |
| 向かい風 | アウトコース有利 | ±5.0点 |
| 満潮 | 1-2コース有利 | ±5.0点 |
| 干潮 | 4-6コース有利 | ±5.0点 |

### BetRecommender

**ファイル**: [src/analysis/bet_recommender.py](../src/analysis/bet_recommender.py)

**役割**: スコアに基づく買い目推奨生成

**出力形式**:
```python
{
    '3tan': [(1, 2, 3), (1, 3, 2), ...],  # 3連単
    '3fuku': [(1, 2, 3), ...],             # 3連複
    '2tan': [(1, 2), (1, 3), ...],         # 2連単
    '2fuku': [(1, 2), ...]                 # 2連複
}
```

---

## 設定システム

### YAML設定ファイル

**ファイル**: [config/presets/scoring_weights.yaml](../config/presets/scoring_weights.yaml)

```yaml
# スコアリング重み設定
extended_scorer:
  class_score: 10
  fl_penalty_max: -10
  st_weight: 3
  exhibition_weight: 1.5
  # ...

# パターン乗数
before_patterns:
  top3_multiplier: 0.7
  2nd_multiplier: 0.5
  3rd_multiplier: 0.3

# 動的重み
dynamic_weights:
  exhibition_boost: 2.0
  exhibition_threshold: 0.15

# 調整上限
adjustment_limits:
  max_weather_adjustment: 5.0
  max_tide_adjustment: 5.0
```

### YAML読み込み

**ファイル**: [config/presets/loader.py](../config/presets/loader.py)

```python
# 使用例
from config.presets.loader import load_scoring_weights, get_pattern_multiplier

# 全設定読み込み
config = load_scoring_weights()

# 特定の乗数取得
multiplier = get_pattern_multiplier('top3_multiplier')  # 0.7
```

---

## フィーチャーフラグ

**ファイル**: [config/feature_flags.py](../config/feature_flags.py)

### アクティブフラグ（12個）

| フラグ名 | デフォルト | 説明 |
|----------|------------|------|
| `use_extended_scores` | True | 拡張スコア計算を使用 |
| `use_ml_model` | False | 機械学習モデルを使用 |
| `use_before_patterns` | True | 直前パターンボーナスを適用 |
| `enable_pattern_analysis` | True | 法則分析を有効化 |
| `use_st_score_boost` | True | STスコアブースト適用 |
| `use_actual_course_boost` | True | 進入コースブースト適用 |
| `use_sinnyu_check` | True | 進入確認チェック |
| `use_before_time_bonus` | True | 直前タイムボーナス適用 |
| `use_dynamic_weights` | True | 動的重み調整を使用 |
| `use_new_st_score` | True | 新STスコア計算を使用 |
| `apply_tenji_time_bonus` | True | 展示タイムボーナス適用 |
| `legacy_exhibition_adjustment` | False | 旧展示調整（非推奨） |

### アーカイブ済みフラグ（21個）

廃止されたフラグは `ARCHIVED_FLAGS` 辞書に保存し、将来の参照用に保持。

---

## 拡張ガイド

### 新しいスコアラーを追加する

1. `src/analysis/scorers/` に新しいファイルを作成
2. `__init__.py` でエクスポート
3. `race_predictor.py` からインポートして使用

```python
# src/analysis/scorers/my_scorer.py
class MyScorer:
    def calculate(self, data):
        ...

# src/analysis/scorers/__init__.py
from .my_scorer import MyScorer
```

### 新しい調整ロジックを追加する

1. `src/analysis/adjusters/` に新しいファイルを作成
2. `MAX_*_ADJUSTMENT` 定数で調整上限を設定
3. `__init__.py` でエクスポート

### 設定パラメータを追加する

1. `config/presets/scoring_weights.yaml` に新しいキーを追加
2. `loader.py` に必要なヘルパー関数を追加
3. コードから `load_scoring_weights()` で読み込み

---

## 関連ドキュメント

- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) - データベース構造
- [CONFIGURATION.md](CONFIGURATION.md) - 設定ファイル一覧
- [残タスク一覧.md](残タスク一覧.md) - 未完了タスク

---

*最終更新: 2025-12-15*
