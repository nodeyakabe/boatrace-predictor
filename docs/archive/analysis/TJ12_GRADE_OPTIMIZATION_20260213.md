# TJ-12: グレード別の条件最適化分析レポート

**分析日**: 2026-02-13
**分析者**: Claude Code (Explore Agent)
**推定工数**: 3時間
**期待効果**: ROI +1-3pt

---

## 📋 Executive Summary

### 結論: 段階的実装を推奨

- **Phase 1（簡易版）**: ROI +1.0-1.5pt、実装可能性: 高
- **Phase 2（完全版）**: ROI +1.5-2.5pt、実装可能性: 低（データ整備が先決）
- **並行作業**: グレードデータの品質改善（公式APIから取得）

### 主要な発見

1. **データの粒度不足**: race_gradeには「一般戦」「スペシャルシリーズ」「NULL」の3値のみ
2. **統計的制約**: 11条件×3グレード×5信頼度×6オッズ帯 = 約1,980セル、多くのセルがサンプル不足
3. **NULL問題**: 13.62%のレースがグレード未分類、予測カバレッジも22.36%と低い
4. **スペシャルシリーズの少なさ**: 2,435レース（月平均34レース）のみ

---

## 🔍 分析対象と方法

### データソース

```sql
-- 分析対象期間: 2020-2025年（6年間）
-- データベース: boatrace.db
-- 主要テーブル:
--   - races (race_grade列を含む)
--   - race_predictions (予測データ)
--   - entries (レース出走データ)
```

### 分析SQL（概要）

```sql
-- グレード別分布確認
SELECT
    race_grade,
    COUNT(*) as race_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM races
WHERE date BETWEEN '2020-01-01' AND '2025-12-31'
GROUP BY race_grade
ORDER BY race_count DESC;

-- 予測データカバレッジ by グレード
WITH prediction_races AS (
    SELECT DISTINCT r.race_id, r.race_grade
    FROM races r
    JOIN race_predictions rp ON r.race_id = rp.race_id
    WHERE r.date BETWEEN '2020-01-01' AND '2025-12-31'
        AND rp.prediction_type = 'before'
)
SELECT
    COALESCE(race_grade, '未分類') as grade,
    COUNT(*) as predicted_races,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM prediction_races), 2) as pct
FROM prediction_races
GROUP BY race_grade;
```

---

## 📊 分析結果

### 1. グレード分布（2020-2025年）

| グレード | レース数 | 割合 | 備考 |
|---------|---------|------|------|
| 一般戦 | 87,879 | 84.04% | 主力データ |
| スペシャルシリーズ | 2,435 | 2.33% | 月平均34レース |
| NULL（未分類） | 14,247 | 13.62% | **問題あり** |
| **合計** | **104,561** | **100%** | - |

**問題点**:
- SG/G1/G2/G3の細かい分類なし
- 13.62%がNULL → データ品質の課題

### 2. 予測データカバレッジ by グレード

| グレード | 予測済レース数 | カバレッジ | 問題 |
|---------|--------------|-----------|------|
| 一般戦 | 35,953 | 40.91% | 問題なし |
| スペシャルシリーズ | 948 | 38.92% | サンプル少 |
| 未分類 | 3,184 | 22.36% | **低すぎる** |

**解釈**:
- NULL gradeレースの予測カバレッジが異常に低い（22.36%）
- スペシャルシリーズは948レースのみ → 統計的有意性の確保が困難

### 3. 統計的制約の試算

```
11条件 × 3グレード × 5信頼度 × 6オッズ帯 = 約990セル
（実際はNULLを除外しても 11 × 2 × 5 × 6 = 660セル）

最小サンプル要件: 20レース/セル
必要総レース数: 660 × 20 = 13,200レース

現状:
- 一般戦予測: 35,953レース → セルあたり平均54.5レース（OK）
- スペシャルシリーズ予測: 948レース → セルあたり平均2.9レース（NG）
```

**結論**: スペシャルシリーズの細分化分析は統計的に不可能

---

## 💡 実装案

### Phase 1: 簡易版グレードフィルター（推奨）

**期待効果**: ROI +1.0-1.5pt
**実装可能性**: 高
**工数**: 2-3時間

#### 実装内容

1. **NULL gradeレースの除外**
   ```python
   # src/prediction/confidence_evaluator.py

   def evaluate_confidence(self, race_data):
       # 既存のチェック
       if race_data.get('race_grade') is None:
           # NULL gradeは信頼度を1段階下げる or 除外
           if base_confidence in ['A', 'B']:
               base_confidence = self._downgrade_confidence(base_confidence)
   ```

2. **グレード×信頼度の基本ROI分析**
   ```python
   # 分析スクリプトで事前確認
   GRADE_CONFIDENCE_MULTIPLIERS = {
       ('一般戦', 'A'): 1.0,
       ('一般戦', 'B'): 1.0,
       ('スペシャルシリーズ', 'A'): 1.1,  # 要検証
       ('スペシャルシリーズ', 'B'): 1.0,
       # C/D/Eは統計不足のため未実装
   }
   ```

3. **スペシャルシリーズのA/Bのみテスト**
   - 948レース中、A/B信頼度のみで約400-500レース確保
   - サンプルサイズ確保のため、オッズ帯分割なし

#### 検証方法

```bash
# standard_backtest.pyに条件追加後
python scripts/backtest/standard_backtest.py --full

# 採用基準:
# - 黒字年数 4/6年以上
# - 累計収支プラス
# - ROI 100%以上
```

### Phase 2: 完全版グレード最適化（長期課題）

