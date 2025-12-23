# ボートレース予想システム - 技術評価資料

**作成日**: 2025年11月18日
**目的**: 外部AIによる技術評価・改善提案のための包括的資料
**システムバージョン**: v2.0

---

## 📋 目次

1. [システム概要](#1-システム概要)
2. [技術スタック](#2-技術スタック)
3. [アーキテクチャ](#3-アーキテクチャ)
4. [データ構造](#4-データ構造)
5. [予測ロジック](#5-予測ロジック)
6. [機械学習モデル](#6-機械学習モデル)
7. [現在の課題](#7-現在の課題)
8. [パフォーマンス指標](#8-パフォーマンス指標)
9. [評価観点](#9-評価観点)

---

## 1. システム概要

### 1.1 プロジェクトの目的

競艇（ボートレース）の過去データを収集・分析し、機械学習による高精度なレース予想と期待値ベースの投資戦略を提供する統合システム。

### 1.2 主要機能

#### データ収集
- レーススケジュール、結果、出走表の自動収集（2016年〜現在）
- オリジナル展示データ収集（直線タイム、1周タイム、回り足タイム）
- 気象データ（気温、水温、風向、風速、波高）
- 潮位データ（気象庁RDMDB API経由）
- リアルタイムオッズデータ（三連単120通り）

#### 機械学習・予測
- 条件付き着順予測モデル（1着→2着→3着の段階的予測）
- 三連単120通りの確率予測
- 確率校正（Platt Scaling / Isotonic Regression）
- 艇番バイアス補正
- SHAP値による予測根拠の可視化

#### ベッティング戦略
- Kelly基準による最適投資額計算
- 期待値フィルタリング（EV >= 1.0）
- バックテストによるROI検証
- 購入履歴・収支管理

#### UIシステム（Streamlit）
- データ参照（レース結果、会場分析、選手分析）
- レース予想（一覧・推奨、詳細分析）
- データ準備（自動/手動収集、モデル学習）
- 設定・管理（システム監視、法則管理）

### 1.3 プロジェクト規模

- **Pythonファイル**: 130個（クリーンアップ後）
- **Markdownファイル**: 66個（クリーンアップ後）
- **データベースサイズ**: 約131,898レース（2016年〜現在）
- **コード行数**: 約15,000行（推定）
- **開発期間**: 約1年

---

## 2. 技術スタック

### 2.1 プログラミング言語
- **Python 3.10+**

### 2.2 データ収集
- `requests` - HTTP通信
- `beautifulsoup4` - HTMLパース
- `selectolax` - 高速HTMLパース
- `playwright` - ブラウザ自動化（オッズ取得）

### 2.3 データ処理
- `pandas` - データフレーム操作
- `numpy` - 数値計算
- `sqlite3` - データベース

### 2.4 機械学習
- `xgboost` - 勾配ブースティング（メインモデル）
- `lightgbm` - 勾配ブースティング（代替）
- `scikit-learn` - 前処理、確率校正、評価指標
- `optuna` - ハイパーパラメータ最適化
- `shap` - モデル解釈

### 2.5 可視化・UI
- `streamlit` - Webアプリケーション
- `plotly` - インタラクティブグラフ
- `matplotlib` - 静的グラフ
- `seaborn` - 統計グラフ

### 2.6 その他
- `pytest` - テスト
- `python-dotenv` - 環境変数管理

---

## 3. アーキテクチャ

### 3.1 ディレクトリ構造

```
BoatRace/
├── src/                      # ソースコード
│   ├── scraper/             # データ取得
│   │   ├── boatrace_scraper.py           # レース結果スクレイパー
│   │   ├── playwright_odds_scraper.py    # オッズスクレイパー
│   │   └── beforeinfo_scraper.py         # オリジナル展示スクレイパー
│   ├── database/            # データベース管理
│   │   ├── models.py                     # テーブル定義
│   │   └── views.py                      # SQLビュー定義
│   ├── analysis/            # データ分析
│   ├── features/            # 特徴量抽出
│   │   ├── racer_features.py             # 選手特徴量
│   │   ├── interaction_features.py       # 交互作用項
│   │   └── equipment_embedding.py        # 機器埋め込み
│   ├── ml/                  # 機械学習
│   │   ├── conditional_rank_model.py     # 条件付き着順予測
│   │   └── probability_adjuster.py       # 確率補正
│   ├── training/            # モデル学習
│   ├── prediction/          # 予測エンジン
│   ├── betting/             # 投資戦略
│   └── utils/               # ユーティリティ
├── ui/                      # Streamlit UI
│   ├── app.py                            # メインアプリ
│   └── components/                       # UIコンポーネント
│       ├── unified_race_list.py          # レース一覧
│       ├── unified_race_detail.py        # レース詳細
│       ├── venue_analysis.py             # 会場分析
│       └── racer_analysis.py             # 選手分析
├── data/                    # データベース
│   └── boatrace.db                       # SQLite DB
├── models/                  # 学習済みモデル
│   ├── conditional_rank_v1_first.json
│   ├── conditional_rank_v1_second.json
│   ├── conditional_rank_v1_third.json
│   └── conditional_rank_v1.meta.json
├── config/                  # 設定ファイル
│   └── settings.py                       # グローバル設定
├── docs/                    # ドキュメント
└── requirements.txt         # 依存パッケージ
```

### 3.2 データフロー

```
[公式サイト]
    ↓ (スクレイピング)
[生データ]
    ↓ (SQLite保存)
[データベース]
    ↓ (特徴量抽出)
[訓練データセット]
    ↓ (XGBoost学習)
[学習済みモデル]
    ↓ (予測)
[三連単確率120通り]
    ↓ (バイアス補正)
[補正後確率]
    ↓ (オッズ取得)
[期待値計算]
    ↓ (Kelly基準)
[推奨ベット]
```

### 3.3 モジュール間の依存関係

```
ui/app.py
  ↓
src/prediction/
  ├── src/ml/conditional_rank_model.py
  ├── src/ml/probability_adjuster.py
  └── src/scraper/playwright_odds_scraper.py
        ↓
src/database/models.py
  ↓
data/boatrace.db
```

---

## 4. データ構造

### 4.1 データベーススキーマ

#### 主要テーブル

##### `races` - レース基本情報
```sql
CREATE TABLE races (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date TEXT NOT NULL,
    venue_code TEXT NOT NULL,
    race_number INTEGER NOT NULL,
    race_class TEXT,          -- 一般、準優勝戦、優勝戦
    is_cancelled INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(race_date, venue_code, race_number)
);
```

##### `entries` - 出走表
```sql
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,        -- 艇番（1〜6）
    racer_number INTEGER,               -- 選手登録番号
    racer_name TEXT,
    racer_rank TEXT,                    -- 級別（A1, A2, B1, B2）
    win_rate REAL,                      -- 全国勝率
    second_rate REAL,                   -- 全国2連率
    third_rate REAL,                    -- 全国3連率
    local_win_rate REAL,                -- 当地勝率
    motor_number INTEGER,
    motor_second_rate REAL,             -- モーター2連率
    motor_third_rate REAL,
    boat_number INTEGER,
    boat_second_rate REAL,
    boat_third_rate REAL,
    avg_st REAL,                        -- 平均スタートタイミング
    racer_weight REAL,                  -- 体重
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (race_id) REFERENCES races(id),
    UNIQUE(race_id, pit_number)
);
```

##### `results` - レース結果
```sql
CREATE TABLE results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,
    rank INTEGER NOT NULL,              -- 着順（1〜6）
    race_time REAL,                     -- レースタイム
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (race_id) REFERENCES races(id),
    UNIQUE(race_id, pit_number)
);
```

##### `race_details` - レース詳細
```sql
CREATE TABLE race_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,
    tenji_time REAL,                    -- 展示タイム
    tenji_course INTEGER,               -- 展示コース
    st_time REAL,                       -- スタートタイミング
    kimarite TEXT,                      -- 決まり手
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (race_id) REFERENCES races(id),
    UNIQUE(race_id, pit_number)
);
```

##### `original_tenji_data` - オリジナル展示データ（重要）
```sql
CREATE TABLE original_tenji_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,
    chikusen_time REAL,                 -- 直線タイム
    isshu_time REAL,                    -- 1周タイム
    mawariashi_time REAL,               -- 回り足タイム
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (race_id) REFERENCES races(id),
    UNIQUE(race_id, pit_number)
);
```

**注意**: オリジナル展示データは公式サイトで「昨日」と「今日」のみ公開。2日前以前のデータは自動削除される。

##### `payouts` - 払戻金
```sql
CREATE TABLE payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    bet_type TEXT NOT NULL,             -- trifecta, exacta, quinella等
    combination TEXT NOT NULL,          -- 例: "1-2-3"
    amount INTEGER NOT NULL,            -- 払戻金（100円あたり）
    popularity INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (race_id) REFERENCES races(id)
);
```

### 4.2 データ統計（2025-11-18時点）

| テーブル | レコード数 | 備考 |
|---------|-----------|------|
| races | 131,898 | 2016年〜2025年11月 |
| entries | 791,388 | 6艇 × レース数 |
| results | 791,388 | 着順データ |
| race_details | 630,471 | 約79%のカバー率 |
| original_tenji_data | **951** | **0.72%のみ** ⚠️ |
| payouts | 約400,000 | 三連単のみ収集 |

**課題**: オリジナル展示データが極端に少ない（日次自動収集が未設定のため）

---

## 5. 予測ロジック

### 5.1 予測フロー全体像

```
1. レース特徴量取得
   └─ 選手成績、モーター成績、級別、体重、ST等

2. 条件付き着順予測
   ├─ 1着予測（6艇全員対象）
   ├─ 2着予測（1着除く5艇対象、1着条件付き）
   └─ 3着予測（1-2着除く4艇対象、1-2着条件付き）

3. 三連単確率計算
   └─ P(1-2-3) = P(1着) × P(2着|1着) × P(3着|1-2着)

4. 確率補正
   └─ 艇番バイアスを統計的に補正

5. オッズ取得
   └─ Playwright経由でリアルタイムオッズを取得

6. 期待値計算
   └─ EV = 予測確率 × オッズ

7. 推奨ベット選定
   └─ EV >= 1.0 かつ 確率 >= 0.5% をフィルタ
```

### 5.2 条件付き着順予測の詳細

#### 従来方式の問題点
```python
# 従来: 1着確率から疑似推定
P(1着=1号艇) = 0.5
P(2着=2号艇|1着=1号艇) = P(2着=2号艇) / (1 - P(1着=1号艇))
```
→ **問題**: 1着艇が確定した後の状況を考慮していない

#### 新方式（条件付きモデル）
```python
# 改善: 段階的予測
P(1着=1号艇) = Model_1st.predict([全艇の特徴量])

# 1着確定後、残り5艇で2着予測
P(2着=2号艇|1着=1号艇) = Model_2nd.predict([
    2号艇の特徴量,
    1号艇の特徴量  # 条件として追加
])

# 1-2着確定後、残り4艇で3着予測
P(3着=3号艇|1着=1号艇, 2着=2号艇) = Model_3rd.predict([
    3号艇の特徴量,
    1号艇の特徴量,  # 条件として追加
    2号艇の特徴量   # 条件として追加
])

# 最終確率
P(1-2-3) = P(1着=1号艇) × P(2着=2号艇|1着=1号艇) × P(3着=3号艇|1着=1号艇, 2着=2号艇)
```

**メリット**:
- 各段階で最適な予測が可能
- 「1着が強い艇の場合、2着争いはより接戦」などの状況を学習
- 三連単120通りの確率をより精密に予測

### 5.3 確率補正ロジック

#### 発見された問題
モデルは艇番（コース位置）を特徴量に含んでいないため、以下のバイアスが存在：

| 艇番 | 実際の勝率 | 予測頻度 | バイアス |
|------|-----------|---------|---------|
| 1号艇 | 49.5% | 24.3% | **-25.2%** 過小評価 |
| 5号艇 | 11.9% | 22.9% | **+11.0%** 過大評価 |
| 6号艇 | 2.4% | 12.4% | **+10.0%** 過大評価 |

#### 補正方法
```python
# 艇番別の実際の勝率（統計データ）
ACTUAL_WIN_RATES = {
    1: 0.495,  # 49.5%
    2: 0.129,  # 12.9%
    3: 0.133,  # 13.3%
    4: 0.100,  # 10.0%
    5: 0.119,  # 11.9%
    6: 0.024,  # 2.4%
}

# 補正係数 = 実際の勝率 / 均等分布（16.7%）
correction_factors = {
    1: 0.495 / 0.167 = 2.97,  # 1号艇を約3倍強化
    5: 0.119 / 0.167 = 0.71,  # 5号艇を30%減衰
    6: 0.024 / 0.167 = 0.14,  # 6号艇を86%減衰
}

# 補正強度（0.0〜1.0）で調整可能
adjusted_factor = 1.0 + (factor - 1.0) * adjustment_strength

# 三連単確率に適用
adjusted_prob['1-2-3'] = prob['1-2-3'] * correction_factors[1]
```

**補正効果**:
- 1号艇中心の組み合わせの確率が上昇
- 5号艇・6号艇中心の組み合わせの確率が低下
- 期待値計算がより実態に即したものになる

---

## 6. 機械学習モデル

### 6.1 モデルアーキテクチャ

#### モデル構成
- **Model_1st**: XGBoostClassifier（1着予測）
- **Model_2nd**: XGBoostClassifier（2着予測、1着条件付き）
- **Model_3rd**: XGBoostClassifier（3着予測、1-2着条件付き）

#### ハイパーパラメータ
```python
params = {
    'objective': 'binary:logistic',
    'eval_metric': 'auc',
    'max_depth': 6,
    'learning_rate': 0.05,
    'n_estimators': 200,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'min_child_weight': 3,
    'gamma': 0.1,
    'random_state': 42,
}
```

### 6.2 特徴量（現在11個）

```python
feature_cols = [
    'win_rate',           # 選手勝率（全国）
    'second_rate',        # 選手2連率
    'third_rate',         # 選手3連率
    'motor_2nd_rate',     # モーター2連率
    'motor_3rd_rate',     # モーター3連率
    'boat_2nd_rate',      # ボート2連率
    'boat_3rd_rate',      # ボート3連率
    'weight',             # 選手体重
    'avg_st',             # 平均スタートタイミング
    'local_win_rate',     # 当地勝率
    'racer_rank_score',   # 級別スコア（A1=4, A2=3, B1=2, B2=1）
]
```

### 6.3 欠けている重要特徴量

#### 🚨 最重要
- **`pit_number`** - 艇番（コース位置）
  - 競艇では1号艇（インコース）が圧倒的に有利
  - この特徴量がないため、モデルは1号艇を過小評価

#### 提案されている追加特徴量
```python
# モデル再学習時に追加予定
additional_features = [
    'pit_number',                    # 艇番（1〜6）
    'tenji_time',                    # 展示タイム
    'st_time',                       # スタートタイミング（実測）
    'chikusen_time',                 # 直線タイム（オリジナル展示）
    'isshu_time',                    # 1周タイム（オリジナル展示）
    'mawariashi_time',               # 回り足タイム（オリジナル展示）
    'motor_win_rate',                # モーター勝率
    'boat_win_rate',                 # ボート勝率
    'wind_speed',                    # 風速
    'wind_direction',                # 風向
    'temperature',                   # 気温
    'water_temperature',             # 水温
    'wave_height',                   # 波高
    'tide_level',                    # 潮位
    'racer_recent_5_avg_rank',       # 直近5走平均着順
    'racer_venue_win_rate',          # 会場別選手勝率
]
```

### 6.4 学習データ

#### データ期間
- **訓練**: 2020-01-01 〜 2024-12-31（約5年）
- **検証**: 2025-01-01 〜 2025-06-30（6ヶ月）
- **テスト**: 2025-07-01 〜 2025-10-31（4ヶ月）

#### データサイズ
- 訓練: 約100,000レース（600,000行）
- 検証: 約20,000レース（120,000行）
- テスト: 約10,000レース（60,000行）

### 6.5 モデル性能

#### AUC（識別性能）
- **Model_1st**: 0.72〜0.75
- **Model_2nd**: 0.68〜0.72
- **Model_3rd**: 0.65〜0.70

#### 予測精度（210レース統計）
- **Top1的中率**: 2.9%（期待値0.83%）→ **3.5倍改善**
- **Top3的中率**: 11.0%（期待値2.5%）→ **4.4倍改善**
- **Top5的中率**: 17.1%（期待値4.2%）→ **4.1倍改善**

#### バックテスト結果（暫定）
- **ROI（回収率）**: 約75%（目標: 110%以上）
- **的中率**: 約3%
- **期待値1.0以上の推奨数**: レースあたり5〜10通り

**課題**: 艇番バイアスにより、ROIが目標に未達

---

## 7. 現在の課題

### 7.1 優先度：最高（🔴）

#### 1. オリジナル展示データの不足
- **現状**: 131,898レース中、わずか951レース（0.72%）のみ
- **原因**: 日次自動収集が未設定
- **影響**: 重要な特徴量（直線タイム等）が使用不可
- **対策**: 毎日20:00に自動収集スクリプトを実行（Windows Task Scheduler）

#### 2. モデルの艇番バイアス
- **現状**: 1号艇を25%過小評価、5号艇を11%過大評価
- **原因**: `pit_number`が特徴量に含まれていない
- **影響**: ROI 75%（目標110%未達）
- **対策**:
  - 短期: 確率補正（実装済み）
  - 中期: `pit_number`を特徴量に追加してモデル再学習

### 7.2 優先度：高（🟠）

#### 3. データ収集の安定性
- **問題**: 公式サイトの仕様変更でスクレイパーが停止するリスク
- **対策**: 定期的な監視、エラーハンドリングの強化

#### 4. オッズ取得の速度
- **現状**: Playwright使用で1レースあたり5〜10秒
- **影響**: 直前予測が間に合わない可能性
- **対策**: 非同期処理、キャッシュ機構の導入

### 7.3 優先度：中（🟡）

#### 5. UIのレスポンス
- **問題**: データ量が多いとStreamlitが遅い
- **対策**: ページング、遅延読み込み、SQLインデックス最適化

#### 6. モデルの解釈性
- **問題**: ユーザーが「なぜこの予測か」を理解しにくい
- **対策**: SHAP値の可視化、特徴量重要度の表示

### 7.4 優先度：低（🟢）

#### 7. テストカバレッジ
- **現状**: 主要機能のみ手動テスト
- **対策**: pytest導入、自動テスト拡充

#### 8. ドキュメント整備
- **現状**: 散在、一部古い情報あり
- **対策**: README統一、APIドキュメント生成

---

## 8. パフォーマンス指標

### 8.1 データ収集速度
- **レース結果**: 約0.3〜0.5レース/秒
- **オッズ**: 約0.1〜0.2レース/秒（Playwright使用）
- **1日分（約144レース）**: 約10〜15分

### 8.2 予測速度
- **特徴量抽出**: 1レースあたり < 0.1秒
- **三連単確率計算**: 1レースあたり約0.2秒
- **合計**: 1レースあたり約0.3秒

### 8.3 データベース性能
- **総レコード数**: 約250万行
- **データベースサイズ**: 約500MB
- **クエリ速度**: 平均 < 50ms

### 8.4 UIレスポンス
- **初回読み込み**: 約2〜3秒
- **ページ切り替え**: 約0.5〜1秒
- **予測実行**: 約5〜10秒（オッズ取得含む）

---

## 9. 評価観点

### 9.1 技術的評価をお願いしたい項目

#### アーキテクチャ
- [ ] モジュール分割は適切か？
- [ ] データフローの設計は最適か？
- [ ] 依存関係の管理は適切か？

#### データモデリング
- [ ] データベーススキーマは正規化されているか？
- [ ] インデックスは適切に設定されているか？
- [ ] データの欠損処理は適切か？

#### 機械学習
- [ ] モデル選択は適切か？（XGBoost vs LightGBM vs 他）
- [ ] 特徴量エンジニアリングの改善余地は？
- [ ] 過学習対策は十分か？
- [ ] データリーケージの危険性はないか？

#### 予測ロジック
- [ ] 条件付き着順予測の実装は正しいか？
- [ ] 確率補正の方法は妥当か？
- [ ] Kelly基準の使用方法は適切か？

#### パフォーマンス
- [ ] ボトルネックはどこか？
- [ ] 並列処理の余地はあるか？
- [ ] メモリ効率は適切か？

#### コード品質
- [ ] 命名規則は一貫しているか？
- [ ] エラーハンドリングは十分か？
- [ ] テストは必要十分か？

### 9.2 ビジネスロジックの評価

#### 投資戦略
- [ ] 期待値フィルタ（EV >= 1.0）は妥当か？
- [ ] Kelly基準の適用は正しいか？
- [ ] リスク管理は十分か？

#### 予測精度
- [ ] Top1的中率2.9%は実用的か？
- [ ] ROI 75%をどう改善すべきか？
- [ ] バイアス補正以外のアプローチはあるか？

### 9.3 改善提案を期待する領域

1. **モデル再学習の実装方法**
   - `pit_number`追加後の学習手順
   - ハイパーパラメータの最適化方法

2. **新特徴量の追加**
   - オリジナル展示データの活用方法
   - 交互作用項の設計

3. **ROI向上策**
   - ベッティング戦略の改善
   - 確率校正の精度向上

4. **システムの堅牢性**
   - エラーハンドリングの改善
   - 監視・アラートの仕組み

5. **スケーラビリティ**
   - データ量増加への対応
   - 複数ユーザー対応

---

## 10. 参考資料

### 10.1 主要ドキュメント
- [README.md](../README.md) - プロジェクト概要
- [README_SCRIPTS.md](../README_SCRIPTS.md) - スクリプト一覧
- [model_bias_analysis_20251118.md](model_bias_analysis_20251118.md) - モデルバイアス分析
- [プロジェクト全体レビュー_20251118.md](プロジェクト全体レビュー_20251118.md) - 全体レビュー

### 10.2 主要スクリプト
- [train_conditional_model.py](../train_conditional_model.py) - モデル学習
- [predict_today.py](../predict_today.py) - 今日のレース予測
- [run_backtest.py](../run_backtest.py) - バックテスト実行
- [ui/app.py](../ui/app.py) - UIメインアプリ

### 10.3 重要コンポーネント
- [src/ml/conditional_rank_model.py](../src/ml/conditional_rank_model.py) - 条件付きモデル
- [src/ml/probability_adjuster.py](../src/ml/probability_adjuster.py) - 確率補正
- [src/scraper/playwright_odds_scraper.py](../src/scraper/playwright_odds_scraper.py) - オッズ取得

---

## 11. 評価のお願い

### 評価してほしい内容

1. **技術的改善点**
   - コードの品質、設計パターン
   - パフォーマンスの最適化
   - セキュリティ上の懸念

2. **機械学習の改善**
   - 特徴量エンジニアリング
   - モデル選択・ハイパーパラメータ
   - バイアス対策

3. **システム設計**
   - アーキテクチャの妥当性
   - スケーラビリティ
   - 保守性

4. **ビジネスロジック**
   - 投資戦略の妥当性
   - ROI改善のアプローチ

### 評価形式

以下のような形式で評価いただけると助かります：

```markdown
## 評価サマリー

**総合評価**: B+（良好、改善余地あり）

**強み**:
- ✅ データ収集の自動化が充実
- ✅ 条件付き予測モデルの設計が良い
- ✅ UIが使いやすい

**改善が必要な領域**:
- ❌ 艇番特徴量の欠如
- ❌ オリジナル展示データの不足
- ⚠️ パフォーマンスのボトルネック

## 詳細評価

### 1. アーキテクチャ
[評価内容]

### 2. 機械学習
[評価内容]

### 3. 具体的改善提案
[提案内容]
```

---

**作成者**: 開発チーム
**最終更新**: 2025年11月18日
**問い合わせ**: プロジェクト管理者
