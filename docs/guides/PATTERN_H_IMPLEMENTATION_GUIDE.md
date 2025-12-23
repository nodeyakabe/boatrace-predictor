# パターンH実装ガイド

**最終更新**: 2025-12-15
**ステータス**: ✅ 実装完了・本番導入済み

---

## 📊 実装概要

パターンH（1-2軸3点傾斜配分）を戦略Bに統合し、年間約1.7万円の収支改善を実現しました。

### 実績比較（2025年バックテスト）

| 指標 | 1点買い | パターンH | 改善 |
|:----:|--------:|---------:|-----:|
| **年間収支** | +49,500円 | **+66,150円** | **+16,650円 (+33.6%)** |
| **ROI** | 125.3% | **126.6%** | +1.2pt |
| **的中率** | 3.5% | **9.2%** | +5.7pt |
| **月間平均的中** | 1.9回 | **5.0回** | +3.1回 |
| **投資額/レース** | 300円 | 400円 | +100円 |

---

## 🎯 パターンHの仕組み

### 買い目構成

```
1レースあたり:
  1-2-3（予測そのまま）    : 200円  ← 本命
  1-2-4（3着を4位に変更）  : 100円  ← 保険①
  1-2-5（3着を5位に変更）  : 100円  ← 保険②
  ─────────────────────────────────
  合計                     : 400円
```

### 設計思想

1. **1着・2着予測の高精度を活用**
   - 信頼度C: 1着的中率46.8%、1着的中時の2着的中率67.3%
   - 信頼度D: 1着的中率33.8%、1着的中時の2着的中率66.0%
   - → **1-2軸は十分に信頼できる**

2. **3着の不確実性をカバー**
   - 3着的中率は20%程度と低い
   - 予測3,4,5位に分散することで的中率を3倍に向上

3. **傾斜配分による効率化**
   - 本命（1-2-3）に200円集中投資
   - 保険（1-2-4, 1-2-5）は各100円
   - オッズ20-50倍のレンジではトリガミリスク極小

---

## 🚀 使用方法

### 1. プログラムでの使用

```python
from src.betting.bet_target_evaluator import BetTargetEvaluator, MultiBetPattern

# パターンH有効化（推奨設定）
evaluator = BetTargetEvaluator(
    use_multi_bet=True,
    multi_bet_pattern=MultiBetPattern.PATTERN_H
)

# レース評価
race_data = {
    'venue_code': 7,
    'entries': [{'pit_number': 1, 'racer_rank': 'A1'}],
}
predictions = {
    'confidence': 'C',
    'old_prediction': [1, 2, 3],
    'new_prediction': [1, 2, 3],
    'full_prediction': [1, 2, 3, 4, 5, 6],  # 1-6位の全予測
}
odds_dict = {
    "1-2-3": 35.0,
    "1-2-4": 42.0,
    "1-2-5": 55.0,
    # ... 他のオッズ
}

target = evaluator.evaluate_race(
    race_data=race_data,
    predictions=predictions,
    odds_data=odds_dict,
    has_beforeinfo=True
)

# 購入対象の場合、複数点買い情報を表示
if target.multi_bet_result:
    for bet in target.multi_bet_result.bets:
        print(f"{bet.combination}: {bet.bet_amount}円（オッズ{bet.odds}倍）")
```

### 2. 日次運用スクリプト

```bash
# 当日の購入推奨レースを表示
python scripts/run_daily_betting_pattern_h.py
```

**出力例**:
```
【1】会場07 5R - 信頼度C / 1CB1
  期待ROI: 158.6%
  買い目:
    1-2-3: 200円（オッズ35.0倍）
    1-2-4: 100円（オッズ42.0倍）
    1-2-5: 100円（オッズ55.0倍）
  投資額計: 400円
```

### 3. バックテスト

```bash
# 2025年データで検証
python scripts/backtest_multi_bet_pattern_h.py
```

---

## 🔧 実装ファイル

### コアモジュール

1. **[src/betting/multi_bet_generator.py](../src/betting/multi_bet_generator.py)**
   - 複数点買いパターン生成クラス
   - パターンH/B/L/I/K対応
   - Opus AIが実装

