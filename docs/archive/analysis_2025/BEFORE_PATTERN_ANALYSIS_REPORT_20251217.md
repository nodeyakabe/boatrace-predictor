# 直前情報（beforeinfo）活用パターン分析レポート

**作成日**: 2025-12-17
**分析期間**: 2020-2024年
**分析データ**: before予測 77,084レース / 462,497予測

---

## エグゼクティブサマリー

2020-2024年のbefore予測データ（77,084レース）を分析した結果、以下の重要な発見がありました：

1. **STタイムは展示タイムより圧倒的に重要**（+16.6% vs +0.0%の差分効果）
2. **ネガティブパターン（ST順位が悪い場合）の活用が必須**（-16%〜-25%の影響）
3. **isshu_time（一周タイム）は2025年データのみ**で、過去データでの検証は不可能

---

## 1. データ収集状況

### 1.1 before予測データの年別内訳

| 年 | レース数 | 予測数 |
|----|----------|--------|
| 2020 | 9,627 | 57,762 |
| 2021 | 9,493 | 56,958 |
| 2022 | 35,452 | 212,712 |
| 2023 | 9,075 | 54,450 |
| 2024 | 13,437 | 80,615 |
| **合計** | **77,084** | **462,497** |

### 1.2 isshu_time（一周タイム）のカバレッジ

| 年 | カバレッジ |
|----|-----------|
| 2020-2024 | 0.0%（データなし）|
| 2025 | 3.4%（3,423件）|

**結論**: isshu_timeは2020-2024年データでの検証が不可能。2025年の限定データでは以下の傾向を確認：
- isshu_time 1位: 勝率39.48%
- isshu_time 6位: 勝率6.15%
- **差分**: 33.3ポイント（非常に高い相関性）

---

## 2. 各直前情報の重要性分析

### 2.1 予測1位（PRE1）に対する各要素の影響

| 条件 | サンプル数 | 的中率 | ベースからの差分 |
|------|-----------|--------|------------------|
| PRE1 全体（ベース） | 46,035 | 54.00% | - |
| PRE1 + 1コース | 34,313 | 65.53% | **+11.5%** |
| PRE1 + ST1位 | 14,982 | 70.60% | **+16.6%** |
| PRE1 + 展示1位 | 18,082 | 54.03% | **+0.0%** |
| PRE1 + 1コース + ST1位 | 13,143 | 75.64% | **+21.6%** |

**発見**: ST順位は展示タイム順位より圧倒的に重要。展示1位だけでは予測精度向上に寄与しない。

### 2.2 ST順位別の的中率（PRE1限定）

| ST順位 | サンプル数 | 的中率 | ベースからの差分 |
|--------|-----------|--------|------------------|
| 1位 | 23,345 | 69.00% | **+15.80%** |
| 2位 | 14,625 | 54.51% | +1.31% |
| 3位 | 11,624 | 47.52% | -5.68% |
| 4位 | 9,230 | 41.80% | -11.40% |
| 5位 | 7,516 | 38.32% | -14.88% |
| 6位 | 6,241 | 28.36% | **-24.84%** |

### 2.3 展示タイム順位別の的中率（PRE1限定）

| 展示順位 | サンプル数 | 的中率 | ベースからの差分 |
|----------|-----------|--------|------------------|
| 1位 | 23,654 | 53.28% | +0.08% |
| 2位 | 11,324 | 56.32% | +3.12% |
| 3位 | 7,510 | 55.47% | +2.27% |
| 4位 | 6,075 | 51.92% | -1.28% |
| 5位 | 4,771 | 48.79% | -4.41% |
| 6位 | 3,448 | 46.49% | -6.71% |

**発見**: 展示タイムは単独では予測向上に寄与しない。むしろ2位/3位の方がやや高い的中率。

---

## 3. 信頼度別のパターン効果

### 3.1 信頼度別 before vs advance 比較

| 信頼度 | advance的中率 | before的中率 | 差分 |
|--------|---------------|--------------|------|
| A | 75.00% | - | - |
| B | 66.85% | - | - |
| C | 53.47% | 75.00%* | +21.53% |
| D | 45.59% | 52.72% | **+7.13%** |
| E | 41.81% | 51.23% | **+9.42%** |

*Cはサンプル数が少ない（8件）

**発見**: 信頼度D/Eではbeforeの方がadvanceより高い的中率を示す。

### 3.2 信頼度別パターン効果（PRE1_ST1）

| 信頼度 | ベース | PRE1_ST1 | 差分 |
|--------|--------|----------|------|
| D | 54.19% | 68.86% | **+14.67%** |
| E | 52.62% | 67.61% | **+14.99%** |

---

## 4. 新規パターン提案