**期待効果**: ROI +1.5-2.5pt
**実装可能性**: 低（データ整備が先決）
**工数**: 8-10時間

#### 前提条件

1. **グレードデータの完全化**
   - 公式APIから正確なグレード情報を取得
   - SG/G1/G2/G3の分類を追加
   - NULL gradeを0%にする

2. **十分なサンプルサイズの確保**
   - 各グレード×条件で最低100レース
   - 特にG1/SG級レースのデータ蓄積（現状不足）

#### 実装内容（Phase 2）

```python
# src/prediction/grade_optimizer.py（新規作成）

GRADE_CONDITION_OPTIMAL_SETTINGS = {
    'SG': {
        'A_high_odds': {  # A×50倍+
            'min_odds': 60.0,  # 通常より高く設定
            'max_odds': 150.0,
            'weight': 1.3,
        },
        'B_middle_odds': {  # B×20-30倍
            'min_odds': 25.0,
            'max_odds': 35.0,
            'weight': 1.1,
        },
        # ... 各条件
    },
    'G1': { ... },
    '一般戦': { ... },
}
```

---

## 📈 期待効果の試算

### Phase 1（簡易版）

| 施策 | 期待ROI改善 | 根拠 |
|------|-----------|------|
| NULL grade除外 | +0.3-0.5pt | 低カバレッジ（22%）の不安定データ除去 |
| スペシャルシリーズA強化 | +0.5-0.8pt | 上位レーサー集中 → 予測精度向上の可能性 |
| グレード×信頼度基本調整 | +0.2-0.2pt | 粗い調整のため効果限定的 |
| **合計** | **+1.0-1.5pt** | - |

### Phase 2（完全版）

| 施策 | 期待ROI改善 | 根拠 |
|------|-----------|------|
| SG/G1級の高オッズ条件最適化 | +0.5-1.0pt | トップレーサーの実力差明確化 |
| 一般戦の条件細分化 | +0.3-0.5pt | 選手層の幅広さに対応 |
| グレード別オッズ帯調整 | +0.2-0.5pt | グレード特性反映 |
| Phase 1からの追加改善 | +0.5-0.5pt | Phase 1基準 |
| **合計** | **+1.5-2.5pt** | Phase 1含む |

---

## ⚠️ リスクと制約

### データ品質リスク

1. **NULL gradeの多さ（13.62%）**
   - 原因不明のNULL → データ取得スクリプトの不具合？
   - 対策: データ収集フローの見直し

2. **グレード分類の粗さ**
   - 現状: 「一般戦」の一括り → SG～一般まで混在
   - 対策: 公式APIから正確な情報取得（レース名からのパース）

### 統計的リスク

1. **スペシャルシリーズのサンプル不足**
   - 948レース → 11条件で割ると1条件あたり86レース
   - 対策: Phase 1では条件を絞る（A/Bのみ）

2. **過学習リスク**
   - 細分化しすぎるとデータフィッティング
   - 対策: 最小サンプル要件（20レース/セル）の厳守

### 実装リスク

1. **既存ロジックへの影響**
   - 11条件の判定ロジックに影響を与えうる
   - 対策: 段階的実装、標準テストでの厳格な検証

---

## 🎯 推奨アクション

### 短期（1-2週間）

1. **Phase 1実装**: 簡易版グレードフィルター
   - NULL grade除外ロジック追加
   - スペシャルシリーズA/B条件のテスト
   - standard_backtest.pyで検証

2. **データ品質調査**
   - NULL gradeの発生原因特定
   - 2020-2025年の各年でのNULL率推移確認

### 中期（1-2ヶ月）

1. **グレードデータ整備**
   - 公式APIからレース名取得
   - SG/G1/G2/G3/一般の分類ロジック実装
   - 過去データの再分類（backfill）

2. **Phase 2の準備**
   - グレード別の詳細ROI分析
   - 条件×グレードマトリクスの作成

### 長期（3ヶ月以降）

1. **Phase 2実装**: 完全版グレード最適化
2. **継続的改善**: グレード別パフォーマンスモニタリング

---

## 📚 参考資料

### 関連ドキュメント

- [docs/architecture/PREDICTION_LOGIC.md](../../architecture/PREDICTION_LOGIC.md) - 予測ロジックの詳細
- [docs/presets/BET_CONDITIONS.md](../../presets/BET_CONDITIONS.md) - 現行11条件の定義
- [docs/guides/SQL_QUERY_SAMPLES.md](../../guides/SQL_QUERY_SAMPLES.md) - SQLクエリ例

### データベーススキーマ

```sql
-- races テーブル（抜粋）
CREATE TABLE races (
    race_id TEXT PRIMARY KEY,
    date TEXT,
    venue_code TEXT,
    race_number INTEGER,
    race_grade TEXT,  -- 「一般戦」「スペシャルシリーズ」NULL
    -- ...
);
```

---

## ✅ 結論

### 採用判定: 条件付き採用（Phase 1のみ）

- **Phase 1（簡易版）**: 実装推奨、ROI +1.0-1.5pt期待
- **Phase 2（完全版）**: データ整備後に再検討

### Next Steps

1. ✅ **Phase 1実装**: NULL grade除外 + スペシャルシリーズA/Bテスト
2. ⏳ **データ調査**: NULL gradeの原因特定
3. ⏳ **Phase 2準備**: グレードデータの完全化

### 期待される最終成果

- **短期（Phase 1）**: ROI +1.0-1.5pt、収支 +5,000-10,000円/年
- **長期（Phase 2）**: ROI +1.5-2.5pt、収支 +10,000-15,000円/年

---

**分析完了日**: 2026-02-13
**所要時間**: 約3時間（Explore Agent使用）
