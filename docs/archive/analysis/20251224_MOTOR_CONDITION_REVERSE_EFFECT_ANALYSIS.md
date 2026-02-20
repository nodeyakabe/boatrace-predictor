# モーター40%+条件の逆効果分析レポート

**作成日**: 2025-12-24
**分析対象**: 2025年データ（before予測）
**目的**: なぜC×A2、C×B1でモーター40%+が逆効果になるのかを解明し、実装推奨を提示

---

## 📊 提示された効果データ（再掲）

### 改善効果があるパターン

| 条件 | ベースROI | +モーター40% | 改善幅 | サンプル |
|:-----|:------:|:----------:|:-----:|:------:|
| A × B1 × モーター40%+ | 1630% | 2748% | **+1118pt** | - |
| D × A1 × モーター40%+ | 1565% | 2020% | **+456pt** | - |
| D × B1 × モーター40%+ | 1959% | 2331% | **+372pt** | - |
| B × B1 × モーター40%+ | 1525% | 1812% | **+287pt** | - |
| A × A2 × モーター40%+ | 1617% | 1898% | **+282pt** | - |

### 逆効果のパターン（注目！）

| 条件 | ベースROI | +モーター40% | 改善幅 | サンプル |
|:-----|:------:|:----------:|:-----:|:------:|
| **C × A2 × モーター40%+** | 1745% | 1356% | **-390pt** | - |
| **C × B1 × モーター40%+** | 1717% | 1547% | **-169pt** | - |
| B × A2 × モーター40%+ | 1702% | 1640% | -62pt | - |

---

## 🔍 逆効果の仮説と分析

### 仮説1: 既存条件との干渉（会場フィルター）

#### 現在のC条件（実装済み）
```python
'C': [
    {
        'odds_min': 20, 'odds_max': 30,
        'c1_rank': ['B1'],  # B1級限定
        'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17],
        'expected_roi': 144.8,
        'paper_trade': False,  # 本番運用
    },
]
```

**会場フィルター対象**: 唐津、徳山、多摩川、平和島、津、丸亀、常滑、大村、若松、宮島

#### **仮説**: 会場フィルター × モーター40%+の組み合わせで過剰フィルターになっている

**検証ポイント**:
1. C×B1の会場フィルターはモーター性能が「すでに高い」会場に絞り込んでいる可能性
2. さらにモーター40%+を追加すると、**サンプル数が激減**し、統計的信頼性が低下
3. **高モーター率×会場フィルター**は偶然の高ROIを拾っている可能性

#### **調査すべきデータ**:
```sql
-- C×B1の会場フィルター対象会場でのモーター率分布
SELECT
    venue_name,
    AVG(motor_second_rate) as avg_motor_rate,
    COUNT(*) as sample_count
FROM races r
JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
JOIN venue_data vd ON r.venue_code = vd.venue_code
WHERE r.venue_code IN ('23', '18', '05', '04', '09', '15', '08', '24', '20', '17')
  AND e.racer_rank = 'B1'
  AND r.race_date >= '2025-01-01'
GROUP BY venue_name
ORDER BY avg_motor_rate DESC;
```

---

### 仮説2: モーター率の分布バイアス

#### **仮説**: C×A2、C×B1は「低モーター率でも勝つパターン」を拾っている

**ロジック**:
1. 信頼度C（低信頼度）× A2/B1（中級）= 高オッズ狙い
2. **モーター率が低くても勝てる展開**（まくり、差し、荒れるレース）を拾っている
3. モーター40%+でフィルターすると、**逃げ型の堅いレース**のみに絞られ、C条件の本質（穴狙い）を失う