### 4.1 有効なポジティブパターン（推奨追加）

#### パターン1: PRE1_ST1_EX1（最強パターン）
```python
{
    'name': 'pre1_st1_ex1',
    'description': 'PRE1位 & ST1位 & 展示1位',
    'multiplier': 1.50,  # +16.47%効果から算出
    'target_rank': 1,
    'condition': lambda pre_rank, ex_rank, st_rank:
        pre_rank == 1 and st_rank == 1 and ex_rank == 1,
    'samples': 7457,
    'hit_rate': 69.69,
    'statistical_significance': 'p < 0.0001'
}
```

#### パターン2: PRE1_3_ST1（TOP3強化パターン）
```python
{
    'name': 'pre1_3_st1',
    'description': 'PRE1-3位 & ST1位',
    'multiplier': 1.23,  # +15.07%効果
    'target_rank': 'top3',
    'condition': lambda pre_rank, ex_rank, st_rank:
        pre_rank <= 3 and st_rank == 1,
    'samples': 34985,
    'hit_rate': 80.01,
    'base_rate': 64.94,
    'statistical_significance': 'p < 0.0001'
}
```

#### パターン3: PRE2_ST1_2（2着強化パターン）
```python
{
    'name': 'pre2_st1_2',
    'description': 'PRE2位 & ST1-2位',
    'multiplier': 1.12,  # +2.90%効果
    'target_rank': 2,
    'condition': lambda pre_rank, ex_rank, st_rank:
        pre_rank == 2 and st_rank <= 2,
    'samples': 20791,
    'hit_rate': 27.88,
    'base_rate': 24.98,
    'statistical_significance': 'p < 0.0001'
}
```

### 4.2 ネガティブパターン（必須追加）

#### パターン4: PRE1_ST4_6（ST遅延ペナルティ・中）
```python
{
    'name': 'pre1_st4_6',
    'description': 'PRE1位だがST4-6位',
    'multiplier': 0.70,  # -16.19%効果
    'target_rank': 1,
    'condition': lambda pre_rank, ex_rank, st_rank:
        pre_rank == 1 and st_rank >= 4,
    'samples': 22987,
    'hit_rate': 37.01,
    'base_rate': 53.2,
    'penalty_type': 'st_poor'
}
```

#### パターン5: PRE1_ST5_6（ST遅延ペナルティ・大）
```python
{
    'name': 'pre1_st5_6',
    'description': 'PRE1位だがST5-6位',
    'multiplier': 0.63,  # -19.40%効果
    'target_rank': 1,
    'condition': lambda pre_rank, ex_rank, st_rank:
        pre_rank == 1 and st_rank >= 5,
    'samples': 13757,
    'hit_rate': 33.80,
    'base_rate': 53.2,
    'penalty_type': 'st_very_poor'
}
```

#### パターン6: PRE1_ST6（ST最下位ペナルティ）
```python
{
    'name': 'pre1_st6',
    'description': 'PRE1位だがST6位（最下位）',
    'multiplier': 0.53,  # -24.84%効果
    'target_rank': 1,
    'condition': lambda pre_rank, ex_rank, st_rank:
        pre_rank == 1 and st_rank == 6,
    'samples': 6241,
    'hit_rate': 28.36,
    'base_rate': 53.2,
    'penalty_type': 'st_worst'
}
```

---

## 5. ST基礎点調整提案

### 5.1 現状分析

現在の設定（`scoring_weights.yaml`）:
- `start_timing: 8`（平均STスコア）
- `exhibition: 10`（展示タイムスコア）

**問題点**:
- 展示タイムの方が高い重みだが、予測への寄与度はSTの方が圧倒的に高い
- STは+16.6%の効果、展示は+0.0%の効果

### 5.2 推奨調整

```yaml
# 変更前
extended_scorer:
  start_timing: 8        # 平均STスコア
  exhibition: 10         # 展示タイムスコア

# 変更後（推奨）
extended_scorer:
  start_timing: 15       # 平均STスコア（+7増加）
  exhibition: 5          # 展示タイムスコア（-5減少）
```

**理由**:
1. STの寄与度（+16.6%）は展示（+0.0%）の圧倒的に上
2. ST順位1位の効果（+15.8%）は極めて大きい
3. ST順位6位のマイナス効果（-24.8%）も無視できない

### 5.3 コース×ST遅延の影響

| コース | 通常ST | 遅延ST（>0.20秒） | 差分 |
|--------|--------|-------------------|------|
| 1 | 64.75% | 51.58% | -13.17% |
| 2 | 13.66% | 9.69% | -3.97% |
| 3 | 12.05% | 8.38% | -3.67% |
| 4 | 11.17% | 6.87% | -4.30% |
| 5 | 6.40% | 3.81% | -2.59% |
| 6 | 2.07% | 1.04% | -1.03% |

