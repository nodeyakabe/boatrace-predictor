# テーブル目的・使い分けガイド

**作成日**: 2025-12-22
**目的**: 似た名前のテーブルの使い分けを明確にし、誤った選択を防ぐ

---

## 🔍 データ種別ごとのテーブル選択ガイド

### 1. 展示タイム・ST・進入隊形（直前情報）

#### ❓ 過去データ分析の場合

**使うテーブル**: `race_details`

```sql
-- 展示タイム（80%カバー率、63万件以上）
SELECT exhibition_time FROM race_details WHERE race_id = ?

-- ST（95%カバー率、75万件以上）
SELECT st_time FROM race_details WHERE race_id = ?

-- 進入隊形（76%カバー率、60万件以上）
SELECT actual_course FROM race_details WHERE race_id = ?
```

**カバー範囲**: 2020-2025年（全年度）
**件数**: race_details 全体で約79万レコード

#### ❓ リアルタイム収集の場合

**使うテーブル**: `exhibition_data`

```sql
SELECT exhibition_time, start_timing FROM exhibition_data WHERE race_id = ?
```

**カバー範囲**: 2025年11月以降のみ
**件数**: 約860件

#### ⚠️ よくある間違い

**❌ 誤り**: 過去データ分析で `exhibition_data` を使う
- 結果: 861件しかヒットせず「データがない」と誤判断

**✅ 正解**: 過去データ分析は `race_details` を使う
- 結果: 63万件ヒット、80%のカバー率で十分な分析が可能

---

### 2. オッズ情報

#### ❓ 3連単オッズ

**使うテーブル**: `trifecta_odds`

```sql
SELECT odds FROM trifecta_odds
WHERE race_id = ? AND first = ? AND second = ? AND third = ?
```

**カバー率**: 高い（詳細カバー率は要確認）

#### ❓ 単勝オッズ

**使うテーブル**: `win_odds`

```sql
SELECT odds FROM win_odds WHERE race_id = ? AND pit_number = ?
```

**⚠️ 注意**: 現在データ0件（未収集）

---

### 3. レース結果

#### ❓ 着順・決まり手

**使うテーブル**: `results`

```sql
SELECT rank, kimarite FROM results
WHERE race_id = ? AND pit_number = ?
```

**カバー率**: 100%

#### ❓ 払戻金

**使うテーブル**: `payouts`

```sql
SELECT amount FROM payouts
WHERE race_id = ? AND bet_type = '3連単' AND combination = '1-2-3'
```

**カバー率**: 高い

---

### 4. レース条件・コンディション

#### ❓ 天候・風速・波高

**使うテーブル**: `race_conditions`

```sql
SELECT temperature, water_temperature, wind_speed, wind_direction, wave_height, weather
FROM race_conditions WHERE race_id = ?
```

**カバー率**: 年度により異なる
- 2020-2023年: 不明（要収集）
- 2024-2025年: 高い

---

### 5. 出走表・選手情報

#### ❓ 選手名・級別・モーター番号

**使うテーブル**: `entries`

```sql
SELECT racer_name, racer_number, racer_rank, motor_number, avg_st
FROM entries WHERE race_id = ? AND pit_number = ?
```

**カバー率**: 100%

---

## 📊 類似テーブルの使い分け一覧

| データ種別 | 主テーブル | 補助/旧テーブル | 使い分け |
|-----------|----------|---------------|---------|
| **展示タイム・ST・進入隊形** | `race_details` | `exhibition_data` | 過去データ→race_details、リアルタイム→exhibition_data |
| **実際のコース** | `race_details.actual_course` | `actual_courses` | 過去データ→race_details、actual_coursesは目的不明 |
| **3連単オッズ** | `trifecta_odds` | - | これのみ |
| **レース基本情報** | `races` | - | これのみ |
| **結果** | `results` | - | これのみ |

---

## 🔧 テーブル選択フローチャート

### 展示タイム・ST・進入隊形を取得したい

```
START
  ↓
[過去データ分析？] --- YES → race_details を使用 ✅
  ↓ NO
[2025年11月以降のリアルタイムデータ？] --- YES → exhibition_data を使用 ✅
  ↓ NO
【エラー】該当テーブルなし
```

### 気象データを取得したい

```
START
  ↓
[レース当日の気象？] --- YES → race_conditions を使用 ✅
  ↓ NO
[外部API連携が必要？] --- YES → WEATHER_API_KEY 使用 ⚠️
  ↓ NO
【エラー】該当データなし
```

---

## ⚠️ データ確認時の注意点

### 1. 件数だけで判断しない

**❌ 誤った判断例**:
```sql
SELECT COUNT(*) FROM exhibition_data;  -- 861件
# → 「展示タイムは861件しかない」と誤判断
```

**✅ 正しい確認**:
```sql
-- 複数テーブルを確認
SELECT COUNT(*) FROM race_details WHERE exhibition_time IS NOT NULL;  -- 637,036件
SELECT COUNT(*) FROM exhibition_data WHERE exhibition_time IS NOT NULL;  -- 861件

-- カバー率も確認
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN exhibition_time IS NOT NULL THEN 1 ELSE 0 END) as has_data,
    ROUND(SUM(CASE WHEN exhibition_time IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as coverage
FROM race_details;
```

### 2. 年度別カバー率を確認

```sql
SELECT
    SUBSTR(r.race_date, 1, 4) as year,
    COUNT(*) as total,
    SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) as has_data,
    ROUND(SUM(CASE WHEN rd.exhibition_time IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as coverage
FROM race_details rd
JOIN races r ON rd.race_id = r.id
GROUP BY year
ORDER BY year;
```

### 3. ドキュメントを確認

件数確認の前に必ず確認すべきドキュメント：

1. [DATA_LOCATION_MAP.md](DATA_LOCATION_MAP.md) - データ所在のクイックリファレンス
2. [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) - 全テーブルの詳細仕様
3. このドキュメント（TABLE_PURPOSE.md） - テーブルの使い分け

---

## 📝 新しいテーブルを追加する際のガイドライン

### 1. 目的を明確に記載

DATABASE_SCHEMA.mdに以下を記載：
- テーブルの目的（何のためのデーブルか）
- 使い分け（類似テーブルとの違い）
- データ範囲（対象年度、カバー率）

### 2. DATA_LOCATION_MAP.mdに追加

よく使うデータの場合、クイックリファレンステーブルに追加

### 3. TABLE_PURPOSE.mdに追加

類似テーブルがある場合、使い分けセクションに追加

---

## 🚨 過去の失敗事例

### 事例1: exhibition_dataで過去データを探した（2025-12-22）

**状況**:
- 「展示タイムはあるか？」という質問
- exhibition_dataテーブルのみ確認
- 861件しかないため「ほとんどない（0.0%）」と誤回答

**真実**:
- race_detailsテーブルに637,036件（80%カバー率）存在
- exhibition_dataは2025年11月以降のリアルタイム収集専用

**教訓**:
- データ探索時は複数テーブルを確認
- 件数が少ない場合、他のテーブルも確認
- ドキュメント（DATA_LOCATION_MAP.md）を先に確認

**再発防止策**:
- このドキュメント（TABLE_PURPOSE.md）作成
- DATA_LOCATION_MAP.md作成
- DATABASE_SCHEMA.mdにexhibition_dataの目的を明記

---

**最終更新**: 2025-12-22
**次回更新時**: 新しいテーブル追加時、使い分けが不明瞭なテーブル発見時
