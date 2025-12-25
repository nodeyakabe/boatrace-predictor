# 予測ロジック構成

**最終更新**: 2025-12-25

---

## 概要：3層アーキテクチャ

```
【第1層】戦略B - 順位予測
    ↓ ExtendedScorer（スコアリング）
    ↓ HierarchicalPredictor（信頼度A-E判定）

【第2層】フィルターC - 購入判定
    ↓ BetTargetEvaluator（信頼度×オッズ×級別で判断）

【第3層】パターンH - 買い目生成
    ↓ MultiBetGenerator（1-2軸3点買い: 200円/100円/100円）
```

---

## 第1層：順位予測（戦略B）

### 5層予測パイプライン

```
【Layer 1】基本スコア
    ├─ GradeScorer: 級別スコア（A1/A2/B1/B2）
    ├─ MotorAnalyzer: モーター2連率
    ├─ RacerAnalyzer: 選手成績・勝率
    └─ StatisticsCalculator: コース別統計
           ↓
【Layer 2】拡張スコア（ExtendedScorer）
    ├─ 展示タイム順位
    ├─ ST（スタートタイミング）順位
    └─ 直近成績トレンド
           ↓
【Layer 3】環境補正
    ├─ WeatherAdjuster: 風向き×風速補正
    ├─ TideAdjuster: 潮位補正
    └─ VenueCourseAdjuster: 会場×コース調整（144パターン）
           ↓
【Layer 4】直前情報パターン
    ├─ BeforeInfoScorer: 展示×ST複合パターン
    ├─ CompoundBuffSystem: 複合バフシステム
    └─ KimariteFlowPredictor: 決まり手展開予測
           ↓
【Layer 5】AI統合
    ├─ HierarchicalPredictor: 階層的条件確率モデル
    ├─ PairwiseScorer: ペアワイズ相対スコアリング
    └─ LightGBMモデル（Stage1/2/3）
           ↓
【出力】1着〜6着の順位予測 + 信頼度（A〜E）
```

### 主要ファイル

| ファイル | 役割 |
|---------|------|
| `src/analysis/race_predictor.py` | 予測エンジン統合ハブ |
| `src/analysis/extended_scorer.py` | 拡張スコアリング |
| `src/analysis/hierarchical_predictor.py` | 階層的確率モデル |
| `src/analysis/beforeinfo_scorer.py` | 直前情報スコアリング |
| `src/prediction/kimarite_flow_predictor.py` | 決まり手展開予測 |
| `src/ml/pairwise_scorer.py` | ペアワイズスコアリング |

### 信頼度計算

| 信頼度 | 条件 | 2025年1着精度 |
|:------:|:-----|:-------------:|
| **A** | スコア差大、パターン強適合 | 72.99% |
| **B** | 中高信頼 | 65.60% |
| **C** | 中信頼 | 46.01% |
| **D** | スコア接近、低信頼 | 23.1% |

---

## 第2層：購入判定（フィルターC）

### BetTargetEvaluator

**ファイル**: `src/betting/bet_target_evaluator.py`

購入条件は [BET_CONDITIONS.md](../presets/BET_CONDITIONS.md) 参照

### 判定フロー

```
入力: 信頼度 + オッズ + 1コース級別 + 会場 + モーター2連率
           ↓
1. 信頼度チェック（A/B/C/D別条件）
           ↓
2. 1コース級別チェック（A1/A2/B1/B2）
           ↓
3. オッズ範囲チェック（条件別に異なる）
           ↓
4. 会場フィルターチェック（条件により適用）
           ↓
5. モーター条件チェック（40%+など）
           ↓
6. 風速・会場除外チェック
           ↓
出力: TARGET / CANDIDATE / EXCLUDED
```

---

## 第3層：買い目生成（パターンH）

### MultiBetGenerator

**ファイル**: `src/betting/multi_bet_generator.py`

```python
# パターンH: 収支最大化
bet_structure = {
    '1-2-3': 200円,  # 予測通り
    '1-2-4': 100円,  # 3着を4位予測に変更
    '1-2-5': 100円,  # 3着を5位予測に変更
}
# 合計: 400円/レース
```

---

## 有効な機能フラグ一覧

**ファイル**: `config/feature_flags.py`

