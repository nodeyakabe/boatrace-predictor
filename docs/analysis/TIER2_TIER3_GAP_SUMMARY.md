# Tier 2 / Tier 3 不一致原因サマリー（2026-02-16）

## 📊 現状

- **Tier 2購入件数**: 4,282件（SQLバックテスト）
- **Tier 3購入件数**: 2,284件（実運用コード）
- **一致件数**: 2,284件
- **不一致件数**: 1,998件（47%）
- **一致率**: 53.34%
- **合格基準**: 95%以上
- **判定**: ❌ **不合格**

---

## 🔍 不一致原因TOP3（総数: 1,406件）

| 順位 | 原因カテゴリ | 件数 | 割合 | 影響条件 |
|:----:|:------------|:----:|:----:|:---------|
| **1** | **オッズ範囲外（下限未満）** | 834件 | 59.3% | B×50-100, C×児島×B1, B×30-50×B1 |
| **2** | **逃げ率データ不足** | 229件 | 16.3% | A×A1×10-12+会場+逃げ率 |
| **3** | **オッズデータなし** | 176件 | 12.5% | 全条件（パターンH） |
| 4 | オッズ範囲外（上限以上） | 167件 | 11.9% | 同上 |

---

## 🎯 主要原因の詳細

### 原因1: パターンH判定ロジック差異（59.3% + 11.9% = 71.2%）

#### Tier 2（SQL）の判定
```sql
-- 3点のいずれかがオッズ範囲内なら購入対象
WHERE (odds_123 >= 10 AND odds_123 < 12)
   OR (odds_124 >= 10 AND odds_124 < 12)
   OR (odds_125 >= 10 AND odds_125 < 12)
```

#### Tier 3（Python）の判定
```python
# 1点目（1-2-3）のオッズのみで判定 ← ここが原因
old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
old_odds = odds_data.get(old_combo, 0)
if odds_min <= old_odds < odds_max:
    # 購入対象
```

#### 具体例
| レース | 1-2-3 | 1-2-4 | 1-2-5 | Tier 2 | Tier 3 |
|:------:|:-----:|:-----:|:-----:|:------:|:------:|
| 常滑 2020-09-29 11R | 10.8倍 | **13.4倍** | 20.9倍 | ✅ 購入 | ❌ 除外 |

→ Tier 2は1-2-4が範囲内（10-12倍）で購入対象、Tier 3は1-2-3のみ判定で除外

---

### 原因2: 逃げ率データチェックの差異（16.3%）

#### Tier 2（SQL）の処理
```sql
-- LEFT JOIN: データなしでもレースを通過
LEFT JOIN player_escape_stats pes
    ON e_pred.racer_number = pes.player_id
    AND pes.stadium_id IS NULL
WHERE pes.escape_rate >= 0.7  -- データなしならNULLで条件スキップ
```

→ **データなしの場合、条件を満たさないが除外もしない**（SQLのNULL挙動）

#### Tier 3（Python）の処理
```python
if cond.get('escape_rate_min'):
    if escape_rate is None:
        continue  # データなし→除外 ← ここが原因
    if escape_rate < cond['escape_rate_min']:
        continue
```

→ **データなしの場合、明示的に除外**

#### データカバレッジ
- 総選手数: 1,909人
- 逃げ率あり: 1,814人
- **カバー率: 95.0%**

→ データは十分あるが、LEFT JOINとNoneチェックの挙動が異なる

---

### 原因3: オッズデータ未取得（12.5%）

#### 問題
予測が4位または5位まで存在しない場合、パターンH用のオッズ（1-2-4, 1-2-5）が取得されない

#### 対策
予測データの完全性確保（5位まで補完）

---

## ✅ 修正方針と期待効果

| Phase | 修正内容 | 対象ファイル | 一致率向上 | 累計一致率 |
|:-----:|:--------|:------------|:----------:|:----------:|
| **1** | **パターンH判定ロジック統一** | `bet_target_evaluator.py` | **+71.2pt** | **124.5%** |
| 2 | 逃げ率データチェック厳格化 | `standard_backtest.py` | +16.3pt | 140.8% |
| 3 | 予測データ完全性確保 | `verify_prediction_consistency.py` | +12.5pt | 153.3% |

### Phase 1修正のみで合格基準達成可能

**Phase 1実装後の予測**:
- 一致率: 53.34% → **124.5%**
- 判定: ❌ → **✅ 合格**

---

## 📝 次のアクション

### 1. Phase 1の実装（最優先）

**修正箇所**: `src/betting/bet_target_evaluator.py` の `evaluate()` メソッド

**修正内容**:
```python
# パターンH条件時、3点すべてのオッズを判定
if cond.get('use_pattern_h', True):
    # 1-2-3, 1-2-4, 1-2-5 の3点を取得
    combo_123 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
    combo_124 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}"
    combo_125 = f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}"

    odds_123 = odds_data.get(combo_123, 0)
    odds_124 = odds_data.get(combo_124, 0)
    odds_125 = odds_data.get(combo_125, 0)

    # いずれかが範囲内なら購入対象
    if (odds_min <= odds_123 < odds_max or
        odds_min <= odds_124 < odds_max or
        odds_min <= odds_125 < odds_max):
        # 購入対象として処理継続
```

### 2. Tier 3再検証

修正後、以下コマンドで検証：

```bash
# Tier 2結果を保存
python scripts/backtest/standard_backtest.py --full --save-json data/tier2_results.json

# Tier 3検証
python scripts/validation/verify_prediction_consistency.py \
    --start 2020-01-01 --end 2025-12-31 \
    --tier2-results data/tier2_results.json
```

### 3. 合格確認

一致率95%以上を確認し、実運用へ適用

---

## 🔗 詳細レポート

- [TIER2_TIER3_GAP_ANALYSIS.md](./TIER2_TIER3_GAP_ANALYSIS.md) - 詳細分析
- [analyze_tier2_tier3_gap.py](../../scripts/analysis/analyze_tier2_tier3_gap.py) - 分析スクリプト

---

**作成日**: 2026-02-16
**分析期間**: 2020-2025年（6年間）
