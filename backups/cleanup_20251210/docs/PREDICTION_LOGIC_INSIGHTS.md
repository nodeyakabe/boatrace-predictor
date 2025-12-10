# 予測ロジック構築のための知見集

最終更新: 2025-11-13

## 目的

このドキュメントは、ボートレース予測システムの精度向上のために、これまでの実験で得られた知見を体系的にまとめたものです。今後の予測ロジック改善の指針として活用してください。

---

## 1. 現状のベストモデル

### Stage2ベースラインモデル（推奨）

**パフォーマンス**:
- AUC: 0.9273
- 的中率: 68.60%
- 推定ROI: 480.19%

**使用特徴量（30個）**:
- 基本レース情報: venue_code, race_number, pit_number
- モーター・ボート情報: motor_number, boat_number, motor_2rate, boat_2rate
- 展示情報: tenji_time, tenji_course
- スタート情報: start_timing, start_course（実際のコース取り）
- 枠番ダミー変数: pit_number_1〜6
- コースダミー変数: actual_course_1〜6
- 派生特徴: pit_course_diff（枠番-コース差）

**強み**:
- シンプルで解釈性が高い
- 過学習リスクが低い
- 基本特徴量が予測に最も重要であることを示唆

**保存場所**: `models/stage2_baseline_3months.json`

---

## 2. 特徴量に関する知見

### 2.1 有効な特徴量

#### A. コース取り（actual_course）
- **重要度**: ★★★★★
- **理由**: ボートレースはインコース有利の競技特性がある
- **活用方法**:
  - actual_course_1（1コース取得）のダミー変数が最重要
  - 枠番とコースの差分（pit_course_diff）も有効
  - 1コース取得時の勝率は約50%と高い

#### B. 展示タイム（tenji_time）
- **重要度**: ★★★★☆
- **理由**: 選手の調子とボートの性能を直接反映
- **注意点**:
  - 展示タイムが記録されていないレースもある（欠損値処理が必要）
  - 会場によって水面特性が異なるため、会場別に正規化すると効果的

#### C. スタートタイミング（start_timing）
- **重要度**: ★★★★☆
- **理由**: スタート巧者は有利なレース展開を作りやすい
- **活用方法**:
  - フライング（負の値）は大幅な不利
  - 0.00〜0.15秒が理想的なスタート
  - 0.15秒を超えると不利になる傾向

#### D. モーター・ボート2連対率
- **重要度**: ★★★☆☆
- **理由**: 機材性能の指標
- **注意点**:
  - モーター・ボートは定期的に入れ替わる
  - 節の序盤は2連対率が当てにならない（サンプル不足）
  - 整備による性能変化を考慮する必要あり

### 2.2 効果が限定的だった特徴量

#### E. 選手の過去成績（racer_features）
- **重要度**: ★★☆☆☆
- **検証結果**: 的中率が2.9%低下（68.60% → 65.70%）
- **考察**:
  - 選手の実力は既に「展示タイム」「スタートタイミング」に反映されている
  - 直近3〜10戦の成績は短期的すぎて情報が不足
  - より長期的な指標（直近30戦、50戦）が必要かもしれない

#### F. 会場別選手成績（racer_venue_features）
- **重要度**: ★★☆☆☆
- **検証結果**: 同じく効果が見られず
- **考察**:
  - 会場特性は選手ごとに大きく異なるが、サンプル数が不足
  - 特定の会場で極端に強い選手を見つけるには有効かもしれない
  - 交互作用項（venue_code × venue_win_rate）が必要

---

## 3. 予測精度を高めるための戦略

### 3.1 確率帯別の信頼性

ベースラインモデルの確率帯別的中率:

| 確率帯 | レース数 | 的中率 | 信頼性 | 推奨戦略 |
|--------|---------|--------|--------|----------|
| 0.8-1.0 | 1,777 | 77.87% | ★★★★★ | **積極投資** |
| 0.6-0.8 | 450 | 35.78% | ★★☆☆☆ | 避ける |
| 0.4-0.6 | 219 | 43.38% | ★★★☆☆ | 慎重に |
| 0.2-0.4 | 38 | 42.11% | ★☆☆☆☆ | 避ける |

