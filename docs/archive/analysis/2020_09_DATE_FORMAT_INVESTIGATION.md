# 2020年9月 日付形式異常調査レポート

**調査日**: 2026-01-29
**調査者**: Claude Code
**対象**: 2020年9月のYYYYMMDD形式レコードとUNIQUE制約エラー

---

## 問題の概要

`fix_abnormal_dates.py`で2020年9月の日付形式修正時に以下のエラーが発生:

```
sqlite3.IntegrityError: UNIQUE constraint failed: races.venue_code, races.race_date, races.race_number
```

YYYYMMDD形式（例: `20200901`）をYYYY-MM-DD形式（例: `2020-09-01`）に変換しようとしたところ、既に同じ日付・会場・レース番号のレコードが存在していた。

---

## 調査結果

### 1. 重複状況

| 日付形式 | レコード数 | ID範囲 | 関連データ |
|---------|-----------|--------|-----------|
| **YYYYMMDD形式** | **3,000件** | 171267-176666 | **なし（すべて0件）** |
| **YYYY-MM-DD形式** | **4,522件** | - | **あり（entries 39,870件、results 39,222件）** |

### 2. 重複ペア数

**3,000ペア**が完全に重複（すべての会場で1対1対応）

#### 会場別の重複状況（抜粋）

| 会場コード | YYYYMMDD形式 | YYYY-MM-DD形式 |
|-----------|-------------|---------------|
| 01（桐生） | 120件 | 120件 |
| 02（戸田） | 108件 | 108件 |
| 03（江戸川）| 156件 | 156件 |
| 04（平和島）| 144件 | 144件 |
| ... | ... | ... |
| **合計** | **3,000件** | **3,000件** |

### 3. 関連データの比較

#### YYYYMMDD形式（異常レコード）

```sql
SELECT COUNT(DISTINCT r.id) as race_count,
       SUM(CASE WHEN e.id IS NOT NULL THEN 1 ELSE 0 END) as entries,
       SUM(CASE WHEN res.id IS NOT NULL THEN 1 ELSE 0 END) as results
FROM races r
LEFT JOIN entries e ON r.id = e.race_id
LEFT JOIN results res ON r.id = res.race_id
WHERE r.race_date LIKE '202009%' AND r.race_date NOT LIKE '%-%'
```

**結果**:
- レース数: 3,000件
- entries: **0件**
- results: **0件**
- race_conditions: **0件**
- race_predictions: **0件**
- trifecta_odds: **0件**

#### YYYY-MM-DD形式（正常レコード）

```sql
SELECT COUNT(DISTINCT r.id) as race_count,
       SUM(CASE WHEN e.id IS NOT NULL THEN 1 ELSE 0 END) as entries,
       SUM(CASE WHEN res.id IS NOT NULL THEN 1 ELSE 0 END) as results
FROM races r
LEFT JOIN entries e ON r.id = e.race_id
LEFT JOIN results res ON r.id = res.race_id
WHERE r.race_date LIKE '2020-09-%'
```

**結果**:
- レース数: 4,522件
- entries: **39,870件**
- results: **39,222件**
- race_conditions: **42,499件**

---

## 原因分析

### なぜこのような重複が発生したか？

1. **データ収集の重複実行**
   - 2020年9月のデータが異なるタイミングで2回収集された
   - 1回目: YYYYMMDD形式で保存（データ未完成、racesテーブルのみ）
   - 2回目: YYYY-MM-DD形式で保存（完全なデータ）

2. **日付形式の不統一**
   - 初期のデータ収集スクリプトが日付形式を統一していなかった
   - YYYYMMDD形式とYYYY-MM-DD形式が混在

3. **UNIQUE制約の動作**
   - `UNIQUE(venue_code, race_date, race_number)`は存在
   - しかし、`20200901`と`2020-09-01`は**文字列として異なる**ため挿入可能だった
   - 日付形式を統一しようとすると衝突が発生

---

## 対処方針

### パターンB: YYYYMMDD形式が空データの場合（該当）

**対処**: YYYYMMDD形式のレコードを削除

#### 理由

1. **関連データが存在しない**
   - entries, results, race_conditions等すべて0件
   - 削除しても情報損失なし

2. **YYYY-MM-DD形式に完全なデータが存在**
   - entries: 39,870件
   - results: 39,222件
   - すべての情報が保持されている

