# クイックリファレンス（Claude Code用）

**作成日**: 2026-01-30
**目的**: Claude Codeが即座に情報を参照できるリファレンス
**対象**: テーブル構造、よく使うクエリ、スクリプト、重要な設定値

---

## 📊 テーブル早見表

### 最重要テーブル（★★★）

| テーブル | 用途 | 主キー | よく使うカラム | 件数 | 充足率 |
|---------|------|:------:|--------------|:----:|:-----:|
| **races** | レース基本情報 | id | race_date, venue_code, race_number, grade | 133,327 | 100% |
| **entries** | 出走情報 | (race_id, pit_number) | racer_number, win_rate, motor_number, racer_rank | 799,824 | 98% |
| **results** | 着順・決まり手 | (race_id, pit_number) | rank, kimarite, race_time | 779,318 | 97% |
| **race_predictions** | 予測データ | (race_id, pit_number, type) | rank_prediction, confidence, score | 196,692 | 25% |
| **trifecta_odds** | 3連単オッズ | (race_id, combination) | odds | 1,429,326 | 60% |

### 中重要テーブル（★★）

| テーブル | 用途 | 主キー | よく使うカラム | 件数 | 充足率 |
|---------|------|:------:|--------------|:----:|:-----:|
| **race_details** | 展示タイム等 | (race_id, pit_number) | exhibition_time, st_time, chikusen_time | 790,680 | 98% |
| **race_conditions** | 天候・風・波 | race_id | weather, wind_speed, wave_height | 130,792 | 98% |
| **payouts** | 払戻金 | (race_id, bet_type, combination) | amount | 117,897 | 89% |
| **exhibition_data** | オリジナル展示 | (race_id, venue_code, pit_number) | tenji_exhibition_time, tenji_tilt | 861 | 1% |

### 統計指標テーブル（★★）⚠️ 命名注意

> **⚠️ 重要**: ドキュメントやスクリプト名で「indicator_stats」と書かれている場合、
> **実際のDBテーブル名は「indicator_stats」ではない**。
> `SELECT name FROM sqlite_master WHERE name='indicator_stats'` → **0件（存在しない）**
> 「indicator_stats」は概念名。実テーブルは以下の2つ:

| テーブル | 用途 | 主キー | よく使うカラム | 件数 | 充足率 |
|---------|------|:------:|--------------|:----:|:-----:|
| **player_escape_stats** | 選手別逃げ率（1コース勝率） | (racer_number, venue_code, year) | escape_rate, win_rate_1st | 104,757 | 100% |
| **stadium_attack_stats** | 会場別まくり率・差し率 | (venue_code, year) | maki_rate, sashi_rate | 168 | 100% |

> 生成コマンド: `python scripts/data_collection/build_indicator_stats.py --year 2024`

### 低重要テーブル（★）

| テーブル | 用途 | 主キー | 件数 | 充足率 | 備考 |
|---------|------|:------:|:----:|:-----:|------|
| **rdmdb_tide** | 潮位データ | (race_id, venue_code, time) | tide_level | 6,475,040 | 100% | 未活用 |
| **win_odds** | 単勝オッズ | (race_id, pit_number) | odds | 0 | 0% | 未収集 |
| **exacta_odds** | 2連単オッズ | (race_id, combination) | odds | 0 | 0% | 未収集 |

---

## 🔍 よく使うクエリ

### 1. 特定期間のレース取得

```sql
-- 基本パターン
SELECT * FROM races
WHERE race_date BETWEEN '2025-01-01' AND '2025-12-31';

-- 会場・グレード指定
SELECT * FROM races
WHERE race_date BETWEEN '2025-01-01' AND '2025-12-31'
  AND venue_code = 18  -- 常滑
  AND grade = 'G3';
```

### 2. 予測と結果の照合

