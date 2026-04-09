# 波高フィルター実装ガイド

**実装日**: 2026-04-06  
**実装バージョン**: v2.40.0以降  
**状態**: 実装済み（現在の全条件には適用していない）

---

## 概要

`BetTargetEvaluator` と各バックテストスクリプトに波高フィルターを追加した。  
現在の全条件は従来通り動作（購入件数に変化なし）。将来の条件定義で `wave_height_max` / `wave_height_min` キーを指定することで有効になる。

**主な用途**:
- `wave_height_max`: 荒れレースを除外する（穏やかレース専用条件）
- `wave_height_min`: 荒れレース専用の条件を作る（将来拡張）

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/betting/bet_target_evaluator.py` | `evaluate()`に`wave_height`引数追加・フィルターチェック追加・`evaluate_race()`でrace_dataから取得して渡す |
| `scripts/backtest/backtest_helpers.py` | `get_race_ids_for_condition()`にwave_height JOINと句を追加 |
| `scripts/backtest/standard_backtest.py` | `build_condition_query()`にwave_height JOINと句を追加 |

**未対応（将来対応）**:
- `scripts/backtest/fast_backtest.py`: prediction_featuresテーブルベースのため構造が異なる。wave_height条件を実際に使い始める際に対応が必要。

---

## 条件定義の使い方

```python
# config/bet_conditions.py での条件定義例

# 荒れレース除外（メイン用途）
{
    'id': 'C_TSU_B1_30_50',
    'name': '津×C×B1×30-50（穏やかレース）',
    'confidence': 'C',
    'c1_rank': ['B1'],
    'odds_min': 30,
    'odds_max': 50,
    'venue_filter': [9],
    'use_pattern_h': False,
    'wave_height_max': 9,  # ← 波高10cm以上を除外（5-9cmまで許容）
}

# 荒れレース専用（将来の拡張用途）
{
    'id': 'ROUGH_RACE_SPECIAL',
    'name': '荒れレース専用条件',
    'confidence': 'C',
    'c1_rank': ['B1'],
    'odds_min': 30,
    'odds_max': 80,
    'use_pattern_h': False,
    'wave_height_min': 10,  # ← 波高10cm以上のレースのみ
}
```

---

## フィルターロジック詳細

### wave_height_max（荒れレース除外）

| wave_heightの状態 | 結果 |
|:---:|:---:|
| `None`（データなし） | **通過**（除外しない） |
| `<= max値` | **通過** |
| `> max値` | **除外** |

波高データがないレースは通過させる。データ欠損で購入機会を失わない設計。

### wave_height_min（荒れレース専用）

| wave_heightの状態 | 結果 |
|:---:|:---:|
| `None`（データなし） | **除外** |
| `< min値` | **除外** |
| `>= min値` | **通過** |

波高データがないレースは除外。「荒れている」と確認できないレースは対象外。

---

## 実装コード（参照用）

### bet_target_evaluator.py（evaluate()内フィルターチェック）

```python
# 波高フィルターチェック（2026-04-06追加）
if 'wave_height_max' in cond:
    if wave_height is not None and wave_height > cond['wave_height_max']:
        continue
if 'wave_height_min' in cond:
    if wave_height is None or wave_height < cond['wave_height_min']:
        continue
```

### backtest_helpers.py / standard_backtest.py（SQL生成）

```python
wave_height_join = ""
wave_height_clause = ""
if cond.get('wave_height_max') is not None or cond.get('wave_height_min') is not None:
    wave_height_join = "LEFT JOIN race_conditions rc ON r.id = rc.race_id"
    if cond.get('wave_height_max') is not None:
        wave_height_clause += f"AND (rc.wave_height IS NULL OR rc.wave_height <= {cond['wave_height_max']}) "
    if cond.get('wave_height_min') is not None:
        wave_height_clause += f"AND rc.wave_height IS NOT NULL AND rc.wave_height >= {cond['wave_height_min']} "
```

---

## 波高データの分布（参考）

2024-2025年の `race_conditions` テーブルでの実測値:

| 波高帯 | 件数 | 割合 |
|:---:|:---:|:---:|
| 0-4cm | 94,543 | 85.7% |
| 5-9cm | 12,732 | 11.5% |
| 10-14cm | 814 | 0.7% |
| 15cm以上 | 1,003 | 0.9% |
| 合計 | 109,092 | 100% |

`wave_height_max: 9` を設定すると、**全レースの約1.6%（10cm以上）を除外**することになる。

---

## B3（wave_height補正改善）との関係

B3（`beforeinfo_scorer.py`で波高スコア補正）は不採用（2026-04-06）。  
**理由**: 高波高 → スコア低下 → confidence低下 → 購入フィルター外れという構造上、波高補正が購入判定に到達しない。

本ガイドの実装（波高フィルター）は**購入条件フィルター段階**で波高を見るため、この構造問題を回避している。  
ただし現在の条件にはどれも `wave_height_max`/`wave_height_min` を設定していないため、実際の効果検証はこれから。

---

## 将来の荒れレース条件を追加する際の手順

1. `quick_condition_test.py` でTier1テスト（wave_height_min/max付き）
2. Tier1合格（ROI 130%+/1/2年黒字/50件+）したら `bet_conditions.py` に追加
3. `standard_backtest_unique.py --full` でTier2テスト
4. Tier2合格（ROI 130%+/4/6年黒字/90件+）で本採用

⚠️ **fast_backtest.py は wave_height フィルター未対応**。  
wave_height条件を追加する際は `standard_backtest_unique.py` での確認のみ有効。  
fast_backtest.pyへの対応は条件追加時に実施すること。
