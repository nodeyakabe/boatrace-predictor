# 計算ミス全数調査報告

**作成日**: 2026-01-30

---

## 1. 計算ミス発見ファイル一覧

| 優先度 | ファイル | 箇所数 | 用途 | 不採用案への影響 | 修正状況 |
|:-----:|---------|:-----:|------|----------------|---------|
| 1 | `scripts/analysis/analyze_b_50_100_details.py` | 1 | B×50-100条件詳細分析 | RJ-1関連 | 未修正 |
| 2 | `scripts/analysis/analyze_b_50_100_details_v2.py` | 1 | 同上（v2版） | RJ-1関連 | 未修正 |
| 3 | `scripts/analysis/analyze_bx50_100_miss_patterns.py` | 2 | B×50-100不的中パターン分析 | RJ-1関連 | 未修正 |
| 4 | `scripts/analysis/analyze_bx50_100_comprehensive.py` | 1 | B×50-100総合分析 | RJ-1関連 | 未修正 |
| 5 | `scripts/analysis/analyze_meta_index_effect.py` | 3 | メタ指数効果検証 | RJ-メタ指数関連 | 未修正 |
| 6 | `src/ml/race_selector.py` | 1 | レース選別モデル（訓練用） | 直接の不採用案なし | 未修正 |

**合計**: 9箇所、6ファイル

---

## 2. ファイル別詳細分析

### 2.1 `scripts/analysis/analyze_b_50_100_details.py`（優先度1）

**問題箇所**: 95行目
```sql
JOIN trifecta_odds t ON r.id = t.race_id AND t.combination = '1-2-3'
```

**影響**:
- B×50-100条件の詳細分析に使用
- オッズ帯別・級別・年度別のROI分析結果が全て誤り
- **不採用案RJ-1の判定に直接影響した可能性**

**正しいクエリ**:
```sql
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(p.pit_number AS TEXT) || '-' ||
                        CAST(p2.pit_number AS TEXT) || '-' ||
                        CAST(p3.pit_number AS TEXT)
```

### 2.2 `scripts/analysis/analyze_b_50_100_details_v2.py`（優先度2）

**問題箇所**: 89行目
- 同上の問題（analyze_b_50_100_details.pyのv2版）

### 2.3 `scripts/analysis/analyze_bx50_100_miss_patterns.py`（優先度3）

**問題箇所**: 99行目、408行目
```sql
WHERE combination = '1-2-3'
```

**影響**:
- 不的中パターン分析で使用
- 予測組み合わせではなく「1-2-3」固定でオッズ取得
- 購入条件の効果分析が誤り

### 2.4 `scripts/analysis/analyze_bx50_100_comprehensive.py`（優先度4）

**問題箇所**: 108行目
- B×50-100条件の総合分析
- advance/beforeの両予測タイプで分析
- 年度別・会場別統計が誤り

### 2.5 `scripts/analysis/analyze_meta_index_effect.py`（優先度5）

**問題箇所**: 110行目、269行目、326行目
```sql
JOIN trifecta_odds t ON rp.race_id = t.race_id AND t.combination = '1-2-3'
```

**影響**:
- メタ指数（安定度エントロピー、上位独占率）の効果検証に使用
- **不採用案「メタ指数フィルター」の判定に直接影響**
- ROI計算が誤っているため、実際の効果が不明

### 2.6 `src/ml/race_selector.py`（優先度6）

**問題箇所**: 241行目
```sql
AVG(CASE WHEN res.combination = '1-2-3' THEN 1.0 ELSE 0.0 END) as jun決着率
```

**影響**:
- レース選別モデル（Stage1）の訓練データ生成に使用
- 「1-2-3決着率」という特徴量を計算
- **この場合は「枠番1-2-3の結果」を見ているため、問題なし**
- results.combinationは実際の決着組み合わせなので正常

---

## 3. 正常なファイル

### 3.1 `scripts/analysis/analyze_confidence_hit_patterns.py`

**状態**: 正常

**使用クエリ**:
```sql
JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
```
- `pred_combo`は予測組み合わせを動的に生成
- 正しく予測ベースのオッズを取得している

### 3.2 `scripts/analysis/analyze_confidence_deep_dive.py`

**状態**: 正常

**使用クエリ**:
```sql
JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
```
- 信頼度×オッズ帯の詳細分析
- 正しく予測ベースのオッズを取得

### 3.3 `scripts/analysis/comprehensive_confidence_analysis.py`

**状態**: 正常

**使用クエリ**: 予測組み合わせを動的に生成してJOIN
- 全条件マトリクス分析
- 正しい実装

### 3.4 `scripts/backtest/standard_backtest.py`

**状態**: 正常（確認済み）
- 標準バックテストは正しい実装
- 予測ベースでオッズを取得

---

## 4. 修正が必要なファイル（優先度順）

### 最優先（不採用案の判定に直接影響）

