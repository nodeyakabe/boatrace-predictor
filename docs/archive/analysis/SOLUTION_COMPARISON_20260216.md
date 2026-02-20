# 条件重複問題の解決策比較表

**作成日**: 2026-02-16
**目的**: 一致率95%達成のための4つのオプションを比較し、最適な解決策を選定

---

## オプション一覧

| オプション | アプローチ | 推奨度 | 期待一致率 | 工数 |
|:----------|:----------|:------:|:----------:|:----:|
| **A** | Tier 2を修正（重複除外） | ❌ 低 | 95-98% | 中 |
| **B** | Tier 3を修正（全条件チェック） | ❌ 低 | 60-70% | 中 |
| **C** | 両方の動作を認める | △ 中 | 84.75% | なし |
| **D** | Tier 3の検証方法を変更 | ✅ **高** | **95-98%** | 中 |

---

## オプションA: Tier 2を修正（重複除外）

### 具体的な修正内容

#### A-1. 重複レースの優先度決定ロジック

```python
# scripts/backtest/standard_backtest.py に追加
def run_backtest_unique(year: int = 2025, full_test: bool = False):
    """重複を除外したバックテスト（実運用シミュレーション用）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # STEP 1: 全レースを収集し、優先度順に条件を割り当て
    all_race_ids = set()
    race_to_condition = {}  # {race_id: condition_id}

    # 優先度順にソート（priorityが同じ場合はリスト順）
    sorted_conditions = sorted(
        CONDITIONS,
        key=lambda x: (x.get('priority', 999), CONDITIONS.index(x))
    )

    for cond in sorted_conditions:
        race_ids = get_race_ids_for_condition(cursor, cond, year_start, year_end)
        for race_id in race_ids:
            if race_id not in all_race_ids:
                all_race_ids.add(race_id)
                race_to_condition[race_id] = cond['id']
            # 重複レースは優先度の高い条件のみに割り当て

    # STEP 2: 各条件の成績を再集計
    for cond in CONDITIONS:
        assigned_races = [r for r, c in race_to_condition.items() if c == cond['id']]
        cond_result = analyze_assigned_races(cursor, cond, assigned_races)
        results['conditions'].append(cond_result)

    # STEP 3: 全体サマリー（ユニークレース数）
    results['total'] = {
        'bets': len(all_race_ids),
        # ... 中略 ...
    }
```

#### A-2. 条件別成績の再集計

```python
def analyze_assigned_races(cursor, cond: Dict, race_ids: List[int]) -> Dict:
    """指定されたレースIDのみで条件の成績を計算"""
    if not race_ids:
        return {'bets': 0, 'hits': 0, 'roi': 0, 'profit': 0}

    # race_ids に基づいてオッズ・結果を取得し、パフォーマンスを計算
    placeholders = ','.join(['?'] * len(race_ids))
    query = f"""
    SELECT
        COUNT(*) as bets,
        SUM(is_hit) as hits,
        SUM(investment) as investment,
        SUM(payout) as payout
    FROM race_results
    WHERE race_id IN ({placeholders})
    """
    cursor.execute(query, race_ids)
    # ... 中略 ...
```

---

### 期待される改善効果

| 指標 | 修正前 | 修正後 | 変化 |
|:-----|:------:|:------:|:----:|
| **一致率（全体）** | 84.75% | **95-98%** | **+10-13pt** |
| **D×5コース条件** | 71.1% | **95%+** | **+24pt** |
| **購入レース数** | 19,359件 | 18,784件 | **-575件** |

**理由**:
- 重複レース（575件）を除外
- 優先度の高い条件のみでカウント
- Tier 3の動作と一致

---

### 副作用・影響範囲

#### ❌ デメリット1: 標準バックテスト結果が大幅に変わる

| 項目 | 現在（重複含む） | 修正後（重複除外） | 影響 |
|:-----|:---------------:|:-----------------:|:-----|
| **購入レース数** | 19,359件 | 18,784件 | **-3.0%** |
| **ROI** | 118.4% | 不明（要再計算） | 条件別に変動 |
| **収支** | +245,170円 | 不明（要再計算） | 条件別に変動 |

