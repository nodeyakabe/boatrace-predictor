# 予測ロジック詳細

**最終更新**: 2025-12-15
**ドキュメント管理者**: Claude Code

---

## 1. 予測エンジン比較表

| エンジン | 用途 | 入力 | 出力 | 本番使用 |
|---------|------|------|------|---------|
| **RacePredictor** | ルールベース+ML統合予測 | race_date, venue, race_num | ランキング+スコア+信頼度 | **メイン** |
| **HierarchicalPredictor** | 階層的確率モデル | race_id | 三連単確率リスト | 補助 |
| RuleBasedEngine | ルールベース予測 | - | - | 内部使用 |
| TrifectaCalculator | 三連単確率計算 | 6艇の特徴量 | 120通りの確率 | 内部使用 |

---

## 2. RacePredictor詳細

### 2.1 ファイル情報

- **ファイル**: `src/analysis/race_predictor.py`
- **クラス**: `RacePredictor`
- **メソッド**: `predict_race_by_key(race_date, venue_code, race_number)`

### 2.2 スコアリング構成要素

RacePredictorは以下のスコアラーを統合して予測を行う:

| スコアラー | 役割 | 重み |
|-----------|------|------|
| `StatisticsCalculator` | コース別統計スコア | 変動 |
| `RacerAnalyzer` | 選手成績スコア | 変動 |
| `MotorAnalyzer` | モーター性能スコア | 変動 |
| `KimariteScorer` | 決まり手傾向スコア | - |
| `GradeScorer` | グレード補正 | - |
| `WeatherAdjuster` | **天候補正（風向×風速）** | - |
| `TideAdjuster` | 潮位補正 | - |
| `ExhibitionAnalyzer` | 展示タイム分析 | - |
| `BeforeInfoScorer` | **直前情報スコア（ST×展示）** | - |
| `ExtendedScorer` | 拡張スコアリング | - |
| `CompoundBuffSystem` | 複合バフシステム | - |

### 2.3 直前情報パターンボーナス

`race_predictor.py` 内で定義されている直前情報パターン:

#### 1着予測用パターン (BEFORE_PATTERNS_1ST)

| パターン名 | 条件 | 倍率 |
|-----------|------|------|
| `pre1_st1` | PRE1位 & ST1位 | 1.411 |
| `pre1_ex1` | PRE1位 & 展示1位 | 1.286 |
| `pre1_ex1_3_st1_3` | PRE1位 & 展示1-3位 & ST1-3位 | 1.328 |
| `pre1_st1_3` | PRE1位 & ST1-3位 | 1.310 |

#### 2着予測用パターン (BEFORE_PATTERNS_2ND)

| パターン名 | 条件 | 倍率 |
|-----------|------|------|
| `pre2_3_ex1_2` | PRE2-3位 & 展示1-2位 | 1.084 |
| `pre2_ex1_3_st1_3` | PRE2位 & 展示1-3位 & ST1-3位 | 1.081 |
| `ex1_3_pre2_3` | 展示1-3位 & PRE2-3位 | 1.069 |
| `pre2_st1_3` | PRE2位 & ST1-3位 | 1.064 |
| `pre2_ex1_3` | PRE2位 & 展示1-3位 | 1.063 |
| `ex_rank_2` | 展示2位 | 1.035 |
| `st_rank_2_3` | ST2-3位 | 1.034 |

#### 3着予測用パターン (BEFORE_PATTERNS_3RD)

| パターン名 | 条件 | 倍率 |
|-----------|------|------|
| `pre3_4_ex2_4` | PRE3-4位 & 展示2-4位 | 1.032 |
| `pre3_ex1_3` | PRE3位 & 展示1-3位 | 1.031 |
| `outer_st1_2` | アウトコース(4-6枠) & ST1-2位 | 1.022 |
| `pre3_4_ex1_3_st1_3` | PRE3-4位 & 展示1-3位 & ST1-3位 | 1.020 |

### 2.4 信頼度計算

予測の信頼度（Confidence）は A/B/C/D の4段階:

```
信頼度計算ロジック:
- スコア差、1着候補の支配率、パターン適合度などを総合評価
- A: 高信頼（スコア差が大きい、パターン強適合）
- B: 中高信頼
- C: 中信頼
- D: 低信頼（スコアが接近、パターン弱適合）
```

**購入対象**: 信頼度 C または D のみ（A/B はサンプル不足で不安定）

### 2.5 最終スコア計算

```python
# 各スコアラーからの出力を統合
total_score = (
    course_score * weight_course +
    racer_score * weight_racer +
    motor_score * weight_motor +
    weather_adjustment +
    tide_adjustment +
    beforeinfo_bonus +
    compound_buff
)

# ランキング生成
ranking = sorted(range(1, 7), key=lambda pit: scores[pit], reverse=True)
```

