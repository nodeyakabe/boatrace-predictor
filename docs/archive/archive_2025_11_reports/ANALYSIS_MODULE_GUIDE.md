# 解析・学習モジュール構成ガイド

**作成日**: 2025年11月3日
**目的**: 現状の複雑な解析モジュール構成を整理し、各モジュールの役割を明確化

---

## 📋 概要

`src/analysis/`ディレクトリには18個のモジュールがあり、それぞれ特定の役割を担っています。
このドキュメントでは、各モジュールの目的・主要機能・使い方を整理します。

---

## 🗂️ モジュール分類

### 1️⃣ データ処理系（4ファイル）

#### `data_explorer.py`
**役割**: データベースからのデータ探索・抽出
**主要機能**:
- レース結果の検索
- 選手成績の取得
- 会場別データの集計

**使用場所**: データ分析UI、バックテスト

---

#### `data_preprocessor.py`
**役割**: 生データの前処理・クリーニング
**主要機能**:
- 欠損値の処理
- 異常値の除去
- データ型の変換

**使用場所**: モデル学習の前処理

---

#### `data_quality.py`
**役割**: データ品質の監視
**主要クラス**: `DataQualityMonitor`
**主要機能**:
- データの完全性チェック
- 欠損率の計算
- データ整合性の検証

**使用場所**: データ管理タブ（UI）

---

#### `data_coverage_checker.py`
**役割**: データカバレッジの確認
**主要クラス**: `DataCoverageChecker`
**主要機能**:
- 期間別のデータ件数確認
- 会場別のデータ有無確認
- データ収集状況のレポート

**使用場所**: データ管理タブ（UI）

---

### 2️⃣ 特徴量生成系（2ファイル）

#### `feature_generator.py`
**役割**: 機械学習用の特徴量を生成
**主要クラス**: `FeatureGenerator`
**主要機能**:
- Phase 1.1: 選手基本特徴量
- Phase 1.2: モーター・ボート特徴量
- Phase 2.1: 組み合わせ特徴量
- Phase 3.3: 展示・水面特徴量（未実装）

**使用場所**: モデル学習タブ（データ準備）

---

#### `feature_calculator.py`
**役割**: 統計的特徴量の計算
**主要クラス**: `FeatureCalculator`
**主要機能**:
- 移動平均の計算
- トレンド指標の計算
- 相関係数の計算

**使用場所**: リアルタイム予想、バックテスト

---

### 3️⃣ 分析系（7ファイル）

#### `racer_analyzer.py`
**役割**: 選手の詳細分析
**主要クラス**: `RacerAnalyzer`
**主要機能**:
- 選手別の勝率計算
- 直近N戦の成績集計
- 会場相性の分析

**使用場所**: 選手タブ（UI）

---

#### `motor_analyzer.py`
**役割**: モーター性能の分析
**主要クラス**: `MotorAnalyzer`
**主要機能**:
- モーター別の勝率
- 節間成績の追跡
- モーター整備履歴の分析

**使用場所**: レース予想、場攻略タブ

---

#### `kimarite_analyzer.py`
**役割**: 決まり手パターンの分析
**主要クラス**: `KimariteAnalyzer`
**主要機能**:
- 会場別の決まり手分布
- 選手別の決まり手傾向
- 決まり手の出現確率

**使用場所**: 場攻略タブ

---

#### `grade_analyzer.py`
**役割**: 選手グレード別の分析
**主要クラス**: `GradeAnalyzer`
**主要機能**:
- A1/A2/B1/B2級別の成績
- グレード昇降の追跡
- グレード別の期待値計算

**使用場所**: 選手タブ

---

#### `kimarite_scorer.py`
**役割**: 決まり手に基づくスコアリング
**主要クラス**: `KimariteScorer`
**主要機能**:
- 決まり手の重要度計算
- スコアベースの順位予測

**使用場所**: リアルタイム予想

---

#### `grade_scorer.py`
**役割**: グレードに基づくスコアリング
**主要クラス**: `GradeScorer`
**主要機能**:
- グレード差のスコア化
- 格上/格下の有利不利計算