### コア機能（常時有効）

| フラグ | 効果 | 有効化日 |
|-------|------|---------|
| `hierarchical_predictor` | 階層的条件確率モデル | - |
| `lightgbm_ranking` | LightGBMランキング | - |
| `before_pattern_bonus` | 直前パターンボーナス（B+9.5pt, C+8.3pt） | - |
| `negative_patterns` | ネガティブパターン除外（+2.0%） | 2025-12-11 |

### 効果検証済み機能

| フラグ | 効果 | 有効化日 |
|-------|------|---------|
| `ab_rank_special_betting` | **+17.2pt（最大効果）** | 2025-12-19 |
| `kimarite_flow_prediction` | **+4.1pt** | 2025-12-20 |
| `makuri_risk_adjustment` | **+4.1pt** | 2025-12-20 |
| `pairwise_scoring` | 2着+7.3pt, 3着+3.9pt | 2025-12-19 |
| `second_place_specialized` | +6.8pt | 2025-12-18 |
| `motor_capsizing_penalty` | モーター転覆ペナルティ | 2025-12-19 |
| `negative_pattern_filter` | マイナスROIパターン除外 | 2025-12-21 |
| `upset_pattern_filter` | 穴狙いパターン | 2025-12-21 |

### 無効化済みフラグ（不採用）

| フラグ | 理由 | 無効化日 |
|-------|------|---------|
| `monte_carlo_simulation` | 1着-8.5pt悪化 | 2025-12-19 |
| `rank23_odds_calibration` | 2025年で効果消失 | 2025-12-18 |
| `forward_mover_filter` | ab_rank ONで-7.6pt | 2025-12-20 |
| `condition_factor` | -9.5pt悪化 | 2025-12-20 |
| `third_place_specialized_scorer` | 未統合・効果なし | 2025-12-20 |

---

## 階層的予測モデル（Stage1/2/3）

### モデル構成

| Stage | 役割 | AUC | 特徴量数 |
|:-----:|:-----|:---:|:--------:|
| **Stage1** | 1着予測 | 0.9010 | 17 |
| **Stage2** | 2着予測（1着条件付き） | 0.7423 | 51 |
| **Stage3** | 3着予測（1-2着条件付き） | 0.6675 | 85 |

### 三連単確率計算

```
P(i-j-k) = P(i=1着) × P(j=2着|i=1着) × P(k=3着|i=1着,j=2着)
```

---

## 直前情報パターン

### 1着予測用パターン

| パターン | 条件 | 倍率 |
|---------|------|------|
| `pre1_st1` | PRE1位 & ST1位 | 1.411 |
| `pre1_ex1` | PRE1位 & 展示1位 | 1.286 |
| `pre1_ex1_3_st1_3` | PRE1位 & 展示1-3位 & ST1-3位 | 1.328 |

### 2着予測用パターン

| パターン | 条件 | 倍率 |
|---------|------|------|
| `pre2_3_ex1_2` | PRE2-3位 & 展示1-2位 | 1.084 |
| `pre2_ex1_3_st1_3` | PRE2位 & 展示1-3位 & ST1-3位 | 1.081 |

---

## 会場×コース調整

### イン強会場（1コース有利）

| 会場 | 1コース勝率 | 調整 |
|------|:-----------:|:----:|
| 徳山(18) | 66.41% | +9pt |
| 大村(24) | 65.80% | +8pt |
| 下関(19) | 62.61% | +6pt |

### イン弱会場（1コース不利）

| 会場 | 1コース勝率 | 調整 |
|------|:-----------:|:----:|
| 戸田(02) | 45.87% | -12pt |
| 平和島(04) | 46.18% | -12pt |
| 江戸川(03) | 48.22% | -9pt |

---

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [BET_CONDITIONS.md](../presets/BET_CONDITIONS.md) | 購入条件・プリセット一覧 |
| [YEARLY_PERFORMANCE.md](../performance/YEARLY_PERFORMANCE.md) | 年度別成績 |
| [REJECTED_IDEAS.md](../improvement_attempts/REJECTED_IDEAS.md) | 不採用案一覧 |
| [TEST_RESULTS.md](../performance/TEST_RESULTS.md) | テスト結果・構成 |

---

*最終更新: 2025-12-25*