**重要な発見**:
- **0.8以上の高確率帯は信頼できる**（77.87%の的中率）
- 0.6-0.8の中確率帯は的中率が急落（35.78%）→ モデルの不確実性が高い
- **投資戦略**: 0.8以上のレースのみに投資することで、期待値を最大化できる

### 3.2 ROI最適化の方針

**現状の仮想ROI**: 480.19%（全レース・平均オッズ7倍で算出）

**最適化案**:

#### A. 確率閾値戦略
```python
# 高確率レースのみに投資
if pred_proba >= 0.8:
    bet_amount = 100  # 投資
else:
    bet_amount = 0    # 見送り
```
- **期待効果**: 的中率77.87%を維持しつつ、低確率レースの損失を回避
- **リスク**: 投資機会が全体の71.6%（1,777/2,484レース）に限定される

#### B. オッズ考慮戦略
```python
# 高確率 × 高オッズのレースを優先
expected_value = pred_proba * odds
if expected_value >= threshold:
    bet_amount = 100 * (expected_value / threshold)
```
- **前提**: 実際のオッズデータが必要
- **期待効果**: 低オッズ（1.1〜1.5倍）の人気薄レースを避けることで、ROIを向上
- **リスク**: モデルが低オッズレースに過剰適合している可能性

#### C. ケリー基準
```python
# 資金管理の最適化
kelly_fraction = (pred_proba * odds - 1) / (odds - 1)
bet_amount = bankroll * kelly_fraction
```
- **期待効果**: 資金を効率的に運用し、破産リスクを最小化
- **注意**: モデルの予測確率が正確であることが前提

---

## 4. 特徴量エンジニアリングの推奨事項

### 4.1 すぐに試すべき改善策

#### A. 交互作用項の追加
```python
# 例1: コース × 展示タイム
df['course1_tenji'] = df['actual_course_1'] * df['tenji_time']

# 例2: コース × 選手勝率（将来実装時）
df['course1_winrate'] = df['actual_course_1'] * df['recent_win_rate_10']

# 例3: 会場 × モーター2連対率
df['venue_motor_quality'] = df['venue_code'] * df['motor_2rate']
```

**期待効果**: コースや会場特性と他の特徴量の相乗効果を捉える

#### B. 展示タイムの会場別正規化
```python
# 会場別に展示タイムを標準化
df['tenji_time_normalized'] = df.groupby('venue_code')['tenji_time'].transform(
    lambda x: (x - x.mean()) / x.std()
)
```

**期待効果**: 会場間の展示タイム基準の違いを吸収

#### C. スタートタイミングの非線形変換
```python
# スタートタイミングの質的評価
df['start_quality'] = pd.cut(
    df['start_timing'],
    bins=[-1.0, 0.0, 0.10, 0.15, 1.0],
    labels=['フライング', '完璧', '良好', '遅れ']
)
# ワンホットエンコーディング
df = pd.get_dummies(df, columns=['start_quality'])
```

**期待効果**: スタートタイミングの非線形な影響を正確に捉える

### 4.2 中期的に検討すべき改善策

#### D. モーター・ボート性能の推移
```python
# モーター2連対率の最近3節の推移
motor_trend = calculate_motor_performance_trend(motor_number, race_date)
```

**データ要件**: 過去の節ごとのモーター成績データ

#### E. 選手の調子指標
```python
# 直近5戦の順位の標準偏差（安定性）
racer_stability = df['recent_ranks_std_5']

# 連勝中・連敗中フラグ
df['on_winning_streak'] = (df['recent_rank_1'] == 1) & (df['recent_rank_2'] == 1)
```

**データ要件**: racer_featuresテーブルの拡張

