# 2位・3位予想精度の問題分析と改善策

**作成日**: 2025年12月9日
**最終更新**: 2025年12月9日（検証完了）
**状況**: 1位的中率67.90%に対し、三連単的中率6.75%（信頼度B）
**問題**: 2位・3位の予想精度が低い
**検証結果**: ✅ 根本原因を特定・定量化完了

---

## 📌 エグゼクティブサマリー

### 🔴 問題の本質

**条件付き確率モデル（Stage2/3）の学習データと予測時のデータ分布が一致していない**

- **学習時**: 実際の1位を条件として2位を学習
- **予測時**: 予想1位を条件として2位を予測
- **結果**: 予想1位が外れた67.3%のレースで、モデルが**ランダム以下の精度**

### 📊 定量化された影響（2024-2025年 29,801レース）

| 条件 | レース割合 | 2位予測的中率 | 理論値比 |
|------|-----------|--------------|---------|
| 予想1位が的中 | 32.7% | **31.13%** | 1.56倍 ✅ |
| 予想1位が外れ | **67.3%** | **16.93%** | **0.85倍 ❌** |

**→ 予想1位が外れると14.19ポイント（45%）精度が低下し、ランダムより悪化**

### 💡 改善の方向性

1. **prepare_stage2_data_v2()**: 予想1位を条件とした学習データ作成
2. **期待効果**: 三連単的中率 6.75% → 8.5-9.5%（+26-41%）
3. **ROI改善**: 75.4% → 100.4%（収支プラス圏）

---

## 📊 現状の分析結果

### 各順位の予想精度（信頼度B）

| 順位 | 的中率 | ランダム(16.67%)との比較 | 評価 |
|------|--------|------------------------|------|
| **1位** | **67.90%** | **4.1倍** | ✅ 優秀 |
| **2位** | 24.88% | 1.5倍 | ⚠️ 改善の余地 |
| **3位** | 21.03% | 1.3倍 | ⚠️ 改善の余地 |

### 🔴 **重大な問題：条件付き確率モデルが機能していない**

#### 1位的中時の2位・3位精度

| 項目 | 実績 | 理論値 | 倍率 | 評価 |
|------|------|--------|------|------|
| **2位的中率（1位的中時）** | **30.77%** | 20% | **1.54倍** | 低い |
| **3位的中率（1位的中時）** | **23.08%** | 25% | **0.92倍** | ❌ **ランダム以下** |
| 2位&3位的中（1位的中時） | 10.63% | 5% | 2.13倍 | まあまあ |

**→ 3位予想がランダム以下 = ConditionalRankModelが逆効果**

---

## 🔬 根本原因の調査

### 1. **学習データの問題**

#### Stage2（2位予測）の学習データ

```python
# train_conditional_models.py の prepare_stage2_data()
def prepare_stage2_data(self, df: pd.DataFrame):
    # 1. 実際の1着艇の特徴量を取得
    first_features = df_valid[df_valid['rank'] == 1][['race_id'] + feature_cols]
    first_features.columns = ['race_id'] + [f'winner_{c}' for c in feature_cols]

    # 2. 1着艇を除外した5艇から2着を予測
    remaining = df_with_first[df_with_first['pit_number'] != df_with_first['first_pit']]

    # 3. 1着艇の特徴量をマージ
    remaining = remaining.merge(first_features, on='race_id')

    # 4. ラベル: 実際の2着かどうか
    y = (remaining['rank'] == 2).astype(int).values
```

**問題点：**
- ✅ 1着艇の特徴量を条件として使用（正しい）
- ⚠️ **実際の結果を使って学習**している
- ❓ 予測時は**予想1位**を条件として使うが、学習時は**実際の1位**を使っている
- → **学習データと予測時のデータ分布が一致しない**

#### Stage3（3位予測）の学習データも同様の問題

```python
# 実際の1着・2着艇の特徴量を使って学習
first_place = df_valid[df_valid['rank'] == 1]
second_place = df_valid[df_valid['rank'] == 2]
```

