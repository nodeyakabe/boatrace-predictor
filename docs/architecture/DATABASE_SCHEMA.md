# ボートレース予想システム データベース仕様書

**生成日時**: 2025-12-08 13:41:52
**最終更新**: 2026-02-09 13:30:00 (日付形式統一ポリシー確立)
**データベース**: data/boatrace.db

## 📅 日付形式の統一ポリシー

**統一形式**: `YYYY-MM-DD`（ISO 8601標準）

### 理由
1. ✅ SQL標準形式（BETWEEN句が直感的）
2. ✅ 国際標準（ISO 8601）準拠
3. ✅ 多くのツールで認識可能
4. ✅ 可読性が高い

### 適用範囲
- **DB内部**: 全てのrace_dateカラムは`YYYY-MM-DD`形式で統一
- **CSV出力**: データ収集スクリプトは`YYYY-MM-DD`形式で出力
- **CSV投入**: `YYYY-MM-DD`形式をそのまま受け入れ

### 注意事項
- **YYYYMMDD形式は使用しない**（過去の互換性のため一部残存するが、新規データは全て`YYYY-MM-DD`形式）
- 投入スクリプト（`scripts/maintenance/投入_2021_2023_補完データ.py`）は、両形式に対応済み
- DB全体の日付形式は2026-02-09に`YYYY-MM-DD`形式に統一完了

### 確認方法
```sql
-- 日付形式の確認
SELECT
    CASE
        WHEN race_date LIKE '____-__-__' THEN 'YYYY-MM-DD'
        WHEN LENGTH(race_date) = 8 THEN 'YYYYMMDD'
        ELSE 'その他'
    END as format,
    COUNT(*) as count
FROM races
GROUP BY format;

-- 期待される結果: 全てYYYY-MM-DD形式
```

---

## 🔄 最新の変更履歴

### 2026-02-09: 日付形式の統一（重要）

**変更内容:**
- DB内の全race_dateを`YYYY-MM-DD`形式に統一
- 古いYYYYMMDD形式のデータ（37,320件）を削除
- 投入スクリプト全関数に日付変換コードのコメント追加

**影響:**
- 日付形式混在問題を解決
- データ重複問題を解決
- 307,233件のレースデータが統一形式で整理

**詳細:** [docs/TROUBLE_ANALYSIS_20260209.md](../TROUBLE_ANALYSIS_20260209.md)

### 2026-01-08: 指標データテーブル追加

**新規テーブル:**
- `player_escape_stats` (104,757件) - 選手別逃げ率
- `stadium_attack_stats` (168件) - 会場別まくり率・差し率

**詳細:** [INDICATOR_STATS_SPEC.md](INDICATOR_STATS_SPEC.md)

### 2025-12-12: Phase 1 DB最適化完了

**削除されたカラム:**
- ❌ `races.grade` → `race_grade` に統一
- ❌ `results.winning_technique` → `kimarite` (TEXT)に統一

**影響:**
- races: 133,755件（gradeカラム削除、race_gradeに統一）
- results: 781,989件（winning_techniqueカラム削除）
- VIEW: `race_details_extended` を更新（r.grade → r.race_grade）

**詳細:** [docs/DATABASE_OPTIMIZATION_REPORT.md](DATABASE_OPTIMIZATION_REPORT.md)

## 📊 外部収集データ種一覧

**最終更新**: 2026-02-10
**総データ種**: 17種類
**総レコード数**: 約26.5百万件

### 収集データ種（公式API・外部ソース）

| # | テーブル名 | レコード数 | 充足率 | データ種 | 収集ソース | 補完可否 |
|---|-----------|-----------|-------|---------|----------|---------|
| 1 | **races** | 307,533 | 100% | レース基本情報 | 公式API | ✅ 補完可 |
| 2 | **entries** | 1,803,640 | 100% | 出走表（選手・モーター・ボート） | 公式API | ✅ 補完可 |
| 3 | **results** | 1,563,645 | 100% | レース結果（着順） | 公式API | ✅ 補完可 |
| 4 | **results.kimarite** | 242,076 | **15.5%** | 決まり手 | 公式API | ✅ **補完必須** |
| 5 | **race_details** | 1,179,692 | - | レース詳細 | 公式API | 部分補完 |
| 5-1 | ∟ st_time | 976,223 | 82.8% | STタイム | 公式API | ✅ 補完可 |
| 5-2 | ∟ actual_course | 792,383 | 67.2% | 実際の進入コース | 公式API | ✅ 補完可 |
| 5-3 | ∟ exhibition_time | 1,015,641 | 86.1% | 展示タイム | 公式API | ✅ 補完可 |
| 5-4 | ∟ chikusen_time | 3,307 | **0.3%** | 直前タイム | 公式API？ | ❌ **前日のみ？** |
| 5-5 | ∟ tilt_angle | 854,298 | 72.4% | チルト角 | 公式API | ✅ 補完可 |
| 6 | **race_conditions** | 285,319 | - | レース条件 | 公式API | 部分補完 |
| 6-1 | ∟ weather | 2,262 | **0.8%** | 天気 | 公式API | ⚠️ weatherテーブル推奨 |
| 6-2 | ∟ wind_speed | 283,747 | 99.4% | 風速 | 公式API | ✅ 完全 |
| 6-3 | ∟ wave_height | 283,747 | 99.4% | 波高 | 公式API | ✅ 完全 |
| 6-4 | ∟ water_temperature | 272,619 | 95.5% | 水温 | 公式API | ✅ 補完可 |
| 6-5 | ∟ temperature | 283,747 | 99.4% | 気温 | 公式API | ✅ 完全 |
| 7 | **trifecta_odds** | 13,731,881 | 45.4% | 三連単オッズ | 公式API | ✅ 補完可 |
| 8 | **exacta_odds** | 75 | 0.02% | 二連単オッズ | 公式API | ⚠️ ほぼ空 |
| 9 | **win_odds** | 954 | 0.3% | 単勝オッズ | 公式API | ⚠️ ほぼ空 |
| 10 | **payouts** | 1,036,207 | 43.3% | 払戻金 | 公式API | ✅ 補完可 |
| 11 | **weather** | 11,528 | - | 天気（会場×日別） | 公式API | ✅ 補完可 |
| 12 | **exhibition_data** | 13,695 | 0.7% | オリジナル展示 | 競艇場独自 | ❌ **前日のみ** |
| 13 | **tide** | 27,353 | - | 潮汐（日次） | 潮位データ | ✅ 補完可 |
| 14 | **race_tide_data** | 7,844 | 2.5% | レース時潮位 | 潮位データ | ✅ 補完可 |
| 15 | **rdmdb_tide** | 6,475,040 | - | RDMDB潮位観測 | RDMDB | - |
| 16 | **racers** | 1,602 | 100% | 選手マスタ | 公式API | ✅ 補完可 |
| 17 | **venues** | 24 | 100% | 会場マスタ | 公式API | ✅ 完全 |

### 重要な注意事項

#### ❌ 前日のみ取得可能（逃すと永久欠損）
1. **exhibition_data（オリジナル展示）**
   - 競艇場独自データ
   - 前日夜～当日朝のみ取得可能
   - 過去データは取得不可
   - 最終更新: 2023-11-19（約1,000日前）

2. **race_details.chikusen_time等（直前タイム系）** ⚠️
   - 充足率0.3%（ほぼ空）
   - 公式レース結果ページに含まれない可能性
   - 要検証: 過去データ取得可否

#### ⚠️ データ二重化（どちらを使うべきか）
- **天気**: `race_conditions.weather`(0.8%) vs `weather`テーブル(11,528件) → **weatherテーブル推奨**
- **展示タイム**: `exhibition_data`(0.7%) vs `race_details.exhibition_time`(86.1%) → **race_details推奨**

#### ✅ 補完優先順位
1. **最優先**: results.kimarite（15.5% → 補完中）
2. **高優先**: race_details.st_time（82.8%）、actual_course（67.2%）
3. **中優先**: trifecta_odds（45.4%）、payouts（43.3%）
4. **低優先**: race_details.tilt_angle（72.4%）
5. **検証必要**: chikusen_time（0.3%、過去データ取得可否不明）

---

## 目次

### テーブル一覧

