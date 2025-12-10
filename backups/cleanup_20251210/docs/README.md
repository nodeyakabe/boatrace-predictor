# ボートレース予測システム ドキュメント

最終更新: 2025-11-13

## 📚 ドキュメント一覧

このディレクトリには、ボートレース予測システムの開発・運用に関する重要なドキュメントが格納されています。

### 🎯 [PREDICTION_LOGIC_INSIGHTS.md](PREDICTION_LOGIC_INSIGHTS.md)
**予測ロジック構築のための知見集**

今後の予測精度向上のために必要な情報を網羅的にまとめたドキュメント。

**主な内容**:
- 現状のベストモデルの詳細
- 特徴量の有効性評価（★評価付き）
- 予測精度を高めるための戦略
- 特徴量エンジニアリングの推奨事項
- データ品質に関する注意事項
- モデル評価の標準手順
- 実運用に向けた推奨事項
- 今後の実験ロードマップ

**こんな時に読む**:
- 新しい特徴量を追加したい時
- モデルの精度が落ちてきた時
- 投資戦略を見直したい時
- 次に何をすべきか迷った時

---

### 📊 [model_experiments.md](model_experiments.md)
**モデル実験履歴**

これまでに実施した全ての実験を時系列で記録したドキュメント。

**主な内容**:
- 実験#001: Stage2ベースラインモデル（推奨）
- 実験#002: Stage2選手特徴量込みモデル（非推奨）
- 今後の実験予定
- 実験テンプレート

**こんな時に読む**:
- 過去の実験結果を振り返りたい時
- どのモデルが最良だったか確認したい時
- 新しい実験を始める前に参考にしたい時

---

### 📈 [../BACKTEST_COMPARISON_REPORT.md](../BACKTEST_COMPARISON_REPORT.md)
**バックテスト比較レポート**

ベースラインモデルと選手特徴量込みモデルの詳細な比較分析レポート。

**主な内容**:
- 2つのモデルの性能比較
- 確率帯別の的中率分析
- 選手特徴量追加による影響の考察
- 推奨アクション（短期・中期・長期）

**こんな時に読む**:
- 2つのモデルの違いを詳しく知りたい時
- なぜ選手特徴量で精度が下がったのか理解したい時

---

## 🚀 クイックスタート

### 1. 現状のベストモデルを使う

```python
# モデルロード
from src.ml.model_trainer import ModelTrainer
trainer = ModelTrainer(model_dir="models")
trainer.load_model("stage2_baseline_3months.json")

# 予測実行
y_pred_proba = trainer.predict(X_test)

# 高確率レースのみ投資
bet_races = df[y_pred_proba >= 0.8]
```

**期待パフォーマンス**:
- 的中率: 約78%（0.8以上の確率帯）
- 推定ROI: 約480%（仮想オッズ）

---

### 2. 新しいモデルを学習する

```bash
# ベースラインモデル（推奨）
python train_stage2_baseline.py

# 選手特徴量込みモデル
python train_stage2_with_racer_features.py
```

---

### 3. バックテストを実行する

```bash
# ベースラインモデルのバックテスト
python run_backtest_baseline.py

# 選手特徴量込みモデルのバックテスト
python run_backtest_with_racer_features.py
```

---

## 📂 ファイル構造

```
BoatRace/
├── docs/
│   ├── README.md                          # このファイル
│   ├── PREDICTION_LOGIC_INSIGHTS.md       # 予測ロジック知見集
│   └── model_experiments.md               # 実験履歴
├── models/
│   ├── stage2_baseline_3months.json       # ベースラインモデル（推奨）⭐
│   └── stage2_with_racer_features_3months.json  # 選手特徴量込み
├── src/
│   ├── ml/
│   │   ├── dataset_builder.py             # データセット構築
│   │   └── model_trainer.py               # モデル学習・予測
│   └── features/
│       └── precompute_features.py         # 特徴量事前計算
├── train_stage2_baseline.py               # 学習スクリプト（推奨）
├── train_stage2_with_racer_features.py    # 学習スクリプト（選手特徴量込み）
├── run_backtest_baseline.py               # バックテストスクリプト
├── run_backtest_with_racer_features.py    # バックテストスクリプト
└── BACKTEST_COMPARISON_REPORT.md          # 比較レポート
```