2. **[src/betting/bet_target_evaluator.py](../src/betting/bet_target_evaluator.py)**
   - 購入対象判定クラス
   - パターンH統合済み（L156-165, L413-436）

### スクリプト

1. **[scripts/run_daily_betting_pattern_h.py](../scripts/run_daily_betting_pattern_h.py)**
   - 日次運用スクリプト
   - 当日の購入推奨レースをリストアップ

2. **[scripts/backtest_multi_bet_pattern_h.py](../scripts/backtest_multi_bet_pattern_h.py)**
   - バックテストスクリプト
   - 2025年データで検証

3. **Opus作成の分析スクリプト群**
   - `scripts/analyze_multi_bet_patterns.py`
   - `scripts/analyze_multi_bet_detailed.py`
   - `scripts/analyze_optimal_multi_bet.py`

---

## 📈 他のパターン

### パターンB（ROI最大: 130.3%）

```python
evaluator = BetTargetEvaluator(
    use_multi_bet=True,
    multi_bet_pattern=MultiBetPattern.PATTERN_B
)
```

- **買い目**: 1-2-3/1-2-4/1-2-5（各100円）
- **合計**: 300円（現行と同じ）
- **ROI**: 130.3%（全パターン中最高）
- **収支**: +55,680円（パターンHより1.2万円低い）

### パターンI（シンプル: 2点買い）

```python
evaluator = BetTargetEvaluator(
    use_multi_bet=True,
    multi_bet_pattern=MultiBetPattern.PATTERN_I
)
```

- **買い目**: 1-2-3（200円）+ 1-2-4（100円）
- **合計**: 300円
- **ROI**: 123.0%
- **収支**: +43,560円

### パターンK（安全重視: MaxDD最小）

```python
evaluator = BetTargetEvaluator(
    use_multi_bet=True,
    multi_bet_pattern=MultiBetPattern.PATTERN_K
)
```

- **買い目**: 1-2-3（150円）+ 1-2-4（100円）+ 2-1-3（50円）
- **合計**: 300円
- **最大ドローダウン**: 33,075円（最小）
- **収支**: +39,995円

---

## ⚠️ 注意事項

### 1. full_prediction必須

複数点買いを利用するには、予測辞書に`full_prediction`（1-6位の全予測）が必要です。

```python
predictions = {
    'confidence': 'C',
    'old_prediction': [1, 2, 3],
    'new_prediction': [1, 2, 3],
    'full_prediction': [1, 2, 3, 4, 5, 6],  # ← これが必須
}
```

`full_prediction`がない場合、自動で補完されますが、正確な予測順位を渡すことを推奨します。

### 2. オッズデータ必須

複数点買いはオッズ情報を使用するため、`odds_data`辞書が必須です。

```python
odds_dict = {
    "1-2-3": 35.0,
    "1-2-4": 42.0,
    "1-2-5": 55.0,
    # ... 全120通りの3連単オッズ
}

target = evaluator.evaluate_race(
    race_data=race_data,
    predictions=predictions,
    odds_data=odds_dict,  # ← これが必須
    has_beforeinfo=True
)
```

### 3. 1点買いへの切り替え

必要に応じて1点買いに戻すことも可能です。

```python
# 1点買いモード
evaluator = BetTargetEvaluator(use_multi_bet=False)
```

---

## 📚 関連ドキュメント

- **[MULTI_BET_ANALYSIS_REPORT.md](MULTI_BET_ANALYSIS_REPORT.md)** - Opus AIによる詳細分析レポート
- **[README.md](../README.md)** - プロジェクト全体概要
- **[残タスク一覧.md](残タスク一覧.md)** - 今後の改善計画

---

## 🎉 まとめ

パターンH実装により:
- ✅ 年間収支が+16,650円改善（+33.6%）
- ✅ 的中率が3.5%→9.2%に向上（+5.7pt）
- ✅ 月間平均的中数が1.9回→5.0回に増加（+3.1回）
- ✅ ROIも125.3%→126.6%に改善（+1.2pt）

**投資額は1レースあたり+100円（300円→400円）のみで、これだけの改善を達成しました。**

---

*最終更新: 2025-12-15*
*作成: Claude Opus 4.5 & Sonnet 4.5*