3. **安全性**
   - 外部キー制約違反のリスクなし
   - トランザクション内で実行可能

---

## 修正手順

### ステップ1: YYYYMMDD形式レコードの削除

```bash
python scripts/maintenance/fix_abnormal_dates_2020_09_v2.py
```

**処理内容**:
1. 削除前検証（関連データがないことを確認）
2. YYYYMMDD形式の3,000件を削除
3. 削除後検証（重複がないことを確認）

**期待結果**:
- YYYYMMDD形式: 0件（削除完了）
- YYYY-MM-DD形式: 4,522件（保持）
- 重複: なし

### ステップ2: 元の日付形式修正スクリプト実行

ステップ1完了後、以下を実行:

```bash
python scripts/maintenance/fix_abnormal_dates.py
```

**処理内容**:
- 他の月のYYYYMMDD形式をYYYY-MM-DD形式に修正
- 2020年9月は既に修正済みのためスキップ

---

## 検証SQL

### 削除前の状態確認

```sql
-- YYYYMMDD形式の件数
SELECT COUNT(*) FROM races
WHERE race_date LIKE '202009%' AND race_date NOT LIKE '%-%';
-- 結果: 3000

-- YYYY-MM-DD形式の件数
SELECT COUNT(*) FROM races
WHERE race_date LIKE '2020-09-%';
-- 結果: 4522

-- 重複ペア数
SELECT COUNT(*) FROM races a
INNER JOIN races b ON
    b.race_date = SUBSTR(a.race_date, 1, 4) || '-' || SUBSTR(a.race_date, 5, 2) || '-' || SUBSTR(a.race_date, 7, 2)
    AND b.venue_code = a.venue_code
    AND b.race_number = a.race_number
WHERE a.race_date LIKE '202009%' AND a.race_date NOT LIKE '%-%';
-- 結果: 3000
```

### 削除後の検証

```sql
-- YYYYMMDD形式の残存確認
SELECT COUNT(*) FROM races
WHERE race_date LIKE '202009%' AND race_date NOT LIKE '%-%';
-- 期待値: 0

-- YYYY-MM-DD形式の維持確認
SELECT COUNT(*) FROM races
WHERE race_date LIKE '2020-09-%';
-- 期待値: 4522

-- 重複の確認（変換後に衝突しないか）
SELECT race_date, venue_code, race_number, COUNT(*) as cnt
FROM races
WHERE race_date LIKE '2020-09-%'
GROUP BY race_date, venue_code, race_number
HAVING COUNT(*) > 1;
-- 期待値: 0件
```

---

## リスク評価

### ✓ 低リスク

- **関連データなし**: YYYYMMDD形式のレコードにはentries/results等が一切紐付いていない
- **完全重複**: 3,000ペアすべてがYYYY-MM-DD形式に対応レコードあり
- **データ損失なし**: すべての情報がYYYY-MM-DD形式に存在

### ✗ 考慮すべき点

- **バックアップ**: 念のため削除前にDBバックアップ推奨
- **トランザクション**: 削除はトランザクション内で実行（ロールバック可能）

---

## まとめ

### 結論

**YYYYMMDD形式の3,000件を安全に削除可能**

- 関連データが存在しない空レコード
- YYYY-MM-DD形式に完全なデータが存在
- 削除後、元の日付形式修正スクリプトが正常実行可能

### 推奨アクション

1. ✅ `fix_abnormal_dates_2020_09_v2.py` を実行（YYYYMMDD削除）
2. ✅ `fix_abnormal_dates.py` を実行（残りの日付形式統一）
3. ✅ 検証SQL実行で結果確認

---

## 参考情報

### データ収集の経緯

- 2020年データは`auto_fetch_2020_2025.py`等で収集
- 日付形式は途中で統一された（YYYY-MM-DD形式へ）
- 移行期に重複データが発生した可能性

### 今後の対策

1. **データ収集前の確認**
   - 同じレースが既に存在しないかチェック
   - `INSERT OR REPLACE`よりも`INSERT OR IGNORE`を検討

2. **日付形式の統一**
   - すべてのスクリプトでYYYY-MM-DD形式を使用
   - 入力時に変換処理を追加

3. **定期的な整合性チェック**
   - `check_data_integrity.py`で異常形式を検出
   - 月次メンテナンスで修正