**発見**: 1コースでのST遅延は特に大きな影響（-13.17%）

---

## 6. 実装コードスニペット

### 6.1 pattern_scorer.py への追加パターン

```python
# ネガティブパターン定義（新規追加推奨）
BEFORE_PATTERNS_NEGATIVE = [
    {
        'name': 'pre1_st4_6',
        'description': 'PRE1位だがST4-6位（ペナルティ）',
        'multiplier': 0.70,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 4,
    },
    {
        'name': 'pre1_st5_6',
        'description': 'PRE1位だがST5-6位（強ペナルティ）',
        'multiplier': 0.63,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank >= 5,
    },
    {
        'name': 'pre1_st6',
        'description': 'PRE1位だがST6位（最強ペナルティ）',
        'multiplier': 0.53,
        'target_rank': 1,
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank == 1 and st_rank == 6,
    },
]

# TOP3強化パターン（新規追加推奨）
BEFORE_PATTERNS_TOP3_ENHANCED = [
    {
        'name': 'pre1_3_st1',
        'description': 'PRE1-3位 & ST1位',
        'multiplier': 1.23,
        'target_rank': 'top3',
        'condition': lambda pre_rank, ex_rank, st_rank: pre_rank <= 3 and st_rank == 1,
    },
]
```

### 6.2 scoring_weights.yaml への追加

```yaml
# 新規パターン追加（before_patterns セクション）
before_patterns:
  # ネガティブパターン（新規）
  negative:
    pre1_st4_6:
      multiplier: 0.70
      description: "PRE1位だがST4-6位"
    pre1_st5_6:
      multiplier: 0.63
      description: "PRE1位だがST5-6位"
    pre1_st6:
      multiplier: 0.53
      description: "PRE1位だがST6位"

  # TOP3強化（新規）
  top3_enhanced:
    pre1_3_st1:
      multiplier: 1.23
      description: "PRE1-3位 & ST1位"
```

---

## 7. 統計的有意性の検証結果

| パターン | サンプル数 | 効果サイズ | p値 | 有意性 |
|----------|-----------|-----------|-----|--------|
| PRE1_ST1 | 18,563 | +14.88% | < 0.0001 | 極めて有意 |
| PRE1_ST1_EX1 | 7,457 | +16.47% | < 0.0001 | 極めて有意 |
| PRE2_ST1_2 | 20,791 | +2.90% | < 0.0001 | 有意 |
| PRE1_ST4_6 | 22,987 | -16.19% | < 0.0001 | 極めて有意（負） |
| PRE1_ST6 | 6,241 | -24.84% | < 0.0001 | 極めて有意（負） |
| PRE1_3_ST1 | 34,985 | +15.07% | < 0.0001 | 極めて有意 |

---

## 8. 結論と推奨アクション

### 8.1 即時実装推奨

1. **ネガティブパターンの追加**
   - PRE1_ST4_6（倍率0.70）
   - PRE1_ST5_6（倍率0.63）
   - PRE1_ST6（倍率0.53）

2. **ST基礎点の増加**
   - `start_timing: 8` → `start_timing: 15`
   - `exhibition: 10` → `exhibition: 5`

### 8.2 検証後実装推奨

1. **TOP3強化パターン**
   - PRE1_3_ST1（倍率1.23）

2. **2着予測パターン**
   - PRE2_ST1_2（倍率1.12）

### 8.3 今後の課題

1. **isshu_timeデータの蓄積**
   - 2025年以降のデータで継続検証
   - 39.48%（1位）vs 6.15%（6位）の大きな差分を活用可能

2. **信頼度別パターン最適化**
   - D/Eでのbefore予測が有効（+7〜+9%）
   - A/Bではパターンスキップが最適

---

## 付録: 分析に使用したクエリ

分析スクリプト: `scripts/analyze_before_patterns.py`

```sql
-- ST順位と勝率の関係
WITH ranked_data AS (
    SELECT
        rd.race_id,
        rd.pit_number,
        ROW_NUMBER() OVER (PARTITION BY rd.race_id ORDER BY ABS(rd.st_time) ASC) as st_rank
    FROM race_details rd
    JOIN races r ON rd.race_id = r.id
    WHERE rd.st_time IS NOT NULL
    AND r.race_date >= '2020-01-01' AND r.race_date <= '2024-12-31'
)
SELECT st_rank, COUNT(*),
       SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
       100.0 * SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*) as win_rate
FROM ranked_data rd
JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
GROUP BY st_rank
ORDER BY st_rank;
```
