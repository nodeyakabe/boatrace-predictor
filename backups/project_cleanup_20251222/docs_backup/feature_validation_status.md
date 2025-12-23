# 新機能検証状況レポート

**作成日**: 2025-12-03
**対象機能**: 動的統合 (dynamic_integration) + 進入予測モデル (entry_prediction_model)

---

## 検証結果サマリー

### ✅ 実装は完了している

1. **BeforeInfoScorer**: 直前情報スコアリング機能は正常動作
2. **DynamicIntegrator**: 動的統合ロジックは実装済み
3. **EntryPredictionModel**: 進入予測モデルは実装済み

### ⚠️ 問題が発生している

1. **before_scoreが0になる**: 予測結果にbefore_scoreが反映されていない
2. **高エラー率**: 100レーステストで97%のレースでエラー発生

---

## 詳細調査結果

### 1. BeforeInfoScorerの動作確認

**テスト**: [test_beforeinfo_scorer.py](../test_beforeinfo_scorer.py)

**結果**: ✅ 正常動作

```
race_id: 132764

全艇のbefore_scoreを確認:
1号: total_score=0.17, confidence=0.10, data_completeness=0.86
2号: total_score=-5.00, confidence=0.09, data_completeness=1.00
3号: total_score=-15.17, confidence=0.05, data_completeness=1.00
4号: total_score=-8.33, confidence=0.07, data_completeness=1.00
5号: total_score=17.50, confidence=0.30, data_completeness=1.00 ← 最高スコア
6号: total_score=3.33, confidence=0.12, data_completeness=0.86
```

**評価**: BeforeInfoScorer単体では正しくスコア計算されている

---

### 2. race_predictor.pyでの統合状況

**該当コード**: [src/analysis/race_predictor.py](../src/analysis/race_predictor.py) Line 1479-1540

```python
# BeforeInfoScorerでスコア計算
for pred in predictions:
    pit_number = pred['pit_number']
    pre_score = pred['total_score']  # 既存の総合スコア = PRE_SCORE

    # 直前情報スコアを計算（BeforeInfoScorerが内部でDBから取得）
    beforeinfo_result = self.beforeinfo_scorer.calculate_beforeinfo_score(
        race_id=race_id,
        pit_number=pit_number
    )

    before_score = beforeinfo_result['total_score']  # 0-100点

    # 統合式を適用
    if use_dynamic_integration and integration_weights:
        # 動的統合モード
        final_score = self.dynamic_integrator.integrate_scores(
            pre_score=pre_score,
            before_score=before_score,
            weights=integration_weights
        )
    else:
        # レガシーモード（固定重み）
        final_score = pre_score * 0.6 + before_score * 0.4

    # スコアを更新
    pred['pre_score'] = round(pre_score, 1)  # 統合前のスコアを保存
    pred['total_score'] = round(final_score, 1)  # 最終スコア
    pred['beforeinfo_score'] = round(before_score, 1)
```

**評価**: コード実装は正しい

---

### 3. 実際の予測結果での問題

**テスト**: [debug_single_race.py](../debug_single_race.py)

**結果**: ⚠️ before_scoreが全て0

```
予測結果: 6艇

1位予測: 1号
  total_score: 71.10
  pre_score: 77.70
  before_score: 0.00  ← 問題！

2位予測: 4号
  total_score: 50.70
  pre_score: 55.20
  before_score: 0.00  ← 問題！
```

**問題点**: BeforeInfoScorerでは正しいスコア（0.17, 17.50など）が計算されているのに、race_predictor.predict_race()の結果では全て0になっている

---

### 4. データベース確認

**テスト**: [check_race_details_data.py](../check_race_details_data.py)

**結果**: ✅ 必要なデータは存在

