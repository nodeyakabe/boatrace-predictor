# システムアーキテクチャ全体図

**最終更新**: 2025-12-15
**ドキュメント管理者**: Claude Code

---

## 1. システム構成図

```
[データ取得層]          [データベース]          [予測エンジン層]
     |                      |                      |
 Scrapers              SQLite3                RacePredictor (本番メイン)
     |                boatrace.db                  |
     v                      |                      v
 race_schedule        +-----+-----+         HierarchicalPredictor (補助)
 race_results         |           |                |
 race_details    <----+   35     +---->    ConditionalRankModel
 entries              |  Tables  |                 |
 conditions           |           |                v
 odds                 +-----------+         TrifectaCalculator
                                                   |
                                                   v
                      [ベッティング判定層]    [出力層]
                             |                     |
                      BetTargetEvaluator     UI (Streamlit)
                      MultiBetGenerator      daily scripts
                      VenueEvaluator         JSON/CSV
```

---

## 2. 主要コンポーネント

### 2.1 予測エンジン

| コンポーネント | ファイル | 役割 | 本番使用 |
|---------------|---------|------|---------|
| **RacePredictor** | `src/analysis/race_predictor.py` | ルールベース+ML統合予測 | **メイン** |
| **HierarchicalPredictor** | `src/prediction/hierarchical_predictor.py` | 階層的確率モデル（三連単確率計算） | 補助 |
| **TrifectaCalculator** | `src/prediction/trifecta_calculator.py` | 三連単120通りの確率計算 | 内部使用 |
| **ConditionalRankModel** | `src/ml/conditional_rank_model.py` | 条件付き着順予測（XGBoost） | 内部使用 |

### 2.2 機械学習モデル

#### 現在の本番モデル体系（2種類存在）

| 体系 | ファイル名パターン | アルゴリズム | AUC Stage2 | 本番使用 |
|-----|-------------------|-------------|-----------|---------|
| **体系A (V1)** | `conditional_stage*.joblib` | LightGBM | 0.7423 | **使用中** |
| **体系A (V2)** | `conditional_rank_v*_*.json` | XGBoost | - | 実験中 |
| ~~体系B (V2)~~ | `deprecated_v2_20251209/*` | LightGBM | 0.6935 | **非推奨** |

**重要**: 現在の本番システムは `conditional_meta.json` に対応する `conditional_stage*.joblib` を使用。

### 2.3 ベッティングシステム

| コンポーネント | ファイル | 役割 |
|---------------|---------|------|
| **BetTargetEvaluator** | `src/betting/bet_target_evaluator.py` | 購入判定（戦略B実装） |
| **MultiBetGenerator** | `src/betting/multi_bet_generator.py` | パターンH複数点買い生成 |
| **VenueEvaluator** | `src/betting/venue_evaluator.py` | 会場別評価 |
| **VenueCourseAdjuster** | `src/betting/venue_course_adjuster.py` | 会場コース調整 |

### 2.4 スコアリングコンポーネント

`src/analysis/` 配下のスコアラー群:

| コンポーネント | 役割 |
|---------------|------|
| `BeforeInfoScorer` | 直前情報（ST、展示）スコアリング |
| `WeatherAdjuster` | 天候補正 |
| `TideAdjuster` | 潮位補正 |
| `GradeScorer` | グレード（SG/G1等）補正 |
| `ExtendedScorer` | 拡張スコアリング |
| `CompoundBuffSystem` | 複合バフシステム |

---

## 3. データフロー図

### 3.1 予測実行フロー

```
[レースID入力]
      |
      v
+-------------------+
| RacePredictor     |
| .predict_race_by_key()  <-- 本番エントリーポイント
+-------------------+
      |
      | (1) データベースからレース情報取得
      v
+-------------------+
| BatchDataLoader   |
| - entries取得     |
| - race_details取得 |
| - conditions取得  |
+-------------------+
      |
      | (2) 各スコアラーでスコア計算
      v
+-------------------+
| BeforeInfoScorer  |
| WeatherAdjuster   |
| TideAdjuster      |
| GradeScorer       |
+-------------------+
      |
      | (3) スコア統合・ランキング生成
      v
+-------------------+
| 従来方式予測      | --> old_prediction [1,2,3,4,5,6]
| 新方式予測        | --> new_prediction [1,2,3,4,5,6]
| 信頼度計算        | --> confidence (A/B/C/D)
+-------------------+
      |
      | (4) オプション: 階層的確率モデル
      v
+-------------------+
| HierarchicalPredictor |
| - Stage1: 1着確率    |
| - Stage2: 2着確率    |
| - Stage3: 3着確率    |
| - 三連単確率計算     |
+-------------------+
      |
      | (5) ベッティング判定
      v
+-------------------+
| BetTargetEvaluator |
| - 戦略B条件チェック |
| - オッズ範囲確認    |
| - 会場風速フィルタ  |
+-------------------+
      |
      v
[購入判定結果]
```