**確認すべきデータ**:
```sql
-- C×A2、C×B1の的中レースにおけるモーター率分布
SELECT
    CASE
        WHEN e.motor_second_rate >= 40 THEN 'motor_40+'
        WHEN e.motor_second_rate >= 30 THEN 'motor_30-40'
        ELSE 'motor_under_30'
    END as motor_range,
    COUNT(*) as hit_count,
    AVG(p.amount) as avg_payout
FROM race_predictions rp
JOIN races r ON rp.race_id = r.id
JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
JOIN results res ON r.id = res.race_id AND res.pit_number = 1 AND res.rank = '1'
JOIN payouts p ON r.id = p.race_id AND p.bet_type = 'trifecta'
WHERE rp.confidence = 'C'
  AND e.racer_rank IN ('A2', 'B1')
  AND r.race_date >= '2025-01-01'
  AND r.race_date < '2025-12-01'
GROUP BY motor_range
ORDER BY motor_range;
```

**期待される結果**:
- C条件の的中レースは**モーター率30-40%帯が多い**
- モーター40%+に絞ると、的中パターンの多くを除外してしまう

---

### 仮説3: オッズ帯との相性

#### 現在のC条件: 20-30倍

**仮説**: 20-30倍のオッズ帯では、モーター40%+は「過剰な信頼」を生み、オッズが下がる

**メカニズム**:
1. モーター40%+ → 人気が集中 → オッズ低下
2. 20-30倍を狙っているのに、実際は**15-20倍に下がっている**可能性
3. 結果として、期待値が悪化

**確認すべきデータ**:
```sql
-- C×A2×モーター40%+のオッズ分布
SELECT
    CASE
        WHEN o.odds < 20 THEN 'under_20'
        WHEN o.odds BETWEEN 20 AND 30 THEN '20-30'
        WHEN o.odds BETWEEN 30 AND 50 THEN '30-50'
        ELSE '50+'
    END as odds_range,
    COUNT(*) as sample_count,
    AVG(o.odds) as avg_odds
FROM race_predictions rp
JOIN races r ON rp.race_id = r.id
JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
JOIN trifecta_odds o ON r.id = o.race_id
WHERE rp.confidence = 'C'
  AND e.racer_rank = 'A2'
  AND e.motor_second_rate >= 40
  AND r.race_date >= '2025-01-01'
GROUP BY odds_range
ORDER BY odds_range;
```

**期待される結果**:
- モーター40%+を追加すると、オッズ20-30倍の件数が**減少**
- 実際のオッズは15-20倍に集中している

---

### 仮説4: サンプルサイズの問題（統計的信頼性）

#### **仮説**: 逆効果は統計的ノイズ（サンプル不足）

**確認すべきデータ**:
```sql
-- C×A2、C×B1でのモーター40%+のサンプル数
SELECT
    rp.confidence,
    e.racer_rank,
    CASE WHEN e.motor_second_rate >= 40 THEN 'motor_40+' ELSE 'motor_other' END as motor_cond,
    COUNT(*) as sample_count
FROM race_predictions rp
JOIN races r ON rp.race_id = r.id
JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
WHERE rp.confidence = 'C'
  AND e.racer_rank IN ('A2', 'B1')
  AND r.race_date >= '2025-01-01'
  AND r.race_date < '2025-12-01'
GROUP BY rp.confidence, e.racer_rank, motor_cond
ORDER BY e.racer_rank, motor_cond;
```

**判定基準**:
- サンプル数 < 50件 → 統計的信頼性なし（過学習リスク高）
- サンプル数 50-100件 → 注意が必要
- サンプル数 >= 100件 → 統計的に一定の信頼性

---

## 🧪 検証すべき追加分析

### 1. 既存条件との干渉チェック

```python
# 疑似コード: C×B1×会場フィルター vs C×B1×モーター40%+
conditions = [
    {'filter': 'venue_filter', 'venues': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17]},
    {'filter': 'motor_40+', 'motor_min': 40},
    {'filter': 'both', 'venues': [...], 'motor_min': 40},
]

for cond in conditions:
    backtest_2025(confidence='C', c1_rank='B1', **cond)
```

**期待される結果**:
- 会場フィルター単独: ROI 144.8%（既知）
- モーター40%+単独: ROI ???%
- **両方適用**: ROI 低下（過剰フィルター）

---

### 2. モーター率別の決まり手分析

