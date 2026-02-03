# 2020年9月 日付形式修正完了レポート

**実施日**: 2026-01-29
**担当**: Claude Code
**ステータス**: ✓ 完了

---

## 実施内容サマリー

### 問題

`fix_abnormal_dates.py`で2020年9月の日付形式修正時にUNIQUE制約エラーが発生:

```
sqlite3.IntegrityError: UNIQUE constraint failed: races.venue_code, races.race_date, races.race_number
```

### 原因

- **重複レコード**: YYYYMMDD形式（`20200901`）とYYYY-MM-DD形式（`2020-09-01`）が同時に存在
- **3,000ペアの完全重複**: すべての会場・日付・レース番号で1対1対応
- **YYYYMMDD形式は空データ**: entries, results等の関連データが一切なし

### 対処

**ステップ1**: YYYYMMDD形式の3,000件を削除
- スクリプト: `scripts/maintenance/fix_abnormal_dates_2020_09_v2.py`
- 削除実行: 2026-01-29
- 結果: 3,000件削除成功

**ステップ2**: 元の日付形式修正は不要
- すべてのYYYYMMDD形式が既に修正済み
- 追加の変換作業なし

---

## 実施結果

### 修正前

| 日付形式 | レコード数 | 関連データ |
|---------|-----------|-----------|
| YYYYMMDD（`20200901`等） | 3,000件 | なし（0件） |
| YYYY-MM-DD（`2020-09-01`等） | 4,522件 | あり（entries 39,870件） |
| **重複ペア** | **3,000組** | - |

### 修正後

| 日付形式 | レコード数 | 関連データ |
|---------|-----------|-----------|
| YYYYMMDD | **0件** | - |
| YYYY-MM-DD | **4,522件** | あり（entries 39,870件） |
| **重複ペア** | **0組** | - |

---

## 検証結果

### 1. 日付形式の統一

```sql
SELECT
    CASE
        WHEN race_date LIKE '____-__-__' THEN 'YYYY-MM-DD'
        WHEN race_date LIKE '________' THEN 'YYYYMMDD'
        ELSE 'その他'
    END as format,
    COUNT(*) as count
FROM races
GROUP BY format
```

**結果**:
- YYYY-MM-DD形式: **285,421件**（全レコード）
- YYYYMMDD形式: **0件**
- その他: **0件**

✓ すべての日付がYYYY-MM-DD形式に統一

### 2. 2020年9月の状況

```sql
SELECT COUNT(*) as total
FROM races
WHERE race_date LIKE '2020-09-%'
```

**結果**: 4,522件

```sql
SELECT COUNT(*)
FROM races
WHERE race_date LIKE '202009%' AND race_date NOT LIKE '%-%'
```

**結果**: 0件

✓ YYYYMMDD形式のレコードが完全に削除

### 3. UNIQUE制約違反の確認

```sql
SELECT
    race_date,
    venue_code,
    race_number,
    COUNT(*) as count
FROM races
GROUP BY race_date, venue_code, race_number
HAVING COUNT(*) > 1
```

**結果**: 0件

✓ 重複なし、UNIQUE制約が正常に機能

### 4. 関連データの整合性

```sql
SELECT
    COUNT(DISTINCT r.id) as races,
    COUNT(DISTINCT e.race_id) as races_with_entries,
    COUNT(DISTINCT res.race_id) as races_with_results
FROM races r
LEFT JOIN entries e ON r.id = e.race_id
LEFT JOIN results res ON r.id = res.race_id
WHERE r.race_date LIKE '2020-09-%'
```

**結果**:
- レース数: 4,522件
- entriesあり: 1,211件
- resultsあり: 1,103件

✓ 関連データの整合性が保持されている

### 5. 年度別レコード数

| 年度 | レコード数 |
|------|-----------|
| 2015 | 1,506件 |
| 2016 | 9,602件 |
| 2017 | 9,697件 |
| 2018 | 9,580件 |
| 2019 | 9,495件 |
| **2020** | **28,695件** |
| 2021 | 55,728件 |
| 2022 | 56,435件 |
| 2023 | 55,980件 |
| 2024 | 19,915件 |
| 2025 | 25,041件 |
| 2026 | 3,747件 |