### 3.2 モデル読み込みフロー

```
HierarchicalPredictor(use_v2=False)  <-- デフォルト設定
      |
      v
TrifectaCalculator(use_v2=False)
      |
      v
_load_v1_models()
      |
      +-- models/conditional_meta.json (メタ情報)
      |
      +-- models/conditional_stage1.joblib (1着予測)
      |
      +-- models/conditional_stage2.joblib (2着予測)
      |
      +-- models/conditional_stage3.joblib (3着予測)
```

---

## 4. 本番システム

### 4.1 エントリーポイント

| 用途 | ファイル | 説明 |
|-----|---------|------|
| **UI** | `ui/app.py` | Streamlit WebUI |
| **日次ベッティング** | `scripts/run_daily_betting_pattern_h.py` | 当日レースの購入判定 |
| **予測生成** | バックグラウンドジョブ | `job_manager.py` 経由 |

### 4.2 デフォルト設定

```python
# HierarchicalPredictor
use_v2 = False  # V1モデルを使用

# BetTargetEvaluator
use_multi_bet = True
multi_bet_pattern = MultiBetPattern.PATTERN_H
enable_venue_wind_filter = True
enable_venue_course_adjustment = True

# 戦略
# 戦略B: 信頼度C/D、オッズ20-50倍範囲
```

### 4.3 UI構成

```
ui/app.py
  |
  +-- Tab1: レース予想
  |     +-- unified_race_list.py (レース一覧)
  |     +-- unified_race_detail.py (レース詳細)
  |
  +-- Tab2: データ準備
  |     +-- workflow_manager.py (ワークフロー管理)
  |     +-- bulk_data_collector.py (一括データ収集)
  |
  +-- Tab3: データ参照
  |     +-- venue_analysis.py (会場分析)
  |     +-- racer_analysis.py (選手分析)
  |
  +-- Tab4: 設定・管理
        +-- model_training.py (モデル学習)
        +-- system_monitor.py (システム監視)
```

---

## 5. ディレクトリ構成

```
BoatRace_package_20251115_172032/
├── config/                    # 設定ファイル
│   ├── settings.py           # 基本設定
│   ├── feature_flags.py      # 機能フラグ
│   ├── venue_wind_adjustments.py  # 風速・会場調整
│   └── venue_course_win_rates.py  # 会場コース勝率
│
├── data/
│   └── boatrace.db           # メインデータベース
│
├── docs/                      # ドキュメント
│   ├── DATABASE_SCHEMA.md    # DB構造
│   ├── betting_implementation_status.md  # 戦略実装状況
│   └── 残タスク一覧.md       # 残タスク
│
├── models/                    # 学習済みモデル
│   ├── conditional_stage*.joblib  # 本番モデル（V1）
│   ├── conditional_meta.json      # V1メタ情報
│   ├── conditional_rank_v1_*.json # XGBoost版V1
│   ├── conditional_rank_v2_*.json # XGBoost版V2（実験）
│   └── deprecated_v2_20251209/    # 非推奨モデル
│
├── scripts/                   # 実行スクリプト
│   ├── train_*.py            # モデル学習
│   ├── backtest_*.py         # バックテスト
│   ├── run_daily_*.py        # 日次実行
│   └── analyze_*.py          # 分析スクリプト
│
├── src/
│   ├── analysis/              # 分析・予測ロジック
│   │   ├── race_predictor.py # メイン予測エンジン
│   │   ├── beforeinfo_scorer.py  # 直前情報スコアリング
│   │   └── weather_adjuster.py   # 天候補正
│   │
│   ├── betting/               # ベッティングロジック
│   │   ├── bet_target_evaluator.py  # 購入判定
│   │   └── multi_bet_generator.py   # 複数点買い
│   │
│   ├── database/              # データベースアクセス
│   │   ├── models.py         # DBモデル
│   │   └── batch_data_loader.py  # バッチデータ読み込み
│   │
│   ├── ml/                    # 機械学習
│   │   └── conditional_rank_model.py  # 条件付きモデル
│   │
│   ├── prediction/            # 予測エンジン
│   │   ├── hierarchical_predictor.py  # 階層的予測
│   │   └── trifecta_calculator.py     # 三連単計算
│   │
│   └── utils/                 # ユーティリティ
│       ├── job_manager.py    # ジョブ管理
│       └── db_connection_pool.py  # DB接続プール
│
└── ui/                        # Streamlit UI
    ├── app.py                # メインアプリ
    └── components/           # UIコンポーネント
```

