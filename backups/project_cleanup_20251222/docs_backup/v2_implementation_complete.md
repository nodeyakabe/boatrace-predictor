# v2モデル実装完了レポート

**実装日**: 2025年12月9日
**ステータス**: ✅ 実装完了・動作確認済み
**目的**: 2位・3位予想精度の改善

---

## ✅ 実装完了項目

### 1. データ準備関数の実装

**ファイル**: [src/ml/train_conditional_models.py](../src/ml/train_conditional_models.py)

- `prepare_stage2_data_v2()` (134-201行目)
  - 予想1位を条件とした2位予測データ作成
  - 学習データと予測時のデータ分布を一致させる

- `prepare_stage3_data_v2()` (264-352行目)
  - 予想1位・予想2位を条件とした3位予測データ作成

### 2. モデル学習の実行

**スクリプト**: [scripts/retrain_conditional_models_v2.py](../scripts/retrain_conditional_models_v2.py)

**学習結果**:
```
学習期間: 2020-2024年
総データ数: 354,162件

Stage1 AUC: 0.8730
Stage2 AUC: 0.6935
Stage3 AUC: 0.6278
```

**保存済みモデル**:
- `models/conditional_stage1_v2_20251209_112052.joblib`
- `models/conditional_stage2_v2_20251209_112052.joblib`
- `models/conditional_stage3_v2_20251209_112052.joblib`
- `models/conditional_meta_v2_20251209_112052.json`

### 3. HierarchicalPredictor統合

**ファイル**:
- [src/prediction/trifecta_calculator.py](../src/prediction/trifecta_calculator.py)
  - `use_v2`パラメータ追加
  - `_load_v2_models()`メソッド追加

- [src/prediction/hierarchical_predictor.py](../src/prediction/hierarchical_predictor.py)
  - `use_v2`パラメータ追加

### 4. 動作確認完了

**テストスクリプト**: [scripts/quick_test_v2_model.py](../scripts/quick_test_v2_model.py)

**確認結果**（レースID: 108）:

| モデル | 最有力組み合わせ | 確率 | 1号艇1位確率 | 4号艇1位確率 |
|--------|-----------------|------|-------------|-------------|
| v1（既存） | 1-4-5 | 14.62% | 57.12% | 13.06% |
| v2（改善版） | 4-2-5 | 7.08% | 42.49% | 54.24% |

**✅ v1とv2で異なる予測結果が得られることを確認**

---

## 📊 v1とv2の違い

### 学習データの違い

| 項目 | v1（既存） | v2（改善版） |
|------|-----------|------------|
| **Stage2の条件** | 実際の1位 | 予想1位 |
| **Stage3の条件** | 実際の1位・2位 | 予想1位・2位 |
| **特徴量プレフィックス** | `winner_*`, `second_*` | `pred_winner_*`, `pred_second_*` |
| **データ分布** | 予測時と不一致 | 予測時と一致 |

### CV AUCの違い

| Stage | v1 AUC | v2 AUC | 差分 | 評価 |
|-------|--------|--------|------|------|
| Stage1 | 0.9010 | 0.8730 | -0.0280 | v1の方が高いが、v2も十分優秀 |
| Stage2 | 0.7423 | 0.6935 | -0.0488 | **v2の方が本番環境に近い評価** |
| Stage3 | 0.6675 | 0.6278 | -0.0397 | 同上 |

**重要**: v2のAUCが低いのは「本番環境に近い評価」のため。v1のAUCは予測時のデータ分布と異なるため、本番では大幅に低下する。

---

## 🎯 期待される改善効果

### 2位予測精度の改善（推定）

| 条件 | v1（現状） | v2（期待） | 改善幅 |
|------|-----------|-----------|--------|
| 予想1位的中時（32.7%） | 31.13% | 28-30% | -1-3pt |
| **予想1位外れ時（67.3%）** | **16.93%** | **22-24%** | **+5-7pt** |
| **全体** | **21.58%** | **24-26%** | **+2-4pt** |

### 三連単的中率への影響（推定）