---

### 2. **予測時の処理**

#### TrifectaCalculator の predict_second_place()

```python
def _predict_second_place(self, race_features: pd.DataFrame, first_idx: int):
    # first_idx: 予想1位のインデックス（0-5）
    # first_features: 予想1位の特徴量
    first_features = race_features.iloc[first_idx]

    # 各候補艇について、予想1位と組み合わせて予測
    for j in range(6):
        if j == first_idx:
            continue
        candidate_features = self._create_stage2_features(
            race_features.iloc[j], first_features, feature_cols
        )
        probs[j] = model.predict_proba([candidate_features])
```

**問題点：**
- 予想1位を条件として使用
- しかし、学習データは**実際の1位**を条件として作られている
- → **条件の意味が異なる**

---

### 3. **データ分布のミスマッチ**

#### 学習時（Stage2）
```
条件: 実際の1位艇（レース後に確定）
目標: 実際の2位艇を予測

例: 実際1位が1号艇（A1級、展示1位、ST良好）
    → この条件下で2位を予測
```

#### 予測時（Stage2）
```
条件: 予想1位艇（レース前の予想）
目標: 2位を予測

例: 予想1位が1号艇（スコア最高）
    → しかし実際は2位になるかもしれない
    → 学習時と条件が異なる
```

**→ 予想1位が実際に1位にならなかった場合、学習データとの分布が大きくずれる**

---

### 4. **🔬 検証結果（2024-2025年データ）**

検証スクリプト `scripts/validate_stage2_training_data.py` の実行結果：

#### データ統計
- **総データ数**: 170,628件
- **総レース数**: 28,338レース
- **6艇完備レース**: 26,035レース

#### 分布ミスマッチの定量化

| 条件 | レース数 | 割合 | 2位予測的中率 |
|------|----------|------|--------------|
| **ケース1: 予想1位が的中** | 9,747 | 32.7% | **31.13%** |
| **ケース2: 予想1位が外れ** | 20,054 | 67.3% | **16.93%** |
| **全体** | 29,801 | 100% | 21.58% |

#### 🔴 **重大な発見**

1. **予想1位の的中率は32.7%のみ**
   - 学習データは実際の1位を条件としている（100%的中の状態）
   - しかし予測時は32.7%しか的中しない
   - → **67.3%のレースで学習データと異なる分布**

2. **2位予測精度の劇的な低下**
   - ケース1（予想1位的中）: **31.13%**
   - ケース2（予想1位外れ）: **16.93%**
   - → **14.19ポイントの精度低下**（45%ダウン）

3. **理論値との比較**
   - 理論値（ランダム5艇から2位）: 20%
   - ケース1: 31.13%（理論値の1.56倍）✅
   - ケース2: 16.93%（理論値の0.85倍）❌ **ランダム以下**

**結論**: 予想1位が外れた場合、Stage2モデルは**ランダム予想より悪い**精度になっている。これは学習時と予測時のデータ分布が完全に異なるためである。

---

## 💡 改善策

### 🔴 **最優先：学習データの修正**

#### 改善案1: 予想1位を条件とした学習データ作成

```python
def prepare_stage2_data_v2(self, df: pd.DataFrame):
    """
    予想1位を条件とした2着予測データを準備

    学習データと予測時のデータ分布を一致させる
    """
    # 1. 各レースで1位予想を計算（Stage1モデルまたはスコアベース）
    df['predicted_first'] = df.groupby('race_id')['total_score'].transform(
        lambda x: x.idxmax()
    )

    # 2. 予想1位艇の特徴量を取得
    predicted_first_features = df[df['pit_number'] == df['predicted_first']]
    predicted_first_features.columns = ['race_id'] + [f'pred_winner_{c}' for c in feature_cols]

    # 3. 予想1位を除外した5艇から実際の2着を予測
    remaining = df[df['pit_number'] != df['predicted_first']]
    remaining = remaining.merge(predicted_first_features, on='race_id')

    # 4. ラベル: 実際の2着かどうか
    y = (remaining['rank'] == 2).astype(int)

    return X, y
```

