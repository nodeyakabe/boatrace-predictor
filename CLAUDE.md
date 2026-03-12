# Claude Code プロジェクト設定

## 言語設定

- 日本語でコミュニケーション

## 参照すべきドキュメント

### 作業開始時（必須）

| 質問 | ドキュメント |
|------|------------|
| **現在の状態** | [docs/残タスク一覧.md](docs/残タスク一覧.md) |
| **前回の作業** | [docs/HANDOVER.md](docs/HANDOVER.md) |

### 技術情報（必要に応じて）

| カテゴリ | ドキュメント |
|---------|------------|
| **予測ロジック** | [docs/architecture/PREDICTION_LOGIC.md](docs/architecture/PREDICTION_LOGIC.md) |
| **年度別成績** | [docs/performance/YEARLY_PERFORMANCE.md](docs/performance/YEARLY_PERFORMANCE.md) |
| **テスト構成** | [docs/performance/TEST_RESULTS.md](docs/performance/TEST_RESULTS.md) |
| **不採用案** | [docs/improvement_attempts/REJECTED_IDEAS.md](docs/improvement_attempts/REJECTED_IDEAS.md) |
| **購入条件** | [docs/presets/BET_CONDITIONS.md](docs/presets/BET_CONDITIONS.md) |
| **DB構造** | [docs/architecture/DATABASE_SCHEMA.md](docs/architecture/DATABASE_SCHEMA.md) |
| **データ収集** | [docs/guides/DATA_COLLECTION_MASTER.md](docs/guides/DATA_COLLECTION_MASTER.md) |

### ⚠️ データ分析・収集前の必読資料

| 目的 | ドキュメント |
|------|------------|
| **データ分析前のチェックリスト** | [docs/guides/DATA_ANALYSIS_CHECKLIST.md](docs/guides/DATA_ANALYSIS_CHECKLIST.md) ⭐**必読** |
| **データ収集依存関係チェーン** | [docs/guides/DATA_DEPENDENCY_CHAIN.md](docs/guides/DATA_DEPENDENCY_CHAIN.md) ⭐**パイプライン設計時必読** |

**重要**:
- データ分析前: チェックリストで見落としがないか確認
- **データ収集パイプライン設計・entries/results追加後**: 依存関係チェーンを確認すること
  （見落とし事例: entries/results追加後にkimarite/race_details/trifecta_oddsが未補完だった→2026-02-19判明）

### すぐに情報が必要なとき（★推奨）

| 情報 | ドキュメント |
|------|------------|
| **テーブル早見表・よく使うクエリ** | [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) |
| **SQLクエリサンプル集（詳細）** | [docs/guides/SQL_QUERY_SAMPLES.md](docs/guides/SQL_QUERY_SAMPLES.md) |

**注意**:
- 日付付きドキュメント（`*_20251220.md`等）は過去ログ。最新情報ではない
- 数値データはDBで直接確認すること

## ⚠️ 参照してはいけないドキュメント

以下のドキュメントは**過去ログ**であり、最新情報ではありません：

- **`docs/archive/` 配下すべて** — 明示的にアーカイブ済み。参照禁止。
  - `archive/analysis/` `archive/analysis_2025/` `archive/implementation/` `archive/reports_2025/` `archive/reports_2026/` `archive/performance_old/`
- **日付付きファイル**（`*_2025*.md`, `*_2026*.md`）— いずれかのarchiveサブディレクトリに移動済み
- **`docs/implementation/`** — 全ファイルをarchiveに移動済み（空ディレクトリ）

**例外（参照必須）**:
- `docs/improvement_attempts/REJECTED_IDEAS.md` - 不採用案の確認に必須
- `docs/guides/` 配下のガイド類 - ハウツー情報として有効

## よく使うコマンド