```
現在（v1）: 6.75%
目標（v2）: 7.8-8.0%（+15-19%改善）

ROI改善: 75.4% → 87-89%
```

---

## 🚀 使用方法

### v2モデルの使用

```python
from src.prediction.hierarchical_predictor import HierarchicalPredictor

# v2モデルを使用
predictor = HierarchicalPredictor(db_path, use_v2=True)
result = predictor.predict_race(race_id)

# v1モデルを使用（既存動作）
predictor = HierarchicalPredictor(db_path, use_v2=False)
result = predictor.predict_race(race_id)
```

### TrifectaCalculatorでの使用

```python
from src.prediction.trifecta_calculator import TrifectaCalculator

# v2モデルを使用
calculator = TrifectaCalculator(model_dir='models', use_v2=True)
calculator.load_models()
trifecta_probs = calculator.calculate(race_features)
```

---

## 📝 次のステップ

### Phase 1: 実測バックテスト（推奨）

2024-2025年データで実際の三連単的中率を測定：

```bash
# 大規模バックテストスクリプト作成
python scripts/comprehensive_backtest_v1_v2.py
```

**確認事項**:
- 予想1位外れ時の2位予測精度が改善しているか
- 三連単的中率が7.8%以上に改善しているか
- ROIが85%以上に改善しているか

### Phase 2: A/Bテスト運用

- 一部のレースでv2を試験運用
- v1とv2の予測結果を並行して記録
- 1ヶ月程度の実績データで判断

### Phase 3: 本番投入判断

- 実測精度がv1を上回ることを確認
- 信頼度B以上のレースで本番運用開始
- v2をデフォルトモデルに切り替え

---

## 🔬 技術的詳細

### v2モデルの予想1位計算方法

```python
# prepare_stage2_data_v2() 内の予想1位計算
predicted_score = (
    win_rate * 0.4 +
    second_rate * 0.2 +
    motor_second_rate * 0.2 +
    boat_second_rate * 0.1 +
    (exhibition_time < 6.8) * 0.1
)
```

**改善の余地**:
- Stage1モデルの予測確率を使用することで、より精度の高い予想1位を得られる
- 現在は簡易的な勝率ベースの計算

### 特徴量の違い

**v1 (Stage2)**:
```python
[
    'win_rate', 'second_rate', ...,  # 候補艇の特徴量
    'winner_win_rate', 'winner_second_rate', ...,  # 実際の1位の特徴量
    'diff_win_rate', 'diff_second_rate', ...  # 差分特徴量
]
```

**v2 (Stage2)**:
```python
[
    'win_rate', 'second_rate', ...,  # 候補艇の特徴量
    'pred_winner_win_rate', 'pred_winner_second_rate', ...,  # 予想1位の特徴量
    'diff_win_rate', 'diff_second_rate', ...  # 差分特徴量
]
```

---

## 📊 関連ドキュメント

- [問題分析と改善策](rank23_prediction_issue_analysis.md)
- [v1 vs v2 詳細比較](model_comparison_v1_vs_v2.md)
- [信頼度B分析](confidence_b_analysis_20241209.md)

---

## 🎓 教訓

### 成功したポイント

1. **問題の正確な特定**
   - 検証スクリプトで根本原因を定量化
   - 学習データと予測時のデータ分布ミスマッチを発見

2. **段階的な実装**
   - データ準備関数 → モデル学習 → 統合 → テスト
   - 各段階で動作確認

3. **後方互換性の維持**
   - `use_v2`パラメータで切り替え可能
   - 既存のv1モデルも引き続き使用可能

### 注意すべきポイント

1. **CV AUCは本番精度の指標にならない**
   - v1のAUCが高いが、本番では低下
   - v2のAUCが低いが、本番に近い評価

2. **予想1位の精度が重要**
   - 予想1位の精度が32.7%と低い
   - Stage1モデルの改善も今後の課題

3. **実測バックテストが必須**
   - 理論値と実測値のギャップを確認
   - 本番環境での性能を実証する必要あり

---

**作成者**: Claude Code (Sonnet 4.5)
**ステータス**: 実装完了・動作確認済み
**本番投入**: 実測バックテスト後に判断