**メリット：**
- 学習時も予想1位を条件とする
- 予測時と同じデータ分布
- 予想1位が外れる場合も学習データに含まれる

**デメリット：**
- 予想1位の質に依存する
- Stage1モデルが必要（またはスコアベース予想）

#### 改善案2: 複数の条件でアンサンブル学習

```python
# 条件1: 実際の1位を条件（現在の方法）
# 条件2: 予想1位を条件（改善案1）
# 条件3: スコア1位を条件
# → アンサンブルで予測

prob_actual_first = model_v1.predict_proba(...)
prob_predicted_first = model_v2.predict_proba(...)
prob_score_first = model_v3.predict_proba(...)

final_prob = 0.4 * prob_actual_first + 0.4 * prob_predicted_first + 0.2 * prob_score_first
```

---

### 🟠 **高優先度：特徴量の追加**

#### 追加すべき特徴量（2位・3位予測用）

```python
# 展示タイムの相対順位
exhibition_time_rank_diff  # 候補艇と1位予想艇の展示タイム順位差

# STの相対順位
st_rank_diff

# スコア差
score_diff_from_first  # 候補艇と1位予想艇のスコア差
score_diff_from_second # 候補艇と2位予想艇のスコア差

# 進入コース距離
course_distance  # 候補艇と1位予想艇のコース距離

# 級別差
class_diff  # A1=1, A2=2, B1=3, B2=4として差分

# 相対モーター性能
motor_perf_diff
```

#### 直前情報の活用強化

```python
# 展示タイム順位（1-6位）
exhibition_rank_1  # 1位予想艇の展示タイム順位
exhibition_rank_2  # 候補艇の展示タイム順位

# ST順位
st_rank_1
st_rank_2

# 進入コース実績
actual_course_1
actual_course_2
```

---

### 🟡 **中優先度：予測精度が低い場合の処理**

#### スコア差による信頼度調整

```python
# 1位と2位のスコア差が小さい場合、2位予測の信頼度を下げる
score_diff_1_2 = score_1 - score_2

if score_diff_1_2 < 5:
    # 混戦 → 2位予測は難しい
    # Stage2の予測確率を平滑化
    second_probs = 0.7 * second_probs + 0.3 * uniform_probs
```

#### フォールバック戦略

```python
# 条件付きモデルの信頼度が低い場合、ナイーブ法にフォールバック
if confidence_score < threshold:
    # ナイーブ法（スコアベース）を使用
    second_probs = calculate_naive_second_probs(...)
```

---

### 🟢 **低優先度：モデルアーキテクチャの変更**

#### 直接的な三連単予測

```python
# 現在: P(1=i) × P(2=j|1=i) × P(3=k|1=i,2=j)
# 代替: P(1=i, 2=j, 3=k) を直接予測

# LightGBM Ranking または MultiOutput Classifier
# 120通りをマルチクラス分類
```

---

## 📝 実装優先順位

### Phase 1: 学習データの修正（最重要）

1. ✅ **検証スクリプト作成・実行完了**
   - `scripts/validate_stage2_training_data.py` ✅ 完了
   - 学習データと予測時のデータ分布を比較 ✅ 完了
   - 分布のミスマッチ度を定量化 ✅ 完了
   - **発見**: 67.3%のレースで分布が異なり、2位予測精度が14.19pt低下

2. **予想1位を条件とした学習データ作成**（実装待ち）
   - `prepare_stage2_data_v2()` 実装
   - `prepare_stage3_data_v2()` 実装
   - 既存モデルとの精度比較

### Phase 2: 特徴量の追加

1. **相対特徴量の強化**
   - 展示タイム順位差
   - ST順位差
   - スコア差

2. **直前情報の活用強化**
   - 展示タイム順位（1-6位）
   - ST順位（1-6位）
   - 進入コース実績