#### マスタデータ (8テーブル)
- [racer_venue_features](#racer_venue_features) (8,952 件)
- [venue_attack_patterns](#venue_attack_patterns) (0 件)
- [venue_data](#venue_data) (24 件)
- [venue_features](#venue_features) (96 件)
- [venue_racer_patterns](#venue_racer_patterns) (0 件)
- [venue_rules](#venue_rules) (308 件)
- [venue_strategies](#venue_strategies) (24 件)
- [venues](#venues) (24 件)

#### 指標データ (2テーブル) ★NEW
- [player_escape_stats](#player_escape_stats) (104,757 件) - 選手別逃げ率
- [stadium_attack_stats](#stadium_attack_stats) (168 件) - 会場別まくり率・差し率

#### レース基本情報 (8テーブル)
- [race_conditions](#race_conditions) (130,792 件)
- [race_details](#race_details) (790,680 件)
- [race_tide_data_backup](#race_tide_data_backup) (12,334 件)
- [racer_attack_patterns](#racer_attack_patterns) (0 件)
- [racer_features](#racer_features) (8,939 件)
- [racer_rules](#racer_rules) (215 件)
- [racers](#racers) (1,602 件)
- [races](#races) (133,327 件)

#### オッズデータ (2テーブル)
- [trifecta_odds](#trifecta_odds) (1,424,376 件)
- [win_odds](#win_odds) (0 件)

#### 予想データ (2テーブル)
- [prediction_history](#prediction_history) (18 件)
- [race_predictions](#race_predictions) (196,692 件)

#### 結果データ (3テーブル)
- [payouts](#payouts) (1,027,127 件)
- [results](#results) (779,318 件)
- [results_backup](#results_backup) (24 件)

#### 選手・モーター情報 (2テーブル)
- [entries](#entries) (799,824 件)
- [motor_features](#motor_features) (0 件)

#### その他 (10テーブル)
- [actual_courses](#actual_courses) (6 件)
- [bet_history](#bet_history) (3 件)
- [exhibition_data](#exhibition_data) (6 件)
- [extracted_rules](#extracted_rules) (308 件)
- [rdmdb_tide](#rdmdb_tide) (6,475,040 件)
- [recommendations](#recommendations) (0 件)
- [sqlite_sequence](#sqlite_sequence) (20 件)
- [sqlite_stat1](#sqlite_stat1) (52 件)
- [tide](#tide) (27,353 件)
- [weather](#weather) (9,018 件)


---

## 🚨 よくある間違い（必読）

**最終更新**: 2026-02-06

### **間違い1: カラム名と同じ名前のテーブルを見落とす**

| データ | カラム（充足率低） | テーブル（充足率高） | 正しい使い方 |
|--------|-------------------|---------------------|-------------|
| **天候データ** | `race_conditions.weather`（0.79%） | `weather`テーブル（27.8%カバレッジ） | **weatherテーブルを使う** |
| | | 結合: `venue_code + race_date` | |

**教訓**: 分析前に必ず全テーブル一覧を確認し、カラム名と同じ名前のテーブルがないかチェック！

### **間違い2: 類似データの保存場所を確認しない**

同じデータが複数の場所に保存されている場合があります：

| データ種別 | 保存場所1 | 保存場所2 | 推奨 |
|-----------|---------|----------|:----:|
| 展示データ | `race_details`（公式API、充足率85%） | `exhibition_data`（Boaters独自、充足率1%） | **保存場所1** |
| 天候データ | `weather`テーブル（27.8%） | `race_conditions.weather`（0.79%） | **保存場所1** |

**詳細**: [データ分析前の必須チェックリスト](../guides/DATA_ANALYSIS_CHECKLIST.md)

---

## ⭐ テーブル活用状況一覧

**最終更新**: 2026-02-06（weather追加）

このセクションではテーブルの活用状況を一覧で確認できます。Claude Codeが効率的にデータを活用できるよう、充足率・活用状況・重要度を明記しています。

### 最重要テーブル（★★★）

| テーブル名 | 件数 | 充足率 | 活用状況 | 備考 |
|-----------|------|:-----:|:-------:|------|
| **races** | 133,327 | 100% | ✅ 使用中 | 全クエリの起点 |
| **entries** | 799,824 | 98% | ✅ 使用中 | 選手・モーター情報 |
| **results** | 779,318 | 97% | ✅ 使用中 | 着順・決まり手 |
| **race_predictions** | 196,692 | 25% | ✅ 使用中 | 予測データ（2020-2025年の25%） |
| **trifecta_odds** | 1,424,376 | 60% | ✅ 使用中 | 3連単オッズ（2021/2023年が低い） |
| **payouts** | 1,027,127 | 89% | ✅ 使用中 | 払戻金 |

### 中重要テーブル（★★）

| テーブル名 | 件数 | 充足率 | 活用状況 | 備考 |
|-----------|------|:-----:|:-------:|------|
| **race_details** | 790,680 | 98% | ✅ 使用中 | 展示タイム、チルト |
| **race_conditions** | 130,792 | 98% | ✅ 使用中 | 天候・風・波（⚠️ weatherカラムは0.79%、**weatherテーブルを使う**） |
| **weather** | 11,528 | - | ✅ 使用中 | **天候データ（会場×日付、27.8%カバレッジ）** |
| **player_escape_stats** | 104,757 | 100% | ✅ 使用中 | 選手別逃げ率（指標データ） |
| **stadium_attack_stats** | 168 | 100% | ✅ 使用中 | 会場別まくり率・差し率（指標データ） |
| **racers** | 1,602 | 100% | ✅ 使用中 | 選手マスタ |
| **venues** | 24 | 100% | ✅ 使用中 | 会場マスタ |
| **rdmdb_tide** | 6,475,040 | 100% | 🟡 未活用 | 潮位データ（活用検討中） |

### 低重要・未使用テーブル（★）

| テーブル名 | 件数 | 充足率 | 活用状況 | 備考 |
|-----------|------|:-----:|:-------:|------|
| **exhibition_data** | 861 | 1% | 🔄 収集中 | オリジナル展示（前日のみ取得可能） |
| **win_odds** | 0 | 0% | ❌ 未収集 | 単勝オッズ（未実装） |
| **exacta_odds** | 0 | 0% | ❌ 未収集 | 2連単オッズ（未実装） |
| **venue_attack_patterns** | 0 | 0% | ❌ 未使用 | 会場攻撃パターン（空テーブル） |
| **motor_features** | 0 | 0% | ❌ 未使用 | モーター特徴量（空テーブル） |
| **racer_attack_patterns** | 0 | 0% | ❌ 未使用 | 選手攻撃パターン（空テーブル） |
| **venue_racer_patterns** | 0 | 0% | ❌ 未使用 | 会場別選手パターン（空テーブル） |
| **recommendations** | 0 | 0% | ❌ 未使用 | 推奨レース（空テーブル） |

### データ充足率の詳細

**2021年・2023年の充足率が低い理由**:
- 2021年: オッズ17.0%、結果25.9% → データ補完作業予定（P1.5）
- 2023年: オッズ16.2%、結果26.9% → データ補完作業予定（P1.5）
- データ補完後: サンプル数が5倍に増加、バックテストの信頼性が大幅向上

**その他の充足率**:
- 2020年: オッズ99.7%、結果100%（ほぼ完全）
- 2022年: オッズ99.9%、結果100%（ほぼ完全）
- 2024年: オッズ99.8%、結果100%（ほぼ完全）
- 2025年: オッズ95.1%、結果100%（収集中）

---

## データベース概要

- **総テーブル数**: 35
- **総レコード数**: 11,831,452

### 主要データ統計

- **総レース数**: 133,327
- **2025年レース数**: 16,979
- **予想データ数**: 196,692
- **オッズ取得済レース数**: 14,505

---

## テーブル詳細

## マスタデータ

### racer_venue_features

**レコード数**: 8,952 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| racer_number | TEXT | ○ |  | ★ |  |
| venue_code | TEXT | ○ |  | ★ | 競艇場コード（01-24） |
| race_date | TEXT | ○ |  | ★ | レース開催日（YYYY-MM-DD形式） |
| venue_win_rate | REAL | ○ |  |  |  |
| venue_avg_rank | REAL | ○ |  |  |  |
| venue_races | INTEGER | ○ |  |  |  |
| computed_at | TEXT | ○ |  |  |  |

#### インデックス

- idx_racer_venue_features_date (race_date)
- sqlite_autoindex_racer_venue_features_1 (racer_number, venue_code, race_date)

#### サンプルデータ

```
サンプル 1:
  racer_number: 3161
  venue_code: 24
  race_date: 2024-04-01
  venue_win_rate: 0.16
  venue_avg_rank: 3.32
  venue_races: 25
  computed_at: 2025-11-13 18:49:30

サンプル 2:
  racer_number: 3257
  venue_code: 24
  race_date: 2024-04-01
  venue_win_rate: 0.3125
  venue_avg_rank: 3.25
  venue_races: 16
  computed_at: 2025-11-13 18:49:30

```

---

### venue_attack_patterns

**レコード数**: 0 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| venue_code | TEXT | ○ |  | ★ | 競艇場コード（01-24） |
| venue_name | TEXT | ○ |  |  |  |
| course_win_rates | TEXT | ○ |  |  |  |
| course_second_rates | TEXT | ○ |  |  |  |
| course_third_rates | TEXT | ○ |  |  |  |
| nige_rate | REAL | ○ |  |  |  |
| sashi_rate | REAL | ○ |  |  |  |
| makuri_rate | REAL | ○ |  |  |  |
| makurisashi_rate | REAL | ○ |  |  |  |
| upset_rate | REAL | ○ |  |  |  |
| high_payout_rate | REAL | ○ |  |  |  |
| total_races | INTEGER | ○ |  |  |  |
| updated_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 更新日時 |

#### インデックス

- idx_venue_patterns_upset (upset_rate)
- sqlite_autoindex_venue_attack_patterns_1 (venue_code)

---

### venue_data

**レコード数**: 24 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| venue_code | TEXT | ○ |  | ★ | 競艇場コード（01-24） |
| venue_name | TEXT | × |  |  |  |
| water_type | TEXT | ○ |  |  |  |
| tidal_range | TEXT | ○ |  |  |  |
| motor_type | TEXT | ○ |  |  |  |
| course_1_win_rate | REAL | ○ |  |  |  |
| course_2_win_rate | REAL | ○ |  |  |  |
| course_3_win_rate | REAL | ○ |  |  |  |
| course_4_win_rate | REAL | ○ |  |  |  |
| course_5_win_rate | REAL | ○ |  |  |  |
| course_6_win_rate | REAL | ○ |  |  |  |
| record_time | TEXT | ○ |  |  |  |
| record_holder | TEXT | ○ |  |  |  |
| record_date | TEXT | ○ |  |  |  |
| characteristics | TEXT | ○ |  |  |  |
| updated_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 更新日時 |

#### インデックス

- sqlite_autoindex_venue_data_1 (venue_code)

#### サンプルデータ

```
サンプル 1:
  venue_code: 01
  venue_name: 桐生
  water_type: 淡水
  tidal_range: なし
  motor_type: 減音
  course_1_win_rate: 47.6
  course_2_win_rate: 12.2
  course_3_win_rate: 13.9
  course_4_win_rate: 15.5
  course_5_win_rate: 8.4
  course_6_win_rate: 3.0
  record_time: 1.42.8
  record_holder: 石田　章央
  record_date: 2004/10/27
  characteristics: None
  updated_at: 2025-11-13 16:16:41

サンプル 2:
  venue_code: 02
  venue_name: 戸田
  water_type: 淡水
  tidal_range: なし
  motor_type: 減音
  course_1_win_rate: 45.2
  course_2_win_rate: 16.9
  course_3_win_rate: 15.7
  course_4_win_rate: 12.3
  course_5_win_rate: 7.4
  course_6_win_rate: 3.1
  record_time: 1.43.8
  record_holder: 横山　節明
  record_date: 2000/04/09
  characteristics: None
  updated_at: 2025-11-13 16:16:41

```

---

### venue_features

**レコード数**: 96 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| venue_code | TEXT | × |  |  | 競艇場コード（01-24） |
| feature | TEXT | × |  |  |  |

#### 外部キー

- venue_code → venue_strategies.venue_code

#### サンプルデータ

```
サンプル 1:
  id: 1
  venue_code: 01
  feature: 標高124mと全24場で最も高い場所に位置し、気圧が低い

サンプル 2:
  id: 2
  venue_code: 01
  feature: 気圧の低さが出足・行き足に影響し、ダッシュ勢が有利

```

---

### venue_racer_patterns

**レコード数**: 0 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| venue_code | TEXT | ○ |  | ★ | 競艇場コード（01-24） |
| racer_number | INTEGER | ○ |  | ★ |  |
| win_rate | REAL | ○ |  |  |  |
| second_rate | REAL | ○ |  |  |  |
| third_rate | REAL | ○ |  |  |  |
| avg_rank | REAL | ○ |  |  |  |
| total_races | INTEGER | ○ |  |  |  |
| updated_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 更新日時 |

#### インデックス

- idx_venue_racer_racer (racer_number)
- idx_venue_racer_venue (venue_code)
- sqlite_autoindex_venue_racer_patterns_1 (venue_code, racer_number)

---

### venue_rules

**レコード数**: 308 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| venue_code | TEXT | ○ |  |  | 競艇場コード（01-24） |
| rule_type | TEXT | × |  |  |  |
| condition_type | TEXT | ○ |  |  |  |
| condition_value | TEXT | ○ |  |  |  |
| target_pit | INTEGER | ○ |  |  |  |
| effect_type | TEXT | × |  |  |  |
| effect_value | REAL | × |  |  |  |
| description | TEXT | × |  |  |  |
| is_active | INTEGER | ○ | 1 |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |
| updated_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 更新日時 |

#### サンプルデータ

```
サンプル 1:
  id: 1079
  venue_code: 08
  rule_type: course_advantage
  condition_type: venue
  condition_value: None
  target_pit: 3
  effect_type: win_rate_penalty
  effect_value: -0.0251
  description: 常滑_3号艇
  is_active: 1
  created_at: 2025-11-28 07:48:04
  updated_at: 2025-11-28 07:48:04

サンプル 2:
  id: 1080
  venue_code: 10
  rule_type: course_advantage
  condition_type: venue
  condition_value: None
  target_pit: 4
  effect_type: win_rate_penalty
  effect_value: -0.0202
  description: 三国_4号艇
  is_active: 1
  created_at: 2025-11-28 07:48:04
  updated_at: 2025-11-28 07:48:04

```

---

### venue_strategies

**レコード数**: 24 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| venue_code | TEXT | ○ |  | ★ | 競艇場コード（01-24） |
| name | TEXT | × |  |  |  |
| water_type | TEXT | ○ |  |  |  |
| course_tendency | TEXT | ○ |  |  |  |
| kimarite_tendency | TEXT | ○ |  |  |  |
| wind_tendency | TEXT | ○ |  |  |  |
| tide_impact | INTEGER | ○ |  |  |  |
| special_notes | TEXT | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |
| updated_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 更新日時 |

#### インデックス

- sqlite_autoindex_venue_strategies_1 (venue_code)

#### サンプルデータ

```
サンプル 1:
  venue_code: 01
  name: 桐生
  water_type: 淡水
  course_tendency: ダッシュ有利
  kimarite_tendency: None
  wind_tendency: None
  tide_impact: 0
  special_notes: 気圧・気温・湿度がモーターに影響し、個体差が大きく出やすい
  created_at: 2025-11-02 01:18:30
  updated_at: 2025-11-02 01:18:30

サンプル 2:
  venue_code: 02
  name: 戸田
  water_type: 淡水
  course_tendency: イン不利、センター有利
  kimarite_tendency: まくり発生率トップクラス、差し・まくり差しはやや決まりにくい
  wind_tendency: 無風約30%
  tide_impact: 0
  special_notes: ２マークも対岸側に振られており、逆転や決まり手「抜き」が多い
  created_at: 2025-11-02 01:18:30
  updated_at: 2025-11-02 01:18:30

```

---

### venues

**レコード数**: 24 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| code | TEXT | × |  |  |  |
| name | TEXT | × |  |  |  |
| latitude | REAL | ○ |  |  |  |
| longitude | REAL | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |

#### インデックス

- sqlite_autoindex_venues_1 (code)

#### サンプルデータ

```
サンプル 1:
  id: 1
  code: 10
  name: 三国
  latitude: 36.2167
  longitude: 136.15
  created_at: 2025-10-29 00:55:55

サンプル 2:
  id: 2
  code: 11
  name: びわこ
  latitude: 35.1333
  longitude: 136.0667
  created_at: 2025-10-29 00:55:55

```

---

## レース基本情報

### race_conditions

**レコード数**: 130,792 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| weather | TEXT | ○ |  |  |  |
| wind_direction | TEXT | ○ |  |  |  |
| wind_speed | REAL | ○ |  |  |  |
| wave_height | INTEGER | ○ |  |  |  |
| temperature | REAL | ○ |  |  |  |
| water_temperature | REAL | ○ |  |  |  |
| collected_at | TEXT | ○ |  |  |  |
| created_at | TEXT | ○ | datetime('now', 'localtime') |  | 作成日時 |

#### インデックス

- sqlite_autoindex_race_conditions_1 (race_id)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 4
  race_id: 15022
  weather: 晴
  wind_direction: 向い風
  wind_speed: 4.2
  wave_height: 2
  temperature: 24.5
  water_temperature: 21.0
  collected_at: 2025-11-25 14:48:06
  created_at: 2025-11-25 14:48:06

サンプル 2:
  id: 5
  race_id: 15023
  weather: None
  wind_direction: 北
  wind_speed: 1.0
  wave_height: 1
  temperature: 17.0
  water_temperature: 13.0
  collected_at: 2025-11-26 11:34:43
  created_at: 2025-11-26 11:34:43

```

---

### race_details

**レコード数**: 790,680 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | × |  |  |  |
| exhibition_time | REAL | ○ |  |  |  |
| tilt_angle | REAL | ○ |  |  |  |
| parts_replacement | TEXT | ○ |  |  |  |
| actual_course | INTEGER | ○ |  |  |  |
| st_time | REAL | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |
| chikusen_time | REAL | ○ |  |  |  |
| isshu_time | REAL | ○ |  |  |  |
| mawariashi_time | REAL | ○ |  |  |  |
| adjusted_weight | REAL | ○ |  |  |  |
| exhibition_course | INTEGER | ○ |  |  |  |
| prev_race_course | INTEGER | ○ |  |  |  |
| prev_race_st | REAL | ○ |  |  |  |
| prev_race_rank | INTEGER | ○ |  |  |  |

#### インデックス

- idx_race_details_actual_course (actual_course)
- idx_race_details_exhibition_course (exhibition_course)
- idx_race_details_st_time (st_time)
- idx_race_details_race_pit (race_id, pit_number)
- idx_race_details_race_id (race_id)
- sqlite_autoindex_race_details_1 (race_id, pit_number)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 7
  race_id: 445
  pit_number: 1
  exhibition_time: 6.73
  tilt_angle: -0.5
  parts_replacement: R
  actual_course: 1
  st_time: 0.1
  created_at: 2025-10-29 11:47:50
  chikusen_time: None
  isshu_time: None
  mawariashi_time: None
  adjusted_weight: None
  exhibition_course: None
  prev_race_course: None
  prev_race_st: None
  prev_race_rank: None

サンプル 2:
  id: 8
  race_id: 445
  pit_number: 2
  exhibition_time: 6.69
  tilt_angle: 0.0
  parts_replacement: R
  actual_course: 2
  st_time: 0.11
  created_at: 2025-10-29 11:47:50
  chikusen_time: None
  isshu_time: None
  mawariashi_time: None
  adjusted_weight: None
  exhibition_course: None
  prev_race_course: None
  prev_race_st: None
  prev_race_rank: None

```

---

### race_tide_data_backup

**レコード数**: 12,334 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INT | ○ |  |  | プライマリキー（自動採番） |
| race_id | INT | ○ |  |  | レースID（racesテーブルへの参照） |
| sea_level_cm | INT | ○ |  |  |  |
| data_source | TEXT | ○ |  |  |  |
| created_at | NUM | ○ |  |  | 作成日時 |
| updated_at | NUM | ○ |  |  | 更新日時 |

#### サンプルデータ

```
サンプル 1:
  id: 1
  race_id: 14998
  sea_level_cm: 30
  data_source: inferred
  created_at: 2025-11-02 09:42:12
  updated_at: 2025-11-02 09:42:12

サンプル 2:
  id: 2
  race_id: 14691
  sea_level_cm: 60
  data_source: inferred
  created_at: 2025-11-02 09:42:13
  updated_at: 2025-11-02 09:42:13

```

---

### racer_attack_patterns

**レコード数**: 0 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| racer_number | INTEGER | ○ |  | ★ |  |
| racer_name | TEXT | ○ |  |  |  |
| rank | TEXT | ○ |  |  |  |
| course_win_rates | TEXT | ○ |  |  |  |
| course_second_rates | TEXT | ○ |  |  |  |
| strong_venues | TEXT | ○ |  |  |  |
| weak_venues | TEXT | ○ |  |  |  |
| avg_start_timing | REAL | ○ |  |  |  |
| start_stability | REAL | ○ |  |  |  |
| total_races | INTEGER | ○ |  |  |  |
| updated_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 更新日時 |

#### インデックス

- idx_racer_patterns_rank (rank)

---

### racer_features

**レコード数**: 8,939 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| racer_number | TEXT | ○ |  | ★ |  |
| race_date | TEXT | ○ |  | ★ | レース開催日（YYYY-MM-DD形式） |
| recent_avg_rank_3 | REAL | ○ |  |  |  |
| recent_avg_rank_5 | REAL | ○ |  |  |  |
| recent_avg_rank_10 | REAL | ○ |  |  |  |
| recent_win_rate_3 | REAL | ○ |  |  |  |
| recent_win_rate_5 | REAL | ○ |  |  |  |
| recent_win_rate_10 | REAL | ○ |  |  |  |
| total_races | INTEGER | ○ |  |  |  |
| computed_at | TEXT | ○ |  |  |  |

#### インデックス

- idx_racer_features_date (race_date)
- sqlite_autoindex_racer_features_1 (racer_number, race_date)

#### サンプルデータ

```
サンプル 1:
  racer_number: 4049
  race_date: 2024-04-14
  recent_avg_rank_3: 1.6666666666666667
  recent_avg_rank_5: 2.4
  recent_avg_rank_10: 2.7
  recent_win_rate_3: 0.6666666666666666
  recent_win_rate_5: 0.4
  recent_win_rate_10: 0.3
  total_races: 10
  computed_at: 2025-11-13 16:59:50

サンプル 2:
  racer_number: 4106
  race_date: 2024-04-14
  recent_avg_rank_3: 3.0
  recent_avg_rank_5: 2.2
  recent_avg_rank_10: 2.9
  recent_win_rate_3: 0.3333333333333333
  recent_win_rate_5: 0.6
  recent_win_rate_10: 0.4
  total_races: 10
  computed_at: 2025-11-13 16:59:50

```

---

### racer_rules

**レコード数**: 215 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| racer_number | TEXT | × |  |  |  |
| racer_name | TEXT | × |  |  |  |
| rule_type | TEXT | × |  |  |  |
| venue_code | TEXT | ○ |  |  | 競艇場コード（01-24） |
| course_number | INTEGER | ○ |  |  |  |
| condition_type | TEXT | ○ |  |  |  |
| effect_type | TEXT | × |  |  |  |
| effect_value | REAL | × |  |  |  |
| description | TEXT | × |  |  |  |
| is_active | INTEGER | ○ | 1 |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |

#### インデックス

- sqlite_autoindex_racer_rules_1 (racer_number, rule_type, venue_code, course_number, condition_type)

#### サンプルデータ

```
サンプル 1:
  id: 1
  racer_number: 4050
  racer_name: 田口　　節子
  rule_type: venue_strong
  venue_code: 24
  course_number: None
  condition_type: None
  effect_type: win_rate_boost
  effect_value: 0.21
  description: 田口　　節子：24場で勝率+21.2%
  is_active: 1
  created_at: 2025-10-31 06:31:12

サンプル 2:
  id: 2
  racer_number: 4050
  racer_name: 田口　　節子
  rule_type: venue_strong
  venue_code: 16
  course_number: None
  condition_type: None
  effect_type: win_rate_boost
  effect_value: 0.21
  description: 田口　　節子：16場で勝率+21.2%
  is_active: 1
  created_at: 2025-10-31 06:31:12

```

---

### racers

**レコード数**: 1,602 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| racer_number | TEXT | ○ |  | ★ |  |
| name | TEXT | × |  |  |  |
| name_kana | TEXT | ○ |  |  |  |
| gender | TEXT | ○ |  |  |  |
| birth_date | DATE | ○ |  |  |  |
| height | REAL | ○ |  |  |  |
| weight | REAL | ○ |  |  |  |
| blood_type | TEXT | ○ |  |  |  |
| branch | TEXT | ○ |  |  |  |
| hometown | TEXT | ○ |  |  |  |
| registration_period | INTEGER | ○ |  |  |  |
| rank | TEXT | ○ |  |  |  |
| win_rate | REAL | ○ |  |  |  |
| second_rate | REAL | ○ |  |  |  |
| third_rate | REAL | ○ |  |  |  |
| ability_index | REAL | ○ |  |  |  |
| average_st | REAL | ○ |  |  |  |
| wins | INTEGER | ○ |  |  |  |
| updated_at | TIMESTAMP | ○ |  |  | 更新日時 |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |

#### インデックス

- sqlite_autoindex_racers_1 (racer_number)

#### サンプルデータ

```
サンプル 1:
  racer_number: 4418
  name: 茅原 悠紀
  name_kana: カヤハラ ユウキ
  gender: female
  birth_date: None
  height: None
  weight: None
  blood_type: None
  branch: 岡山支部
  hometown: 岡山
  registration_period: None
  rank: A1級
  win_rate: 8.88
  second_rate: None
  third_rate: None
  ability_index: 75.0
  average_st: None
  wins: None
  updated_at: 2025-12-01T13:30:07.554645
  created_at: 2025-12-01 04:09:33

サンプル 2:
  racer_number: 4444
  name: 桐生 順平
  name_kana: キリュウ ジュンペイ
  gender: female
  birth_date: None
  height: None
  weight: None
  blood_type: None
  branch: 埼玉支部
  hometown: 福島
  registration_period: None
  rank: A1級
  win_rate: 8.17
  second_rate: None
  third_rate: None
  ability_index: 69.0
  average_st: None
  wins: None
  updated_at: 2025-12-01T13:30:08.151458
  created_at: 2025-12-01 04:09:37

```

---

### races

**レコード数**: 133,327 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| venue_code | TEXT | × |  |  | 競艇場コード（01-24） |
| race_date | DATE | × |  |  | レース開催日（YYYY-MM-DD形式） |
| race_number | INTEGER | × |  |  | レース番号（1-12R） |
| race_time | TEXT | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |
| race_grade | TEXT | ○ |  |  |  |
| race_distance | INTEGER | ○ |  |  |  |
| race_status | TEXT | ○ | 'unknown' |  |  |
| grade | TEXT | ○ | '' |  |  |
| is_nighter | INTEGER | ○ | 0 |  |  |
| is_ladies | INTEGER | ○ | 0 |  |  |
| is_rookie | INTEGER | ○ | 0 |  |  |
| is_shinnyuu_kotei | INTEGER | ○ | 0 |  |  |

#### インデックス

- idx_races_venue_date_number (venue_code, race_date, race_number)
- idx_races_venue_date (venue_code, race_date)
- idx_races_date (race_date)
- sqlite_autoindex_races_1 (venue_code, race_date, race_number)

#### 外部キー

- venue_code → venues.code

#### サンプルデータ

```
サンプル 1:
  id: 1
  venue_code: 10
  race_date: 2025-10-29
  race_number: 1
  race_time: 08:47
  created_at: 2025-10-29 02:36:47
  race_grade: 一般
  race_distance: 1800
  race_status: completed
  grade: 
  is_nighter: 0
  is_ladies: 0
  is_rookie: 0
  is_shinnyuu_kotei: 0

サンプル 2:
  id: 2
  venue_code: 10
  race_date: 2025-10-29
  race_number: 2
  race_time: 09:13
  created_at: 2025-10-29 02:36:47
  race_grade: 一般
  race_distance: 1800
  race_status: completed
  grade: 
  is_nighter: 0
  is_ladies: 0
  is_rookie: 0
  is_shinnyuu_kotei: 0

```

---

## オッズデータ

### trifecta_odds

**レコード数**: 1,429,326 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| combination | TEXT | × |  |  |  |
| odds | REAL | × |  |  | オッズ倍率 |
| fetched_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  |  |

#### インデックス

- idx_trifecta_odds_race_id (race_id)
- sqlite_autoindex_trifecta_odds_1 (race_id, combination)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 10557
  race_id: 132731
  combination: 1-2-3
  odds: 8.3
  fetched_at: 2025-12-02 05:32:17

サンプル 2:
  id: 10558
  race_id: 132731
  combination: 2-1-3
  odds: 9.3
  fetched_at: 2025-12-02 05:32:17

```

---

### win_odds

**レコード数**: 0 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | × |  |  |  |
| odds | REAL | × |  |  | オッズ倍率 |
| fetched_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  |  |

#### インデックス

- idx_win_odds_race_id (race_id)
- sqlite_autoindex_win_odds_1 (race_id, pit_number)

#### 外部キー

- race_id → races.id

---

## 予想データ

### prediction_history

**レコード数**: 18 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | × |  |  |  |
| prediction_type | TEXT | × |  |  | 予想タイプ（advance/before） |
| rank_prediction | INTEGER | ○ |  |  | 予想順位 |
| confidence | TEXT | ○ |  |  |  |
| total_score | REAL | ○ |  |  | 予想スコア |
| course_score | REAL | ○ |  |  | 予想スコア |
| racer_score | REAL | ○ |  |  | 予想スコア |
| motor_score | REAL | ○ |  |  | 予想スコア |
| kimarite_score | REAL | ○ |  |  | 予想スコア |
| grade_score | REAL | ○ |  |  | 予想スコア |
| has_exhibition_data | BOOLEAN | ○ | 0 |  |  |
| has_condition_data | BOOLEAN | ○ | 0 |  |  |
| has_course_data | BOOLEAN | ○ | 0 |  |  |
| created_at | TEXT | ○ | datetime('now', 'localtime') |  | 作成日時 |

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 1
  race_id: 15022
  pit_number: 1
  prediction_type: initial
  rank_prediction: 1
  confidence: D
  total_score: 45.9
  course_score: None
  racer_score: None
  motor_score: None
  kimarite_score: None
  grade_score: None
  has_exhibition_data: 0
  has_condition_data: 0
  has_course_data: 0
  created_at: 2025-11-25 14:44:46

サンプル 2:
  id: 2
  race_id: 15022
  pit_number: 2
  prediction_type: initial
  rank_prediction: 3
  confidence: E
  total_score: 42.3
  course_score: None
  racer_score: None
  motor_score: None
  kimarite_score: None
  grade_score: None
  has_exhibition_data: 0
  has_condition_data: 0
  has_course_data: 0
  created_at: 2025-11-25 14:44:46

```

---

### race_predictions

**レコード数**: 196,692 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | × |  |  |  |
| rank_prediction | INTEGER | × |  |  | 予想順位 |
| total_score | REAL | × |  |  | 予想スコア |
| confidence | TEXT | ○ |  |  |  |
| racer_name | TEXT | ○ |  |  |  |
| racer_number | TEXT | ○ |  |  |  |
| applied_rules | TEXT | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |
| course_score | REAL | ○ |  |  | 予想スコア |
| racer_score | REAL | ○ |  |  | 予想スコア |
| motor_score | REAL | ○ |  |  | 予想スコア |
| kimarite_score | REAL | ○ |  |  | 予想スコア |
| grade_score | REAL | ○ |  |  | 予想スコア |
| prediction_type | TEXT | ○ | 'advance' |  | 予想タイプ（advance/before） |
| generated_at | TIMESTAMP | ○ |  |  |  |

#### インデックス

- sqlite_autoindex_race_predictions_1 (race_id, pit_number, prediction_type)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 1
  race_id: 131857
  pit_number: 1
  rank_prediction: 1
  total_score: 11.0
  confidence: E
  racer_name: 下條　雄太郎
  racer_number: 4352
  applied_rules: None
  created_at: 2025-11-25 04:45:05
  course_score: 2.0
  racer_score: 5.0
  motor_score: 4.0
  kimarite_score: 0.0
  grade_score: 0.0
  prediction_type: advance
  generated_at: None

サンプル 2:
  id: 2
  race_id: 131857
  pit_number: 3
  rank_prediction: 5
  total_score: -5.76
  confidence: E
  racer_name: 山口　　広樹
  racer_number: 5053
  applied_rules: None
  created_at: 2025-11-25 04:45:05
  course_score: -5.76
  racer_score: 0.0
  motor_score: 0.0
  kimarite_score: 0.0
  grade_score: 0.0
  prediction_type: advance
  generated_at: None

```

---

## 結果データ

### payouts

**レコード数**: 1,027,127 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| bet_type | TEXT | × |  |  |  |
| combination | TEXT | × |  |  |  |
| amount | INTEGER | × |  |  |  |
| popularity | INTEGER | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |

#### インデックス

- idx_payouts_bet_type (bet_type)
- idx_payouts_race_id (race_id)
- sqlite_autoindex_payouts_1 (race_id, bet_type, combination)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 1
  race_id: 96
  bet_type: trifecta
  combination: 3-4-2
  amount: 14320
  popularity: 33
  created_at: 2025-10-29 23:55:49

サンプル 2:
  id: 2
  race_id: 96
  bet_type: trio
  combination: 2=3=4
  amount: 1960
  popularity: 7
  created_at: 2025-10-29 23:55:49

```

---

### results

**レコード数**: 779,318 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | × |  |  |  |
| rank | TEXT | ○ |  |  |  |
| is_invalid | INTEGER | ○ | 0 |  |  |
| trifecta_odds | REAL | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |
| kimarite | TEXT | ○ |  |  |  |
| winning_technique | INTEGER | ○ |  |  |  |

#### インデックス

- idx_results_race_invalid_rank (race_id, is_invalid, rank)
- idx_results_invalid (is_invalid)
- idx_results_rank (rank)
- idx_results_race_id (race_id)
- idx_results_race_pit (race_id, pit_number)
- sqlite_autoindex_results_1 (race_id, pit_number)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 331
  race_id: 325
  pit_number: 4
  rank: 1
  is_invalid: 0
  trifecta_odds: None
  created_at: 2025-10-29 08:17:15
  kimarite: まくり
  winning_technique: None

サンプル 2:
  id: 332
  race_id: 325
  pit_number: 5
  rank: 2
  is_invalid: 0
  trifecta_odds: None
  created_at: 2025-10-29 08:17:15
  kimarite: None
  winning_technique: None

```

---

### results_backup

**レコード数**: 24 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INT | ○ |  |  | プライマリキー（自動採番） |
| race_id | INT | ○ |  |  | レースID（racesテーブルへの参照） |
| first_place | INT | ○ |  |  | 着順 |
| second_place | INT | ○ |  |  | 着順 |
| third_place | INT | ○ |  |  | 着順 |
| trifecta_odds | REAL | ○ |  |  |  |
| created_at | NUM | ○ |  |  | 作成日時 |

#### サンプルデータ

```
サンプル 1:
  id: 1
  race_id: 13
  first_place: 3
  second_place: None
  third_place: None
  trifecta_odds: None
  created_at: 2025-10-29 04:56:57

サンプル 2:
  id: 2
  race_id: 14
  first_place: 3
  second_place: None
  third_place: None
  trifecta_odds: None
  created_at: 2025-10-29 04:57:19

```

---

## 選手・モーター情報

### entries

**レコード数**: 799,824 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | × |  |  |  |
| racer_number | TEXT | ○ |  |  |  |
| racer_name | TEXT | ○ |  |  |  |
| racer_rank | TEXT | ○ |  |  |  |
| racer_home | TEXT | ○ |  |  |  |
| racer_age | INTEGER | ○ |  |  |  |
| racer_weight | REAL | ○ |  |  |  |
| motor_number | INTEGER | ○ |  |  |  |
| boat_number | INTEGER | ○ |  |  |  |
| win_rate | REAL | ○ |  |  |  |
| second_rate | REAL | ○ |  |  |  |
| third_rate | REAL | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |
| f_count | INTEGER | ○ |  |  |  |
| l_count | INTEGER | ○ |  |  |  |
| avg_st | REAL | ○ |  |  |  |
| local_win_rate | REAL | ○ |  |  |  |
| local_second_rate | REAL | ○ |  |  |  |
| local_third_rate | REAL | ○ |  |  |  |
| motor_second_rate | REAL | ○ |  |  |  |
| motor_third_rate | REAL | ○ |  |  |  |
| boat_second_rate | REAL | ○ |  |  |  |
| boat_third_rate | REAL | ○ |  |  |  |

#### インデックス

- idx_entries_racer_race (racer_number, race_id)
- idx_entries_boat_number (boat_number)
- idx_entries_motor_number (motor_number)
- idx_entries_racer_number (racer_number)
- idx_entries_race_pit (race_id, pit_number)
- idx_entries_race_id (race_id)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 464
  race_id: 69
  pit_number: 1
  racer_number: 5256
  racer_name: 中山　　翔太
  racer_rank: A2
  racer_home: 三重
  racer_age: 21
  racer_weight: 52.0
  motor_number: 31
  boat_number: 67
  win_rate: 6.5
  second_rate: 46.9
  third_rate: 68.97
  created_at: 2025-10-29 05:47:30
  f_count: 0
  l_count: 0
  avg_st: 0.16
  local_win_rate: 6.0
  local_second_rate: 50.0
  local_third_rate: 66.67
  motor_second_rate: 36.89
  motor_third_rate: 56.56
  boat_second_rate: 28.1
  boat_third_rate: 52.07

サンプル 2:
  id: 465
  race_id: 69
  pit_number: 2
  racer_number: 3590
  racer_name: 濱野谷　憲吾
  racer_rank: A1
  racer_home: 東京
  racer_age: 51
  racer_weight: 53.1
  motor_number: 52
  boat_number: 27
  win_rate: 7.08
  second_rate: 53.44
  third_rate: 70.23
  created_at: 2025-10-29 05:47:30
  f_count: 0
  l_count: 0
  avg_st: 0.14
  local_win_rate: 6.71
  local_second_rate: 35.71
  local_third_rate: 35.71
  motor_second_rate: 37.01
  motor_third_rate: 58.27
  boat_second_rate: 34.45
  boat_third_rate: 52.1

```

---

### motor_features

**レコード数**: 0 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| race_id | INTEGER | ○ |  | ★ | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | ○ |  | ★ |  |
| motor_recent_2rate_diff | REAL | ○ |  |  |  |
| motor_trend | REAL | ○ |  |  |  |
| computed_at | TEXT | ○ |  |  |  |

#### インデックス

- sqlite_autoindex_motor_features_1 (race_id, pit_number)

---

## その他

### actual_courses

**レコード数**: 6 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | × |  |  |  |
| actual_course | INTEGER | × |  |  |  |
| collected_at | TEXT | ○ |  |  |  |
| created_at | TEXT | ○ | datetime('now', 'localtime') |  | 作成日時 |

#### インデックス

- sqlite_autoindex_actual_courses_1 (race_id, pit_number)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 13
  race_id: 15022
  pit_number: 1
  actual_course: 1
  collected_at: 2025-11-25 14:48:06
  created_at: 2025-11-25 14:48:06

サンプル 2:
  id: 14
  race_id: 15022
  pit_number: 2
  actual_course: 2
  collected_at: 2025-11-25 14:48:06
  created_at: 2025-11-25 14:48:06

```

---

### bet_history

**レコード数**: 3 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| bet_date | TEXT | × |  |  |  |
| venue_code | TEXT | × |  |  | 競艇場コード（01-24） |
| venue_name | TEXT | ○ |  |  |  |
| race_number | INTEGER | × |  |  | レース番号（1-12R） |
| combination | TEXT | × |  |  |  |
| bet_amount | INTEGER | × |  |  |  |
| odds | REAL | × |  |  |  |
| predicted_prob | REAL | ○ |  |  |  |
| expected_value | REAL | ○ |  |  |  |
| buy_score | REAL | ○ |  |  |  |
| result | INTEGER | ○ |  |  |  |
| payout | INTEGER | ○ |  |  |  |
| profit | INTEGER | ○ |  |  |  |
| notes | TEXT | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |

#### インデックス

- idx_result (result)
- idx_venue_code (venue_code)
- idx_bet_date (bet_date)

#### サンプルデータ

```
サンプル 1:
  id: 1
  bet_date: 2025-11-01
  venue_code: 06
  venue_name: 浜名湖
  race_number: 1
  combination: 1-2-3
  bet_amount: 1000
  odds: 15.5
  predicted_prob: 0.1
  expected_value: 1.55
  buy_score: 0.75
  result: 1
  payout: 15500
  profit: 14500
  notes: None
  created_at: 2025-11-03 02:35:53

サンプル 2:
  id: 2
  bet_date: 2025-11-01
  venue_code: 06
  venue_name: 浜名湖
  race_number: 2
  combination: 3-1-4
  bet_amount: 1000
  odds: 25.0
  predicted_prob: 0.06
  expected_value: 1.5
  buy_score: 0.72
  result: 0
  payout: 0
  profit: -1000
  notes: None
  created_at: 2025-11-03 02:35:53

```

---

### exhibition_data

**レコード数**: 861 件

**目的**: 2025年11月以降のリアルタイム展示情報収集専用テーブル

**重要**: 過去の展示データは `race_details` テーブルに格納されています（80%以上のカバー率）。
exhibition_dataは新規収集用であり、過去データ分析には `race_details.exhibition_time` を使用してください。

**使い分け**:
- **過去データ分析** → `race_details` テーブル（2020-2025年、63万件以上）
- **リアルタイム収集** → `exhibition_data` テーブル（2025年11月～、約860件）

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| pit_number | INTEGER | × |  |  |  |
| exhibition_time | REAL | ○ |  |  |  |
| start_timing | INTEGER | ○ |  |  |  |
| turn_quality | INTEGER | ○ |  |  |  |
| weight_change | REAL | ○ |  |  |  |
| boat_condition | TEXT | ○ |  |  |  |
| collected_at | TEXT | ○ |  |  |  |
| created_at | TEXT | ○ | datetime('now', 'localtime') |  | 作成日時 |

#### インデックス

- sqlite_autoindex_exhibition_data_1 (race_id, pit_number)

#### 外部キー

- race_id → races.id

#### サンプルデータ

```
サンプル 1:
  id: 19
  race_id: 15022
  pit_number: 1
  exhibition_time: 6.72
  start_timing: 4
  turn_quality: 4
  weight_change: 0.0
  boat_condition: None
  collected_at: 2025-11-25 14:48:04
  created_at: 2025-11-25 14:48:04

サンプル 2:
  id: 20
  race_id: 15022
  pit_number: 2
  exhibition_time: 6.85
  start_timing: 3
  turn_quality: 3
  weight_change: 0.5
  boat_condition: None
  collected_at: 2025-11-25 14:48:04
  created_at: 2025-11-25 14:48:04

```

---

### extracted_rules

**レコード数**: 308 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| rule_id | INTEGER | ○ |  | ★ |  |
| rule_name | TEXT | × |  |  |  |
| condition_json | TEXT | × |  |  |  |
| adjustment | REAL | × |  |  |  |
| sample_size | INTEGER | × |  |  |  |
| baseline_rate | REAL | × |  |  |  |
| actual_rate | REAL | × |  |  |  |
| confidence | REAL | × |  |  |  |
| is_valid | INTEGER | × |  |  |  |
| created_at | TEXT | × |  |  | 作成日時 |

#### インデックス

- sqlite_autoindex_extracted_rules_1 (rule_name)

#### サンプルデータ

```
サンプル 1:
  rule_id: 16
  rule_name: 常滑_3号艇
  condition_json: {"venue_code": "08", "pit_number": 3}
  adjustment: -0.0251
  sample_size: 477
  baseline_rate: 0.1321
  actual_rate: 0.1069
  confidence: 0.5159
  is_valid: 1
  created_at: 2025-11-19T13:11:35.614086

サンプル 2:
  rule_id: 30
  rule_name: 三国_4号艇
  condition_json: {"venue_code": "10", "pit_number": 4}
  adjustment: -0.0202
  sample_size: 642
  baseline_rate: 0.0996
  actual_rate: 0.0794
  confidence: 0.5695
  is_valid: 1
  created_at: 2025-11-19T13:11:35.614305

```

---

### rdmdb_tide

**レコード数**: 6,475,040 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| station_name | TEXT | × |  |  |  |
| observation_datetime | TEXT | × |  |  |  |
| sea_level_cm | INTEGER | ○ |  |  |  |
| air_pressure_hpa | REAL | ○ |  |  |  |
| temperature_c | REAL | ○ |  |  |  |
| sea_level_smoothed_cm | REAL | ○ |  |  |  |
| created_at | TEXT | ○ | datetime('now') |  | 作成日時 |

#### インデックス

- idx_rdmdb_tide_station_datetime (station_name, observation_datetime)
- sqlite_autoindex_rdmdb_tide_1 (station_name, observation_datetime)

#### サンプルデータ

```
サンプル 1:
  id: 1
  station_name: Hakata
  observation_datetime: 2022-11-01 00:00:00
  sea_level_cm: 230
  air_pressure_hpa: 10.22
  temperature_c: None
  sea_level_smoothed_cm: 228.73
  created_at: 2025-11-01 06:40:25

サンプル 2:
  id: 2
  station_name: Hakata
  observation_datetime: 2022-11-01 00:00:30
  sea_level_cm: 229
  air_pressure_hpa: 10.22
  temperature_c: None
  sea_level_smoothed_cm: 228.79
  created_at: 2025-11-01 06:40:25

```

---

### recommendations

**レコード数**: 0 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| race_id | INTEGER | × |  |  | レースID（racesテーブルへの参照） |
| recommend_date | DATE | × |  |  |  |
| confidence_score | REAL | ○ |  |  |  |
| reason | TEXT | ○ |  |  |  |
| prediction_1st | INTEGER | ○ |  |  |  |
| prediction_2nd | INTEGER | ○ |  |  |  |
| prediction_3rd | INTEGER | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |

#### 外部キー

- race_id → races.id

---

### sqlite_sequence

**レコード数**: 20 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| name |  | ○ |  |  |  |
| seq |  | ○ |  |  |  |

#### サンプルデータ

```
サンプル 1:
  name: venues
  seq: 31

サンプル 2:
  name: races
  seq: 133327

```

---

### sqlite_stat1

**レコード数**: 52 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| tbl |  | ○ |  |  |  |
| idx |  | ○ |  |  |  |
| stat |  | ○ |  |  |  |

#### サンプルデータ

```
サンプル 1:
  tbl: results_backup
  idx: None
  stat: 24

サンプル 2:
  tbl: race_details
  idx: idx_race_details_actual_course
  stat: 788880 112698

```

---

### tide

**レコード数**: 27,353 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| venue_code | TEXT | × |  |  | 競艇場コード（01-24） |
| tide_date | DATE | × |  |  |  |
| tide_time | TEXT | ○ |  |  |  |
| tide_type | TEXT | ○ |  |  |  |
| tide_level | REAL | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |

#### 外部キー

- venue_code → venues.code

#### サンプルデータ

```
サンプル 1:
  id: 1
  venue_code: 22
  tide_date: 2022-11-01
  tide_time: 02:20
  tide_type: 満潮
  tide_level: 236.83
  created_at: 2025-11-02 00:06:13

サンプル 2:
  id: 2
  venue_code: 22
  tide_date: 2022-11-01
  tide_time: 09:40
  tide_type: 干潮
  tide_level: 140.98
  created_at: 2025-11-02 00:06:13

```

---

### weather

**レコード数**: 9,018 件

#### カラム一覧

| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |
|----------|-----|----------|--------------|-----|------|
| id | INTEGER | ○ |  | ★ | プライマリキー（自動採番） |
| venue_code | TEXT | × |  |  | 競艇場コード（01-24） |
| weather_date | DATE | × |  |  |  |
| temperature | REAL | ○ |  |  |  |
| weather_condition | TEXT | ○ |  |  |  |
| wind_speed | REAL | ○ |  |  |  |
| wind_direction | TEXT | ○ |  |  |  |
| humidity | INTEGER | ○ |  |  |  |
| created_at | TIMESTAMP | ○ | CURRENT_TIMESTAMP |  | 作成日時 |
| water_temperature | REAL | ○ |  |  |  |
| wave_height | REAL | ○ |  |  |  |
| weather_code | INTEGER | ○ |  |  |  |
| wind_dir_code | INTEGER | ○ |  |  |  |

#### インデックス

- sqlite_autoindex_weather_1 (venue_code, weather_date)

#### 外部キー

- venue_code → venues.code

#### サンプルデータ

```
サンプル 1:
  id: 16
  venue_code: 04
  weather_date: 2025-10-02
  temperature: 25.0
  weather_condition: None
  wind_speed: 1.0
  wind_direction: 北北西
  humidity: None
  created_at: 2025-10-30 12:57:56
  water_temperature: 24.0
  wave_height: 3.0
  weather_code: None
  wind_dir_code: None

サンプル 2:
  id: 27
  venue_code: 05
  weather_date: 2025-10-02
  temperature: 26.0
  weather_condition: None
  wind_speed: 1.0
  wind_direction: 北北西
  humidity: None
  created_at: 2025-10-30 13:01:23
  water_temperature: 25.0
  wave_height: 1.0
  weather_code: None
  wind_dir_code: None

```

---

## よくある検索パターン

### データ名の対応表

| 探しているデータ | 実際のテーブル名 | カラム名 | 備考 |
|-----------------|------------------|----------|------|
| 3連単オッズ | `trifecta_odds` | `odds` | ✅ 存在 |
| 2連単オッズ | ❌ `exacta_odds` | - | **テーブル自体が存在しません** |
| 単勝オッズ | `win_odds` | `odds` | ✅ 存在（データ0件） |
| レース結果（着順） | `results` | `rank` | ✅ 正: `rank` (誤: position) |
| 払戻金 | `payouts` | `amount` | ✅ 正: `amount` (誤: payout_amount) |
| 予想データ | `race_predictions` | `rank_prediction` | ✅ 正: `rank_prediction` (誤: predicted_position) |
| 出走表 | `entries` | `racer_number`, `motor_number` | ✅ 正: `racer_number` (誤: racer_id) |
| 選手情報（名前） | `entries` | `racer_name` | ✅ 出走表に含まれる |
| 選手情報（級別） | `entries` | `racer_rank` | ✅ 出走表に含まれる |
| ST時間 | ❌ `entries` | - | **カラム自体が存在しません** |
| 展示タイム | ❌ `entries` | - | **カラム自体が存在しません** |
| F/L回数 | `entries` | `f_count`, `l_count` | ✅ 存在 |
| 平均ST | `entries` | `avg_st` | ✅ 存在 |

### クエリ例

```sql
-- 2025年のレース一覧
SELECT * FROM races WHERE race_date LIKE '2025%';

-- 特定レースの3連単オッズ
SELECT * FROM trifecta_odds WHERE race_id = 12345;

-- 特定レースの予想データ（正しいカラム名）
SELECT
  pit_number,
  rank_prediction,
  total_score,
  confidence,
  racer_name
FROM race_predictions
WHERE race_id = 12345
ORDER BY rank_prediction;

-- 特定レースの結果（正しいカラム名）
SELECT
  pit_number,
  rank,
  kimarite
FROM results
WHERE race_id = 12345
ORDER BY CAST(rank AS INTEGER);

-- 特定レースの払戻金（正しいカラム名）
SELECT
  bet_type,
  combination,
  amount,
  popularity
FROM payouts
WHERE race_id = 12345;

-- 特定レースの出走表（正しいカラム名）
SELECT
  pit_number,
  racer_number,
  racer_name,
  racer_rank,
  win_rate,
  motor_number,
  avg_st,
  f_count,
  l_count
FROM entries
WHERE race_id = 12345
ORDER BY pit_number;

-- オッズが取得済みのレース
SELECT DISTINCT r.*
FROM races r
INNER JOIN trifecta_odds o ON r.id = o.race_id
WHERE r.race_date LIKE '2025%';

-- 予想と結果の比較
SELECT
  p.pit_number,
  p.racer_name,
  p.rank_prediction AS 予想順位,
  r.rank AS 実際の順位,
  p.total_score AS 予想スコア
FROM race_predictions p
LEFT JOIN results r ON p.race_id = r.race_id AND p.pit_number = r.pit_number
WHERE p.race_id = 12345
ORDER BY p.rank_prediction;
```

### 重要な注意事項

#### ⚠️ 存在しないデータ

以下のデータは**データベースに存在しません**：

1. **2連単オッズ（exacta_odds）**
   - テーブル自体が存在しません
   - スクリプト `scripts/fetch_exacta_odds.py` は存在しますが、データは未取得です

2. **ST時間（個別レース）**
   - `entries` テーブルに `start_timing` カラムは存在しません
   - **代替**: `avg_st`（平均ST時間）が存在します

3. **展示タイム（個別レース）**
   - `entries` テーブルに `exhibition_time` カラムは存在しません
   - 別テーブル `exhibition_data` (6件のみ) に少量データあり

#### ✅ 実際に使用可能なデータ

- **3連単オッズ**: `trifecta_odds.odds`
- **着順**: `results.rank`
- **払戻金**: `payouts.amount`
- **予想順位**: `race_predictions.rank_prediction`
- **平均ST**: `entries.avg_st`
- **F/L回数**: `entries.f_count`, `entries.l_count`

---

## ⚠️ よくある計算ミスと対策

**最終更新**: 2026-01-30

このセクションでは、過去に発生した計算ミスのパターンと対策を記載します。分析スクリプト作成時に必ず参照してください。

### 🚨 1-2-3固定オッズ問題（★★★★★ 超重要）

#### 問題の説明

分析スクリプトで「予測順位ベースのオッズ」ではなく「枠番固定オッズ（1号艇-2号艇-3号艇）」を取得していた。

#### 誤った実装例

❌ **誤り**: 枠番固定オッズを取得
```sql
-- 1号艇-2号艇-3号艇の固定オッズを取得（間違い）
SELECT
    rp.race_id,
    rp.confidence,
    t.odds
FROM race_predictions rp
JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = '1-2-3'  -- ←これが間違い
WHERE rp.prediction_type = 'before' AND rp.rank_prediction = 1;
```

**問題点**:
- 予測が「4-3-2」（4号艇1着、3号艇2着、2号艇3着）でも、オッズは「1-2-3」を取得してしまう
- 実際の買い目と異なるオッズで分析するため、ROIが大幅に乖離する

#### 正しい実装例

✅ **正しい**: 予測順位ベースのオッズを取得
```sql
-- CTE（Common Table Expression）で予測組み合わせを構築
WITH prediction_combos AS (
    -- 予測1着-予測2着-予測3着の組み合わせを構築
    SELECT
        rp1.race_id,
        rp1.confidence,
        CAST(rp1.pit_number AS TEXT) || '-' ||
        CAST(rp2.pit_number AS TEXT) || '-' ||
        CAST(rp3.pit_number AS TEXT) as pred_combo
    FROM race_predictions rp1
    -- 予測2着を取得
    JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    -- 予測3着を取得
    JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
        AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
),
actual_combos AS (
    -- 実際の結果組み合わせを構築（実際1着-実際2着-実際3着）
    SELECT
        race_id,
        CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
        CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
        CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
    FROM results
    WHERE rank IN ('1', '2', '3')
    GROUP BY race_id
)
-- 予測組み合わせのオッズを取得
SELECT
    pc.race_id,
    pc.confidence,
    pc.pred_combo,
    ac.actual_combo,
    t.odds,
    CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END as is_hit
FROM prediction_combos pc
-- 予測組み合わせと一致するオッズを取得
JOIN trifecta_odds t ON pc.race_id = t.race_id
                     AND t.combination = pc.pred_combo  -- ←これが正しい
JOIN actual_combos ac ON pc.race_id = ac.race_id;
```

#### 影響

**実例**: A×50倍+条件の分析
- 誤った計算: ROI 396%（分析スクリプト）
- 正しい計算: ROI 58.4%（standard_backtest.py）
- **乖離**: -338pt

**原因**:
- 1号艇が1着になるレースは多い（インコース有利）
- 「1-2-3」固定オッズは低くなりがち（平均15-20倍）
- 実際の予測は多様（4-3-2、3-1-5など）で、オッズは高い（50-100倍）
- 的中判定も間違う（予測4-3-2が的中しても、実際1-2-3でないと不的中扱い）

#### 対策

1. **分析スクリプトは必ずCTEパターンを使用**
   - 予測組み合わせを動的に構築
   - `combination = pc.pred_combo` で正しいオッズを取得

2. **ROI 200%超えは計算ミスを疑う**
   - 過去の購入条件は全てROI 100-200%の範囲
   - ROI 300%超えは計算ミスの可能性が高い

3. **standard_backtest.py で最終検証必須**
   - 分析スクリプトの結果が良くても、必ず standard_backtest.py で検証
   - standard_backtest.py は正しいロジックで実装済み

4. **修正済みスクリプト一覧**（2026-01-30修正完了）
   - `scripts/analysis/analyze_confidence_hit_patterns.py` (5箇所修正)
   - `scripts/analysis/analyze_confidence_deep_dive.py` (9箇所修正)
   - `scripts/analysis/analyze_meta_index_effect.py` (3箇所修正)
   - `scripts/analysis/analyze_b_50_100_details.py` (1箇所修正)
   - `scripts/analysis/analyze_b_50_100_details_v2.py` (1箇所修正)
   - `scripts/analysis/analyze_bx50_100_miss_patterns.py` (2箇所修正)
   - `scripts/analysis/analyze_bx50_100_comprehensive.py` (1箇所修正)

---

## 関連ドキュメント

- **クイックリファレンス**: [docs/QUICK_REFERENCE.md](../QUICK_REFERENCE.md) - テーブル早見表・よく使うクエリ
- **SQLクエリサンプル集**: [docs/guides/SQL_QUERY_SAMPLES.md](../guides/SQL_QUERY_SAMPLES.md) - 詳細なクエリ例
- **予測ロジック**: [docs/architecture/PREDICTION_LOGIC.md](PREDICTION_LOGIC.md) - 予測アルゴリズム
- **購入条件**: [docs/presets/BET_CONDITIONS.md](../presets/BET_CONDITIONS.md) - 10条件の詳細

---

**最終更新**: 2026-01-30
**更新者**: Claude Sonnet 4.5（上位AI: Claude Opus 4.5）