---

## 6. 依存関係グラフ

### 6.1 予測システムの依存関係

```
RacePredictor
├── StatisticsCalculator
├── RacerAnalyzer
├── MotorAnalyzer
├── KimariteScorer
├── GradeScorer
├── FirstPlaceLockAnalyzer
├── WeatherAdjuster
├── TideAdjuster
├── ExhibitionAnalyzer
├── ExtendedScorer
├── CompoundBuffSystem
├── BeforeInfoScorer
├── DynamicIntegrator
├── BeforeSafeScorer
├── SafeIntegrator
├── EntryPredictionModel
├── ProbabilityCalibrator
├── BeforeInfoFlagAdjuster
├── Top3Scorer
├── PatternPriorityOptimizer
├── NegativePatternChecker
├── VenuePatternOptimizer
├── RuleBasedEngine
└── HierarchicalPredictor (optional)
    └── TrifectaCalculator
        └── ConditionalRankModel (LightGBM/XGBoost)
```

### 6.2 ベッティングシステムの依存関係

```
BetTargetEvaluator
├── MultiBetGenerator
├── VenueEvaluator
├── VenueCourseAdjuster
└── venue_wind_adjustments (config)
```

---

## 7. 設定パラメータ一覧

### 7.1 予測エンジン設定

| パラメータ | デフォルト値 | 説明 |
|-----------|-------------|------|
| `use_v2` | `False` | V2モデルを使用するか |
| `use_optimized` | `True` | 最適化版TrifectaCalculatorを使用 |
| `use_conditional_model` | `True` | 条件付きモデルを使用 |

### 7.2 ベッティング設定

| パラメータ | デフォルト値 | 説明 |
|-----------|-------------|------|
| `use_multi_bet` | `True` | 複数点買いを使用 |
| `multi_bet_pattern` | `PATTERN_H` | 複数点買いパターン |
| `enable_venue_wind_filter` | `True` | 風速・会場フィルター |
| `enable_venue_course_adjustment` | `True` | 会場コース調整 |

### 7.3 戦略B購入条件

| 信頼度 | 級別 | オッズ範囲 | 賭け金 |
|-------|-----|----------|-------|
| C | B1 | 30-40倍 | 300円 |
| C | A1 | 30-40倍 | 300円 |
| D | B1 | 40-50倍 | 300円 |
| D | A1 | 40-50倍 | 300円 |
| D | A2 | 20-30倍 | 300円 |

---

## 8. トラブルシューティング

### 8.1 よくある問題

| 問題 | 原因 | 解決策 |
|-----|-----|-------|
| モデル読み込みエラー | モデルファイルが見つからない | `models/` ディレクトリを確認 |
| 予測が生成されない | データベースにデータがない | データ収集を実行 |
| AUCが低い | 学習データの問題 | 学習データ期間を確認 |

### 8.2 ログ確認方法

```bash
# UIのログ確認
streamlit run ui/app.py --log_level debug

# スクリプトのログ確認
python scripts/run_daily_betting_pattern_h.py 2>&1 | tee debug.log
```

---

## 関連ドキュメント

- [モデル管理ガイド](MODEL_MANAGEMENT.md)
- [予測ロジック詳細](PREDICTION_LOGIC.md)
- [開発ワークフロー](DEVELOPMENT_WORKFLOW.md)
- [データベース構造](DATABASE_SCHEMA.md)
- [残タスク一覧](残タスク一覧.md)