| 操作 | コマンド |
|------|---------|
| UI起動 | `cd ui && python -m streamlit run app.py` |
| **標準テスト（推奨）** | `python scripts/backtest/standard_backtest_unique.py --full` |
| 標準テスト（条件分析用） | `python scripts/backtest/standard_backtest.py --full` |
| 知見検索 | `python scripts/search_knowledge.py "キーワード"` |
| 知見DB統計 | `python scripts/query_knowledge_db.py --stats` |

## 予測生成スクリプト（重要）⭐

**2026-02-20更新**: CSV方式に移行。DB一括削除不要・中断耐性あり。

### 使い分け早見表

| 用途 | スクリプト | コマンド例 |
|------|-----------|----------|
| **当日 before 予測**（展示後・毎日） | `fast_prediction_generator.py` | `python scripts/prediction/fast_prediction_generator.py --date 2026-02-19 --type before` |
| **翌日 advance 予測**（前日夜・毎日） | `fast_prediction_generator.py` | `python scripts/prediction/fast_prediction_generator.py --date 2026-02-20 --type advance` |
| **年度一括 advance**（再生成等） | `generate_advance_fast.py` | `python scripts/prediction/generate_advance_fast.py --year 2025` |
| **年度一括 before**（再生成等） | `generate_before_fast.py` | `python scripts/prediction/generate_before_fast.py --year 2025` |
| **全年度まとめて自動生成** | `watch_and_generate_advance.py` | `python scripts/automation/watch_and_generate_advance.py --run-once` |
| **CSV単独投入**（確認後に手動投入） | `import_predictions_csv.py` | `python scripts/prediction/import_predictions_csv.py --dir data/predictions_csv/advance/2025` |

### 詳細ルール

```
【毎日の運用】（DB直接保存、従来通り）
前日夜:  fast_prediction_generator.py --type advance  （翌日のadvance）
当日朝:  fast_prediction_generator.py --type before   （展示後のbefore）

【年度一括・再生成】（CSV方式、DB削除不要）
通常:       generate_advance_fast.py --year XXXX   （Phase 1 CSV書き出し → Phase 2 DB投入）
            generate_before_fast.py  --year XXXX
全年度まとめ: watch_and_generate_advance.py --run-once  （未生成分のみ）

【再生成（既存上書き）が必要な場合の手順】
※ CSV方式なのでDB事前削除は不要。そのまま実行するだけで ON CONFLICT DO UPDATE により上書き。
1. generate_advance_fast.py --year XXXX  を実行（既存予測を自動上書き）
2. generate_before_fast.py  --year XXXX  を実行

【段階的実行（CSVを手動確認してからDB投入したい場合）】
1. generate_advance_fast.py --year XXXX --csv-only   （Phase 1のみ: CSV書き出し、DB無変更）
2. CSV確認: data/predictions_csv/advance/XXXX/YYYY-MM-DD.csv
3. import_predictions_csv.py --dir data/predictions_csv/advance/XXXX   （Phase 2: DB投入）
   ※ --dry-run で件数確認のみも可能
```

### 年度一括スクリプトの内部フロー（CSV方式）

```
generate_advance_fast.py / generate_before_fast.py の処理:

Phase 1: 予測計算 → CSV書き出し（DBに触れない）
  - 対象日付の既存CSVを削除（重複追記防止）
  - predictor.predict_race() で予測計算
  - data/predictions_csv/{advance|before}/YYYY/YYYY-MM-DD.csv に書き出し

Phase 2: CSV → DB UPSERT投入
  - INSERT INTO ... ON CONFLICT(race_id, pit_number, prediction_type) DO UPDATE SET ...
  - 既存行の id・created_at を保持したまま上書き（INSERT OR REPLACE と異なる点）
  - 1ファイル=1日分を順次投入
```

### CSVファイルの場所

```
data/predictions_csv/
  advance/
    2025/
      2025-01-01.csv   ← 1日1ファイル（6艇 × レース数 行）
      2025-01-02.csv
      ...
  before/
    2025/
      2025-01-01.csv
      ...
```

