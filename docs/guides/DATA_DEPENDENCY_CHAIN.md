# データ収集 依存関係チェーン

**作成日**: 2026-02-19
**作成経緯**: overnight_pipeline設計時にSTEP 7b/7cが見落とされた問題の根本原因として、依存関係チェーンの文書化不足が特定されたため作成。

---

## ⚠️ このドキュメントを使う理由

### 今回発生した問題（2026-02-19）

overnight_pipeline.pyを設計した際、以下のSTEPが漏れていた:
- STEP 7でシェルレース（entries/results）を追加した
- しかし「entries/resultsが追加されたら、kimarite/race_detailsも補完が必要」という依存関係を見落とした
- これはOpus上位AIの検証で発見・修正

**根本原因**: データ収集の依存関係チェーンが「各スクリプトのコード内の暗黙知」としてのみ存在し、明示的な文書がなかった。

---

## データ収集 依存関係チェーン（確定版）

```
races（レース基本情報）
  ├→ entries（出走表）           ← fetch_to_csv / fetch_historical_data_parallel
  │    └→ results（結果）        ← fetch_to_csv / fetch_historical_data_parallel
  │         ├→ kimarite          ← 補完_決まり手データ_改善版.py ★必須
  │         ├→ race_details      ← 補完_レース詳細データ_改善版v4.py ★必須
  │         └→ race_conditions   ← fetch_historical と fetch_to_csv で同時保存
  │
  ├→ payouts（払戻金）           ← fetch_to_csv で同時保存
  │
  ├→ trifecta_odds（三連単オッズ）← fetch_odds_parallel_safe.py ★バックテスト必須
  │
  ├→ beforeinfo（直前情報）      ← fetch_today_beforeinfo.py（前日のみ取得可）
  │
  └→ race_predictions（予測）
       ├→ advance予測            ← generate_advance_fast.py ★entries+results+kimarite+race_detailsが前提
       └→ before予測             ← generate_advance_fast.py ★beforeinfoも前提

統計指標（概念名: indicator_stats）← build_indicator_stats.py ★results全体から再集計
  ⚠️ 「indicator_stats」というDBテーブルは存在しない。実テーブルは以下:
  ├→ player_escape_stats（選手別逃げ率）     ← SELECT name FROM sqlite_master で確認可
  └→ stadium_attack_stats（会場別まくり率・差し率）
```

### スクリプト別取得データ範囲

| スクリプト | races | entries | results | conditions | kimarite | race_details | payouts | odds |
|-----------|:-----:|:-------:|:-------:|:----------:|:--------:|:------------:|:-------:|:----:|
| `fetch_to_csv_parallel_improved.py` | ✅ | ✅ | ✅ | ✅ | ✗ | ✗ | ✅ | ✗ |
| `fetch_historical_data_parallel.py` | ✗ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✗ |
| `補完_決まり手データ_改善版.py` | ✗ | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ | ✗ |
| `補完_レース詳細データ_改善版v4.py` | ✗ | ✗ | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ |
| `fetch_odds_parallel_safe.py` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✅ |
| `build_indicator_stats.py` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

**注意**: `fetch_historical_data_parallel.py`は既存のraces行に対してentries/resultsを追加するスクリプト。racesの新規作成はしない。
**2026-02-26修正**: payouts/actual_courses(race_details)/kimariteも保存するよう修正済み。ただしoddsは未対応。

---

## ✅ 必須チェックリスト：entries/resultsを追加した場合

**このチェックリストは、以下のいずれかを実行した後に必ず確認する:**
- `fetch_historical_data_parallel.py` でシェルレースを補完した
- `import_db` で新しいCSVをDBに取り込んだ
- 何らかの方法で entries/results データが追加された

### データ補完チェック

- [ ] **kimarite 補完を実行したか**
  ```bash
  python scripts/automation/collect_all_data_complete.py --step kimarite --year XXXX
  ```

- [ ] **race_details 補完を実行したか**
  ```bash
  python scripts/automation/collect_all_data_complete.py --step race_details --year XXXX
  ```