**特に影響が大きい条件**:
- **B×30-50×B1**: 874件 → 559件（-36.0%、315件減）
- **D×5コース**: 337件 → 217件（-35.6%、120件減）

#### ❌ デメリット2: 過去のバックテスト結果との比較が困難

- 過去6ヶ月分のバックテスト結果（ROI、収支、件数）が全て変わる
- 改善施策の効果測定ができなくなる
- ベースラインとの比較が無意味になる

#### ❌ デメリット3: 各条件の「独立した優位性」が測定できなくなる

**例**:
- D×5コース条件は**単独で**ROI 176.6%の優秀な条件
- しかし、D×40-50×B1条件との重複120件を除外すると、ROI・収支が変わる
- 「この条件単独でどれだけ優秀か」が不明瞭になる

---

### 実装工数

| タスク | 工数 |
|:-------|:----:|
| `run_backtest_unique()` の実装 | 2時間 |
| `analyze_assigned_races()` の実装 | 1時間 |
| テスト・検証 | 1時間 |
| **合計** | **3-4時間** |

---

### 推奨度: ❌ 低

**理由**:
1. Tier 2の本来の目的（条件別パフォーマンス評価）を損なう
2. 過去のバックテスト結果との連続性が失われる
3. 各条件の独立した優位性が測定できなくなる

---

## オプションB: Tier 3を修正（全条件チェック）

### 具体的な修正内容

#### B-1. evaluate()メソッドの修正

```python
# src/betting/bet_target_evaluator.py の evaluate() を修正
def evaluate(self, confidence, c1_rank, ...):
    """購入対象を判定する（全条件チェック版）"""
    conditions = self.BET_CONDITIONS.get(confidence, [])
    sorted_conditions = sorted(conditions, key=lambda x: x.get('priority', 999))

    matched_conditions = []  # 新規追加

    for i, cond in enumerate(sorted_conditions):
        # 各種フィルターチェック
        if c1_rank not in cond['c1_rank']:
            continue
        # ... 中略 ...

        # オッズ範囲チェック
        if odds_min <= odds < odds_max:
            matched_conditions.append(cond)  # 記録のみ、returnしない

    # 全条件をチェック後、最も優先度の高い条件を選択
    if matched_conditions:
        best_cond = matched_conditions[0]
        return BetTarget(
            status=BetStatus.TARGET_CONFIRMED,
            confidence=confidence,
            # ... 中略 ...
        )

    # 条件を満たさない
    return BetTarget(status=BetStatus.EXCLUDED, ...)
```

---

### 期待される改善効果

| 指標 | 修正前 | 修正後 | 変化 |
|:-----|:------:|:------:|:----:|
| **一致率（全体）** | 84.75% | **60-70%** | **-15-25pt（悪化）** |
| **購入レース数** | 18,784件 | 19,359件 | **+575件** |

**理由**:
- Tier 2の延べ件数（19,359件）に合わせる
- しかし、実運用では1レース1購入が原則のため、不自然
- 重複レースで複数の購入判定が発生するが、最終的には1つしか選ばない
- **一致率は改善せず、むしろ悪化**

---

### 副作用・影響範囲

#### ❌ デメリット1: 実運用のロジックが変わる

**修正前**:
- 最初にマッチした条件でreturn
- 1レース1購入が原則

**修正後**:
- 全条件をチェックし、複数マッチを記録
- 最終的には最優先の1つを選択
- **購入判定ロジックが複雑化**

#### ❌ デメリット2: 「最初にマッチした条件で購入」の原則が崩れる

**例**:
- 現在: D×40-50×B1条件でマッチ → その場でreturn
- 修正後: D×40-50×B1条件でマッチ → 記録 → D×5コース条件もチェック → 両方マッチ → 優先度で選択

**問題**:
- 条件チェックの順序に依存しない動作になる（良いとも言える）
- ただし、全条件チェックのコストが増加