### ⚠️ 使ってはいけないスクリプト（廃止済み・_deprecated / archive フォルダに移動済み）

**2026-02-27更新**: 大規模整理実施済み。各ディレクトリのルートにあるファイルのみが現役。

> ⚠️ **例外**: `scripts/automation/` ルートの以下3ファイルは旧世代だが `block_a` / `block_d` が依存しているため現役扱い:
> - `generate_daily_predictions.py`（block_d_today_prediction.py から使用）
> - `generate_yesterday_before_predictions.py`（block_a_yesterday_data.py から使用）
> - `daily_tenji_collector.py`（block_a_yesterday_data.py から使用）
>
> 将来的に block_a / block_d を `fast_prediction_generator.py` 等に書き換えた後に _deprecated 移動予定。

#### 予測生成系

| 格納先 | 理由 |
|--------|------|
| `scripts/automation/_deprecated/generate_year_predictions_fast.py` | 旧 before 生成（1日1サブプロセス方式）→ `generate_before_fast.py` に置き換え済み |
| `scripts/prediction/_deprecated/regenerate_predictions_*.py` 系 | DataManager を使わない直接 INSERT → EnvironmentalPenaltySystem をバイパス |
| `scripts/prediction/_deprecated/` 配下すべて（27ファイル） | 年度限定・旧世代スクリプト。現役4ファイルのみ使うこと |
| `scripts/_deprecated/quick_generate_advance.py` | `generate_advance_fast.py` に統合済み |

#### データ収集系（旧版）

| 使ってはいけない | 正しい現役版 |
|----------------|------------|
| `scripts/data_collection/archive/deprecated/補完_決まり手データ_csv版.py` | `補完_決まり手データ_改善版.py` |
| `scripts/data_collection/archive/deprecated/fetch_odds_to_csv_parallel.py` | `fetch_odds_parallel_safe.py` |
| `scripts/data_collection/archive/deprecated/fetch_exhibition_data_to_csv.py` | `collect_beforeinfo_to_csv_parallel.py` |
| `scripts/data_collection/archive/deprecated/fetch_race_details_to_csv.py` | `fetch_to_csv_parallel_improved.py` |
| `scripts/data_collection/archive/deprecated/fetch_race_conditions_to_csv.py` | `fetch_to_csv_parallel_improved.py` |
| `scripts/data_collection/archive/one_time/` 配下（年度限定スクリプト群） | 汎用スクリプトで代替。年度をオプション指定 |

#### 完了済み一時パイプライン（再実行不可）

| 格納先 | 理由 |
|--------|------|
| `scripts/automation/_deprecated/overnight_pipeline.py` | 2026-02-19シェルレース問題対応用・完了済み |
| `scripts/automation/_deprecated/phase2_pipeline.py` | 同上の後続処理・完了済み |
| `scripts/automation/_deprecated/post_recovery_pipeline.py` | 特定PID・特定DB状態を前提とした一時スクリプト |
| `scripts/automation/_deprecated/run_prediction_recovery.py` | 2026-02-24時点のDB状態を前提・完了済み |

## 標準テスト（重要）⭐

### 2つの標準テストの使い分け

**2026-02-16更新**: Tier 2/3統一化により、2種類のテストを用途別に使い分けます。

#### 1. ユニーク版（実運用シミュレーション）⭐ **推奨**

```bash
python scripts/backtest/standard_backtest_unique.py --full
```

**用途**:
- 実際の購入レース数と収支を正確に把握
- Tier 3（実運用）との一致率95.48%を達成
- 重複レースは優先度順に1条件のみに割り当て

**特徴**:
- 優先度ベースの重複除外（config/bet_conditions.py の priority フィールド）
- オッズデータ・範囲チェック対応
- Tier 3（BetTargetEvaluator）と同じロジック

#### 2. 従来版（条件別分析用）

```bash
python scripts/backtest/standard_backtest.py --full
```

