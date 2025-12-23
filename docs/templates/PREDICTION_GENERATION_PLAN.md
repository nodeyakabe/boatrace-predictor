# 予測データ生成 作業計画書

**作成日**: YYYY-MM-DD
**作成者**:

---

## 1. 目的

**なぜこのデータを生成するのか？**

- [ ] バックテストのため
- [ ] 新アルゴリズム検証のため
- [ ] 欠損データ補完のため
- [ ] その他: ___________

**具体的な目的**:
```
（例）2024年のバックテストで戦略Aの効果を検証するため
```

---

## 2. 生成対象の明確化

### 対象年度
- [ ] 2022年
- [ ] 2023年
- [ ] 2024年
- [ ] 2025年
- [ ] その他: ___________

### 予測タイプ
- [ ] advance（事前予測）
- [ ] before（直前予測）
- [ ] 両方

### 生成範囲
- [ ] 全件再生成（既存データ上書き）
- [ ] 未生成分のみ（--skip-existing）

**選択理由**:
```
（例）既存の2024年データはD/Eのみなので全件再生成が必要
```

---

## 3. 期待される成果物

### データの仕様

| 項目 | 期待値 |
|------|--------|
| 対象レース数 | _____ 件 |
| 信頼度分布 | A/B/C/D/E すべて存在 |
| prediction_type | advance / before |
| hierarchical_predictor | ✅ ON |

### 使用目的

**このデータは何に使うのか？**
```
（例）
- 2024年の年間ROIを計算
- 信頼度C×B1級×30-40倍の条件でバックテスト
- 2022-2024年の3年間で安定した購入条件を発見
```

**使わないデータは生成しない**:
- [ ] 確認済み：このデータは必ず使う

---

## 4. 実行計画

### 使用スクリプト
- [ ] **generate_predictions.py** ⭐推奨（統合スクリプト）
- [ ] **regenerate_predictions_optimized.py** ⭐推奨（最適化版）
- [ ] その他: ___________（理由: ___________）

### 実行コマンド（予定）
```bash
# ドライラン
python scripts/generate_predictions.py --dry-run --years 2024

# 本実行
python scripts/generate_predictions.py --years 2024 --type advance
```

### 推定所要時間
- 対象レース数: _____ 件
- 処理速度（予想）: 1.5件/秒
- 推定時間: _____ 時間

---

## 5. 事前チェックリスト

### 環境確認
- [ ] hierarchical_predictor: True を確認
- [ ] 仮想環境の有効化（venv）
- [ ] DBバックアップ作成済み

### ドライラン実施
- [ ] ドライラン実行済み（`--dry-run`）
- [ ] サンプル10件で信頼度分布を確認
- [ ] A/B/C/D/E すべて存在することを確認

### 並列実行チェック
- [ ] 他のプロセスが同じ年度を処理していないか確認
- [ ] ロックファイルが残っていないか確認（`data/.lock_prediction_*`）

---

## 6. 実行後の検証

### 生成結果の確認
- [ ] 対象レース数が一致（期待: _____ 件、実際: _____ 件）
- [ ] 信頼度分布を確認（A/B/C/D/E すべて存在）
- [ ] エラー件数を確認（許容範囲: 1%未満）

### データの使用確認
- [ ] 実際に目的の分析・バックテストで使用できることを確認
- [ ] 想定通りの結果が得られることを確認

**確認SQL**:
```sql
-- 信頼度分布
SELECT confidence, COUNT(DISTINCT race_id)
FROM race_predictions
WHERE race_id IN (SELECT id FROM races WHERE race_date LIKE '2024%')
AND prediction_type = 'advance'
GROUP BY confidence;

-- カバー率
SELECT
    COUNT(DISTINCT r.id) as total,
    COUNT(DISTINCT rp.race_id) as predicted,
    ROUND(100.0 * COUNT(DISTINCT rp.race_id) / COUNT(DISTINCT r.id), 1) as coverage
FROM races r
LEFT JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'advance'
WHERE r.race_date LIKE '2024%';
```

---

## 7. 完了判定

- [ ] 生成完了（エラー率 < 1%）
- [ ] 信頼度分布が正常（A-E全て存在）
- [ ] 実際に使用目的で動作確認済み
- [ ] 不要なデータを生成していないことを確認

---

## 8. 振り返り（実施後記入）

### 想定との差異
```
（例）
- 推定3時間 → 実際2.5時間（処理速度が速かった）
- 信頼度Aが予想より少なかった（要調査）
```

### 発生した問題
```
（例）
- ロックファイルエラーが発生（前回の処理が異常終了していた）
- 対処: data/.lock_prediction_2024 を削除して再実行
```

### 次回への改善点
```
（例）
- ドライランのサンプル数を20件に増やす
- バックアップを2世代分残す
```

---

**テンプレート作成日**: 2025-12-22
**目的**: 予測データ生成の3日間の無駄を防止する