---

## 3. HierarchicalPredictor詳細

### 3.1 ファイル情報

- **ファイル**: `src/prediction/hierarchical_predictor.py`
- **クラス**: `HierarchicalPredictor`
- **依存**: `TrifectaCalculator`, `ConditionalRankModel`

### 3.2 3段階予測モデル

```
Stage1: P(i = 1着)
  - 入力: 6艇の特徴量
  - 出力: 各艇の1着確率 [p1, p2, p3, p4, p5, p6]

Stage2: P(j = 2着 | i = 1着)
  - 入力: 6艇の特徴量 + 1着艇の特徴量
  - 出力: 1着艇以外の各艇が2着になる確率

Stage3: P(k = 3着 | i = 1着, j = 2着)
  - 入力: 6艇の特徴量 + 1着艇の特徴量 + 2着艇の特徴量
  - 出力: 1-2着艇以外の各艇が3着になる確率
```

### 3.3 三連単確率計算

**計算式**:
```
P(i-j-k) = P(i=1st) × P(j=2nd|i=1st) × P(k=3rd|i=1st,j=2nd)
```

**実装** (`trifecta_calculator.py`):
```python
for i in range(6):  # 1着候補
    p_first = first_probs[i]

    for j in range(6):  # 2着候補
        if j == i: continue
        p_second = second_probs[j]

        for k in range(6):  # 3着候補
            if k == i or k == j: continue
            p_third = third_probs[k]

            # 三連単確率
            prob = p_first * p_second * p_third
            trifecta_probs[f"{i+1}-{j+1}-{k+1}"] = prob
```

### 3.4 モデル読み込み

```python
# V1モデル（本番）
predictor = HierarchicalPredictor(
    db_path='data/boatrace.db',
    model_dir='models',
    use_v2=False  # デフォルト
)

# V2モデル（実験）
predictor = HierarchicalPredictor(
    db_path='data/boatrace.db',
    model_dir='models',
    use_v2=True
)
```

---

## 4. ConditionalRankModel詳細

### 4.1 ファイル情報

- **ファイル**: `src/ml/conditional_rank_model.py`
- **クラス**: `ConditionalRankModel`
- **アルゴリズム**: XGBoost（体系B）/ LightGBM（体系A）

### 4.2 特徴量設計

#### Stage1 (1着予測)

基本特徴量 (17個):
```
win_rate, second_rate, motor_second_rate, boat_second_rate,
exhibition_time, avg_st, actual_course, exh_rank, exh_diff,
exh_zscore, exh_gap_to_best, exh_relative_position,
st_vs_expectation, st_rank, st_diff, st_zscore, st_relative
```

#### Stage2 (2着予測)

基本特徴量 + 1着艇特徴量 + 相対特徴量 (51個):
```
[基本特徴量] +
winner_win_rate, winner_second_rate, ... (1着艇の特徴量) +
diff_win_rate, diff_second_rate, ... (候補艇と1着艇の差分)
```

**2025-12-15 改善点**:
- 1着艇との相対特徴量（差分特徴量）追加
- 1着艇のコースとの位置関係追加
  - `course_diff_from_first`: コース差
  - `is_inner_than_first`: 1着より内側か
  - `is_outer_than_first`: 1着より外側か

#### Stage3 (3着予測)

基本特徴量 + 1着艇特徴量 + 2着艇特徴量 + 相対特徴量 (85個):
```
[基本特徴量] +
winner_*, second_* (1着・2着艇の特徴量) +
diff_winner_*, diff_second_* (候補艇との差分) +
gap_1st_2nd_* (1-2着間の差分 = レース展開情報)
```

### 4.3 学習パラメータ

```python
params = {
    'objective': 'binary:logistic',
    'eval_metric': 'auc',
    'max_depth': 6,
    'learning_rate': 0.05,
    'n_estimators': 500,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'min_child_weight': 3,
    'gamma': 0.1,
    'random_state': 42,
    'n_jobs': -1,
}
```

---

## 5. ベッティング判定ロジック

### 5.1 BetTargetEvaluator

- **ファイル**: `src/betting/bet_target_evaluator.py`
- **クラス**: `BetTargetEvaluator`

### 5.2 戦略B購入条件