**用途**:
- 各条件の個別性能を詳細分析
- 重複レースも各条件でカウント（条件別の最大ポテンシャル把握）

---

### 「標準テストして」と言われたら【必須手順】

**STEP 1: 推奨コマンドを実行**
```bash
python scripts/backtest/standard_backtest_unique.py --full
```

**STEP 2: 結果を表形式で報告**

以下の形式で必ず報告してください：

```markdown
## ✅ 標準テスト結果

### 全体サマリー（6年間 2020-2025）

| 指標 | 値 | 前回比 |
|------|:--:|:------:|
| **購入レース数** | X,XXX件 | ±XXX件 |
| **ROI** | XXX.X% | ±X.Xpt |
| **収支** | +XXX,XXX円 | ±XXX,XXX円 |
| **的中率** | X.X% | ±X.Xpt |
| **黒字年数** | X/6年 | 維持/改善/悪化 |

### 年度別パフォーマンス

| 年度 | 件数 | ROI | 収支 | 判定 |
|:----:|:----:|:---:|:----:|:----:|
| 2020 | XXX | XXX.X% | +XX,XXX | ○/× |
| 2021 | XXX | XXX.X% | +XX,XXX | ○/× |
| 2022 | XXX | XXX.X% | +XX,XXX | ○/× |
| 2023 | XXX | XXX.X% | +XX,XXX | ○/× |
| 2024 | XXX | XXX.X% | +XX,XXX | ○/× |
| 2025 | XXX | XXX.X% | +XX,XXX | ○/× |

### 主要条件の成績（上位3条件）

| 条件 | 方式 | 件数 | ROI | 収支 |
|:-----|:---:|:---:|:---:|:----:|
| XXX | P.H/1点 | XXX | XXX% | +XXX,XXX |
| XXX | P.H/1点 | XXX | XXX% | +XXX,XXX |
| XXX | P.H/1点 | XXX | XXX% | +XXX,XXX |
```

**STEP 3: 変化がある場合は原因分析**

前回比で大きな変化（±10%以上）がある場合は、必ず原因を報告：
- 条件追加/削除の影響
- パラメータ変更の影響
- データ修正の影響
- 実装変更の影響

**STEP 4: HANDOVER.mdの更新確認**

標準テスト結果が前回と異なる場合、`docs/HANDOVER.md`の以下セクションを更新する必要があるか確認：
- **6年間バックテスト結果**（Line 39-49）
- **標準バックテスト結果**（Line 51-66）
- **年度別パフォーマンス**（Line 70-80）

---

### 標準テストの出力内容

#### ユニーク版（standard_backtest_unique.py）⭐ 推奨

- **重複除外レポート**: 各条件の候補数と割り当て数
- **条件別パフォーマンス**: ユニークレースのみでの成績
- **全体サマリー**: 実際の購入件数・ROI・収支

**オプション:**
- `--full`: 6年間（2020-2025）の全体テスト
- `--year 2024`: 特定年度のテスト
- `--save-json data/tier2_unique_results.json`: 結果をJSONで保存

#### 従来版（standard_backtest.py）

- 6年間（2020-2025年）の全体サマリー（ROI、収支、的中率）
- 条件別パフォーマンス（パターンH/1点買い区分付き、重複カウント）
- 年度別パフォーマンス（黒字年数判定）
- 2025年月別パフォーマンス（黒字月数判定）

**オプション:**
- `--year 2024`: 特定年度の詳細テスト
- `--save-baseline`: ベースライン保存
- `--compare`: ベースラインと比較

## セッション開始時

1. `docs/残タスク一覧.md` を読む
2. `docs/HANDOVER.md` を読む
3. 新規施策の場合のみ: `python scripts/search_knowledge.py "キーワード"`

## 施策検証完了時

```bash
python scripts/register_experiment.py \
    --id "施策ID" --name "施策名" --category "カテゴリ" \
    --result "accepted/rejected" --effect "効果値" --keywords "キーワード"
```