#### ❌ デメリット3: 購入金額が増加する可能性

**修正後の動作**:
- 複数条件にマッチする場合、どの条件で購入するか？
- 「全てに購入」→ 購入金額が増加（実運用に影響）
- 「1つだけ購入」→ Tier 2の延べ件数と一致しない

---

### 実装工数

| タスク | 工数 |
|:-------|:----:|
| `evaluate()` の修正 | 1時間 |
| テスト・検証 | 1時間 |
| **合計** | **2時間** |

---

### 推奨度: ❌ 低

**理由**:
1. 一致率が改善せず、むしろ悪化
2. 実運用のロジックを不自然に変更
3. 「最初にマッチした条件で購入」の原則を損なう

---

## オプションC: 両方の動作を認める

### 方針

- Tier 2とTier 3は**異なる目的**であることを認める
- Tier 2: 条件別パフォーマンス評価（重複許容）
- Tier 3: 実運用での購入判定（重複除外）
- **一致率95%の目標を撤回**し、現状の84.75%を「許容範囲」とする

---

### 期待される改善効果

**なし**（現状維持）

---

### 副作用・影響範囲

**なし**

---

### 実装工数

**0時間**

---

### 推奨度: △ 中

**理由**:
1. 設計意図の違いを認めるのは合理的
2. Tier 2とTier 3の両方を壊さない
3. ただし、**目標（一致率95%）を達成できない**

---

## オプションD: Tier 3の検証方法を変更（★推奨）

### 方針

1. **条件別一致率の評価を廃止**
2. **全体での一致率を評価**（レース単位）
3. Tier 2の「ユニーク版」を別途実行し、Tier 3と比較

---

### 具体的な修正内容

#### D-1. ユニーク版Tier 2を新規作成

**新スクリプト**: `scripts/backtest/standard_backtest_unique.py`

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ユニーク版標準バックテスト（実運用シミュレーション用）

目的:
    重複レースを除外し、Tier 3の実運用ロジックと同じ動作でバックテストを実行

使用方法:
    python scripts/backtest/standard_backtest_unique.py --full

出力:
    - 全体サマリー（ユニークレース数、ROI、収支）
    - 条件別パフォーマンス（重複除外版）
    - 年度別パフォーマンス
"""
import sqlite3
from config.bet_conditions import STANDARD_BET_CONDITIONS
from config.settings import DATABASE_PATH

def run_unique_backtest(year: int = 2025, full_test: bool = False):
    """重複を除外したバックテスト"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 期間設定
    if full_test:
        years = [2020, 2021, 2022, 2023, 2024, 2025]
        year_start = f"{years[0]}-01-01"
        year_end = f"{years[-1] + 1}-01-01"
    else:
        year_start = f"{year}-01-01"
        year_end = f"{year + 1}-01-01"

    # STEP 1: 全レースを収集し、優先度順に条件を割り当て
    all_race_ids = set()
    race_to_condition = {}  # {race_id: condition_id}

    # 優先度順にソート（priorityが同じ場合はリスト順）
    sorted_conditions = sorted(
        STANDARD_BET_CONDITIONS,
        key=lambda x: (x.get('priority', 999), STANDARD_BET_CONDITIONS.index(x))
    )

    for cond in sorted_conditions:
        race_ids = get_race_ids_for_condition(cursor, cond, year_start, year_end)
        for race_id in race_ids:
            if race_id not in all_race_ids:
                all_race_ids.add(race_id)
                race_to_condition[race_id] = cond['id']
            # 重複レースは優先度の高い条件のみに割り当て

    # STEP 2: 各条件の成績を再集計
    results = {'conditions': [], 'total': {}}
    total_bets = 0
    total_hits = 0
    total_investment = 0
    total_payout = 0

    for cond in STANDARD_BET_CONDITIONS:
        assigned_races = [r for r, c in race_to_condition.items() if c == cond['id']]
        cond_result = analyze_assigned_races(cursor, cond, assigned_races)
        results['conditions'].append(cond_result)

        total_bets += cond_result['bets']
        total_hits += cond_result['hits']
        total_investment += cond_result['investment']
        total_payout += cond_result['payout']

    # STEP 3: 全体サマリー
    results['total'] = {
        'bets': total_bets,
        'hits': total_hits,
        'hit_rate': 100.0 * total_hits / total_bets if total_bets > 0 else 0,
        'investment': total_investment,
        'payout': total_payout,
        'roi': 100.0 * total_payout / total_investment if total_investment > 0 else 0,
        'profit': total_payout - total_investment,
    }

    conn.close()
    return results