```sql
SELECT
    rp.race_id,
    rp.pit_number,
    rp.rank_prediction,
    r.rank as actual_rank,
    CASE WHEN rp.rank_prediction = CAST(r.rank AS INTEGER)
         THEN 'HIT' ELSE 'MISS' END as result
FROM race_predictions rp
JOIN results r ON rp.race_id = r.race_id
              AND rp.pit_number = r.pit_number
WHERE rp.prediction_type = 'before';
```

### 3. オッズ付きで結果取得（★重要: 正しいJOIN）

```sql
WITH prediction_combos AS (
    -- 予測組み合わせを構築（予測1着-予測2着-予測3着）
    SELECT
        rp1.race_id,
        CAST(rp1.pit_number AS TEXT) || '-' ||
        CAST(rp2.pit_number AS TEXT) || '-' ||
        CAST(rp3.pit_number AS TEXT) as pred_combo
    FROM race_predictions rp1
    JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
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
SELECT
    pc.race_id,
    pc.pred_combo,
    ac.actual_combo,
    t.odds,
    CASE WHEN pc.pred_combo = ac.actual_combo THEN 'HIT' ELSE 'MISS' END as result
FROM prediction_combos pc
JOIN trifecta_odds t ON pc.race_id = t.race_id
                     AND t.combination = pc.pred_combo
JOIN actual_combos ac ON pc.race_id = ac.race_id;
```

### 4. 信頼度×オッズ帯別の的中率

```sql
WITH prediction_combos AS (
    SELECT
        rp1.race_id,
        rp1.confidence,
        CAST(rp1.pit_number AS TEXT) || '-' ||
        CAST(rp2.pit_number AS TEXT) || '-' ||
        CAST(rp3.pit_number AS TEXT) as pred_combo
    FROM race_predictions rp1
    JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
        AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
),
actual_combos AS (
    SELECT
        race_id,
        CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
        CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
        CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
    FROM results
    WHERE rank IN ('1', '2', '3')
    GROUP BY race_id
)
SELECT
    pc.confidence,
    CASE
        WHEN t.odds < 10 THEN '01: <10倍'
        WHEN t.odds < 20 THEN '02: 10-20倍'
        WHEN t.odds < 30 THEN '03: 20-30倍'
        WHEN t.odds < 50 THEN '04: 30-50倍'
        WHEN t.odds < 100 THEN '05: 50-100倍'
        ELSE '06: 100倍+'
    END as odds_band,
    COUNT(*) as total,
    SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
    ROUND(100.0 * SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
    ROUND(AVG(t.odds), 1) as avg_odds
FROM prediction_combos pc
JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
JOIN actual_combos ac ON pc.race_id = ac.race_id
GROUP BY pc.confidence, odds_band
ORDER BY pc.confidence, odds_band;
```

### 5. 会場別の成績集計

```sql
SELECT
    r.venue_code,
    COUNT(DISTINCT rp.race_id) as races,
    SUM(CASE WHEN rp.rank_prediction = CAST(res.rank AS INTEGER) THEN 1 ELSE 0 END) as hits,
    ROUND(100.0 * SUM(CASE WHEN rp.rank_prediction = CAST(res.rank AS INTEGER) THEN 1 ELSE 0 END) / COUNT(DISTINCT rp.race_id), 2) as hit_rate
FROM race_predictions rp
JOIN races r ON rp.race_id = r.id
JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
WHERE rp.prediction_type = 'before' AND rp.rank_prediction = 1
GROUP BY r.venue_code
ORDER BY hit_rate DESC;
```

---

## 💻 スクリプト早見表

### データ確認・分析

| やりたいこと | コマンド | 所要時間 |
|-------------|---------|:-------:|
| **標準テスト（全体）** | `python scripts/backtest/standard_backtest.py --full` | 2-3分 |
| 特定年度のテスト | `python scripts/backtest/standard_backtest.py --year 2024` | 30秒 |
| ベースライン保存 | `python scripts/backtest/standard_backtest.py --full --save-baseline` | 2-3分 |
| ベースライン比較 | `python scripts/backtest/standard_backtest.py --full --compare` | 2-3分 |
| 知見検索 | `python scripts/search_knowledge.py "キーワード"` | 5秒 |
| 知見DB統計 | `python scripts/query_knowledge_db.py --stats` | 3秒 |