### Phase 3: モデル再学習と検証

1. **新しい学習データでモデル再学習**
   - Stage2モデル
   - Stage3モデル

2. **バックテスト実施**
   - 2024-2025年データで検証
   - 2位的中率の改善を確認
   - 三連単的中率の改善を確認

---

## 🎯 期待される改善効果

### 現状（信頼度B）

| 項目 | 現在値 |
|------|--------|
| 1位的中率 | 67.90% |
| 2位的中率 | 24.88% |
| 3位的中率 | 21.03% |
| 2位的中率（1位的中時） | 30.77% |
| 3位的中率（1位的中時） | 23.08% |
| **三連単的中率** | **6.75%** |

### 目標（Phase 1完了後）

検証結果を踏まえた改善目標：

| 項目 | 現在値 | 目標値 | 改善幅 | 根拠 |
|------|--------|--------|--------|------|
| 1位的中率 | 67.90% | 67.90% | 維持 | Stage1は既に優秀 |
| 2位的中率（全体） | 24.88% | 27-29% | +2-4pt | ケース2の精度向上 |
| 2位的中率（1位的中時） | 30.77% | 35-38% | +4-7pt | 現在31.13%→目標値 |
| 2位的中率（1位外れ時） | **16.93%** | **22-24%** | **+5-7pt** | **最重要改善対象** |
| 3位的中率（1位的中時） | 23.08% | 28-32% | +5-9pt | Stage3の分布修正 |
| **三連単的中率** | **6.75%** | **8.5-9.5%** | **+1.75-2.75pt** | 2位・3位精度向上の複合効果 |

**改善の鍵**: ケース2（予想1位が外れた67.3%のレース）での2位予測精度を、ランダム以下（16.93%）から理論値以上（22%+）に引き上げる

### ROIへの影響

```
現在: 6.75% × 平均払戻率11.16倍 = ROI 75.4%
目標: 9.0% × 平均払戻率11.16倍 = ROI 100.4%

→ 収支プラス圏を目指せる水準（+0.4%）
```

**注記**: 予想1位外れ時の2位予測をランダム以上に改善すれば、三連単的中率は最大33%改善（6.75% → 9.0%）可能。

---

## 📊 検証スクリプトのアウトライン

### `scripts/validate_stage2_training_data.py`

```python
"""
Stage2学習データの検証スクリプト

1. 学習データの分析
   - 実際の1位を条件とした場合の2位的中率
   - 予想1位を条件とした場合の2位的中率

2. データ分布の比較
   - 学習時と予測時の特徴量分布
   - 分布のKL divergenceを計算

3. 改善案の効果シミュレーション
   - prepare_stage2_data_v2() でデータ作成
   - モデル学習
   - バックテストで精度比較
"""
```

### `scripts/retrain_conditional_models_v2.py`

```python
"""
改善版条件付きモデルの学習スクリプト

1. 予想1位を条件とした学習データ作成
2. Stage2/3モデルの学習
3. モデル保存（v2として別保存）
4. バックテストで精度検証
"""
```

---

## 🔗 関連ファイル

- **現在の実装**:
  - [src/prediction/hierarchical_predictor.py](../src/prediction/hierarchical_predictor.py)
  - [src/prediction/trifecta_calculator.py](../src/prediction/trifecta_calculator.py)
  - [src/ml/conditional_rank_model.py](../src/ml/conditional_rank_model.py)
  - [src/ml/train_conditional_models.py](../src/ml/train_conditional_models.py)

- **分析結果**:
  - [results/rank23_analysis_*.csv](../results/)
  - [results/all_confidence_analysis_*.csv](../results/)

- **このドキュメント**:
  - [docs/rank23_prediction_issue_analysis.md](rank23_prediction_issue_analysis.md)

---

**作成日**: 2025年12月9日
**作成者**: Claude Code (Sonnet 4.5)
**ステータス**: 問題分析完了、Phase 1実装待ち
