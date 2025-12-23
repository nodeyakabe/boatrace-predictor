# データ所在マップ

**作成日**: 2025-12-22
**目的**: 「このデータはどのテーブルにあるのか？」を即座に答えられるようにする

---

## 🎯 よく使うデータの所在（クイックリファレンス）

| 探しているデータ | 主テーブル | カラム名 | カバー率 | 備考 |
|----------------|-----------|---------|---------|------|
| **展示タイム** | `race_details` | `exhibition_time` | 80% | **過去データはここ** |
| **ST（スタートタイミング）** | `race_details` | `st_time` | 95% | **過去データはここ** |
| **進入隊形（実際のコース）** | `race_details` | `actual_course` | 76% | **過去データはここ** |
| **平均ST** | `entries` | `avg_st` | 100% | 選手の平均値 |
| **チルト角度** | `race_details` | `tilt_angle` | 高い | - |
| **部品交換** | `race_details` | `parts_replacement` | 高い | - |
| **選手名** | `entries` | `racer_name` | 100% | - |
| **選手番号** | `entries` | `racer_number` | 100% | - |
| **級別** | `entries` | `racer_rank` | 100% | A1/A2/B1/B2 |
| **モーター番号** | `entries` | `motor_number` | 100% | - |
| **F/L回数** | `entries` | `f_count`, `l_count` | 100% | - |
| **3連単オッズ** | `trifecta_odds` | `odds` | 高い | - |
| **着順** | `results` | `rank` | 100% | - |
| **決まり手** | `results` | `kimarite` | 高い | - |
| **払戻金** | `payouts` | `amount` | 高い | - |

---

## 📊 テーブル構造の全体像

### レイヤー1: 基本情報（レース前に確定）

```
races（レース基本情報）
  ├─ entries（出走表）
  │    ├─ racer_name, racer_number
  │    ├─ racer_rank（級別）
  │    ├─ motor_number
  │    ├─ avg_st（平均ST）
  │    └─ f_count, l_count
  │
  └─ race_conditions（天候・コンディション）
       ├─ wind_speed（風速）
       ├─ wave_height（波高）
       └─ temperature（気温）
```

### レイヤー2: 直前情報（レース当日）

```
race_details（★ 最重要 ★）
  ├─ exhibition_time（展示タイム）- 80%
  ├─ st_time（ST） - 95%
  ├─ actual_course（進入隊形）- 76%
  ├─ tilt_angle（チルト）
  ├─ parts_replacement（部品交換）
  ├─ chikusen_time（直線タイム）
  ├─ isshu_time（一周タイム）
  ├─ mawariashi_time（まわり足タイム）
  └─ prev_race_*（前走情報）

exhibition_data（新規収集用、わずか861件）
  ├─ exhibition_time
  ├─ start_timing
  └─ turn_quality
  ※ 2025年11月以降のリアルタイム収集専用
  ※ 過去データはrace_detailsにある
```

### レイヤー3: 結果データ

```
results（着順・決まり手）
  ├─ rank（着順）
  └─ kimarite（決まり手）

payouts（払戻金）
  └─ amount（払戻額）
```

### レイヤー4: オッズ

```
trifecta_odds（3連単オッズ）
  └─ odds

win_odds（単勝オッズ）
  └─ odds（データ0件）
```

---

## ⚠️ よくある間違い

### 間違い1: exhibition_dataだけを確認

**❌ 誤った判断**:
```python
# exhibition_dataテーブルを確認
SELECT COUNT(*) FROM exhibition_data  # → 861件
# 「展示タイムは861件しかない」と結論
```

**✅ 正しい確認**:
```python
# race_detailsテーブルを確認
SELECT COUNT(*) FROM race_details WHERE exhibition_time IS NOT NULL  # → 637,036件
# 「展示タイムは63万件ある（80%のカバー率）」
```

**教訓**:
- exhibition_dataは最近のリアルタイム収集用（2025年11月～）
- 過去データはrace_detailsにある
- **データ探しは必ずrace_detailsから確認する**

