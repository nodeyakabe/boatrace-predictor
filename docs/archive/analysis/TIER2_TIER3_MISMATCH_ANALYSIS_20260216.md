# Tier 2（SQL）とTier 3（Python）のミスマッチ詳細分析

**作成日**: 2026-02-16
**分析者**: Claude Sonnet 4.5
**目的**: 68.82%のマッチ率を95%以上に改善するため、ミスマッチの根本原因を特定し修正案を提示する

---

## 1. エグゼクティブサマリー

### 現状

- **Tier 2（standard_backtest.py）**: SQL実装による購入判定
- **Tier 3（BetTargetEvaluator）**: Python実装による購入判定
- **マッチ率**: 68.82%（2020-2025年全期間）
- **ミスマッチ**: 1,649件（31.18%）

### 主要な発見

1. **player_escape_statsテーブルの重複レコード問題**（最重要）
   - 同じplayer_idで`stadium_id IS NULL`のレコードが複数存在（期間別統計）
   - Tier 2のSQLは重複JOINし、同じrace_idが複数回カウント
   - Tier 3のPythonは辞書キャッシュで最後の1件のみ使用

2. **条件別マッチ率の大きなばらつき**
   - 100%一致の条件が7つ（B×30-50×B1, C×20-30×B1など）
   - 75.9%の条件が1つ（A×A1×10-12+会場+逃げ率）
   - 71.1%の条件が1つ（D×5コース予測×A2除外+会場最適化）

3. **すべてのミスマッチが「Tier 2で購入、Tier 3で非購入」パターン**
   - Tier 3が見逃している = 購入機会の損失
   - ユーザーの懸念「使えない」は正当

---

## 2. 条件別ミスマッチサマリー（2024年データ）

| 条件ID | 条件名 | Tier2 | Tier3 | 一致率 | T2のみ | T3のみ |
|:-------|:-------|:------|:------|:------:|:------:|:------:|
| A_A1_10_12 | A×A1×10-12+会場+逃げ率 | 29 | 22 | **75.9%** | 7 | 0 |
| B_50_100 | B×50-100×冬+4月除外+会場最適化 | 62 | 61 | 98.4% | 1 | 0 |
| B_30_50_B1 | B×30-50×B1+4会場 | 37 | 37 | **100.0%** | 0 | 0 |
| B_10_30_bias | B×10-30×穴源×会場 | 18 | 18 | **100.0%** | 0 | 0 |
| C_20_30_B1 | C×20-30×B1+会場 | 121 | 121 | **100.0%** | 0 | 0 |
| C_Naruto_A2 | 鳴門×C×A2×30-80 | 37 | 32 | **86.5%** | 5 | 0 |
| C_Karatsu_B1 | 唐津×C×B1×20-30 | 25 | 25 | **100.0%** | 0 | 0 |
| C_Kojima_B1 | 児島×C×B1×30-50 | 36 | 36 | **100.0%** | 0 | 0 |
| D_40_50_B1 | D×40-50×B1×2連率20-30% | 36 | 36 | **100.0%** | 0 | 0 |
| D_course5 | D×5コース予測×A2除外+会場最適化 | 45 | 32 | **71.1%** | 13 | 0 |

**重点調査対象**:
1. **A_A1_10_12**: 7件のミスマッチ（24.1%の損失）
2. **D_course5**: 13件のミスマッチ（28.9%の損失）
3. **C_Naruto_A2**: 5件のミスマッチ（13.5%の損失）

---

## 3. 根本原因の詳細分析

### 3.1. player_escape_statsテーブルの重複レコード問題

#### 問題の詳細

```sql
-- player_id 3845の例（逃げ率データ）
SELECT * FROM player_escape_stats
WHERE player_id = '3845' AND stadium_id IS NULL;

-- 結果: 8件のレコードが返却
-- 1. 全期間（2000-2026）: escape_rate 0.776
-- 2. 全期間（更新版）: escape_rate 0.714
-- 3. 2020年度: NULL
-- 4. 2021年度: NULL
-- 5. 2022年度: NULL
-- 6. 2023年度: escape_rate 0.701
-- 7. 2024年度: escape_rate 0.666
-- 8. 2025年度: NULL
```