---

## 🎓 重要な知見まとめ

### ✅ 効果的な特徴量（重要度順）

1. **コース取り（actual_course）** ★★★★★
   - 1コース取得時の勝率は約50%
   - actual_course_1のダミー変数が最重要

2. **展示タイム（tenji_time）** ★★★★☆
   - 選手の調子とボートの性能を反映
   - 会場別に正規化すると効果的

3. **スタートタイミング（start_timing）** ★★★★☆
   - 0.00〜0.15秒が理想的
   - フライングは大幅な不利

4. **モーター・ボート2連対率** ★★★☆☆
   - 機材性能の指標
   - 節の序盤は信頼性が低い

### ❌ 効果が限定的だった特徴量

5. **選手の過去成績（racer_features）** ★★☆☆☆
   - 直近3〜10戦の成績では効果なし
   - より長期的な指標が必要かも

6. **会場別選手成績（racer_venue_features）** ★★☆☆☆
   - サンプル数が不足
   - 交互作用項が必要

### 🎯 推奨投資戦略

```python
# 戦略1: 高確率帯のみ投資（推奨）
if pred_proba >= 0.8:
    bet_amount = 100
    # 期待的中率: 77.87%
```

```python
# 戦略2: オッズ考慮（将来実装）
expected_value = pred_proba * odds
if expected_value >= 1.2:  # 期待値120%以上
    bet_amount = 100 * (expected_value / 1.2)
```

---

## 📋 次にやるべきこと

### Phase 1: 短期改善（1〜2週間）
- [ ] 交互作用項の追加（actual_course_1 × tenji_time など）
- [ ] 展示タイムの会場別正規化
- [ ] 確率閾値の最適化（0.8 vs 0.85 vs 0.9）

### Phase 2: 中期改善（1〜2ヶ月）
- [ ] 実際のオッズデータを取得してROI再計算
- [ ] モーター性能推移の特徴量追加
- [ ] SHAP値による特徴量重要度分析

### Phase 3: 長期改善（3〜6ヶ月）
- [ ] 天候データの取得と特徴量化
- [ ] LSTMなど深層学習モデルの検証
- [ ] アンサンブル学習の実装

詳細は [PREDICTION_LOGIC_INSIGHTS.md](PREDICTION_LOGIC_INSIGHTS.md) の「8. 今後の実験ロードマップ」を参照。

---

## 🔧 トラブルシューティング

### Q. モデルの的中率が急に下がった
→ [PREDICTION_LOGIC_INSIGHTS.md](PREDICTION_LOGIC_INSIGHTS.md) の「7.2 リスク管理」を参照

### Q. 新しい特徴量を追加したい
→ [PREDICTION_LOGIC_INSIGHTS.md](PREDICTION_LOGIC_INSIGHTS.md) の「4. 特徴量エンジニアリング」を参照

### Q. どのモデルを使えばいいか分からない
→ [model_experiments.md](model_experiments.md) の「実験#001」（ベースラインモデル）を推奨

### Q. 実験結果を記録したい
→ [model_experiments.md](model_experiments.md) の「実験テンプレート」を使用

---

## 📞 サポート

質問や提案がある場合は、以下のドキュメントを参照してください:
- 予測ロジック関連: [PREDICTION_LOGIC_INSIGHTS.md](PREDICTION_LOGIC_INSIGHTS.md)
- 実験履歴: [model_experiments.md](model_experiments.md)
- 比較分析: [../BACKTEST_COMPARISON_REPORT.md](../BACKTEST_COMPARISON_REPORT.md)

---

**最終更新**: 2025-11-13
**次回レビュー予定**: Phase 1完了時