#### F. 天候・水面条件
```python
# 風速・風向き、気温、波高など
df['wind_speed'] = fetch_weather_data(venue_code, race_date)
df['wave_height'] = fetch_wave_data(venue_code, race_date)
```

**データ要件**: 外部APIからの天候データ取得

### 4.3 長期的に検討すべき改善策

#### G. 深層学習モデル
```python
# LSTMによる時系列予測
# 選手の過去N戦の成績をシーケンスとして扱う
model = LSTM(input_shape=(seq_length, num_features))
```

**メリット**: 選手の調子の波を時系列データとして捉えられる
**デメリット**: 学習に大量のデータと計算リソースが必要

#### H. アンサンブル学習
```python
# 複数モデルのブレンディング
pred_final = (
    0.5 * pred_baseline +
    0.3 * pred_with_racer_features +
    0.2 * pred_lstm
)
```

**メリット**: 各モデルの強みを活かして予測精度を向上
**デメリット**: 複雑性が増し、運用コストが上がる

---

## 5. データ品質に関する注意事項

### 5.1 欠損値の扱い

**現状の課題**:
- 展示タイム（tenji_time）: 一部レースで欠損
- スタートタイミング（start_timing）: レース前は取得不可
- モーター・ボート2連対率: 節の序盤は信頼性が低い

**推奨対処法**:
```python
# 平均値補完（現状）
X = df[feature_cols].fillna(df[feature_cols].mean())

# より高度な補完（今後検討）
from sklearn.impute import KNNImputer
imputer = KNNImputer(n_neighbors=5)
X = imputer.fit_transform(df[feature_cols])
```

### 5.2 データ漏洩のチェックポイント

**重要**: 予測時点で利用不可能なデータを特徴量に使わないこと

| 特徴量 | 利用可否 | 理由 |
|--------|---------|------|
| 展示タイム | ✅ OK | レース前日に公開 |
| スタートタイミング | ❌ NG | レース後にしか分からない（学習時のみ使用可） |
| 選手の過去成績 | ✅ OK | 「レース当日より前」のデータのみ使用 |
| レース結果（result_rank） | ❌ NG | 目的変数（予測対象） |

**racer_featuresのデータ漏洩チェック**:
```python
# precompute_features.pyの計算ロジック（正しい実装）
query = """
    SELECT rank
    FROM results res
    JOIN races r ON res.race_id = r.id
    WHERE racer_number = ?
      AND r.race_date < ?  -- 重要: レース当日より前のデータのみ
    ORDER BY r.race_date DESC
    LIMIT 10
"""
```

現状の実装は正しく、データ漏洩は発生していません。

---

## 6. モデル評価の標準手順

### 6.1 評価指標の優先順位

**1位: ROI（投資収益率）**
- 最終的な利益を測る唯一の指標
- 実際のオッズデータを使って算出すること

**2位: レース単位の的中率**
- 実運用での体感的な精度
- 目標: 70%以上

**3位: AUC（Area Under the Curve）**
- モデルの予測能力を測る統計的指標
- 過学習の検出に有用

**4位: Log Loss**
- 予測確率の精度を測る指標
- 確率較正（calibration）の評価に有用

### 6.2 バックテストの実施手順

```python
# 1. データ分割（時系列を考慮）
train_data = df[df['race_date'] < '2024-04-01']
test_data = df[df['race_date'] >= '2024-04-01']

# 2. モデル学習
model.fit(X_train, y_train)

# 3. 予測
y_pred_proba = model.predict(X_test)

# 4. レース単位で最高確率の艇を選択
race_predictions = test_data.groupby('race_id').apply(
    lambda x: x.loc[x['pred_proba'].idxmax()]
)

# 5. 的中率計算
hit_rate = (race_predictions['is_win'] == 1).mean()

# 6. ROI計算（実際のオッズを使用）
total_return = (race_predictions['is_win'] * race_predictions['odds'] * 100).sum()
total_bet = len(race_predictions) * 100
roi = (total_return / total_bet - 1) * 100
```

### 6.3 モデル比較の記録方法