## 新規購入条件の検証プロセス【重要】⭐

**2026-02-13更新**: 3段階検証フロー（Tier 1-3）を導入しました。

### 📋 3段階検証フロー（必須）

分析スクリプトで有望な条件を発見したら、必ず以下の手順で検証してください：

```
Tier 1: 簡易テスト（2年間、高速）
  ↓ 合格（ROI 150%+, 1/2年黒字, 50件+）
Tier 2: 標準テスト（6年間、厳格）
  ↓ 合格（ROI 100%+, 4/6年黒字）
Tier 3: 実環境確認（一致率95%+）
  ↓ 合格
採用決定
```

**詳細ガイド**: [docs/guides/VALIDATION_WORKFLOW.md](docs/guides/VALIDATION_WORKFLOW.md)

---

### Tier 1: 簡易テスト（高速検証）

**コマンド**:
```bash
# カスタム条件のテスト
python scripts/backtest/quick_condition_test.py --condition-json '{
  "id": "TEST",
  "name": "テスト条件",
  "confidence": "B",
  "c1_rank": ["B1"],
  "odds_min": 30,
  "odds_max": 50,
  "venue_filter": [9, 10],
  "use_pattern_h": true
}'
```

**合格基準**:
- ROI 150%以上
- 1/2年黒字（2024年または2025年が黒字）
- サンプル数 50件以上

**不合格の場合** → 条件を見直すか、不採用案として記録

---

### Tier 2: 標準テスト（本採用判定）

**手順**:
1. `config/bet_conditions.py` に条件を追加
2. `python scripts/backtest/standard_backtest.py --full` を実行
3. 合格基準を確認

**合格基準**:
- **黒字年数 4/6年以上**
- **累計収支がプラス**
- **ROI 100%以上**

**異常に良い結果への対応**:
- ROI 200%超え、6/6年黒字 → **計算ミスを疑う**
- 分析と実テストの乖離が大きい → **JOIN条件を確認**

---

### Tier 3: 実環境確認（最終検証）

**コマンド**:
```bash
# Tier 2の結果をJSON保存
python scripts/backtest/standard_backtest.py --full --save-json data/tier2_results.json

# Tier 3で一致率確認
python scripts/validation/verify_prediction_consistency.py \
    --start 2020-01-01 --end 2025-12-31 \
    --tier2-results data/tier2_results.json
```

**合格基準**:
- Tier 2との一致率 95%以上

**不合格の場合** → 実装乖離があるため、修正が必要

---

### 分析スクリプトでの注意点

```sql
-- ❌ 誤り: 枠番固定オッズ（1-2-3固定）
JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = '1-2-3'

-- ✅ 正しい: 予測順位ベースのオッズ（実際の買い目）
JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                     || CAST(rp2.pit_number AS TEXT) || '-'
                     || CAST(rp3.pit_number AS TEXT)
```

### 不採用時の記録

不採用案は `docs/improvement_attempts/REJECTED_IDEAS.md` に追記

## 残タスクへの追記

「残タスクに追記して」等のリクエスト → `docs/残タスク一覧.md` に追加

## データ収集タスク（重要）

**「データ収集」を依頼されたら必ず参照:**

### ⚠️ entries/results を追加・補完したら必ず実行する後続処理【必須】

> **2026-02-19 教訓**: overnight_pipeline設計時にこの依存関係を見落とし、kimarite/race_detailsが補完されない問題が発生（Opus検証で発見）。
> entries/resultsを追加しただけでは「データ収集完了」ではない。