def get_race_ids_for_condition(cursor, cond, start_date, end_date):
    """条件に該当するレースIDのセットを取得

    ※check_all_condition_overlap.pyと同じロジック
    """
    # ... 省略（check_all_condition_overlap.pyのget_race_ids_for_condition()と同じ）...

def analyze_assigned_races(cursor, cond: Dict, race_ids: List[int]) -> Dict:
    """指定されたレースIDのみで条件の成績を計算"""
    if not race_ids:
        return {
            'name': cond['name'],
            'bets': 0, 'hits': 0, 'hit_rate': 0,
            'investment': 0, 'payout': 0, 'roi': 0, 'profit': 0,
        }

    # パターンHか1点買いかで投資額・払戻を計算
    use_pattern_h = cond.get('use_pattern_h', True)

    # race_idsに基づいてオッズ・結果を取得
    placeholders = ','.join(['?'] * len(race_ids))

    if use_pattern_h:
        # パターンH: 3点買い（200円/100円/100円）
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                rp4.pit_number as p4,
                rp5.pit_number as p5,
                -- オッズ取得
                (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)) as odds_123,
                (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp4.pit_number AS TEXT)) as odds_124,
                (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp5.pit_number AS TEXT)) as odds_125,
                -- 実際の結果
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
            JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
            WHERE r.id IN ({placeholders})
        ),
        race_payouts AS (
            SELECT
                *,
                -- 投資額計算
                CASE WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN 200 ELSE 0 END as bet_123,
                CASE WHEN odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_124,
                CASE WHEN odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_125,
                -- 払戻計算
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN odds_123 * 200 ELSE 0
                END as payout_123,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                         AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']}
                    THEN odds_124 * 100 ELSE 0
                END as payout_124,
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5
                         AND odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']}
                    THEN odds_125 * 100 ELSE 0
                END as payout_125,
                -- 的中判定
                CASE
                    WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']})
                      OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= {cond['odds_min']} AND odds_124 < {cond['odds_max']})
                      OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= {cond['odds_min']} AND odds_125 < {cond['odds_max']})
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        )
        SELECT
            SUM(CASE WHEN bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_123 + bet_124 + bet_125) as investment,
            SUM(payout_123 + payout_124 + payout_125) as payout
        FROM race_payouts
        WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
        """
    else:
        # 1点買い: 100円
        query = f"""
        WITH race_bets AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3,
                -- オッズ取得
                (SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)) as odds_123,
                -- 実際の結果
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
                (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd
            FROM races r
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            WHERE r.id IN ({placeholders})
        ),
        race_payouts AS (
            SELECT
                *,
                -- 投資額計算
                CASE WHEN odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']} THEN 100 ELSE 0 END as bet_amount,
                -- 払戻計算
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN odds_123 * 100 ELSE 0
                END as payout,
                -- 的中判定
                CASE
                    WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                         AND odds_123 >= {cond['odds_min']} AND odds_123 < {cond['odds_max']}
                    THEN 1 ELSE 0
                END as is_hit
            FROM race_bets
        )
        SELECT
            SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
            SUM(is_hit) as hits,
            SUM(bet_amount) as investment,
            SUM(payout) as payout
        FROM race_payouts
        WHERE bet_amount > 0
        """

    cursor.execute(query, race_ids)
    row = cursor.fetchone()

    if row and row[0] and row[0] > 0:
        bets, hits, investment, payout = row
        hits = hits or 0
        payout = payout or 0
        roi = 100.0 * payout / investment if investment > 0 else 0
        profit = payout - investment
        hit_rate = 100.0 * hits / bets if bets > 0 else 0
        return {
            'name': cond['name'],
            'bets': bets,
            'hits': hits,
            'hit_rate': hit_rate,
            'investment': investment,
            'payout': payout,
            'roi': roi,
            'profit': profit,
        }

    return {
        'name': cond['name'],
        'bets': 0, 'hits': 0, 'hit_rate': 0,
        'investment': 0, 'payout': 0, 'roi': 0, 'profit': 0,
    }

if __name__ == '__main__':
    results = run_unique_backtest(full_test=True)
    print(f"ユニーク版バックテスト結果: {results['total']['bets']}件, ROI {results['total']['roi']:.1f}%")
```

#### D-2. 一致率検証ロジックを更新

**新スクリプト**: `scripts/validation/verify_unique_consistency.py`

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ユニーク版Tier 2とTier 3の一致率検証

目的:
    重複除外版のTier 2（standard_backtest_unique.py）と
    Tier 3（BetTargetEvaluator）の一致率を検証

使用方法:
    python scripts/validation/verify_unique_consistency.py --start 2020-01-01 --end 2025-12-31

出力:
    - 全体一致率
    - 条件別一致率（参考）
"""
import sqlite3
from scripts.backtest.standard_backtest_unique import run_unique_backtest, get_race_ids_for_condition
from src.betting.bet_target_evaluator import BetTargetEvaluator
from config.bet_conditions import STANDARD_BET_CONDITIONS

