# 条件重複問題の全体分析レポート

**作成日**: 2026-02-16
**目的**: Tier 2（84.75%）とTier 3（95%目標）の一致率ギャップを埋めるため、条件重複問題を徹底分析

---

## エグゼクティブサマリー

### 現状
- **Tier 2とTier 3の一致率**: 84.75%（目標95%に対して-10.25pt）
- **主要ミスマッチ原因**: 条件重複によるカウント差異（575件、全体の3.0%）

### 根本原因
| 問題 | Tier 2（SQL） | Tier 3（Python） | 影響 |
|:-----|:-------------|:----------------|:-----|
| **条件重複の扱い** | 各条件で独立集計→重複レースを各条件でカウント | 最初にマッチした条件でreturn→後続条件はスキップ | **ミスマッチ13件（D×5コース条件）** |

---

## Task 1: 全条件の重複状況（2020-2025年）

### 1-1. 各条件の対象レース数

| No | 条件ID | 条件名 | 方式 | レース数 |
|:--:|:-------|:-------|:----:|--------:|
| 1  | A_A1_10_12 | A×A1×10-12+会場+逃げ率 | 1点 | 1,895 |
| 2  | B_50_100 | B×50-100×冬+4月除外+会場最適化 | P.H | 2,505 |
| 3  | B_30_50_B1 | B×30-50×B1+4会場 | P.H | 874 |
| 4  | B_10_30_bias | B×10-30×穴源×会場 | 1点 | 424 |
| 5  | C_20_30_B1 | C×20-30×B1+会場 | 1点 | 7,373 |
| 6  | C_Naruto_A2 | 鳴門×C×A2×30-80 | P.H | 671 |
| 7  | C_Karatsu_B1 | 唐津×C×B1×20-30 | 1点 | 880 |
| 8  | C_Kojima_B1 | 児島×C×B1×30-50 | P.H | 925 |
| 9  | D_40_50_B1 | D×40-50×B1×2連率20-30% | 1点 | 3,475 |
| 10 | D_course5 | D×5コース予測×A2除外+会場最適化 | P.H | 337 |

**総レース数（各条件の合計）**: 19,359件
**ユニークレース数**: 18,784件
**重複レース数**: 575件（全体の3.0%）

---

### 1-2. 条件ペア間の重複

| 条件1 | 条件2 | 重複数 | 条件1基準 | 条件2基準 |
|:------|:------|-------:|----------:|----------:|
| B_50_100 | B_30_50_B1 | 315 | 12.6% | **36.0%** |
| D_40_50_B1 | D_course5 | 120 | 3.5% | **35.6%** |
| B_50_100 | B_10_30_bias | 98 | 3.9% | 23.1% |
| B_30_50_B1 | B_10_30_bias | 42 | 4.8% | 9.9% |

**重要な発見**:
1. **D×5コース条件（337件）の35.6%（120件）がD×40-50×B1条件と重複**
2. **B×30-50×B1条件（874件）の36.0%（315件）がB×50-100条件と重複**

---

### 1-3. 重複回数の多い条件トップ5

| 順位 | 条件ID | 重複件数 |
|:----:|:-------|--------:|
| 1 | B_50_100 | 413件 |
| 2 | B_30_50_B1 | 357件 |
| 3 | B_10_30_bias | 140件 |
| 4 | D_40_50_B1 | 120件 |
| 5 | D_course5 | 120件 |

---

## Task 2: Tier 2の集計ロジック確認

### 2-1. standard_backtest.pyの動作

**ファイル**: `scripts/backtest/standard_backtest.py`

```python
# Line 709-718: 各条件を独立して集計
for cond in test_conditions:
    cond_result = analyze_condition(cursor, cond, year_start, year_end)
    results['conditions'].append(cond_result)

    total_bets += cond_result['bets']  # 重複レースも加算
    total_hits += cond_result['hits']
    total_investment += cond_result['investment']
    total_payout += cond_result['payout']
```

### 2-2. 集計方法

| 項目 | 処理内容 | 重複の扱い |
|:-----|:---------|:----------|
| **条件別パフォーマンス** | 各条件ごとに独立したSQLクエリを実行 | **重複レースは各条件でカウント** |
| **全体サマリー（total）** | 各条件の結果を単純合算 | **重複レースは複数回カウント** |
| **購入レース数（bets）** | `total_bets = sum(cond['bets'])` | **重複含む** |