```
entries/results を追加/補完した
  → 1. kimarite 補完（補完_決まり手データ_改善版.py）          ← 必須
  → 2. race_details 補完（補完_レース詳細データ_改善版v4.py）   ← 必須
  → 3. trifecta_odds 収集（fetch_odds_parallel_safe.py）        ← バックテストに必須
  → 4. 統計指標再生成（build_indicator_stats.py）                ← 予測精度に影響
          ⚠️ 実テーブル名: player_escape_stats（選手別逃げ率）, stadium_attack_stats（会場別まくり率）
          ⚠️「indicator_stats」というテーブルは存在しない（概念名のみ。検索しても0件になる）
  → 5. advance予測再生成（ウォッチャー自動 or generate_advance_fast.py）
```

詳細チェックリスト: [docs/guides/DATA_DEPENDENCY_CHAIN.md](docs/guides/DATA_DEPENDENCY_CHAIN.md)

---

### ⚠️ スケジュールAPIの過去データ欠損について【必読】

> **2026-02-20 教訓**: スケジュールAPIが返す過去の開催情報が不完全だったため、シェルレースを「ゴーストデータ（実在しない）」と誤判断しそうになった。
> Opus上位AIがrace_details/trifecta_oddsの存在を確認して阻止。

**背景**: `ScheduleScraper`（`src/scraper/schedule_scraper.py`）は `boatrace.jp/owpc/pc/race/monthlyschedule` から月間スケジュールをスクレイピングする。このページは**過去データ（特に2020-2022年）の開催情報が不完全**で、実際には開催されていた会場が返されないことがある。

**絶対にやってはいけないこと**:
- 「スケジュールAPIにない会場のレース = ゴーストデータ（実在しない）」と判断してはならない
- entries/resultsがないracesをゴーストデータと見なして削除してはならない

**データ削除前の必須確認手順**:
```sql
-- racesに対してrace_details/trifecta_oddsが存在するか確認
-- 存在する場合、そのレースは実在する（削除は危険）
SELECT COUNT(*) FROM race_details rd
WHERE rd.race_id IN (
  SELECT r.id FROM races r
  LEFT JOIN entries e ON r.id = e.race_id
  WHERE e.race_id IS NULL
);

SELECT COUNT(*) FROM trifecta_odds t
WHERE t.race_id IN (
  SELECT r.id FROM races r
  LEFT JOIN entries e ON r.id = e.race_id
  WHERE e.race_id IS NULL
);
```

**過去期間の正しい補完方法**:
- `fetch_historical_data_parallel.py` はスケジュールAPIに依存するため、過去データの補完には不十分
- 過去データ（2020-2022年）の補完には必ず `--brute-force` オプションを使う:
  ```bash
  python scripts/data_collection/fetch_to_csv_parallel_improved.py \
    --start 2020-09-01 --end 2020-12-31 --output data/csv/2020_補完 --brute-force
  ```

---

### クイックリファレンス

| やりたいこと | 推奨スクリプト |
|-------------|---------------|
| **過去全データ（2020-2025）** | `python scripts/data_collection/auto_fetch_2020_2025.py` |
| **特定期間のデータ** ✅ **開催スケジュール最適化済み** | `python scripts/data_collection/fetch_historical_data_parallel.py --start 2024-01-01 --end 2024-12-31` |
| **大量CSV収集（DB負荷なし）** ✅ **開催スケジュール最適化済み** | `python scripts/data_collection/fetch_to_csv_parallel_improved.py --start 2020-01-01 --end 2020-12-31 --output data/csv/2020` |
| **CSV→DB投入（races/entries/results）** | `python scripts/data_collection/import_races_csv.py` |
| **過去データ補完（2020-2022年等）** ⚠️ **ブルートフォース必須** | `python scripts/data_collection/fetch_to_csv_parallel_improved.py --start 2020-09-01 --end 2020-12-31 --output data/csv/補完 --brute-force` |
| **決まり手補完** | `python scripts/data_collection/補完_決まり手データ_改善版.py` |
| **決まり手CSV→DB投入** | `python scripts/data_collection/import_kimarite_csv.py` |
| **レース詳細補完** | `python scripts/data_collection/補完_レース詳細データ_改善版v4.py` |
| **オッズ収集** | `python scripts/data_collection/fetch_odds_parallel_safe.py --start 2024-01-01 --end 2024-12-31` |
| **オッズCSV→DB投入** | `python scripts/data_collection/import_odds_csv_to_db.py` |
| **払戻金補完（CSV出力）** | `python scripts/data_collection/補完_払戻金データ.py` |
| **払戻金CSV→DB投入** | `python scripts/data_collection/import_payouts_csv.py` |
| **本日の直前情報** | `python scripts/data_collection/fetch_today_beforeinfo.py` |
| **統計指標生成** ⚠️実テーブル=player_escape_stats/stadium_attack_stats | `python scripts/data_collection/build_indicator_stats.py --year 2024` |
| **特徴量再計算（racer_features / racer_venue_features）** | `python scripts/maintenance/run_racer_features_recompute.py` |