- [ ] **trifecta_odds（三連単オッズ）が存在するか** ← バックテストに必須
  ```bash
  python scripts/data_collection/fetch_odds_parallel_safe.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
  ```
  ※ オッズがないレースはバックテストで除外される（買い目特定不可）

- [ ] **統計指標を再生成したか** ← 予測精度に影響
  ```bash
  python scripts/data_collection/build_indicator_stats.py --year XXXX
  ```
  > ⚠️ 実テーブル名は `player_escape_stats` / `stadium_attack_stats`。「indicator_stats」というテーブルは存在しない。

### 予測生成チェック

- [ ] **advance 予測を再生成したか**（ウォッチャーが自動実行、または手動）
  ```bash
  python scripts/prediction/generate_advance_fast.py --year XXXX
  ```

### 最終確認

- [ ] **標準テストを再実行して結果を確認したか**
  ```bash
  python scripts/backtest/standard_backtest_unique.py --full
  ```

---

## overnight_pipeline.py 現状のカバレッジ（2026-02-19版）

overnight_pipeline.py（8ステップ）は以下をカバーする:

| データ種別 | 2024/2025 | 2020/2021/2022（シェルレース補完分） |
|-----------|:---------:|:-----------------------------------:|
| entries/results | ✅ STEP 1-2 | ✅ STEP 7 |
| kimarite | ✅ STEP 5 | ✅ STEP 7b |
| race_details | ✅ STEP 6 | ✅ STEP 7c |
| trifecta_odds | ✗ 対象外 | ✗ **未対応** |
| indicator_stats | ✗ 対象外 | ✗ **未対応** |
| advance予測 | 🔄 ウォッチャー自動 | 🔄 ウォッチャー自動 |

### overnight完了後に手動実行が必要なもの

**1. trifecta_odds収集（推奨）**
シェルレース補完後のレースにオッズがなく、バックテストで除外される。
後日実行することでバックテストのサンプルが増加する（今すぐ必要なわけではない）。

```bash
# 2020年9-12月分
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2020-09-01 --end-date 2020-12-31

# 2021年11-12月分
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2021-11-01 --end-date 2021-12-31

# 2022年8-12月分
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2022-08-01 --end-date 2022-12-31
```

**2. indicator_stats再生成（推奨）**
結果データが大幅増加したため、統計指標が古い状態になっている可能性がある。

```bash
python scripts/data_collection/build_indicator_stats.py --year 2020
python scripts/data_collection/build_indicator_stats.py --year 2021
python scripts/data_collection/build_indicator_stats.py --year 2022
```

---

## ⚠️ スケジュールAPIの制約【必読】

> **2026-02-20 教訓**: スケジュールAPIの過去データ不完全性により、実在するレースを「ゴーストデータ」と誤判断するインシデントが発生。

### 根本原因

`ScheduleScraper`（`src/scraper/schedule_scraper.py`）は `boatrace.jp` の月間スケジュールページをスクレイピングしている。このページは**現在〜直近の開催情報は正確だが、過去のデータ（特に2020-2022年）は一部の会場しか返さない**ことがある。

例: 2020年9月1日のスケジュールAPIが `venue=03,06` のみ返す → 実際には6-7会場で開催されていた

### 影響を受けるスクリプト

| スクリプト | スケジュールAPI依存 | 過去データの問題 |
|-----------|:-----------------:|:-------------:|
| `fetch_historical_data_parallel.py` | **はい（常に）** | 補完が不完全になる |
| `fetch_to_csv_parallel_improved.py` | デフォルトはい、`--brute-force`でスキップ可能 | `--brute-force`で回避可能 |
| `auto_fetch_2020_2025.py` | **はい** | 同上 |

### 確認方法

スケジュールAPIの返却が正しいかどうかを確認するには、DBの既存データと比較する:

```sql
-- ある日に実際にレースが存在する会場を確認
SELECT DISTINCT venue_code
FROM races
WHERE race_date = '2020-09-01'
ORDER BY venue_code;

-- スケジュールAPIが返す会場数 vs DB上の会場数を比較
-- DBの方が多い場合、スケジュールAPIが不完全
```

### 過去期間の正しい補完方法

**スケジュールAPIが不完全な期間（2020-2022年等）のデータ補完には`--brute-force`オプションを使う**:

```bash
# 全24会場×全日付をブルートフォースで試行（開催なし会場は自動スキップ）
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2020-09-01 --end 2020-12-31 \
  --output data/csv/2020_補完 \
  --brute-force
```

---

## ⚠️ シェルレースの扱い【データ削除前に必読】

> **2026-02-20 教訓**: entries/resultsがないracesを「ゴーストデータ（実在しないレース）」と誤判断し、削除しようとした。race_detailsが220,098件、trifecta_oddsが3,553,590件存在していたため、上位AIが阻止した。

### シェルレースとは

racesテーブルに行があるが、entries/resultsが未取得の状態。以下の原因で発生する:
- 過去のスクリプトでスケジュール登録のみ実行され、実データ取得が失敗した
- **スケジュールAPIの過去データ不完全性**により、補完スクリプトがその会場をスキップした

### 絶対にやってはいけないこと

- entries/resultsがないからといって「このレースは実在しない」と判断してはならない
- race_details/trifecta_oddsが存在するレースを削除してはならない

### データ削除前の必須確認SQL

```sql
-- 1. entries/resultsがないracesの件数を確認
SELECT COUNT(*) AS shell_races
FROM races r
LEFT JOIN entries e ON r.id = e.race_id
WHERE e.race_id IS NULL;

-- 2. そのうちrace_detailsが存在するレースの件数（存在 = 実データ = 削除禁止）
SELECT COUNT(*) FROM race_details rd
WHERE rd.race_id IN (
  SELECT r.id FROM races r
  LEFT JOIN entries e ON r.id = e.race_id
  WHERE e.race_id IS NULL
);

-- 3. そのうちtrifecta_oddsが存在するレースの件数（存在 = 実データ = 削除禁止）
SELECT COUNT(*) FROM trifecta_odds t
WHERE t.race_id IN (
  SELECT r.id FROM races r
  LEFT JOIN entries e ON r.id = e.race_id
  WHERE e.race_id IS NULL
);

-- 4. 年度・月別のシェルレース分布
SELECT
  strftime('%Y', race_date) AS year,
  strftime('%m', race_date) AS month,
  COUNT(*) AS shell_count
FROM races r
LEFT JOIN entries e ON r.id = e.race_id
WHERE e.race_id IS NULL
GROUP BY year, month
ORDER BY year, month;
```

**判断基準**:
- race_details/trifecta_oddsが**1件でも存在する** → そのレースは実在する → **削除禁止**
- entries/resultsの補完が必要（`--brute-force`オプションで補完する）

### 正しい対応フロー

```
シェルレースを発見した
  → 1. 上記SQLでrace_details/trifecta_oddsの存在を確認
  → 2. 存在する場合: entries/resultsの補完が必要（--brute-forceで取得）
  → 3. 存在しない場合: 本当にゴーストデータの可能性があるが、
       boatrace.jpで該当日の開催を手動確認してから判断
  → 4. 削除は最終手段。まず補完を試みる
```

---

## パイプライン設計時のレビューチェックリスト

新しいデータ収集パイプラインを設計する際は、以下を確認する:

1. **entries/resultsを追加するSTEPの後に、kimarite/race_detailsのSTEPがあるか**
2. **対象年度・期間が全STEPで一致しているか（ある年度だけ漏れていないか）**
3. **オッズ収集が必要なデータを補完したか（バックテストで使用するなら必須）**
4. **統計指標（player_escape_stats/stadium_attack_stats）の再生成が必要か（大量のresults追加後は必要）**
   ※ スクリプト名は `build_indicator_stats.py`、テーブル名は `player_escape_stats` / `stadium_attack_stats`
5. **collect_all_data_complete.pyのSTEPS順序（fetch_csv→import_db→kimarite→race_details）と同じパターンが再現されているか**

---

## 関連ドキュメント

- [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) - 収集スクリプト全体ガイド
- [DATA_ANALYSIS_CHECKLIST.md](DATA_ANALYSIS_CHECKLIST.md) - 分析前チェックリスト
- [DATA_COLLECTION_OPTIMIZATION_GUIDE.md](DATA_COLLECTION_OPTIMIZATION_GUIDE.md) - 最適化ガイド
