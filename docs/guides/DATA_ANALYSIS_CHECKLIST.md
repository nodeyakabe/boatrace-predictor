# データ分析前の必須チェックリスト

**作成日**: 2026-02-06
**目的**: データ分析時の見落としを防止するための必須確認項目

---

## ⚠️ このチェックリストを使う理由

**過去の失敗例（2026-02-06）**:
- `race_conditions.weather`（充足率0.79%）だけを見て「天候データなし」と判断
- **weatherテーブル（11,528件、27.8%カバレッジ）の存在を見落とした**

→ **類似データが別テーブルに存在する可能性を確認しなかった**

---

## ✅ 必須チェック項目（分析前）

### **Step 1: 全テーブル一覧の確認**

```sql
-- 全テーブル一覧
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
```

**確認ポイント**:
- [ ] 分析対象のカラム名と類似する**テーブル名**がないか確認
  - 例: `race_conditions.weather`（カラム）→ `weather`（テーブル）を見落とすな！
- [ ] 分析対象データと関連しそうなテーブルをリストアップ

---

### **Step 2: 類似データの保存場所を確認**

| データ種別 | 保存場所（複数ある場合） | 結合方法 | 優先度 |
|-----------|----------------------|---------|:-----:|
| **天候データ** | 1. `weather`テーブル（会場×日付）<br>2. `race_conditions.weather`（レース単位） | 1. venue_code + race_date<br>2. race_id | **1を優先** |
| **オッズデータ** | `trifecta_odds`テーブル | race_id + combination | - |
| **展示データ** | 1. `race_details`（公式API）<br>2. `exhibition_data`（Boaters独自） | race_id + pit_number | **1を優先** |
| **潮位データ** | `rdmdb_tide`テーブル | 会場×日時で結合 | - |

**確認ポイント**:
- [ ] 同じデータが**複数の場所**に保存されていないか確認
- [ ] どちらの保存場所が**充足率が高い**か確認
- [ ] テーブル間の**結合方法**を確認

---

### **Step 3: テーブル間の関係性確認**

```sql
-- 例: weatherテーブルとracesテーブルの結合可能性
SELECT COUNT(DISTINCT r.id)
FROM races r
JOIN weather w ON r.venue_code = w.venue_code
    AND r.race_date = w.weather_date
WHERE r.race_date >= '2020-01-01';
```

**確認ポイント**:
- [ ] 外部キー以外の結合方法がないか確認（venue_code + race_date など）
- [ ] 結合後のカバレッジ率を確認

---

### **Step 4: DATABASE_SCHEMA.mdの該当箇所を熟読**

**確認ポイント**:
- [ ] [テーブル活用状況一覧](../architecture/DATABASE_SCHEMA.md#テーブル活用状況一覧)を確認
- [ ] 分析対象テーブルの「備考」欄を確認（関連テーブルの記載がある）
- [ ] 「よくある間違い」セクション（後述）を確認

---

### **Step 5: 充足率の確認（複数ソースの比較）**

```sql
-- 例: 天候データの充足率（2つのソースを比較）
SELECT
    'race_conditions.weather' as source,
    COUNT(CASE WHEN weather IS NOT NULL THEN 1 END) as count,
    COUNT(*) as total
FROM race_conditions

UNION ALL

SELECT
    'weatherテーブル結合' as source,
    COUNT(DISTINCT r.id) as count,
    COUNT(*) as total
FROM races r
LEFT JOIN weather w ON r.venue_code = w.venue_code
    AND r.race_date = w.weather_date
WHERE w.id IS NOT NULL;
```

**確認ポイント**:
- [ ] 複数のデータソースがある場合、**全ての充足率を比較**
- [ ] 最も充足率が高いソースを特定

---

## 🚨 よくある間違い（必読）

### **間違い1: 単一カラムだけを見て判断**

❌ **誤り**:
```python
# race_conditions.weatherだけを見て判断
cursor.execute("SELECT COUNT(*) FROM race_conditions WHERE weather IS NOT NULL")
# → 0.79%しかない → 「天候データなし」と判断
```

✅ **正しい**:
```python
# 関連テーブル（weather）も確認
cursor.execute("""
    SELECT COUNT(DISTINCT r.id)
    FROM races r
    JOIN weather w ON r.venue_code = w.venue_code
        AND r.race_date = w.weather_date
""")
# → 27.8%ある → 「weatherテーブルを使えば天候データあり」と判断
```

---

### **間違い2: テーブル名とカラム名の混同**

| 名称 | 種類 | 説明 |
|------|------|------|
| `race_conditions.weather` | カラム | レース単位の天気（充足率0.79%） |
| `weather` | **テーブル** | 会場×日付単位の天気（11,528件、27.8%カバレッジ） |

**教訓**: カラム名と同じ名前のテーブルがないか必ず確認！

---

### **間違い3: DATABASE_SCHEMA.mdの表面的な読み方**

❌ **誤り**:
- テーブル一覧を眺めるだけ
- 件数だけを見て終わり

✅ **正しい**:
- テーブルの「備考」欄を熟読
- 類似テーブルの関係性を理解
- 「活用状況」を確認（✅使用中 / 🟡未活用 / ❌未収集）

---

## 📋 分析開始時のチェックシート

```
分析対象: ___________________（例: 天候データ）

□ Step 1: 全テーブル一覧を確認した
□ Step 2: 類似データの保存場所を確認した（複数ある場合はリスト化）
  - 保存場所1: ___________________
  - 保存場所2: ___________________
□ Step 3: テーブル間の結合方法を確認した
□ Step 4: DATABASE_SCHEMA.mdの該当箇所を熟読した
□ Step 5: 複数ソースの充足率を比較した

分析開始日: ___________________
確認者: ___________________
```

---

## 🔄 このチェックリストの更新ルール

- 新しい見落としが発生したら、「よくある間違い」に追加
- 月1回、チェックリストの有効性を検証
- 改善案があれば随時更新

---

**作成日**: 2026-02-06
**最終更新**: 2026-02-06
**更新者**: Claude Sonnet 4.5