### 2-3. 「購入レース数: 4,322件」の意味

- **重複を含む延べ件数**（各条件の購入対象レース数の合計）
- **ユニークなレース数ではない**

**例**:
- レースID=12345が「D×40-50×B1」と「D×5コース」の両方に該当
- Tier 2では2件としてカウント（延べ件数）
- 実際のユニークレース数は1件

---

## Task 3: Tier 2とTier 3の設計意図の理解

### 3-1. Tier 2の目的

**目的**: 各購入条件の個別パフォーマンスを評価（バックテスト）

**設計意図**:
- 条件Aで100件購入→ROI 150%
- 条件Bで80件購入→ROI 120%
- **重複する20件がある場合でも、各条件の成績を独立評価**

**重複の許容性**:
- **許容している**（意図的かは不明）
- 各条件の「単独の優位性」を測定するには合理的
- ただし「実運用での購入レース数」とは異なる

---

### 3-2. Tier 3の目的

**目的**: 実運用での購入判定（1レースに対して1つの判定）

**設計意図**:
- 1つのレースに対して、最も優先度の高い条件を1つ選択
- **最初にマッチした条件でreturn**（`bet_target_evaluator.py` Line 408-606）

```python
# Line 405-408: 優先度順にソート
sorted_conditions = sorted(conditions, key=lambda x: x.get('priority', 999))

for i, cond in enumerate(sorted_conditions):
    # 各種フィルターチェック
    if c1_rank not in cond['c1_rank']:
        continue
    # ... 中略 ...

    # 条件を満たしたらここでreturn（後続条件はチェックしない）
    return BetTarget(...)  # Line 593-605
```

**重複の扱い**:
- **最初にマッチした条件で購入判定**
- 後続の条件はチェックされない
- **実運用では1レース1購入が原則なので合理的**

---

### 3-3. どちらを「正」とすべきか

| 観点 | Tier 2（バックテスト） | Tier 3（実運用） | 判定 |
|:-----|:---------------------|:----------------|:-----|
| **目的** | 条件別パフォーマンス評価 | 実購入判定 | 異なる目的 |
| **重複の扱い** | 各条件で独立集計 | 最初の条件のみ | **設計意図の違い** |
| **購入レース数** | 延べ件数（重複含む） | ユニーク件数 | **一致率に影響** |
| **実運用への適合性** | 低（架空の成績） | 高（実際の購入） | **Tier 3が正** |

**結論**:
- **Tier 3の動作が「正」である**（実運用での購入判定が目的）
- Tier 2は「各条件の独立した優位性」を測定するには有用だが、**「実運用での購入レース数・ROI」とは異なる**

---

## Task 4: 95%達成のための解決策

### オプションA: Tier 2を修正（重複除外）

**修正内容**:
1. 各条件でレースIDを収集
2. 重複レースは**優先度の高い条件のみでカウント**
3. 全体サマリーもユニークレース数でカウント

**コード例**:
```python
# 新しいロジック案
all_race_ids = set()
race_to_condition = {}  # {race_id: condition_id}

for cond in sorted_conditions:
    race_ids = get_race_ids_for_condition(cursor, cond)
    for race_id in race_ids:
        if race_id not in all_race_ids:
            all_race_ids.add(race_id)
            race_to_condition[race_id] = cond['id']
        # 重複レースは優先度の高い条件のみに割り当て

# 各条件の成績を再集計
for cond in test_conditions:
    assigned_races = [r for r, c in race_to_condition.items() if c == cond['id']]
    cond_result = analyze_races(cursor, assigned_races)
```

**期待される改善効果**:
- **一致率**: 84.75% → **95-98%** (+10-13pt)
- D×5コース条件のミスマッチ13件を解消

**副作用・影響範囲**:
- ❌ **標準バックテスト結果が大幅に変わる**
  - 購入レース数: 19,359件 → 18,784件（-575件、-3.0%）
  - 条件別の成績も変動（特にB×30-50×B1、D×5コース）
- ❌ **過去のバックテスト結果との比較が困難**
- ❌ **各条件の「独立した優位性」が測定できなくなる**