- [ ] `analyze_meta_index_effect.py` - メタ指数フィルター（RJ-メタ指数）の再検証必須
- [ ] `analyze_b_50_100_details.py` - B×50-100条件の再検証
- [ ] `analyze_b_50_100_details_v2.py` - 同上
- [ ] `analyze_bx50_100_miss_patterns.py` - B×50-100不的中パターン再分析

### 中優先度（参考分析に使用）

- [ ] `analyze_bx50_100_comprehensive.py` - 総合分析の再実行

### 低優先度（直接の不採用案なし）

- [x] `src/ml/race_selector.py` - **修正不要**（この場合は正常）

---

## 5. 修正計画

| ファイル | 修正箇所 | 工数 | 実施タイミング |
|---------|---------|:---:|:------------:|
| analyze_meta_index_effect.py | 3箇所 | 30分 | 即時 |
| analyze_b_50_100_details.py | 1箇所 | 15分 | 即時 |
| analyze_b_50_100_details_v2.py | 1箇所 | 15分 | 即時 |
| analyze_bx50_100_miss_patterns.py | 2箇所 | 20分 | 即時 |
| analyze_bx50_100_comprehensive.py | 1箇所 | 15分 | 即時 |

**合計工数**: 約1.5時間

---

## 6. 補足: ドキュメント内の警告記述

以下のドキュメントにも「1-2-3固定オッズ」の例が記載されています（教育目的）:

| ファイル | 行番号 | 用途 |
|---------|:-----:|------|
| CLAUDE.md | 83行目 | 「誤った例」として記載 |
| docs/残タスク一覧.md | 710行目 | 問題の説明として記載 |
| docs/improvement_attempts/REJECTED_IDEAS.md | 265行目 | 不採用理由の説明 |
| docs/guides/SQL_QUERY_SAMPLES.md | 768行目 | クエリサンプル（要確認） |
| docs/architecture/TABLE_PURPOSE.md | 95行目 | テーブル構造説明 |

これらは教育・説明目的のため、修正不要。

---

# 「1-2-3固定オッズ」問題の影響分析

## 1. 影響を受けた不採用案（超高優先度）

### RJ-1: A×50倍+等 信頼度条件

| 項目 | 内容 |
|------|------|
| **不採用理由** | 計算ミス疑惑（分析ROI 396% vs 実テストROI 58.4%） |
| **使用スクリプト** | 不明（直接特定できず） |
| **問題** | 分析時に「1-2-3固定オッズ」を使用した可能性 |
| **乖離** | 約338pt（396% → 58.4%） |
| **再検証の期待** | 正しい計算でも赤字の可能性が高い（標準バックテストで確認済み） |
| **優先度** | ★★★☆☆（再検証済みだが、分析方法の確認は必要）|

**詳細**:
- REJECTED_IDEAS.mdによると、`standard_backtest.py`での実テスト結果がROI 58.4%
- 分析スクリプトの計算ミスが原因と特定済み
- **再検証の必要性**: 低（実テストで赤字確定）

### RJ-メタ指数: メタ指数フィルター

| 項目 | 内容 |
|------|------|
| **不採用理由** | 仕様と実態の乖離、効果なし |
| **使用スクリプト** | `analyze_meta_index_effect.py`（3箇所で計算ミス） |
| **問題** | ROI計算に「1-2-3固定オッズ」を使用 |
| **影響** | 安定度エントロピー、上位独占率のROI分析が全て誤り |
| **再検証の期待** | ROI傾向が逆転する可能性あり |
| **優先度** | ★★★★★（最優先で再検証必要）|

**詳細**:
- analyze_meta_index_effect.pyの3箇所で「1-2-3固定オッズ」を使用
- 安定度エントロピー別ROI、上位独占率別ROI、複合条件ROIが全て誤り
- **再検証の必要性**: 高（スクリプト修正後に再実行必須）

---

## 2. 影響を受けた可能性がある案件（高優先度）

### B×50-100条件の詳細分析

| 項目 | 内容 |
|------|------|
| **関連スクリプト** | analyze_b_50_100_details.py, analyze_b_50_100_details_v2.py |
| **問題** | オッズ帯別・級別・年度別の分析結果が誤り |
| **影響** | B×50-100条件の改善検討に使用された可能性 |
| **再検証の期待** | 異なるオッズ帯が有望になる可能性 |
| **優先度** | ★★★★☆（スクリプト修正後に再分析推奨）|

---

## 3. 影響がない/軽微な案件

### RJ-0-0: 連帯率フィルター（Motor40%+）

- **判定**: 影響なし
- **理由**: `standard_backtest.py`での実テスト結果に基づいて不採用判定
- 分析スクリプトとの乖離はあるが、実テスト結果は信頼できる

### RJ-0-1: motor_second_rate + venue_affinity

- **判定**: 影響なし
- **理由**: ExtendedScorerの重み調整テスト
- オッズ計算ではなく、スコアリングの検証