### 基本原則

1. **大量データはCSV方式** - DB負荷を回避
2. **並列化を活用** - 高速化（8-12ワーカー）
3. **月別に分割** - リカバリ容易
4. **旧版は使わない** - 必ず推奨スクリプトを使用

### ⚠️ 重要な制約（必読）

| データ種別 | 取得可能期間 | 補完可否 |
|-----------|-------------|---------|
| レース基本情報・結果・オッズ | 2020年～ | ✅ 可能（公式APIで常時公開） |
| **直前情報（exhibition_time等）** | **2020年～** | **✅ 可能（過去日付でも `/beforeinfo?hd=YYYYMMDD` でアクセス可）** |

**直前情報の過去補完方法**:
```bash
# Phase 1: CSV収集
python scripts/data_collection/collect_beforeinfo_to_csv_parallel.py \
    --start 2024-01-01 --end 2024-12-31 \
    --output data/csv/beforeinfo/2024 --workers 12

# Phase 2: DB投入
python scripts/data_collection/import_beforeinfo_csv_to_db.py \
    --input data/csv/beforeinfo/2024
```

**Claude Codeへの注意**:
- 公式データ（レース・結果・オッズ・直前情報）は過去2020年分まで取得可能
- 毎日の自動収集が理想だが、欠損が発生しても過去補完で復旧できる

### 詳細ドキュメント

- **最適化ガイド**: [docs/guides/DATA_COLLECTION_OPTIMIZATION_GUIDE.md](docs/guides/DATA_COLLECTION_OPTIMIZATION_GUIDE.md) **(推奨)**
- **マスターガイド**: [docs/guides/DATA_COLLECTION_MASTER.md](docs/guides/DATA_COLLECTION_MASTER.md)
- **スクリプトカタログ**: [docs/guides/DATA_COLLECTION_SCRIPTS_CATALOG.md](docs/guides/DATA_COLLECTION_SCRIPTS_CATALOG.md)
- **CSV方式詳細**: [docs/guides/CSV_DATA_COLLECTION_GUIDE.md](docs/guides/CSV_DATA_COLLECTION_GUIDE.md)
- **競艇場独自データ**: [docs/guides/VENUE_SPECIFIC_DATA_COLLECTION.md](docs/guides/VENUE_SPECIFIC_DATA_COLLECTION.md)

## ディレクトリ構成