**使用場所**: リアルタイム予想

---

#### `pattern_analyzer.py`
**役割**: レースパターンの分析
**主要クラス**: `PatternAnalyzer`
**主要機能**:
- 1-2-3着の頻出パターン
- スタート展示とレース結果の相関
- 枠番別の勝率パターン

**使用場所**: 場攻略タブ

---

### 4️⃣ 予測系（2ファイル）

#### `race_predictor.py`
**役割**: レース結果の予測（メインエンジン）
**主要クラス**: `RacePredictor`
**主要機能**:
- XGBoostモデルによる着順予測
- 三連単確率の計算
- TOP10組み合わせの抽出

**使用場所**: リアルタイム予想タブ、バックテスト

---

#### `realtime_predictor.py`
**役割**: リアルタイム予想の実行
**主要クラス**: `RealtimePredictor`
**主要機能**:
- 今日のレース一覧取得
- レース選択UI
- 予測結果の表示制御

**使用場所**: リアルタイム予想タブ（UI統合）

---

### 5️⃣ 評価系（3ファイル）

#### `backtest.py`
**役割**: 予測モデルのバックテスト
**主要クラス**: `Backtester`
**主要機能**:
- 過去データでの予測精度検証
- ROI（投資収益率）の計算
- 期間別のパフォーマンス分析

**使用場所**: バックテストタブ（UI）

---

#### `rule_validator.py`
**役割**: 予測ルールの検証
**主要クラス**: `RuleValidator`
**主要機能**:
- ルールベース予測の評価
- if-thenルールの精度測定

**使用場所**: ルール検証UI（設定タブ）

---

#### `statistics_calculator.py`
**役割**: 統計指標の計算
**主要クラス**: `StatisticsCalculator`
**主要機能**:
- 勝率・連対率の計算
- 信頼区間の計算
- t検定・カイ二乗検定

**使用場所**: データ分析タブ、ホームタブ

---

## 🔗 依存関係マップ

```
データ収集（scraper/）
  ↓
データベース（database/）
  ↓
【データ処理系】
  - data_explorer.py ──→ データ取得
  - data_preprocessor.py ──→ クリーニング
  - data_quality.py ──→ 品質監視
  - data_coverage_checker.py ──→ カバレッジ確認
  ↓
【特徴量生成系】
  - feature_generator.py ──→ 学習用特徴量
  - feature_calculator.py ──→ 統計特徴量
  ↓
【分析系】
  - racer_analyzer.py ──→ 選手分析
  - motor_analyzer.py ──→ モーター分析
  - kimarite_analyzer.py ──→ 決まり手分析
  - grade_analyzer.py ──→ グレード分析
  - kimarite_scorer.py ──→ 決まり手スコア
  - grade_scorer.py ──→ グレードスコア
  - pattern_analyzer.py ──→ パターン分析
  ↓
【予測系】
  - race_predictor.py ──→ メイン予測
  - realtime_predictor.py ──→ リアルタイム実行
  ↓
【評価系】
  - backtest.py ──→ バックテスト
  - rule_validator.py ──→ ルール検証
  - statistics_calculator.py ──→ 統計計算
  ↓
UI（ui/）
```

---

## 📈 データフロー（リアルタイム予想の例）

```
1. ユーザーが会場・レースを選択
   ↓
2. realtime_predictor.py が起動
   ↓
3. data_explorer.py でレースデータ取得
   ↓
4. feature_generator.py で特徴量生成
   ↓
5. race_predictor.py で予測実行
   ↓
6. kimarite_scorer.py, grade_scorer.py でスコア補正
   ↓
7. statistics_calculator.py で統計指標計算
   ↓
8. UI に結果表示（TOP10組み合わせ、確率、オッズ）
```

---

## 📈 データフロー（モデル学習の例）

```
1. データ準備タブで期間・特徴量を選択
   ↓
2. data_explorer.py で過去データ取得
   ↓
3. data_preprocessor.py でクリーニング
   ↓
4. feature_generator.py で特徴量生成
   ↓
5. ModelTrainer（ml/）で学習実行
   ↓
6. backtest.py でバックテスト評価
   ↓
7. statistics_calculator.py で評価指標計算
   ↓
8. UI に学習結果表示（精度、Log Loss、特徴量重要度）
```