### RJ-逃げ率/会場攻撃率スコアリング

- **判定**: 影響なし
- **理由**: 予測精度（的中数）の比較であり、ROI計算に依存しない

### RJ-Bias Index / Error Variance

- **判定**: 影響なし
- **理由**: `standard_backtest.py`での実テスト結果に基づいて不採用判定

---

## 4. 再検証の実施順序

| 順位 | 案件/スクリプト | 期待される改善 | 工数 |
|:---:|--------|------------|:---:|
| 1 | `analyze_meta_index_effect.py`修正 + 再実行 | メタ指数の真の効果が判明 | 1h |
| 2 | `analyze_b_50_100_details.py`修正 + 再実行 | B×50-100の最適オッズ帯が判明 | 0.5h |
| 3 | メタ指数フィルター再検証（標準バックテストで） | 採用可否の最終判定 | 1h |

**合計工数**: 約2.5時間

---

# 不採用案の「目星付け」と再検証計画

## 1. 超高優先度（計算ミス疑惑）

### メタ指数フィルター

| 項目 | 内容 |
|------|------|
| **当時の分析** | 安定度エントロピー<0.85でROI 68.8%、不安定(>=0.92)でROI 88.8% |
| **当時の判定** | 「仕様書の想定と逆、安定した選手がROI悪い」 |
| **問題の原因** | `analyze_meta_index_effect.py`で「1-2-3固定オッズ」使用 |
| **再検証方法** | スクリプト修正後に再実行 |
| **期待効果** | ROI傾向が逆転する可能性（安定選手が有利になる可能性） |
| **採用基準** | 4/6年黒字、ROI 100%以上の改善 |
| **工数** | 1.5h |

**再検証コマンド**:
```bash
# 1. スクリプト修正（手動）
# 2. 再実行
python scripts/analysis/analyze_meta_index_effect.py

# 3. 有望であれば標準バックテストで確認
python scripts/backtest/standard_backtest.py --full
```

---

## 2. 高優先度（サンプル数不足の可能性）

### B×A1条件の改善

| 項目 | 内容 |
|------|------|
| **当時の分析** | B×A1 ROI 97.7%（惜しい赤字） |
| **当時の判定** | 会場限定で4/6年黒字達成の可能性 |
| **再検証方法** | `analyze_b_50_100_details.py`修正後に再実行 |
| **期待効果** | 最適オッズ帯・会場の特定 |
| **工数** | 0.5h |

---

## 3. 中優先度（年度依存性の可能性）

### Bias Index / Error Variance

- **当時の判定**: 年度間で傾向逆転、2025年で効果が逆
- **再検証不要**: 標準バックテストで確認済み、計算ミスの影響なし

---

## 4. 低優先度（ロジック的に困難）

### コース強制化

- **当時の判定**: 精度+5.6pt、ROI-51pt
- **再検証不要**: ロジックの問題（高配当チャンスを逃す）

### モンテカルロシミュレーション

- **当時の判定**: 全指標悪化
- **再検証不要**: 物理モデルの限界

---

## 5. 再検証の実施スケジュール

### Phase 1（即時）: 計算ミス修正

1. `analyze_meta_index_effect.py`の3箇所を修正
2. `analyze_b_50_100_details.py`の1箇所を修正
3. `analyze_b_50_100_details_v2.py`の1箇所を修正
4. `analyze_bx50_100_miss_patterns.py`の2箇所を修正
5. `analyze_bx50_100_comprehensive.py`の1箇所を修正

### Phase 2（修正後）: 再分析実行

1. `python scripts/analysis/analyze_meta_index_effect.py`
2. `python scripts/analysis/analyze_b_50_100_details.py`

### Phase 3（有望な結果が出た場合）: 標準バックテスト

```bash
python scripts/backtest/standard_backtest.py --full
```

---

## 6. 期待される「宝の山」

| 案件 | 現状判定 | 再検証期待 | 改善可能性 |
|------|---------|---------|----------|
| メタ指数フィルター | 効果なし | ROI傾向逆転 | ★★★★☆ |
| B×50-100最適化 | 部分黒字 | 最適条件特定 | ★★★☆☆ |

**注意**:
- 「宝の山」はあくまで可能性であり、再検証後も赤字の場合がある
- 標準バックテスト（`standard_backtest.py --full`）での最終確認が必須

---

## 7. 結論

### 計算ミスの影響

1. **直接影響を受けた不採用案**: メタ指数フィルター（超高優先度で再検証必要）
2. **間接影響**: B×50-100条件の詳細分析
3. **影響なし**: 標準バックテストで判定された案件（RJ-1含む）

### 次のアクション

1. **即時**: 5ファイル、9箇所の計算ミスを修正
2. **修正後**: メタ指数分析を再実行
3. **有望な場合**: 標準バックテストで最終判定

**工数見積もり**: 修正1.5h + 再分析1h + 検証1h = 約3.5時間