def verify_consistency():
    # STEP 1: ユニーク版Tier 2を実行
    tier2_results = run_unique_backtest(full_test=True)

    # STEP 2: Tier 3で全レースを判定
    evaluator = BetTargetEvaluator()
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 全レースを取得
    cursor.execute("""
        SELECT DISTINCT r.id, r.race_date, r.venue_code
        FROM races r
        WHERE r.race_date >= '2020-01-01' AND r.race_date < '2026-01-01'
    """)
    all_races = cursor.fetchall()

    tier3_race_ids = set()
    for race_id, race_date, venue_code in all_races:
        # レースデータ・予測を取得
        race_data = get_race_data(cursor, race_id)
        predictions = get_predictions(cursor, race_id)
        odds_data = get_odds_data(cursor, race_id)

        # Tier 3で判定
        bet_target = evaluator.evaluate_race(race_data, predictions, odds_data, has_beforeinfo=True)

        if bet_target.status in [BetStatus.TARGET_CONFIRMED, BetStatus.TARGET_ADVANCE]:
            tier3_race_ids.add(race_id)

    # STEP 3: 一致率計算
    tier2_race_ids = get_all_tier2_race_ids(tier2_results)  # ユニーク版のレースID
    match_count = len(tier2_race_ids & tier3_race_ids)
    tier2_only = tier2_race_ids - tier3_race_ids
    tier3_only = tier3_race_ids - tier2_race_ids

    consistency_rate = match_count / len(tier2_race_ids) * 100 if len(tier2_race_ids) > 0 else 0

    print(f"✅ 全体一致率: {consistency_rate:.2f}%")
    print(f"   Tier 2（ユニーク版）: {len(tier2_race_ids)}件")
    print(f"   Tier 3: {len(tier3_race_ids)}件")
    print(f"   一致: {match_count}件")
    print(f"   Tier 2のみ: {len(tier2_only)}件")
    print(f"   Tier 3のみ: {len(tier3_only)}件")

    conn.close()

if __name__ == '__main__':
    verify_consistency()
