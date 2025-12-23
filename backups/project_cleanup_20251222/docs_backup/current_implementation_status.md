# 現状の実装環境と評価方法

**作成日**: 2025-12-09
**目的**: 今後のテストで混乱しないよう、現状の実装環境と正しい評価方法を明確化

---

## 現状の実装環境

### 戦略A（2025-12-08確立）

**対象**: 信頼度C/D × 高配当条件
**実装箇所**: [src/betting/bet_target_evaluator.py](../src/betting/bet_target_evaluator.py)

#### 購入条件（BET_CONDITIONS）
```python
'C': [
    # C × B1 × 150-200倍: ROI 376.3%
    {'odds_min': 150, 'odds_max': 200, 'c1_rank': ['B1'], ...}
],
'D': [
    # Tier 1: 超高配当（200-300倍、100-150倍など）
    # Tier 2: 中高配当（20-50倍）
    # Tier 3: 堅実（5-10倍）
]
```

#### 2025年バックテスト結果
- 検証期間: 2025年1月～12月
- 総レース数: 16,979レース
- **購入対象: 637レース**（フィルタ適用後）
- **年間収支: +380,070円**
- **ROI: 298.9%**
- 月別: 12ヶ月中9ヶ月でプラス収支（75%）

**検証スクリプト**: `scripts/validate_strategy_a.py`（2025-12-08実行）

---

### 信頼度B改善（2025-12-09実装）

**対象**: 信頼度Bレースのみ
**実装箇所**: [src/analysis/race_predictor.py](../src/analysis/race_predictor.py:862-867)

#### 実装内容
ハイブリッドスコアリング（三連対率ベース + 1着確率ベース）

```python
# 信頼度Bのみハイブリッドスコアリング適用
top_confidence = predictions[0]['confidence'] if predictions else 'E'
if top_confidence == 'B':
    predictions = self._add_top3_scores(predictions, venue_code, race_date)
```

#### 目的
- 2着・3着予測精度の向上
- 戦略Aに上乗せできる収支源の確立

#### 状態
- **実装完了**: 2025-12-09
- **評価未完了**: race_predictionsテーブルの再生成が必要

---

## 重要な注意事項

### 1. 戦略Aと信頼度B改善は独立

```
┌─────────────────────────────────────┐
│ 戦略A（信頼度C/D高配当）            │
│ - 購入条件フィルタあり              │
│ - 年間+38万円確定                   │
│ - 信頼度B改善の影響を受けない      │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 信頼度B改善（ハイブリッド）         │
│ - 全信頼度Bレースの精度向上        │
│ - 戦略Aとは別の収支源              │
│ - 購入条件は今後検討                │
└─────────────────────────────────────┘

最終収支 = 戦略A（+38万円） + 信頼度B（+α万円）
```

### 2. race_predictionsテーブルの状態

#### 現状（2025-12-09 16:00時点）
- 2025年データ: 102,720件
- ハイブリッド実装後生成: **0.8%（864件）のみ**
- 残り99.2%: **ハイブリッド実装前の古いデータ**

#### 影響
古いrace_predictionsを使った分析は**不正確**：
- 今回の分析結果（ROI 84.22%）は信頼できない
- 2025年全データの再生成が必要

---

## 正しい評価方法

### 戦略Aの評価（購入対象フィルタあり）

**目的**: 実際の運用での収支を測定

**手順**:
1. BetTargetEvaluator.evaluate_race()で購入対象判定
2. 購入対象レースのみで的中率・ROI計算
3. オッズ範囲別、信頼度別の詳細分析

**使用スクリプト**:
```bash
python scripts/backtest_final_strategy.py  # 戦略A検証
python scripts/monthly_performance_analysis.py  # 月別分析
```

**条件**:
- BetTargetEvaluatorのBET_CONDITIONS適用
- オッズ範囲: 各Tier定義に従う
- 1コース級別: B1/A1/A2など

---

### 信頼度B改善の評価（全レース対象）

**目的**: ハイブリッドスコアリングの予想精度を測定

**手順**:
1. **必須**: race_predictions再生成（ハイブリッド適用後）
2. 信頼度B全レースで的中率・ROI計算
3. 信頼度C/Dとの比較

**使用スクリプト**:
```bash
# 1. 予想再生成（今晩実行予定）
python scripts/regenerate_predictions_2025.py

# 2. 評価
python scripts/analyze_2025_fast.py  # 高速版
python scripts/analyze_confidence_b_only.py  # 信頼度B詳細
```

**条件**:
- 全信頼度Bレース対象（フィルタなし）
- race_predictions.generated_at >= '2025-12-09'のデータのみ使用
- 信頼度C/Dは従来スコアのまま（比較用）

---

## 今後のテスト時チェックリスト

### 戦略Aをテストする場合

- [ ] BetTargetEvaluatorのBET_CONDITIONS確認
- [ ] 購入対象フィルタが適用されているか確認
- [ ] 購入レース数が600-700レース程度か確認
- [ ] 比較対象: 2025-12-08の結果（+38万円、ROI 298.9%）

### 信頼度B改善をテストする場合

- [ ] race_predictions再生成済みか確認
- [ ] generated_at >= '2025-12-09'のデータを使用しているか確認
- [ ] 信頼度B全レース対象か確認（フィルタなし）
- [ ] 信頼度C/Dとの比較を含めるか確認

### 統合評価する場合

- [ ] 戦略A + 信頼度B の合計収支を計算
- [ ] レース重複がないか確認（信頼度Bと戦略Aの購入対象が重なる場合）
- [ ] 月別の安定性を確認

---

## データファイル参照

### 戦略A検証結果
- `results/FINAL_REPORT_20251208.md`
- `results/strategy_a_monthly_validation_20251208.txt`
- `results/optimal_betting_strategy_20251208.md`

### 信頼度B改善実装
- `docs/hybrid_scoring_implementation.md`
- `docs/confidence_b_analysis_20241209.md`
- `scripts/test_confidence_specific_hybrid.py`

---

## 次回実行予定

**日時**: 2025-12-09 夜
**内容**: 2025年全データでrace_predictions再生成
**所要時間**: 約3-5時間（17,131レース）
**スクリプト**: `scripts/regenerate_predictions_2025.py`（作成予定）

---

**重要**: この資料は今後のテストの混乱を避けるため、更新時は必ず日付と変更内容を記録すること