```sql
-- モーター率別の決まり手傾向
SELECT
    CASE
        WHEN e.motor_second_rate >= 40 THEN 'motor_40+'
        ELSE 'motor_other'
    END as motor_cond,
    res.kimarite,
    COUNT(*) as count
FROM races r
JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
JOIN results res ON r.id = res.race_id AND res.pit_number = 1 AND res.rank = '1'
JOIN race_predictions rp ON r.id = rp.race_id
WHERE rp.confidence = 'C'
  AND e.racer_rank IN ('A2', 'B1')
  AND r.race_date >= '2025-01-01'
  AND r.race_date < '2025-12-01'
GROUP BY motor_cond, res.kimarite
ORDER BY motor_cond, count DESC;
```

**期待される仮説**:
- motor_40+: 「逃げ」が多い（堅いレース）
- motor_other: 「まくり」「差し」が多い（荒れるレース）
- C条件は**荒れるレース**で高ROIを稼いでいる可能性

---

## 💡 暫定結論と推奨アクション

### ❌ 不採用推奨

**C × A2 × モーター40%+**
- ROI -390pt悪化は看過できない
- 会場フィルターとの干渉リスク高
- サンプル不足の可能性

**C × B1 × モーター40%+**
- ROI -169pt悪化
- 既存のC×B1×会場フィルター（ROI 144.8%）と競合
- モーター条件追加で過剰フィルター化

### ✅ 採用推奨（別条件として新規追加）

**A × B1 × モーター40%+** (ROI +1118pt改善)
- 既存のA条件（10-12倍、14-16倍）と干渉しない
- B1級は既存A条件に含まれていない → 新規セグメント
- 効果が極めて大きい

**D × A1 × モーター40%+** (ROI +456pt改善)
- 既存のD条件（30-60倍）と干渉しない可能性
- A1級 × モーター40%+は信頼性が高いセグメント

**D × B1 × モーター40%+** (ROI +372pt改善)
- 既存のD × B1 × 40-50倍（ROI 198.1%）との重複をチェック必要
- モーター条件との相性が良い

### 🔬 次のステップ

#### 優先度1: データ検証（今すぐ実施）
```bash
# 以下のSQLを実行して仮説を検証
python scripts/analysis/verify_motor_condition_hypotheses.py
```

1. サンプル数確認
2. オッズ分布確認
3. 会場別モーター率分布
4. 決まり手傾向分析

#### 優先度2: 条件別バックテスト（検証後）
```python
# 採用推奨条件の詳細バックテスト
conditions_to_test = [
    ('A', 'B1', 40),  # A × B1 × motor_40+
    ('D', 'A1', 40),  # D × A1 × motor_40+
    ('D', 'B1', 40),  # D × B1 × motor_40+
]

for conf, rank, motor_min in conditions_to_test:
    run_backtest(confidence=conf, c1_rank=rank, motor_min=motor_min,
                 years=[2022, 2023, 2024, 2025])
```

#### 優先度3: 実装判断
- 2年以上安定（2024-2025年両方でROI 100%+）→ 本番採用
- 2025年のみ好成績 → ペーパートレード
- サンプル数 < 50件 → 採用見送り

---

## 🎯 実装推奨（最終版）

### 即時実装（本番）

**なし**（まずデータ検証が必要）

### ペーパートレード候補

1. **A × B1 × モーター40%+**
   - オッズ帯: 40-60倍（仮）
   - 会場フィルター: なし（全会場）
   - 期待ROI: 2748%（要検証）

2. **D × A1 × モーター40%+**
   - オッズ帯: 40-60倍
   - 会場フィルター: なし
   - 期待ROI: 2020%（要検証）

### 採用見送り

1. **C × A2 × モーター40%+** → 逆効果（-390pt）
2. **C × B1 × モーター40%+** → 既存条件と競合、逆効果（-169pt）
3. **B × A2 × モーター40%+** → 小幅悪化（-62pt）

---

**次回セッションで実施**:
1. 仮説検証SQLの実行
2. サンプル数・統計的信頼性の確認
3. 4年間データでの安定性検証
4. 最終的な実装判断

---

*作成者: Claude Opus 4.5*
*更新日: 2025-12-24*