### UI・ツール

| やりたいこと | コマンド | ポート |
|-------------|---------|:-----:|
| **UI起動** | `cd ui && python -m streamlit run app.py` | 8501 |

### データ収集

| やりたいこと | コマンド | 所要時間 |
|-------------|---------|:-------:|
| 過去全データ（2020-2025） | `python scripts/data_collection/auto_fetch_2020_2025.py` | 数時間 |
| 特定期間のデータ | `python scripts/data_collection/fetch_historical_data_parallel.py --start 2024-01-01 --end 2024-12-31` | 1-2時間 |
| 本日のオッズ | `python scripts/data_collection/fetch_today_odds.py` | 1-2分 |
| 本日の直前情報 | `python scripts/data_collection/fetch_today_beforeinfo.py` | 1-2分 |
| 統計指標生成 | `python scripts/data_collection/build_indicator_stats.py --year 2024` | 5-10分 |

### データ補完（2021年・2023年）

| やりたいこと | コマンド | 所要時間 |
|-------------|---------|:-------:|
| 2021年補完（CSV収集） | `python scripts/data_collection/補完_2021_2023_欠損データ.py --year 2021 --all-months` | 30-40時間 |
| 2021年投入（DB） | `python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months` | 10-20分 |
| 進捗確認 | `python scripts/analysis/check_2021_2023_data.py` | 5秒 |

---

## ⚙️ 重要な閾値・設定値

### 購入条件の採用基準

| 項目 | 値 | ソース |
|------|:--:|--------|
| **黒字年数** | **4/6年以上** | BET_CONDITIONS.md |
| **ROI** | **100%以上** | BET_CONDITIONS.md |
| **サンプル数** | **100件以上** | BET_CONDITIONS.md |

### 投資額設定

| 方式 | 投資額 | 内訳 | ソース |
|------|:-----:|------|--------|
| **パターンH** | **400円** | 200円/100円/100円 | standard_backtest.py |
| **1点買い** | **100円** | 100円 | standard_backtest.py |

### 信頼度レベル

| 信頼度 | 意味 | 目安 |
|:-----:|------|------|
| **A** | 非常に高い | 勝率50%以上、1コースA1級など |
| **B** | 高い | 勝率30-50%、1コースB1級など |
| **C** | 中程度 | 勝率20-30%、2-3コース有力選手など |
| **D** | 低い | 勝率20%未満、4-6コース等 |

### 会場コード

| コード | 会場名 | 水質 | 特徴 |
|:-----:|--------|:----:|------|
| 01 | 桐生 | 淡水 | インが強い |
| 02 | 戸田 | 淡水 | 日本一狭い |
| 03 | 江戸川 | 汽水 | 荒れやすい |
| 04 | 平和島 | 海水 | 潮の影響大 |
| 05 | 多摩川 | 淡水 | - |
| 06 | 浜名湖 | 汽水 | - |
| 07 | 蒲郡 | 海水 | - |
| 08 | 常滑 | 海水 | - |
| 09 | 津 | 海水 | - |
| 10 | 三国 | 海水 | - |
| 11 | びわこ | 淡水 | - |
| 12 | 住之江 | 淡水 | - |
| 13 | 尼崎 | 淡水 | - |
| 14 | 鳴門 | 海水 | 潮流強い |
| 15 | 丸亀 | 海水 | - |
| 16 | 児島 | 海水 | - |
| 17 | 宮島 | 海水 | 満潮差大 |
| 18 | 徳山 | 海水 | - |
| 19 | 下関 | 海水 | 潮流強い |
| 20 | 若松 | 海水 | - |
| 21 | 芦屋 | 海水 | - |
| 22 | 福岡 | 海水 | - |
| 23 | 唐津 | 海水 | - |
| 24 | 大村 | 海水 | - |

---

## ⚠️ よくある計算ミスと対策

