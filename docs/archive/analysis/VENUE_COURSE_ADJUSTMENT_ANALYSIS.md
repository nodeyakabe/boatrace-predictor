# 会場×コース別 ポイント調整分析

## 概要

2024-2025年の全レースデータから各会場のコース別勝率を分析し、全国平均との差分に基づいてデバフ/バフポイントを算出するシステムを実装した。

### 目的
- パターンH戦略の精度向上
- 会場特性を考慮した精緻な買い目選定
- 単純除外から段階的調整への移行による機会損失削減

## 分析結果

### 全体平均勝率（2024-2025年）

| コース | 勝率 |
|--------|------|
| 1コース | 57.87% |
| 2コース | 12.84% |
| 3コース | 12.32% |
| 4コース | 10.16% |
| 5コース | 6.01% |
| 6コース | 1.91% |

### 会場×コース別 調整ポイント

調整ロジック: **勝率差分1%につき1pt調整**（最大±20pt）

#### インが弱い会場（1コース勝率が平均より低い）

| 会場 | 1コース勝率 | 差分 | 調整 |
|------|-------------|------|------|
| 戸田 | 46.15% | -11.72% | **-12pt** |
| 平和島 | 46.29% | -11.58% | **-12pt** |
| 江戸川 | 49.18% | -8.69% | **-9pt** |
| 鳴門 | 50.10% | -7.77% | **-8pt** |
| 桐生 | 52.88% | -4.99% | -5pt |

#### インが強い会場（1コース勝率が平均より高い）

| 会場 | 1コース勝率 | 差分 | 調整 |
|------|-------------|------|------|
| 徳山 | 67.06% | +9.19% | **+9pt** |
| 大村 | 66.17% | +8.30% | **+8pt** |
| 下関 | 63.47% | +5.60% | **+6pt** |
| 宮島 | 62.40% | +4.53% | +5pt |

### 全会場調整マップ

```
会場     | 1コース | 2コース | 3コース | 4コース | 5コース | 6コース
---------|---------|---------|---------|---------|---------|--------
桐生     |   -5pt  |   -1pt  |   +2pt  |   +2pt  |   +2pt  |    0pt
戸田     |  -12pt  |   +3pt  |   +4pt  |   +3pt  |   +1pt  |   +1pt
江戸川   |   -9pt  |   +6pt  |   +1pt  |   +2pt  |    0pt  |    0pt
平和島   |  -12pt  |   +4pt  |   +3pt  |   +1pt  |   +2pt  |   +2pt
多摩川   |   -3pt  |    0pt  |    0pt  |   +1pt  |   +1pt  |   +1pt
浜名湖   |   -2pt  |    0pt  |   +2pt  |    0pt  |   +1pt  |    0pt
蒲郡     |   +4pt  |   -3pt  |   -1pt  |   +1pt  |   -2pt  |    0pt
常滑     |   +3pt  |   -1pt  |   -2pt  |    0pt  |    0pt  |   -1pt
津       |   +3pt  |   -1pt  |   -2pt  |   -1pt  |   +1pt  |    0pt
三国     |    0pt  |    0pt  |   +1pt  |   -1pt  |    0pt  |    0pt
びわこ   |   +1pt  |    0pt  |    0pt  |   +1pt  |   -1pt  |   -1pt
住之江   |   +4pt  |   -1pt  |   -1pt  |   -1pt  |    0pt  |   -1pt
尼崎     |   +4pt  |   -3pt  |   +1pt  |    0pt  |   -1pt  |   -1pt
鳴門     |   -8pt  |   +2pt  |   +2pt  |   +2pt  |   +2pt  |    0pt
丸亀     |   +1pt  |   +1pt  |    0pt  |   -2pt  |    0pt  |    0pt
児島     |   +4pt  |   -1pt  |   -2pt  |   -1pt  |   -1pt  |    0pt
宮島     |   +5pt  |   -2pt  |   -2pt  |   -2pt  |   +1pt  |    0pt
徳山     |   +9pt  |   -2pt  |   -3pt  |   -2pt  |   -2pt  |    0pt
下関     |   +6pt  |   -2pt  |   -1pt  |   -2pt  |   -1pt  |    0pt
若松     |    0pt  |   +1pt  |   -3pt  |   +1pt  |    0pt  |    0pt
芦屋     |   +1pt  |   -1pt  |   -1pt  |   +1pt  |    0pt  |    0pt
福岡     |   +2pt  |   +1pt  |   +4pt  |   -3pt  |   -3pt  |   -1pt
唐津     |   -2pt  |   +3pt  |   -1pt  |    0pt  |   -1pt  |    0pt
大村     |   +8pt  |   -2pt  |   -1pt  |   -3pt  |   -1pt  |   -1pt
```