```python
BET_CONDITIONS = {
    'C': [
        # C × B1 × 30-40倍: ROI 158.6%
        {'method': '両方式', 'odds_min': 30, 'odds_max': 40,
         'c1_rank': ['B1'], 'expected_roi': 158.6, 'bet_amount': 300},

        # C × A1 × 30-40倍: ROI 141.7%
        {'method': '両方式', 'odds_min': 30, 'odds_max': 40,
         'c1_rank': ['A1'], 'expected_roi': 141.7, 'bet_amount': 300},
    ],
    'D': [
        # D × B1 × 40-50倍: ROI 132.0%
        {'method': '両方式', 'odds_min': 40, 'odds_max': 50,
         'c1_rank': ['B1'], 'expected_roi': 132.0, 'bet_amount': 300},

        # D × A1 × 40-50倍: ROI 405.8%
        {'method': '両方式', 'odds_min': 40, 'odds_max': 50,
         'c1_rank': ['A1'], 'expected_roi': 405.8, 'bet_amount': 300},

        # D × A2 × 20-30倍: ROI 173.3%
        {'method': '両方式', 'odds_min': 20, 'odds_max': 30,
         'c1_rank': ['A2'], 'expected_roi': 173.3, 'bet_amount': 300},
    ],
}
```

### 5.3 除外条件

```python
# 除外信頼度
EXCLUDED_CONFIDENCE = ['A', 'B']  # サンプル不足

# 除外級別
EXCLUDED_C1_RANKS = ['B2']  # 回収率低
```

### 5.4 複数点買い（パターンH）

```python
# MultiBetPattern.PATTERN_H
bet_structure = {
    '1-2-3': 200,  # 予測そのまま
    '1-2-4': 100,  # 3着を4位に変更
    '1-2-5': 100,  # 3着を5位に変更
}
# 合計: 400円/レース
```

### 5.5 会場×コース調整

```python
# VenueCourseAdjuster
# 24会場×6コース=144パターンの調整ポイント

# 例:
venue_course_adjustments = {
    '01': {1: -12, 2: +3, ...},  # 戸田（インが弱い）
    '18': {1: +9, 2: -2, ...},   # 徳山（インが強い）
    '24': {1: +9, 2: -3, ...},   # 大村（インが強い）
}

# 調整閾値: -12pt以下は購入見送り
```

---

## 6. 予測フロー詳細図

```
[入力] race_date, venue_code, race_number
           |
           v
+----------------------+
| BatchDataLoader      |
| - entries取得        |
| - race_details取得   |
| - race_conditions取得|
+----------------------+
           |
           v
+----------------------+
| スコアリング Layer   |
| +------------------+ |
| | StatisticsCalc   | | --> course_score
| | RacerAnalyzer    | | --> racer_score
| | MotorAnalyzer    | | --> motor_score
| | ExhibitionAnalyzer| | --> ex_score
| +------------------+ |
+----------------------+
           |
           v
+----------------------+
| 補正 Layer           |
| +------------------+ |
| | WeatherAdjuster  | | --> weather_adj
| | TideAdjuster     | | --> tide_adj
| | GradeScorer      | | --> grade_adj
| +------------------+ |
+----------------------+
           |
           v
+----------------------+
| 直前情報 Layer       |
| +------------------+ |
| | BeforeInfoScorer | | --> before_bonus
| | CompoundBuff     | | --> compound_adj
| +------------------+ |
+----------------------+
           |
           v
+----------------------+
| スコア統合           |
| total_score = Σ(...)  |
+----------------------+
           |
           v
+----------------------+
| ランキング生成       |
| - old_prediction     | --> [1,2,3,4,5,6]
| - new_prediction     | --> [1,2,3,4,5,6]
| - confidence         | --> A/B/C/D
+----------------------+
           |
           v
+----------------------+
| 階層的確率モデル     |
| (オプション)         |
| - Stage1/2/3予測     |
| - 三連単確率         |
+----------------------+
           |
           v
+----------------------+
| ベッティング判定     |
| - 戦略B条件チェック  |
| - オッズ範囲確認     |
| - 会場風速フィルタ   |
| - 会場コース調整     |
+----------------------+
           |
           v
[出力] BetTarget
  - status: TARGET/EXCLUDED
  - combination: "1-2-3"
  - odds: 35.5
  - bet_amount: 400 (パターンH)
```

---

## 7. 改善履歴

| 日付 | 改善内容 | 効果 |
|-----|---------|------|
| 2025-12-15 | 会場×コース別調整システム実装 | 収支 +1,420円 |
| 2025-12-15 | Stage2/3に相対特徴量追加 | 実験中 |
| 2025-12-14 | 戦略B条件マトリクス最適化 | ROI +4.6pt |
| 2025-12-08 | パターンH複数点買い実装 | 的中率 +5.7pt |
| 2025-12-04 | V1モデル（LightGBM）作成 | AUC Stage2: 0.7423 |
| 2025-11-17 | V0モデル（XGBoost）作成 | 初期版 |

---

## 関連ドキュメント

- [システムアーキテクチャ](SYSTEM_ARCHITECTURE.md)
- [モデル管理ガイド](MODEL_MANAGEMENT.md)
- [開発ワークフロー](DEVELOPMENT_WORKFLOW.md)
- [戦略実装状況](betting_implementation_status.md)