### 1-2-3固定オッズ問題（★★★★★ 超重要）

**問題**: 分析スクリプトで「予測順位ベースのオッズ」ではなく「枠番固定オッズ」を取得

❌ **誤り**:
```sql
-- 1号艇-2号艇-3号艇の固定オッズを取得（枠番固定）
JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = '1-2-3'
```

✅ **正しい**:
```sql
-- 予測1着-予測2着-予測3着のオッズを取得（予測順位ベース）
-- CTEで予測組み合わせを構築
WITH prediction_combos AS (
    SELECT
        rp1.race_id,
        CAST(rp1.pit_number AS TEXT) || '-' ||
        CAST(rp2.pit_number AS TEXT) || '-' ||
        CAST(rp3.pit_number AS TEXT) as pred_combo
    FROM race_predictions rp1
    JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
        AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
        AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
)
-- 予測組み合わせのオッズを取得
SELECT pc.race_id, t.odds
FROM prediction_combos pc
JOIN trifecta_odds t ON pc.race_id = t.race_id
                     AND t.combination = pc.pred_combo
```

**影響**:
- 分析ROI 396% → 実テストROI 58.4%（-338pt乖離）
- 不採用案の誤判定（本当は有望な条件を誤って棄却）

**対策**:
1. 分析スクリプトは必ず正しいJOIN条件を使用
2. ROI 200%超えは計算ミスを疑う
3. `standard_backtest.py` で最終検証必須
4. 修正済みスクリプト一覧:
   - `analyze_confidence_hit_patterns.py` (5箇所修正)
   - `analyze_confidence_deep_dive.py` (9箇所修正)
   - `analyze_meta_index_effect.py` (3箇所修正)
   - `analyze_b_50_100_details.py` (1箇所修正)
   - `analyze_b_50_100_details_v2.py` (1箇所修正)
   - `analyze_bx50_100_miss_patterns.py` (2箇所修正)
   - `analyze_bx50_100_comprehensive.py` (1箇所修正)

---

## 📚 関連ドキュメント

### 必読ドキュメント

| カテゴリ | ドキュメント | 内容 |
|---------|------------|------|
| **タスク管理** | [docs/残タスク一覧.md](残タスク一覧.md) | 現在の状態・前回の作業 |
| **引継ぎ** | [docs/HANDOVER.md](HANDOVER.md) | セッション間の引継ぎ |
| **予測ロジック** | [docs/architecture/PREDICTION_LOGIC.md](architecture/PREDICTION_LOGIC.md) | 予測アルゴリズム詳細 |
| **DB仕様** | [docs/architecture/DATABASE_SCHEMA.md](architecture/DATABASE_SCHEMA.md) | テーブル定義・制約 |
| **SQLサンプル** | [docs/guides/SQL_QUERY_SAMPLES.md](guides/SQL_QUERY_SAMPLES.md) | クエリ例（詳細版） |
| **購入条件** | [docs/presets/BET_CONDITIONS.md](presets/BET_CONDITIONS.md) | 10条件の詳細 |
| **不採用案** | [docs/improvement_attempts/REJECTED_IDEAS.md](improvement_attempts/REJECTED_IDEAS.md) | 過去の不採用案 |
| **データ収集** | [docs/guides/DATA_COLLECTION_MASTER.md](guides/DATA_COLLECTION_MASTER.md) | データ収集ガイド |

### 参考ドキュメント

| カテゴリ | ドキュメント | 内容 |
|---------|------------|------|
| **年度別成績** | [docs/performance/YEARLY_PERFORMANCE.md](performance/YEARLY_PERFORMANCE.md) | 2020-2025年の成績 |
| **テスト結果** | [docs/performance/TEST_RESULTS.md](performance/TEST_RESULTS.md) | バックテスト結果 |
| **システム設計** | [docs/architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | 全体設計 |

---

**作成日**: 2026-01-30
**作成者**: Claude Opus 4.5
**最終更新**: 2026-01-30