新しいモデルを試すたびに、以下の情報を記録してください:

```markdown
## モデル名: [descriptive_name]
- 日付: YYYY-MM-DD
- 特徴量数: XX個
- 特徴量リスト: [feature1, feature2, ...]
- ハイパーパラメータ: {param1: value1, ...}
- Train AUC: X.XXXX
- Test AUC: X.XXXX
- 的中率: XX.XX%
- ROI: XXX.XX%
- 備考: [特記事項]
```

**保存場所**: `docs/model_experiments.md`

---

## 7. 実運用に向けた推奨事項

### 7.1 予測システムのアーキテクチャ

```
┌─────────────────┐
│  データ収集     │ ← 毎日自動実行（前日の展示情報など）
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 特徴量計算      │ ← racer_features, motor_featuresなど
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ モデル予測      │ ← stage2_baseline_3months.json
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 投資判断        │ ← 確率 >= 0.8 のレースのみ投資
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 結果記録        │ ← 的中率・ROIをトラッキング
└─────────────────┘
```

### 7.2 リスク管理

#### A. 資金管理
- 1レースあたりの投資額を資金の1〜5%以内に抑える
- 連敗時は投資額を減らす（マーチンゲール法は避ける）

#### B. モデルの信頼性監視
- 週次で的中率をモニタリング
- 的中率が60%を下回ったらモデルを再評価

#### C. データ更新
- 月次でモデルを再学習（最新データを反映）
- 年次でモデルアーキテクチャを見直し

---

## 8. 今後の実験ロードマップ

### Phase 1: 短期改善（1〜2週間）
- [ ] 交互作用項の追加と評価
- [ ] 展示タイムの会場別正規化
- [ ] 確率閾値戦略の最適化（0.8, 0.85, 0.9で比較）

### Phase 2: 中期改善（1〜2ヶ月）
- [ ] 実際のオッズデータを取得してROI再計算
- [ ] モーター・ボート性能推移の特徴量追加
- [ ] より長期的な選手成績（直近30戦、50戦）の評価
- [ ] SHAP値による特徴量重要度の詳細分析

### Phase 3: 長期改善（3〜6ヶ月）
- [ ] 天候データの取得と特徴量化
- [ ] LSTMなど深層学習モデルの検証
- [ ] アンサンブル学習の実装
- [ ] 6ヶ月〜1年間の長期バックテスト

---

## 9. 参考情報

### 関連ファイル
- ベースラインモデル: `models/stage2_baseline_3months.json`
- 学習スクリプト: `train_stage2_baseline.py`
- バックテストスクリプト: `run_backtest_baseline.py`
- 比較レポート: `BACKTEST_COMPARISON_REPORT.md`

### 重要な関数・クラス
- `DatasetBuilder.build_training_dataset()`: 学習データ構築
- `FeaturePrecomputer.compute_racer_features()`: 選手特徴量計算
- `ModelTrainer.train()`: モデル学習
- `ModelTrainer.predict()`: 予測実行

### データベーステーブル
- `races`: レース基本情報
- `entries`: 出走表
- `results`: レース結果
- `racer_features`: 選手特徴量（事前計算）
- `racer_venue_features`: 会場別選手特徴量（事前計算）

---

## 10. まとめ

### 現状の最良戦略
1. **Stage2ベースラインモデル**（30特徴量）を使用
2. 予測確率 **0.8以上のレースのみ**に投資
3. 期待的中率: 約78%
4. 資金管理を徹底（1レース = 資金の1〜5%）

### 次に試すべきこと
1. 交互作用項の追加（特に `actual_course_1 × tenji_time`）
2. 実際のオッズデータを使ったROI検証
3. 確率閾値の最適化（0.8 vs 0.85 vs 0.9）

### 長期的な目標
- 的中率70%以上を安定的に維持
- 実運用でROI 200%以上（年間）を達成
- 予測システムの完全自動化

---

**最終更新**: 2025-11-13
**次回レビュー予定**: Phase 1完了時