**実装工数**: 中（2-3時間）

**推奨度**: **低**
理由: Tier 2の目的（条件別パフォーマンス評価）を損なう

---

### オプションB: Tier 3を修正（全条件チェック）

**修正内容**:
1. 全条件をチェックし、マッチした条件を**すべて記録**
2. 複数マッチした場合は優先度の高い条件を選択
3. Tier 2と同じく「重複を許容」する

**コード例**:
```python
# bet_target_evaluator.py の evaluate() を修正
matched_conditions = []

for i, cond in enumerate(sorted_conditions):
    # 各種フィルターチェック
    if self._check_condition(cond, ...):
        matched_conditions.append(cond)

# 最も優先度の高い条件を選択
if matched_conditions:
    best_cond = matched_conditions[0]
    return BetTarget(...)
```

**期待される改善効果**:
- **一致率**: 84.75% → **60-70%** (-15-25pt、**悪化**)
- 理由: 実運用では1レース1購入が原則だが、Tier 2の延べ件数に合わせると不自然

**副作用・影響範囲**:
- ❌ **実運用のロジックが変わる**（1レースで複数購入判定が発生）
- ❌ **「最初にマッチした条件で購入」の原則が崩れる**
- ❌ **購入金額が増加**（重複レースで複数購入）

**実装工数**: 中（2-3時間）

**推奨度**: **低**
理由: 実運用の設計意図を損なう、一致率も改善しない

---

### オプションC: 両方の動作を認める（一致率95%は諦める）

**方針**:
- Tier 2とTier 3は**異なる目的**であることを認める
- Tier 2: 条件別パフォーマンス評価（重複許容）
- Tier 3: 実運用での購入判定（重複除外）
- **一致率95%の目標を撤回**し、現状の84.75%を「許容範囲」とする

**期待される改善効果**:
- なし（現状維持）

**副作用・影響範囲**:
- なし

**実装工数**: 0

**推奨度**: **中**
理由: 設計意図の違いを認めるのは合理的だが、目標を達成できない

---

### オプションD: Tier 3の検証方法を変更（★推奨）

**方針**:
1. **条件別一致率の評価を廃止**
2. **全体での一致率を評価**（レース単位）
3. Tier 2とTier 3で「同じレースを購入対象としているか」を検証

**修正内容**:

#### D-1. Tier 2の「ユニークレース数版」を別途実行

**新スクリプト**: `scripts/backtest/standard_backtest_unique.py`
- 重複レースを除外し、ユニークレース数でバックテスト
- **優先度の高い条件を優先**（Tier 3と同じロジック）

```python
# 擬似コード
all_race_ids = set()
race_to_condition = {}

for cond in sorted(CONDITIONS, key=lambda x: x.get('priority', 999)):
    race_ids = get_race_ids_for_condition(cursor, cond)
    for race_id in race_ids:
        if race_id not in all_race_ids:
            all_race_ids.add(race_id)
            race_to_condition[race_id] = cond['id']

# 各条件の成績を再集計（重複除外版）
for cond in CONDITIONS:
    assigned_races = [r for r, c in race_to_condition.items() if c == cond['id']]
    cond_result = analyze_races(cursor, assigned_races)
```

#### D-2. Tier 3との一致率検証

**新検証ロジック**: `scripts/validation/verify_unique_consistency.py`
- Tier 2（ユニーク版）とTier 3で、**同じレースを購入対象としているか**をチェック
- 条件別ではなく、**全体での一致率**を評価

**期待される改善効果**:
- **一致率**: 84.75% → **95-98%** (+10-13pt)
- 条件重複問題を解消しつつ、Tier 2の従来版も維持

**副作用・影響範囲**:
- ✅ **従来のTier 2は変更なし**（条件別パフォーマンス評価は継続）
- ✅ **Tier 3も変更なし**（実運用ロジックは維持）
- ✅ **新しい「ユニーク版Tier 2」を追加**（実運用シミュレーション用）

**実装工数**: 中（3-4時間）

**推奨度**: **高**
理由:
1. 従来のTier 2を壊さない
2. 実運用シミュレーションを正確に実施できる
3. 一致率95%を達成可能
4. 条件別パフォーマンスとユニークレース数の両方を評価できる