---

## 🎯 使い方ガイド

### 基本的な使い方

#### 1. データ探索

```python
from src.analysis.data_explorer import DataExplorer

explorer = DataExplorer()

# 過去30日のレース結果を取得
races = explorer.get_recent_races(days=30)

# 特定選手の成績を取得
racer_stats = explorer.get_racer_stats(racer_id=12345)
```

#### 2. 特徴量生成

```python
from src.analysis.feature_generator import FeatureGenerator

generator = FeatureGenerator()

# Phase 1.1特徴量（選手基本情報）を生成
features = generator.generate_phase1_features(race_data)

# Phase 2.1特徴量（組み合わせ）を生成
combo_features = generator.generate_phase2_features(race_data)
```

#### 3. レース予測

```python
from src.analysis.race_predictor import RacePredictor

predictor = RacePredictor()

# レース予測を実行
predictions = predictor.predict_race(
    venue_code='01',
    race_number=12,
    race_date='2024-11-03'
)

# TOP10組み合わせを取得
top10 = predictions['top10_combinations']
```

---

## 🚀 改善案

### 現状の課題

1. **モジュール数が多い（18ファイル）**
   - 役割が重複している部分がある
   - 命名規則が統一されていない（analyzer vs scorer vs calculator）

2. **依存関係が複雑**
   - どのモジュールがどのモジュールに依存しているか不明瞭
   - 循環参照の可能性

3. **ドキュメント不足**
   - 各モジュールの docstring が不十分
   - 使い方の例が少ない

### 改善提案

#### 短期（1週間）

- [ ] 各モジュールの docstring を充実させる
- [ ] README.md に使い方の例を追加
- [ ] 重複機能の統合検討

#### 中期（2-3週間）

- [ ] モジュール名の統一（analyzer に統一など）
- [ ] 依存関係の可視化（図解）
- [ ] 不要な抽象化の削減

#### 長期（1-2ヶ月）

- [ ] モジュール再編成（カテゴリ別にサブディレクトリ化）
- [ ] インターフェースの統一
- [ ] ユニットテストの追加

---

## 📝 命名規則の提案

### 現状

- analyzer: 7ファイル
- scorer: 2ファイル
- calculator: 2ファイル
- generator: 1ファイル
- predictor: 2ファイル
- その他: 4ファイル

### 統一案

すべて `***_analyzer.py` に統一:

```
src/analysis/
├── data/
│   ├── explorer_analyzer.py (data_explorer.py)
│   ├── preprocessor_analyzer.py (data_preprocessor.py)
│   ├── quality_analyzer.py (data_quality.py)
│   └── coverage_analyzer.py (data_coverage_checker.py)
├── features/
│   ├── feature_analyzer.py (feature_generator.py)
│   └── stats_analyzer.py (feature_calculator.py)
├── entities/
│   ├── racer_analyzer.py ✅
│   ├── motor_analyzer.py ✅
│   ├── kimarite_analyzer.py ✅
│   ├── grade_analyzer.py ✅
│   └── pattern_analyzer.py ✅
├── prediction/
│   ├── race_analyzer.py (race_predictor.py)
│   └── realtime_analyzer.py (realtime_predictor.py)
└── evaluation/
    ├── backtest_analyzer.py (backtest.py)
    ├── rule_analyzer.py (rule_validator.py)
    └── statistics_analyzer.py (statistics_calculator.py)
```

**注意**: この再編成は破壊的変更のため、慎重に実施すべき

---

## 🔗 関連ドキュメント

- [MODULE_CONSOLIDATION_COMPLETED.md](MODULE_CONSOLIDATION_COMPLETED.md) - モジュール統合完了報告
- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md) - システム仕様書
- [HANDOVER.md](HANDOVER.md) - 開発引継ぎ資料

---

**最終更新**: 2025-11-03
**次回レビュー**: 2025-11-10