```
race_detailsデータ確認 (race_id: 132764)
データ件数: 6艇

艇  | 展示タイム | ST    | 展示コース | チルト | 重量 | 部品 | 前ST  | 前着 |
 1  |  6.7       |  1.12 |  1         | -0.5   | None | R    |  1.14 |  3   |
 2  |  6.71      |  2.01 |  2         | -0.5   |  1.0 | R    |  2.11 |  3   |
 3  |  6.78      |  3.18 |  3         | -0.5   |  3.0 | R    |  3.16 |  5   |
 4  |  6.71      |  4.07 |  4         | -0.5   |  5.0 | R    |  4.14 |  2   |
 5  |  6.68      |  5.01 |  5         | None   |  3.0 | R    |  5.12 |  2   |
 6  |  6.69      |  6.03 |  6         | -0.5   | None | R    | None  | None |
```

**評価**: race_detailsテーブルには必要なデータが全て存在

---

### 5. feature_flags設定

**ファイル**: [config/feature_flags.py](../config/feature_flags.py)

```python
FEATURE_FLAGS = {
    # Phase 1: 実装完了・動作確認済み
    'dynamic_integration': True,      # 動的合成比
    'entry_prediction_model': True,   # 進入予測モデル

    # Phase 2-3: 未実装または動作未確認 → False
    'lightgbm_ranking': False,
    'hierarchical_predictor': False,
    'shap_explainability': False,
    # ... その他全てFalse
}
```

**評価**: 設定は正しい

---

## 推定される原因

### 仮説1: predict_raceメソッド内でのearly return

race_predictor.py の predict_race メソッド（Line 474開始）において、BeforeInfoScorerの処理（Line 1479）に到達する前に何らかの理由でreturnしている可能性

**確認が必要な箇所**:
- Line 506-507: race_infoが存在しない場合のearly return
- その他のエラーハンドリング

### 仮説2: dynamic_integrationのフラグチェック

use_dynamic_integration フラグがFalseになっている、または integration_weights が None の可能性

**確認が必要な箇所**:
- Line 1495: `if use_dynamic_integration and integration_weights:`

### 仮説3: 例外処理でのサイレント失敗

BeforeInfoScorer.calculate_beforeinfo_score() 内でExceptionが発生し、空のスコア（0点）が返されている可能性

**確認が必要な箇所**:
- beforeinfo_scorer.py Line 554-556: Exception処理

---

## 次のステップ

### 優先度高: 原因特定

1. **デバッグログ追加**
   race_predictor.py の predict_race メソッドにログを追加し、BeforeInfoScorerが呼ばれているか確認

2. **use_dynamic_integration フラグの確認**
   実際の predict_race 実行時に use_dynamic_integration が True かどうか確認

3. **例外ハンドリングの確認**
   BeforeInfoScorer内での例外発生を catch して詳細ログを出力

### 優先度中: テスト拡充

4. **統合テストの実行**
   30レーステスト ([test_feature_detailed.py](../test_feature_detailed.py)) の完了を待つ

5. **手動検証**
   特定の1レースについて、全処理の流れをステップバイステップで確認

### 優先度低: パフォーマンス最適化

6. **DB接続最適化** (別タスク)
   [db_optimization_task.md](./db_optimization_task.md) 参照

---

## 暫定結論

- **実装は完了している**: 動的統合、進入予測モデル、BeforeInfoScorerはすべて実装済み
- **データは存在している**: race_detailsテーブルには必要なデータがある
- **スコア計算は正しい**: BeforeInfoScorer単体では正しくスコアが計算される
- **統合処理に問題**: predict_race メソッド内で before_score が 0 になる原因が不明

**必要なアクション**: デバッグログを追加して、predict_race メソッドの実行フローを詳細にトレースする

---

## 関連ファイル

- [src/analysis/race_predictor.py](../src/analysis/race_predictor.py)
- [src/analysis/beforeinfo_scorer.py](../src/analysis/beforeinfo_scorer.py)
- [src/analysis/dynamic_integration.py](../src/analysis/dynamic_integration.py)
- [config/feature_flags.py](../config/feature_flags.py)
- [test_beforeinfo_scorer.py](../test_beforeinfo_scorer.py)
- [debug_single_race.py](../debug_single_race.py)
- [check_race_details_data.py](../check_race_details_data.py)