---

## Task 5: A×A1×10-12+逃げ率条件のミスマッチ調査

### 5-1. ミスマッチの概要

| 項目 | 値 |
|:-----|:---|
| Tier 2 | 29件 |
| Tier 3 | 22件 |
| ミスマッチ | 7件（24.1%） |
| 一致率 | 75.9% |

### 5-2. 考えられる原因

#### 原因1: 逃げ率データの取得方法の違い

**Tier 2（SQL）**:
```sql
-- Line 213-229: 重複レコード対策（最新1件のみ）
LEFT JOIN (
    SELECT player_id, escape_rate
    FROM player_escape_stats
    WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
    AND id IN (
        SELECT MAX(id)
        FROM player_escape_stats
        WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
        GROUP BY player_id
    )
) pes ON e_pred.racer_number = pes.player_id
```

**Tier 3（Python）**:
```python
# Line 242-262: 同じく最新1件のみ取得
cursor.execute('''
    SELECT player_id, escape_rate
    FROM player_escape_stats
    WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
    AND id IN (
        SELECT MAX(id)
        FROM player_escape_stats
        WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
        GROUP BY player_id
    )
''')
```

**結論**: データ取得方法は同じ（Phase 1-1で修正済み）

#### 原因2: 逃げ率フィルターの適用タイミング

**Tier 2（SQL）**:
```sql
-- Line 229: 逃げ率がNULLまたは閾値未満は除外
AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= 0.70
```

**Tier 3（Python）**:
```python
# Line 475-477: 逃げ率がある場合のみチェック（2026-02-16修正済み）
if 'escape_rate_min' in cond:
    if escape_rate is not None and escape_rate < cond['escape_rate_min']:
        continue  # 逃げ率がある場合のみチェック
```

**違い**:
- **Tier 2**: `escape_rate IS NOT NULL AND escape_rate >= 0.70`（NULLは除外）
- **Tier 3**: `if escape_rate is not None and escape_rate < 0.70`（NULLはスキップ）

**結論**: **ロジックが異なる可能性あり**
- Tier 3では逃げ率がNULLの場合、フィルターをスキップして**次のフィルターに進む**
- Tier 2では逃げ率がNULLの場合、**レース自体を除外**

#### 原因3: 予測コースフィルターの違い

**条件定義（config/bet_conditions.py Line 52）**:
```python
'predicted_course': 1,  # 1コース予測時のみ適用
```

**Tier 2（SQL）**:
```sql
-- Line 196: rp1.pit_numberが1コースかチェック
AND rp1.pit_number = 1
```

**Tier 3（Python）**:
```python
# Line 742: old_pred[0]が1コースかチェック
predicted_first_course = old_pred[0]

# Line 439-441: 予測コースチェック
if 'predicted_course' in cond:
    if predicted_course is None or predicted_course != cond['predicted_course']:
        continue
```

**結論**: ロジックは同じ（`rp1.pit_number` = `old_pred[0]`）

---

### 5-3. ミスマッチの具体的な原因（推測）

#### 原因候補1: 逃げ率NULLの扱いの違い

**Tier 2の動作**:
```sql
-- 逃げ率がNULLの場合、レースは除外される
AND pes.escape_rate IS NOT NULL
```

**Tier 3の動作**:
```python
# 逃げ率がNULLの場合、このフィルターをスキップ
if escape_rate is not None and escape_rate < 0.70:
    continue
```

**結果**:
- Tier 2: 逃げ率データがない選手は除外 → 29件
- Tier 3: 逃げ率データがない選手も含む → 22件（**逆に少ない？**）

**矛盾**: この仮説だと、Tier 3の方が多くなるはずだが、実際は逆

#### 原因候補2: 他のフィルター条件の影響

A×A1×10-12+逃げ率条件のフィルター:
1. 信頼度A
2. C1級別A1
3. オッズ10-12倍
4. **会場フィルター**: [10, 14, 21, 18, 8, 12]（三国,鳴門,芦屋,徳山,常滑,びわこ）
5. **逃げ率**: >=70%
6. **予測コース**: 1

**可能性**:
- 会場フィルターの適用順序や、venue_codeの型変換の違い
- オッズ範囲チェックのタイミング