## バックテスト結果

### 検証条件
- 期間: 2024年1月〜2025年12月
- 対象: パターンH（信頼度C/D、オッズ30-50倍）
- ベース賭け金: 1-2-3:200円、1-2-4:100円、1-2-5:100円

### パラメータ最適化結果

| スキップ閾値 | バフ閾値 | 2024収支 | 2025収支 | 合計収支 | 改善額 |
|--------------|----------|----------|----------|----------|--------|
| -12pt | 10pt | -255,720円 | -77,700円 | -333,420円 | **+8,580円** |
| -10pt | 10pt | -255,720円 | -77,700円 | -333,420円 | +8,580円 |
| -8pt | 10pt | -257,120円 | -76,520円 | -333,640円 | +8,360円 |
| 調整なし | - | -263,300円 | -78,700円 | -342,000円 | 基準 |

### 最適パラメータ

- **スキップ閾値**: -12pt（これ以下の調整値でスキップ）
- **バフ閾値**: 10pt（これ以上で増額）
- **改善効果**: +8,580円/2年

### 調整値別ROI（2025年）

| 調整値 | レース数 | 的中数 | ROI |
|--------|----------|--------|-----|
| -2pt | 116 | 17 | **133.0%** |
| +2pt | 279 | 25 | **133.5%** |
| +6pt | 99 | 5 | 79.8% |
| +9pt | 43 | 1 | 27.9% |

**発見**: 調整値-2pt〜+2ptの範囲で最もROIが高い傾向がある。

## 実装詳細

### ファイル構成

```
config/
  venue_course_adjustments.py     # 調整設定ファイル

src/betting/
  venue_course_adjuster.py        # VenueCourseAdjusterクラス
  bet_target_evaluator.py         # BetTargetEvaluator（統合済み）

scripts/
  analysis/
    analyze_venue_course_performance.py  # 分析スクリプト
  backtest_pattern_h_with_venue_course_adjustment.py  # バックテスト

data/
  venue_course_analysis.json      # 分析結果JSON
```

### 使用方法

#### 1. 調整ポイント取得

```python
from config.venue_course_adjustments import get_adjustment

# 戸田の1コース調整
adj = get_adjustment('02', 1)  # -12
```

#### 2. VenueCourseAdjusterクラス

```python
from src.betting.venue_course_adjuster import VenueCourseAdjuster

adjuster = VenueCourseAdjuster(enabled=True)

# 調整適用
result = adjuster.apply_adjustment_with_details(
    base_score=50.0,
    venue_code='02',  # 戸田
    course=1
)
print(result.adjusted_score)  # 38.0
print(result.reason)  # "戸田は1コース勝率が平均より低い（-12pt）"
```

#### 3. BetTargetEvaluatorでの使用

```python
from src.betting.bet_target_evaluator import BetTargetEvaluator

evaluator = BetTargetEvaluator(
    enable_venue_course_adjustment=True,
    venue_course_adjustment_scale=1.0
)

# 評価時に自動適用
target = evaluator.evaluate_race(race_data, predictions, odds_data)
print(target.venue_course_adjustment)  # 調整情報
```

## 活用ガイドライン

### 推奨設定

1. **保守的運用**: 調整機能は有効化するが、スキップは行わない
   ```python
   enable_venue_course_adjustment=True
   # スキップ閾値は使用しない
   ```

2. **積極的運用**: -12pt以下でスキップ、+10pt以上で増額
   ```python
   adjustment_threshold=-12
   buff_threshold=10
   ```

### 注意事項

1. **風速フィルターとの併用**
   - 会場コース調整は風速フィルターとは独立して動作
   - 両方を有効化することで多角的なリスク管理が可能

2. **過学習リスク**
   - 2年間のデータに基づく調整のため、過去の傾向が将来に適用される保証はない
   - 定期的な再分析を推奨（年1回程度）

3. **効果の限定性**
   - バックテストでの改善効果は+8,580円/2年と限定的
   - 主な価値は「インが極端に弱い会場」での損失回避

## 今後の改善案

1. **信頼度×会場コース調整の組み合わせ分析**
   - 信頼度Cと信頼度Dで調整効果が異なる可能性

2. **風速との複合条件**
   - 強風時のコース特性変動を考慮

3. **季節変動の考慮**
   - 水温変化によるコース特性の変動

4. **2着3着予測への適用**
   - 現在は1着予測のみに適用

## 更新履歴

- 2025-12-15: 初版作成
  - 2024-2025年データから会場×コース別調整ポイント算出
  - VenueCourseAdjusterクラス実装
  - BetTargetEvaluator統合
  - バックテスト実施
