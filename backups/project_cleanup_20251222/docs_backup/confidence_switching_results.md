# 信頼度ベースの2着・3着予測戦略切り替え（アプローチ1）

## 実装日
2025-12-18

## 概要

1着予測の確信度に応じて、2着・3着予測方法を動的に切り替える機能を実装。

### 理論的根拠

`docs/rank23_prediction_issue_analysis.md`の分析結果より：

| 条件 | 2着的中率 |
|------|----------|
| 1着予測が正しい場合 | 31.67%（良好） |
| 1着予測が誤りの場合 | 16.93%（ランダム20%以下） |

この差異から、**1着予測の確信度が低い場合は条件付きモデルを使わない方が良い**という仮説に基づく。

## 実装内容

### 1. 信頼度スコアの定義

4つの指標を組み合わせて信頼度を算出：

```python
confidence = (
    0.4 * normalize(score_gap) +       # 1位と2位のスコア差
    0.3 * normalize(top_score_abs) +   # 1位の絶対スコア
    0.2 * odds_agreement_score +       # オッズとの一致度
    0.1 * preset_bonus                 # プリセットパターンへの該当
)
```

### 2. 戦略切り替えロジック

| 信頼度 | 閾値 | 戦略 |
|--------|------|------|
| HIGH | >= 0.7 | 条件付きモデル + 2着専用スコアリング |
| MEDIUM | >= 0.5 | 2着専用スコアリングのみ |
| LOW | < 0.5 | 独立予測（1着を条件としない全艇並列評価） |

### 3. 独立予測モード

低信頼度時は、全艇を並列評価：
- コース別2着・3着基準勝率を使用
- スコアによる補正係数を適用

## 新規ファイル

### `src/ml/confidence_based_rank_predictor.py`

主要クラス：

1. **ConfidenceScore** (dataclass)
   - 信頼度スコアの詳細を保持
   - `score_gap`, `top_score_abs`, `odds_agreement`, `preset_match`, `total_confidence`, `confidence_level`

2. **ConfidenceBasedRankPredictor**
   - 信頼度計算: `calculate_confidence()`
   - 2着予測: `predict_second_place()`
   - 3着予測: `predict_third_place()`
   - 再ランキング: `rerank_predictions()`

3. **ConfidenceBasedIntegrator**
   - 既存システムとの統合
   - 統計情報の収集

## 更新ファイル

### `src/analysis/race_predictor.py`

1. インポート追加
   ```python
   from src.ml.confidence_based_rank_predictor import (
       ConfidenceBasedRankPredictor,
       ConfidenceBasedIntegrator,
       calculate_market_probs_from_odds
   )
   ```

2. `__init__`に予測器を追加
   ```python
   self.confidence_based_predictor = ConfidenceBasedRankPredictor(
       high_threshold=0.7,
       medium_threshold=0.5
   )
   self.confidence_based_integrator = ConfidenceBasedIntegrator(...)
   ```

3. `predict_race()`に信頼度ベース戦略を適用
   ```python
   if is_feature_enabled('confidence_based_switching'):
       predictions = self._apply_confidence_based_switching(predictions, race_id)
   ```

4. `_apply_confidence_based_switching()`メソッドを追加

### `config/feature_flags.py`

```python
'confidence_based_switching': True,  # 信頼度ベース戦略切り替え（アプローチ1）
```

## バックテストスクリプト

### `scripts/test_confidence_switching.py`

テスト内容：
1. Baseline（信頼度ベースなし）との比較
2. 閾値パターンの最適化（A/B/C）
3. 信頼度別の分布と精度分析

閾値パターン：
- パターンA: (high=0.7, medium=0.5) - デフォルト
- パターンB: (high=0.75, medium=0.6)
- パターンC: (high=0.8, medium=0.65)

評価指標：
- ROI（回収率）
- 2着的中率、3着的中率
- 三連単的中率
- 購入数
- 信頼度別の精度

## 予測結果に追加される情報

```python
{
    'confidence_based': True,
    'confidence_score': {
        'score_gap': 0.732,
        'top_score_abs': 0.654,
        'odds_agreement': 0.821,
        'preset_match': 1.0,
        'total_confidence': 0.756,
        'confidence_level': 'high'
    },
    'cb_second_prob': 0.3215,
    'cb_third_prob': 0.2143
}
```

## 既存機能との連携

### アプローチ2（2着専用スコアリング）との統合

- 高信頼度時: アプローチ2の確率を条件付き確率と統合
- 中信頼度時: アプローチ2の確率をそのまま使用
- 低信頼度時: 独立予測を使用

### アプローチ4（オッズ逆算）との統合

- 市場確率の計算にオッズデータを使用
- 信頼度計算のodds_agreementに反映

## 期待される効果

| 指標 | 期待効果 |
|------|----------|
| 2着的中率 | +2-3pt |
| 3着的中率 | +1-2pt |
| 三連単的中率 | +0.5-1pt |
| ROI | 維持または改善 |

## 注意事項

1. **フラグ制御**
   - `confidence_based_switching`フラグでON/OFF可能
   - 効果が見られない場合はOFFにして運用可能

2. **閾値調整**
   - デフォルト: high=0.7, medium=0.5
   - バックテストで最適値を継続検証

3. **パフォーマンス**
   - 信頼度計算は軽量（追加コスト: 約1ms/レース）

## 今後の課題

1. 閾値の継続的な最適化
2. 信頼度計算の重みの調整
3. プリセットパターンの拡充
4. 季節・会場別の閾値調整

## 関連ドキュメント

- `docs/rank23_prediction_issue_analysis.md` - 2着・3着予測問題の分析
- `docs/betting_implementation_status.md` - ベッティング戦略の実装状況
- `config/feature_flags.py` - 機能フラグ設定