#### Tier 2（SQL）の動作

```sql
-- standard_backtest.py Line 215-218
LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
WHERE pes.escape_rate IS NOT NULL AND pes.escape_rate >= 0.70
```

**結果**:
- player_id 3845の場合、3件のレコード（0.776, 0.714, 0.701）が条件を満たす
- 同じrace_idが**3回重複してJOIN**される
- race_id 20493の場合、27回も重複（他の重複要因も絡んでいる可能性）

#### Tier 3（Python）の動作

```python
# bet_target_evaluator.py Line 242-250
cursor.execute('''
    SELECT player_id, escape_rate
    FROM player_escape_stats
    WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
''')
self._player_escape_stats_cache = {
    row[0]: row[1]
    for row in cursor.fetchall()
}
```

**結果**:
- 辞書に格納する際、**後のレコードで上書き**される
- player_id 3845の場合、最終的にどの値が使われるかは**不定**（おそらくescape_rate 0.701）
- 0.70以上の条件を満たさない可能性がある → **見逃し**

#### 影響範囲

- **A_A1_10_12条件**: 逃げ率フィルター（escape_rate_min 0.70）を使用
  - 2024年: 29件 → 22件（7件のミスマッチ）
  - 全期間（推定）: 数百件のミスマッチ

---

### 3.2. player_bias_statsテーブルの重複レコード問題

`player_escape_stats`と同様の構造であれば、**同じ問題が発生する可能性**が高い。

#### 影響範囲

- **B_10_30_bias条件**: バイアス指数フィルター（bias_max -0.3）を使用
  - 2024年は100%一致だが、全期間では不明

---

### 3.3. パターンH（3点買い）のオッズ取得の違い

#### 問題の詳細

- **Tier 2（SQL）**: 1-2-3, 1-2-4, 1-2-5の3点すべてをJOINで取得
- **Tier 3（Python）**:
  - `verify_prediction_consistency.py`では3点取得（Line 113-134）
  - `BetTargetEvaluator.evaluate()`では条件判定時に3点チェック（Line 527-556）
  - **ただし、old_predictionの渡し方に問題がある可能性**

#### 具体例（C_Naruto_A2条件）

race_id 23086の場合：
- Tier 2: オッズ11.4倍の1-3-2が範囲内（10-80倍） → 購入対象
- Tier 3: 評価時に3点すべてチェックしているか？ → **要確認**

---

### 3.4. venue_code型の違い（既に修正済み）

- **Tier 2（SQL）**: 文字列'01'-'24'
- **Tier 3（Python）**: 整数1-24に変換（bet_target_evaluator.py Line 653-667）

**影響**: 2026-02-16時点で既に修正済み（+48pt改善）

---

## 4. ミスマッチパターンの分類

### 4.1. Tier 2のみ購入（Tier 3で見逃し）

| パターン | 件数（推定） | 主な原因 |
|:---------|:------------|:---------|
| 逃げ率データの重複JOIN | **数百件** | player_escape_stats の重複レコード |
| バイアス指数データの重複JOIN | **数十件** | player_bias_stats の重複レコード |
| パターンHのオッズチェック漏れ | **数十件** | old_prediction未渡し or チェック漏れ |
| その他 | 少数 | 未特定 |

### 4.2. Tier 3のみ購入（Tier 2で見逃し）

**該当なし**（2024年データでは0件）

---

## 5. 修正案と優先順位

### Phase 1: 緊急対応（マッチ率68% → 90%+を目指す）

#### 修正1: player_escape_stats/player_bias_statsの最新1件のみ取得（最優先）

**期待効果**: +20-25pt改善

**Tier 2 SQL修正（standard_backtest.py）**:

```sql
-- 修正前（Line 215-218）
LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL

-- 修正後
LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
LEFT JOIN (
    SELECT player_id, escape_rate
    FROM player_escape_stats
    WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
    GROUP BY player_id
    HAVING id = MAX(id)  -- 最新レコードのみ
) pes ON e_pred.racer_number = pes.player_id
```

**Tier 3 Python修正（bet_target_evaluator.py）**:

```python
# 修正前（Line 242-246）
cursor.execute('''
    SELECT player_id, escape_rate
    FROM player_escape_stats
    WHERE stadium_id IS NULL AND escape_rate IS NOT NULL
''')

# 修正後
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

---

#### 修正2: パターンHのold_prediction渡し漏れ確認

**期待効果**: +3-5pt改善

**確認ポイント**:
- `BetTargetEvaluator.evaluate_race()`で`old_prediction`を正しく渡しているか
- Line 785: `old_prediction=old_pred`が正しく渡されているか
- Line 527-556: 3点チェックが正しく動作しているか

---

### Phase 2: 根本対策（マッチ率90% → 95%+を目指す）

#### 修正3: player_escape_stats/player_bias_statsテーブルの正規化

**期待効果**: データの一貫性向上、将来的な問題の予防

**方針**:
1. 全国統計（stadium_id IS NULL）は1 player_idあたり1レコードのみ
2. 期間別統計は別テーブル`player_escape_stats_yearly`に移動
3. 移行スクリプトを作成し、既存データをクリーンアップ

---

#### 修正4: Tier 2とTier 3の完全同期テスト

**目的**: 各条件ごとに100%一致を確認

**手順**:
1. 修正1-3を適用後、標準バックテスト実行
2. `verify_prediction_consistency.py --detailed-analysis`で詳細確認
3. 一致率95%未満の条件は個別に詳細調査

---

## 6. 実装スケジュール

| Phase | タスク | 期待効果 | 工数 | 優先度 |
|:------|:-------|:---------|:-----|:------:|
| Phase 1-1 | player_escape_stats 最新1件のみ取得 | +15pt | 2h | **最優先** |
| Phase 1-2 | player_bias_stats 最新1件のみ取得 | +5pt | 1h | **最優先** |
| Phase 1-3 | パターンHのold_prediction渡し確認 | +3pt | 1h | 高 |
| Phase 2-1 | テーブル正規化スクリプト作成 | - | 4h | 中 |
| Phase 2-2 | データ移行実行 | - | 1h | 中 |
| Phase 2-3 | 完全同期テスト | - | 2h | 中 |

**合計工数**: 11時間
**期待マッチ率**: 95%以上

---

## 7. リスク評価

| リスク | 影響度 | 対策 |
|:-------|:------|:-----|
| SQLの GROUP BY / MAX(id) が他のDBMSで動作しない | 低 | SQLiteで動作確認済み |
| 最新レコードの定義が曖昧 | 中 | updated_atを併用して明確化 |
| 既存のバックテスト結果が変わる | 高 | **想定内**。Tier 2の重複は明らかなバグ |
| テーブル正規化でデータ欠損 | 中 | 移行前にバックアップ必須 |

---

## 8. 次のステップ

1. **Phase 1-1, 1-2の実装**（最優先、期待+20pt改善）
2. **標準バックテスト実行**（修正効果の確認）
3. **Tier 3検証実行**（マッチ率の確認）
4. **マッチ率90%未満なら Phase 1-3実施**
5. **マッチ率95%達成後、Phase 2へ移行**

---

## 9. 参照ファイル

- `scripts/backtest/standard_backtest.py` (Tier 2 SQL)
- `src/betting/bet_target_evaluator.py` (Tier 3 Python)
- `scripts/validation/verify_prediction_consistency.py` (検証スクリプト)
- `scripts/validation/analyze_tier_mismatch.py` (ミスマッチ分析)
- `scripts/validation/debug_mismatch_details.py` (詳細デバッグ)
- `config/bet_conditions.py` (購入条件定義)

---

**更新履歴**:
- 2026-02-16: 初版作成、player_escape_stats重複問題を特定