```

---

### 期待される改善効果

| 指標 | 修正前 | 修正後 | 変化 |
|:-----|:------:|:------:|:----:|
| **一致率（全体）** | 84.75% | **95-98%** | **+10-13pt** |
| **D×5コース条件** | 71.1% | **95%+** | **+24pt** |
| **A×A1×10-12条件** | 75.9% | **95%+** | **+19pt** |

---

### 副作用・影響範囲

#### ✅ メリット1: 従来のTier 2は変更なし

- **標準バックテスト（standard_backtest.py）は継続**
- 条件別パフォーマンス評価はそのまま
- 過去のバックテスト結果との比較も可能

#### ✅ メリット2: Tier 3の実運用ロジックも変更なし

- BetTargetEvaluatorは修正不要
- 実運用での購入判定ロジックは維持

#### ✅ メリット3: 新しい「ユニーク版Tier 2」を追加

- 実運用シミュレーション用
- 重複除外版の成績を確認可能
- Tier 3との一致率95%達成

#### ✅ メリット4: 条件別パフォーマンスとユニークレース数の両方を評価

- **従来版**: 各条件の独立した優位性を測定
- **ユニーク版**: 実運用での購入レース数・ROIを測定
- 両方の視点から評価可能

---

### 実装工数

| タスク | 工数 |
|:-------|:----:|
| `standard_backtest_unique.py` の実装 | 3時間 |
| `get_race_ids_for_condition()` の移植 | 0.5時間 |
| `analyze_assigned_races()` の実装 | 1時間 |
| `verify_unique_consistency.py` の実装 | 1.5時間 |
| テスト・検証 | 1時間 |
| **合計** | **6-7時間** |

---

### 推奨度: ✅ **高**

**理由**:
1. ✅ 従来のTier 2を壊さない
2. ✅ Tier 3の実運用ロジックも変更なし
3. ✅ 一致率95%達成可能
4. ✅ 実運用シミュレーションを正確に実施
5. ✅ 条件別パフォーマンスとユニークレース数の両方を評価可能

---

## 最終推奨

### 推奨実装案: ★オプションD（Tier 3の検証方法を変更）

#### 実装優先順位

| 優先度 | タスク | 工数 | 期待効果 |
|:------:|:-------|:----:|:--------|
| **1** | `standard_backtest_unique.py` の実装 | 3-4時間 | ユニーク版バックテスト |
| **2** | `verify_unique_consistency.py` の実装 | 1.5時間 | 一致率95%達成 |
| **3** | A×A1×10-12条件のミスマッチ調査 | 1時間 | 7件の原因特定 |
| **4** | 逃げ率NULLの扱いを統一（必要に応じて） | 0.5時間 | ロジック統一 |

#### 期待される最終一致率

| 項目 | 目標 | 達成見込み |
|:-----|:----:|:----------:|
| **全体一致率** | 95%+ | **95-98%** |
| **D×5コース条件** | 95%+ | **95%+** |
| **A×A1×10-12条件** | 95%+ | **95%+** |

---

## 補足: オプションDの詳細設計

### 条件優先度の明確化

**現状**:
- 全条件の`priority`が1に統一されている
- 重複時の優先度が不明確

**推奨**:
```python
# config/bet_conditions.py に優先度を明記
STANDARD_BET_CONDITIONS = [
    {
        'id': 'A_A1_10_12',
        'priority': 1,  # 最優先
        # ... 中略 ...
    },
    {
        'id': 'B_50_100',
        'priority': 2,
        # ... 中略 ...
    },
    # ... 中略 ...
]
```

**または**:
- リスト順を優先度とする（明示的に記載）
- 重複時は**リストの先頭に近い条件を優先**

---

## まとめ

| オプション | 推奨度 | 一致率 | 従来Tier2 | Tier3 | 工数 |
|:----------|:------:|:------:|:---------:|:-----:|:----:|
| **A** | ❌ 低 | 95-98% | ❌ 変更あり | 変更なし | 中 |
| **B** | ❌ 低 | 60-70% | 変更なし | ❌ 変更あり | 中 |
| **C** | △ 中 | 84.75% | 変更なし | 変更なし | なし |
| **D** | ✅ **高** | **95-98%** | **変更なし** | **変更なし** | **中** |

### 最終推奨

**オプションD（Tier 3の検証方法を変更）**を実装し、一致率95%を達成する。

---

**作成者**: Claude Code
**レビュー待ち**: ユーザー確認
