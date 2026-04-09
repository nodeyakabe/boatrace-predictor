# システム更新ガイド

**作成日**: 2026-02-16
**対象**: Claude Code（セッション間の引継ぎ用）
**目的**: 予測ロジック・フィルター条件を更新する際の手順と注意点

---

## 📋 目次

1. [更新の種類と対応方法](#更新の種類と対応方法)
2. [購入条件の追加・変更](#購入条件の追加変更)
3. [予測ロジックの更新](#予測ロジックの更新)
4. [新しいフィルター条件の追加](#新しいフィルター条件の追加)
5. [一致率検証の実施](#一致率検証の実施)
6. [トラブルシューティング](#トラブルシューティング)

---

## 更新の種類と対応方法

### ✅ 安全に更新できるもの（自動同期）

| 更新内容 | 対応 | 検証 |
|---------|------|------|
| 購入条件の追加 | `priority`フィールド設定 | 標準テスト推奨 |
| オッズ範囲変更 | 設定変更のみ | 標準テスト推奨 |
| 会場フィルター変更 | 設定変更のみ | 標準テスト推奨 |

### ⚠️ 注意が必要なもの

| 更新内容 | 対応 | 検証 |
|---------|------|------|
| 予測ロジック更新 | 予測データ再生成 | 標準テスト**必須** |
| 新フィルター追加 | Tier 2/3の同期更新 | 一致率検証**必須** |

---

## 購入条件の追加・変更

### 新規条件の追加

**ファイル**: `config/bet_conditions.py`

**必須フィールド**:
```python
{
    'id': 'NEW_CONDITION',           # 条件ID（一意）
    'priority': 11,                   # ★必須: 優先度（1～N）
    'name': '新条件',
    'confidence': 'B',
    'c1_rank': ['B1'],
    'odds_min': 30,
    'odds_max': 50,
    # ... その他の条件フィールド
}
```

**重要**：
- ✅ `priority`フィールドは**必ず設定**
- ✅ 優先度は1（最高）～N（最低）
- ✅ 重複レースは優先度の高い条件が優先される

### 既存条件の変更

**変更可能な項目**（自動同期）：
- `odds_min` / `odds_max`: オッズ範囲
- `venue_filter`: 会場フィルター
- `venue_exclude`: 会場除外
- `month_exclude`: 月除外
- `escape_rate_min`: 逃げ率
- `bias_max`: バイアス指数
- `use_pattern_h`: パターンH使用

**検証手順**：
```bash
# 標準テスト（ユニーク版）で検証
python scripts/backtest/standard_backtest_unique.py --full
```

---

## 予測ロジックの更新

### 影響範囲

**変更されるファイル例**：
- `src/scoring/extended_scorer.py`
- `src/prediction/hierarchical_predictor.py`
- `config/feature_flags.py`

**影響**：
- `race_predictions`テーブルの予測結果が変わる
- 購入対象レースが変わる可能性
- ROI・収支が変化

### 更新手順

#### STEP 1: 予測データの再生成

```bash
# 特定年度の予測データを再生成
python scripts/prediction/fast_prediction_generator.py --year 2024

# または、全年度の再生成（時間がかかる）
python scripts/prediction/fast_prediction_generator.py --start 2020-01-01 --end 2026-01-01
```

#### STEP 2: 標準テストで検証

```bash
# ユニーク版で標準テスト
python scripts/backtest/standard_backtest_unique.py --year 2024

# 6年間フルテスト（推奨）
python scripts/backtest/standard_backtest_unique.py --full
```

**期待結果**：
- ROI・収支が改善（または維持）
- 黒字年数が維持（または増加）

#### STEP 3: 一致率の再確認（推奨）

```bash
# 一致率検証（目標：95%以上を維持）
python scripts/validation/verify_unique_consistency.py --start 2024-01-01 --end 2025-01-01
```

**期待結果**：
- 一致率 ≥ 95%
- 予測ロジックの変更は一致率に影響しない（Tier 2/3の判定ロジックは同じため）

---

## 新しいフィルター条件の追加

### 例：コース別期待順位フィルターの追加

#### STEP 1: config/bet_conditions.py に条件を定義

```python
{
    'id': 'TEST_EXPECTED_RANK',
    'priority': 11,
    'name': 'テスト×期待順位',
    'confidence': 'C',
    'c1_rank': ['B1'],
    'odds_min': 20,
    'odds_max': 30,
    'expected_rank_max': 2.5,  # ★新フィルター
    # ...
}
```

#### STEP 2: Tier 2側の実装（backtest_helpers.py）

**ファイル**: `scripts/backtest/backtest_helpers.py`

**追加箇所**: `get_race_ids_for_condition()` 関数

```python
# 期待順位フィルター
expected_rank_join = ""
expected_rank_clause = ""
if cond.get('expected_rank_max') is not None:
    expected_rank_join = """
    LEFT JOIN course_expected_ranks cer ON r.id = cer.race_id AND cer.pit_number = rp1.pit_number
    """
    expected_rank_clause = f"AND cer.expected_rank <= {cond['expected_rank_max']} "

# SQLクエリに追加
query = f"""
SELECT DISTINCT r.id
FROM races r
...
{expected_rank_join}
WHERE ...
{expected_rank_clause}
"""
```

#### STEP 3: Tier 3側の実装（bet_target_evaluator.py）

**ファイル**: `src/betting/bet_target_evaluator.py`

**追加箇所1**: `evaluate_race()` メソッド（データ取得）

```python
# 期待順位を取得（2026-XX-XX追加）
expected_rank = None
if predicted_first_course == 1:
    first_pred_racer = predictions.get('first_racer_number')
    if first_pred_racer:
        expected_rank = self._get_expected_rank(venue_code_str, predicted_first_course)
```

**追加箇所2**: `evaluate()` メソッド（条件チェック）

```python
# 期待順位チェック（expected_rank_max が指定されている場合）- 2026-XX-XX追加
if 'expected_rank_max' in cond:
    if expected_rank is None:
        continue  # データなしは除外
    if expected_rank > cond['expected_rank_max']:
        continue  # 閾値超えは除外
```

**追加箇所3**: ヘルパーメソッド

```python
def _get_expected_rank(self, venue_code: str, course: int) -> Optional[float]:
    """会場×コース別の期待順位を取得"""
    if not self.conn:
        return None

    cursor = self.conn.cursor()
    cursor.execute("""
        SELECT expected_rank
        FROM course_expected_ranks
        WHERE venue_code = ? AND course = ?
    """, (venue_code, course))

    row = cursor.fetchone()
    return row[0] if row else None
```

#### STEP 4: 一致率検証（必須）

```bash
# 一致率検証
python scripts/validation/verify_unique_consistency.py --start 2024-01-01 --end 2025-01-01
```

**目標**：
- 一致率 ≥ 95%
- もし95%未満になったら、Tier 2/3の実装に差異があるため修正が必要

---

## 一致率検証の実施

### 検証コマンド

```bash
# 短期間テスト（2024年のみ）
python scripts/validation/verify_unique_consistency.py --start 2024-01-01 --end 2025-01-01

# 6年間フル検証
python scripts/validation/verify_unique_consistency.py --start 2020-01-01 --end 2026-01-01
```

### 結果の読み方

**成功例**：
```
Match rate: 95.48%

[OK] Match rate >= 95% achieved!
```

**失敗例**：
```
Match rate: 87.50%

[WARNING] Match rate 87.50% < 95%

Investigating mismatches...

[Only Tier 2] 450 races
[Only Tier 3] 30 races
```

### 一致率が低い場合の対応

#### Only Tier 2が多い場合

**原因**：
- Tier 2が条件にマッチしているが、Tier 3が除外している
- Tier 3側にTier 2にない追加条件がある

**確認箇所**：
- `bet_target_evaluator.py`の`evaluate()`メソッド
- Tier 2のSQLクエリで取得できるレースが、Tier 3で除外されていないか

#### Only Tier 3が多い場合

**原因**：
- Tier 3が条件にマッチしているが、Tier 2が除外している
- Tier 2のSQLクエリに漏れがある

**確認箇所**：
- `backtest_helpers.py`の`get_race_ids_for_condition()`
- Tier 3でマッチするレースが、Tier 2のSQLでも取得できるか

---

## トラブルシューティング

### 問題1: 一致率が95%未満

**症状**：
```
Match rate: 87.50% < 95%
```

**原因**：
- Tier 2とTier 3の実装に差異がある

**対処法**：
1. Only Tier 2とOnly Tier 3のサンプルrace_idを確認
2. Tier 2のSQLとTier 3のPythonチェックを比較
3. 差異を特定して修正
4. 一致率を再確認

### 問題2: 標準テスト結果が大幅に変化

**症状**：
```
ROI: 100.0% → 150.0% (前回比 +50.0pt)
```

**原因**：
- 予測ロジック更新により予測結果が大幅に変化
- または、条件定義に誤りがある

**対処法**：
1. 変更内容を確認（何を変更したか）
2. 予測データが正しく再生成されているか確認
3. config/bet_conditions.pyに誤りがないか確認
4. 意図的な改善か、バグかを判断

### 問題3: 新フィルターが機能しない

**症状**：
- 新フィルターを追加したが、購入件数が変わらない

**原因**：
- Tier 2またはTier 3の実装が不完全

**対処法**：
1. Tier 2（backtest_helpers.py）のSQLクエリを確認
2. Tier 3（bet_target_evaluator.py）のチェックロジックを確認
3. データが存在するか確認（DBに新フィルター用のデータがあるか）
4. 一致率検証でTier 2/3の差異を確認

---

## チェックリスト（更新時）

### 購入条件の追加・変更

- [ ] config/bet_conditions.pyに`priority`フィールドを設定
- [ ] 標準テストを実行（`standard_backtest_unique.py --full`）
- [ ] ROI・収支が妥当か確認

### 予測ロジックの更新

- [ ] 予測データを再生成（`fast_prediction_generator.py`）
- [ ] 標準テストを実行（`standard_backtest_unique.py --full`）
- [ ] ROI・収支が改善（または維持）しているか確認
- [ ] 一致率検証を実施（推奨、`verify_unique_consistency.py`）
- [ ] 一致率 ≥ 95%を確認

### 新フィルター条件の追加

- [ ] config/bet_conditions.pyに新フィルターを定義
- [ ] backtest_helpers.pyにSQLクエリを追加
- [ ] bet_target_evaluator.pyにチェックロジックを追加
- [ ] 一致率検証を実施（**必須**、`verify_unique_consistency.py`）
- [ ] 一致率 ≥ 95%を確認
- [ ] 標準テストを実行
- [ ] ROI・収支が改善しているか確認

---

## 関連ドキュメント

- [HANDOVER.md](../HANDOVER.md) - セッション間の引継ぎ情報
- [VALIDATION_WORKFLOW.md](VALIDATION_WORKFLOW.md) - 3段階検証フロー
- [config/bet_conditions.py](../../config/bet_conditions.py) - 購入条件定義
- [scripts/backtest/backtest_helpers.py](../../scripts/backtest/backtest_helpers.py) - Tier 2共通関数
- [src/betting/bet_target_evaluator.py](../../src/betting/bet_target_evaluator.py) - Tier 3実装

---

## まとめ

**安定したシステムアーキテクチャ**：
- ✅ config/bet_conditions.pyを中心とした一元管理
- ✅ Tier 2（バックテスト）とTier 3（実運用）が同じ条件定義を参照
- ✅ 一致率95.48%を達成（2026-02-16時点）

**今後の更新**：
- 通常の条件変更：自動同期（検証推奨）
- 予測ロジック更新：予測データ再生成 + 標準テスト必須
- 新フィルター追加：Tier 2/3の同期 + 一致率検証必須

**目標**：
- 一致率 ≥ 95%を常に維持
- 実運用（Tier 3）との乖離を最小化