✓ 2020年のレコード数が正常（9月の削除後も適切な件数）

---

## 削除されたレコードの詳細

### ID範囲

- **最小ID**: 171267
- **最大ID**: 176666
- **総数**: 3,000件

### 会場別の削除数

| 会場コード | 会場名 | 削除数 |
|-----------|-------|-------|
| 01 | 桐生 | 120件 |
| 02 | 戸田 | 108件 |
| 03 | 江戸川 | 156件 |
| 04 | 平和島 | 144件 |
| 05 | 多摩川 | 96件 |
| ... | ... | ... |
| **合計** | **全会場** | **3,000件** |

### 関連データの削除

削除されたレコードには以下の関連データが**一切存在しなかった**:

- entries: 0件
- results: 0件
- race_conditions: 0件
- race_predictions: 0件
- trifecta_odds: 0件

**結論**: データ損失なし

---

## 作成されたスクリプト

### 1. fix_abnormal_dates_2020_09_v2.py

**場所**: `scripts/maintenance/fix_abnormal_dates_2020_09_v2.py`

**機能**:
- 2020年9月のYYYYMMDD形式レコードを安全に削除
- 削除前・削除後の検証機能
- トランザクション管理（ロールバック可能）

**実行結果**:
```
削除対象レコード数: 3000 件
関連データ - entries: 0, results: 0, conditions: 0
[OK] 関連データなし - 安全に削除可能

削除完了: 3000 件

YYYYMMDD形式の残存: 0 件
YYYY-MM-DD形式: 4522 件
[OK] 重複なし - 日付形式修正が可能

[OK] すべての検証に成功
```

### 2. fix_abnormal_dates.py

**場所**: `scripts/maintenance/fix_abnormal_dates.py`

**機能**:
- YYYYMMDD形式をYYYY-MM-DD形式に一括変換
- 重複チェック機能
- トランザクション管理

**実行結果**:
- 異常な日付形式: **0件**（既に全修正済み）
- 追加の変換作業不要

---

## 調査ドキュメント

### 詳細調査レポート

**場所**: `docs/analysis/2020_09_DATE_FORMAT_INVESTIGATION.md`

**内容**:
- 重複状況の詳細分析
- 関連データの比較
- 原因分析
- 対処方針の決定プロセス
- 検証SQL集

---

## まとめ

### ✓ 達成事項

1. **重複レコードの削除**: YYYYMMDD形式の3,000件を安全に削除
2. **日付形式の統一**: すべてのレコードがYYYY-MM-DD形式に統一
3. **UNIQUE制約の正常化**: 重複が0件、制約が正常に機能
4. **データ整合性の維持**: 関連データが完全に保持
5. **スクリプトの作成**: 再利用可能なメンテナンススクリプト整備

### ✓ 検証完了

- [x] 日付形式の統一（YYYY-MM-DD: 285,421件、YYYYMMDD: 0件）
- [x] 重複の解消（重複ペア: 0組）
- [x] UNIQUE制約の正常動作
- [x] 関連データの整合性（entries, results等）
- [x] 年度別レコード数の妥当性

### 今後の予防策

1. **データ収集時の日付形式統一**
   - すべてのスクリプトでYYYY-MM-DD形式を使用
   - 入力時に変換処理を追加

2. **定期的な整合性チェック**
   - `check_data_integrity.py`で異常形式を検出
   - 月次メンテナンスで修正

3. **UNIQUE制約の強化**
   - データ収集前に重複チェック
   - `INSERT OR IGNORE`の活用検討

---

## 関連ファイル

- 修正スクリプト1: `scripts/maintenance/fix_abnormal_dates_2020_09_v2.py`
- 修正スクリプト2: `scripts/maintenance/fix_abnormal_dates.py`
- 調査レポート: `docs/analysis/2020_09_DATE_FORMAT_INVESTIGATION.md`
- 完了レポート: `docs/analysis/2020_09_DATE_FIX_COMPLETION_REPORT.md`（本ファイル）

---

**ステータス**: ✓ すべての修正と検証が完了
**次のアクション**: なし（修正完了）