### 間違い2: actual_coursesテーブルで進入隊形を探す

**❌ 誤った判断**:
```python
SELECT COUNT(*) FROM actual_courses  # → 55,578件
# 「進入隊形は5.5万件しかない」
```

**✅ 正しい確認**:
```python
SELECT COUNT(*) FROM race_details WHERE actual_course IS NOT NULL  # → 604,170件
# 「進入隊形は60万件ある（76%のカバー率）」
```

**教訓**:
- actual_coursesは別の目的のテーブル（用途不明、要調査）
- 進入隊形の実データはrace_details.actual_courseにある

### 間違い3: 件数だけでデータの有無を判断

**❌ 誤った判断**:
```python
SELECT COUNT(*) FROM exhibition_data  # → 861件
# 「データが少ない = 使えない」
```

**✅ 正しい確認**:
```python
# 1. テーブル構造を確認
PRAGMA table_info(exhibition_data)

# 2. 他のテーブルも確認
SELECT COUNT(*) FROM race_details WHERE exhibition_time IS NOT NULL

# 3. ドキュメントを確認
# docs/DATABASE_SCHEMA.md
# docs/DATA_LOCATION_MAP.md（このドキュメント）
```

**教訓**:
- 件数が少ないテーブルでも、他に同じデータがあるかもしれない
- 必ず複数のテーブルを確認する
- ドキュメントを参照する

---

## 🔍 データ探索の手順（標準プロセス）

### ステップ1: このドキュメントで確認
```
docs/DATA_LOCATION_MAP.md（このファイル）の
「よく使うデータの所在」テーブルを確認
```

### ステップ2: DATABASE_SCHEMA.mdで詳細確認
```
docs/DATABASE_SCHEMA.md で該当テーブルの構造を確認
```

### ステップ3: 実データを確認
```sql
-- カバー率確認
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN カラム名 IS NOT NULL THEN 1 ELSE 0 END) as has_data
FROM テーブル名;

-- 年度別カバー率
SELECT
    SUBSTR(r.race_date, 1, 4) as year,
    COUNT(*) as total,
    SUM(CASE WHEN rd.カラム名 IS NOT NULL THEN 1 ELSE 0 END) as has_data
FROM テーブル名 rd
JOIN races r ON rd.race_id = r.id
GROUP BY year
ORDER BY year;
```

### ステップ4: 複数テーブルの横断確認
```sql
-- 同じデータが複数テーブルにある可能性を確認
SELECT 'race_details' as source, COUNT(*) FROM race_details WHERE exhibition_time IS NOT NULL
UNION ALL
SELECT 'exhibition_data' as source, COUNT(*) FROM exhibition_data WHERE exhibition_time IS NOT NULL;
```

---

## 📚 関連ドキュメント

| ドキュメント | 用途 |
|-------------|------|
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | 全テーブルの詳細仕様 |
| [DATA_LOCATION_MAP.md](DATA_LOCATION_MAP.md) | データ所在のクイックリファレンス（このドキュメント） |
| [TABLE_PURPOSE.md](TABLE_PURPOSE.md) | 各テーブルの目的と使い分け |

---

## 🚨 緊急時の確認コマンド

### 「XXXのデータはどこ？」と聞かれたら

```bash
# 1. このドキュメントを確認
cat docs/DATA_LOCATION_MAP.md

# 2. DATABASE_SCHEMA.mdで検索
grep -i "XXX" docs/DATABASE_SCHEMA.md

# 3. 実際のDBで検索
python -c "
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()

# 全テーブル名取得
cur.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
tables = [row[0] for row in cur.fetchall()]

# 各テーブルのカラム名を検索
for table in tables:
    cur.execute(f'PRAGMA table_info({table})')
    columns = [row[1] for row in cur.fetchall()]
    if any('XXX' in col.lower() for col in columns):
        print(f'{table}: {columns}')
"
```

---

**最終更新**: 2025-12-22
**次回更新時**: 新しいテーブルを追加した時、データ探索で迷った時