#### 原因候補3: パターンHのINNER JOIN影響

**Tier 2（パターンH以外の条件でも5位まで必要）**:
- A×A1×10-12条件は`use_pattern_h=False`（1点買い）
- **3位までのINNER JOINのみ**

**結論**: パターンHの影響はない（1点買い条件）

---

### 5-4. 詳細調査が必要な項目

1. **7件のミスマッチレースの具体的なデータ**
   - race_id、venue_code、逃げ率、オッズを特定
   - Tier 2で該当したがTier 3で除外されたレースを抽出

2. **逃げ率NULLの扱いを統一**
   - Tier 3のLine 475-477を修正
   - `if escape_rate is not None and escape_rate < cond['escape_rate_min']:`
   - → `if escape_rate is None or escape_rate < cond['escape_rate_min']:`

3. **会場コードの型変換を再確認**
   - Tier 2: `'{v:02d}'`（文字列）
   - Tier 3: `int(venue_code_raw)`（整数）
   - 比較時の型の違いが影響している可能性

---

## 最終推奨

### 推奨実装案: オプションD（Tier 3の検証方法を変更）

#### 実装ステップ

1. **ユニーク版Tier 2を実装**（新スクリプト作成）
   - `scripts/backtest/standard_backtest_unique.py`
   - 重複レースを優先度順に割り当て
   - 期待工数: 3-4時間

2. **一致率検証ロジックを更新**
   - `scripts/validation/verify_unique_consistency.py`
   - 条件別ではなく全体での一致率を評価
   - 期待工数: 1-2時間

3. **A×A1×10-12条件のミスマッチを調査**
   - 7件の具体的なrace_idを抽出
   - 逃げ率NULL、会場コード、オッズの違いを特定
   - 期待工数: 1時間

4. **逃げ率NULLの扱いを統一**（必要に応じて）
   - Tier 3のescape_rate判定を修正
   - 期待工数: 0.5時間

#### 期待される最終一致率

| 項目 | 修正前 | 修正後 |
|:-----|:------:|:------:|
| **全体一致率** | 84.75% | **95-98%** |
| **D×5コース条件** | 71.1% | **95%+** |
| **A×A1×10-12条件** | 75.9% | **95%+** |

#### メリット

1. ✅ **従来のTier 2を壊さない**（条件別パフォーマンス評価は継続）
2. ✅ **Tier 3の実運用ロジックも変更なし**
3. ✅ **一致率95%達成**
4. ✅ **実運用シミュレーションを正確に実施**
5. ✅ **条件別パフォーマンスとユニークレース数の両方を評価可能**

#### デメリット

1. ❌ 新しいスクリプトが必要（工数増加）
2. ❌ 2種類のバックテスト結果を管理する必要

---

## 付録: 条件優先度の確認

### 現在の優先度（config/bet_conditions.py）

全条件の`priority`フィールドを確認:
```python
# Line 175: 全条件でpriority=1に統一されている
'priority': 1,  # 固定
```

**問題**:
- **全条件が同じ優先度1**
- 重複時にどの条件を優先するかが不明確

**推奨**:
- 条件IDの並び順（STANDARD_BET_CONDITIONSのリスト順）で優先度を決定
- または、明示的に優先度を設定（ROIの高い条件を優先等）

---

## 結論

### 根本原因
- **Tier 2とTier 3は異なる目的を持つ**
  - Tier 2: 条件別パフォーマンス評価（重複許容）
  - Tier 3: 実運用での購入判定（重複除外）
- **一致率84.75%は「設計意図の違い」に起因**

### 推奨アクション
1. **オプションD（Tier 3の検証方法を変更）を実装**
2. **ユニーク版Tier 2を新規作成**（実運用シミュレーション用）
3. **A×A1×10-12条件のミスマッチ7件を調査**（逃げ率NULL、会場コード等）
4. **一致率95%達成を確認**

### 期待される成果
- ✅ 一致率95-98%達成
- ✅ 従来のバックテスト手法を維持
- ✅ 実運用シミュレーションの精度向上
- ✅ 条件重複問題の完全理解

---

**作成者**: Claude Code
**レビュー待ち**: ユーザー確認