```
├── src/           # ソースコード（261ファイル）
├── scripts/       # 運用スクリプト
│   ├── prediction/     # 予測生成（現役4ファイル）
│   ├── backtest/       # バックテスト
│   ├── analysis/       # 分析
│   ├── automation/     # 自動化パイプライン（daily_scheduler, block_a/c/d等）
│   ├── validation/     # 検証（verify_prediction_consistency.py等）
│   ├── data_collection/# データ収集
│   ├── maintenance/    # メンテナンス
│   ├── templates/      # スクリプトテンプレート
│   └── _one_time/      # 一時・年度限定スクリプト（使用後移動済み）
├── config/        # 設定
├── docs/          # ドキュメント
│   ├── HANDOVER.md          # ★引継ぎ資料（常に最新）
│   ├── 残タスク一覧.md       # ★唯一の最新タスク情報源
│   ├── QUICK_REFERENCE.md   # テーブル早見表・よく使うクエリ
│   ├── architecture/        # システム設計・予測ロジック
│   ├── performance/         # 年度別成績・テスト結果（最新版のみ）
│   ├── presets/             # 購入条件・プリセット
│   ├── improvement_attempts/ # 不採用案・検証履歴
│   ├── guides/              # ガイド類（56ファイル）
│   ├── knowledge/           # 予測ロジック知見ベース
│   ├── checklists/          # 検証チェックリスト
│   ├── lessons_learned/     # 過去の教訓
│   ├── templates/           # ドキュメントテンプレート
│   ├── maintenance/         # メンテナンス記録
│   └── archive/             # 過去ログ（★参照禁止）
│       ├── analysis/        # 分析レポート（90ファイル）
│       ├── analysis_2025/   # 2025年の分析レポート（51ファイル）
│       ├── implementation/  # 完了済み実装レポート（36ファイル）
│       ├── reports_2025/    # 2025年のその他レポート（4ファイル）
│       ├── reports_2026/    # 2026年の過去レポート（14ファイル）
│       └── performance_old/ # 旧ベースライン・補完完了レポート
├── ui/            # Streamlit UI
├── tests/         # テスト
├── temp/          # 一時ファイル（展示データJSON等）
├── migrations/    # DBマイグレーション
├── logs/          # ログ（直近3月分のみ保持）
├── data/          # データ（Git管理外）
│   ├── boatrace.db          # 本番DB（6.0GB）
│   ├── backups/             # 自動バックアップ（定期削除対象）
│   └── predictions_csv/     # 予測CSV中間ファイル
└── models/        # MLモデル（Git管理外）
    └── conditional_rank_v3_*  # 最新版モデル（v1/v2は削除済み）
```

**重要**: `docs/archive/` 配下は過去ログです。参照不要。

---

## ⚠️ AI（Claude/Opus）の既知の誤推論パターン【必読】

過去に実際に発生した誤判断のパターン。同じ誤りを繰り返さないために必ず確認すること。

### パターン1: 「旧コード予測の方が的中率が高い → 再生成不要」（2026-03-12 確認）

**誤った推論**:
> 旧コード予測（st_time修正前）のA的中率73.3% > 新コード70.0% → 再生成不要

**なぜ間違いか**:
st_time 2スケール混在 → スコア歪み → A率低下（19.8% vs 21.4%）→ 的中率が高く見える、という因果チェーンを見落とした。的中率の差はデータ品質向上の証拠ではなく、**問題の症状そのもの**。

**正しい確認方法**:
的中率だけで判断せず、**A率・信頼度分布**も必ず確認する。コード変更前後でA率が大きく変わっている場合は「なぜ変わったか」を必ず掘り下げること。

---

### パターン2: 「generated_at が古い → 問題あり」の単純判断（一般注意）

データの generated_at が古いことは問題の証拠だが、「古い = 必ず再生成が必要」ではない。
**必ず確認すること**: そのデータが実際にバックテスト結果に悪影響を与えているか（的中率・ROIで定量確認）。

---

### パターン3: 「ドキュメントに書いてある → やるべき」の盲目的実行（一般注意）

ドキュメントの記載が古い・文脈が変わった可能性がある。**疑問があれば必ず定量確認してから実行する**。

---

### 誤推論防止の原則

1. **表面の数値だけで判断しない** → 「なぜその数値になったか」を2〜3段階掘り下げる
2. **結論を出す前に反論を検討** → 「この結論が間違っている場合、何が理由か」を考える
3. **因果チェーンを明示** → A→B→C の因果関係を省略せず確認する
4. **複数指標で検証** → 1つの指標だけで判断しない（的中率 + A率 + ROI を組み合わせる）
