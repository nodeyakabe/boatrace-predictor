# 全ロジック再チェック項目リスト

**作成日**: 2026-01-30
**目的**: データ補完後にシステム全体を根本から見直すための包括的な調査項目

**注意**: 本ドキュメントは `docs/DATA_COMPLETION_REVIEW_ITEMS.md` と **重複しない** 項目に焦点を当てています。

---

## 1. データ品質・整合性の全数チェック

### 1-1. 各年度のデータ充足率の詳細確認

**現状認識**:
- 2021年: オッズ17.0%、結果25.9%（**83%欠損**）
- 2023年: オッズ16.2%、結果26.9%（**83%欠損**）
- 2020年/2022年/2024年/2025年は「問題なし」と仮定されている

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| 2020年のデータ品質 | 月別・会場別充足率SQL | 特定月・会場の偏り |
| 2022年のデータ品質 | 同上 | 62.8%で本当に信頼性高いか |
| 2024年のデータ品質 | 同上 | 35.1%の欠損が特定期間に集中か |
| 2025年のデータ品質 | 同上 | 84.2%でどこが欠損か |

**調査SQL例**:
```sql
-- 年度・月別のデータ充足率
SELECT
    strftime('%Y', r.race_date) as year,
    strftime('%m', r.race_date) as month,
    COUNT(DISTINCT r.id) as total_races,
    COUNT(DISTINCT CASE WHEN t.race_id IS NOT NULL THEN r.id END) as races_with_odds,
    COUNT(DISTINCT CASE WHEN res.race_id IS NOT NULL THEN r.id END) as races_with_results,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN t.race_id IS NOT NULL THEN r.id END) / COUNT(DISTINCT r.id), 1) as odds_rate,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN res.race_id IS NOT NULL THEN r.id END) / COUNT(DISTINCT r.id), 1) as results_rate
FROM races r
LEFT JOIN (SELECT DISTINCT race_id FROM trifecta_odds) t ON r.id = t.race_id
LEFT JOIN (SELECT DISTINCT race_id FROM results) res ON r.id = res.race_id
WHERE r.race_date >= '2020-01-01'
GROUP BY year, month
ORDER BY year, month;
```

**工数**: 2時間
**期待効果**: データ欠損パターンの正確な把握、補完優先度の決定

---

### 1-2. テーブル間整合性チェック

**調査内容**:
| チェック項目 | SQL例 | 期待される発見 |
|-------------|------|--------------|
| races vs results 整合性 | `SELECT COUNT(*) FROM races r WHERE NOT EXISTS (SELECT 1 FROM results res WHERE res.race_id = r.id)` | 結果データなしのレース数 |
| races vs entries 整合性 | 同上パターン | 出走表なしのレース |
| races vs trifecta_odds 整合性 | 同上パターン | オッズなしのレース |
| races vs race_predictions 整合性 | 同上パターン | 予測データなしのレース |
| results vs payouts 整合性 | 同上パターン | 払戻なしのレース |
| race_details vs entries 整合性 | race_id + pit_number の一致 | 展示データの欠損 |

**調査SQL例**:
```sql
-- レース結果の整合性チェック
SELECT
    strftime('%Y', r.race_date) as year,
    COUNT(*) as total_races,
    SUM(CASE WHEN res.cnt IS NULL THEN 1 ELSE 0 END) as no_results,
    SUM(CASE WHEN res.cnt < 6 THEN 1 ELSE 0 END) as incomplete_results,
    SUM(CASE WHEN e.cnt IS NULL THEN 1 ELSE 0 END) as no_entries,
    SUM(CASE WHEN e.cnt < 6 THEN 1 ELSE 0 END) as incomplete_entries
FROM races r
LEFT JOIN (SELECT race_id, COUNT(*) as cnt FROM results GROUP BY race_id) res ON r.id = res.race_id
LEFT JOIN (SELECT race_id, COUNT(*) as cnt FROM entries GROUP BY race_id) e ON r.id = e.race_id
WHERE r.race_date >= '2020-01-01'
GROUP BY year;
```

**工数**: 3時間
**期待効果**: データ不整合の発見、バックテスト信頼性の向上

---

### 1-3. 欠損パターンの偏り分析

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| 会場別の欠損率 | 24会場×6年 = 144セグメント分析 | 特定会場のデータ欠損 |
| 曜日別の欠損率 | 曜日×年度で集計 | 収集タイミングの問題 |
| グレード別の欠損率 | 一般/G3/G2/G1/SG別 | 特定グレードの収集漏れ |
| レース番号別の欠損率 | 1R-12R別 | 時間帯による収集漏れ |

**調査SQL例**:
```sql
-- 会場別の欠損パターン
SELECT
    r.venue_code,
    v.name as venue_name,
    strftime('%Y', r.race_date) as year,
    COUNT(*) as total_races,
    SUM(CASE WHEN t.race_id IS NULL THEN 1 ELSE 0 END) as missing_odds,
    ROUND(100.0 * SUM(CASE WHEN t.race_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as missing_rate
FROM races r
LEFT JOIN venues v ON r.venue_code = v.code
LEFT JOIN (SELECT DISTINCT race_id FROM trifecta_odds) t ON r.id = t.race_id
WHERE r.race_date >= '2020-01-01'
GROUP BY r.venue_code, year
HAVING missing_rate > 10
ORDER BY year, missing_rate DESC;
```

**工数**: 2時間
**期待効果**: 補完戦略の最適化

---

### 1-4. 異常値の検出

**調査内容**:
| チェック項目 | 正常範囲 | 異常検出条件 |
|-------------|---------|-------------|
| オッズ異常 | 1.0 - 5000.0 | odds < 1.0 OR odds > 5000 |
| 展示タイム異常 | 6.3 - 7.5秒 | exh_time < 6.0 OR exh_time > 8.0 |
| 選手勝率異常 | 0.0 - 100.0 | win_rate < 0 OR win_rate > 100 |
| モーター2連率異常 | 0.0 - 100.0 | motor_second_rate < 0 OR motor_second_rate > 100 |
| STタイム異常 | -0.10 - 0.30 | st_time < -0.20 OR st_time > 0.40 |
| 波高異常 | 0 - 10cm | wave_height < 0 OR wave_height > 15 |

**調査SQL例**:
```sql
-- オッズ異常値の検出
SELECT
    race_id, combination, odds,
    CASE
        WHEN odds < 1.0 THEN '異常：低すぎ'
        WHEN odds > 5000 THEN '異常：高すぎ'
        WHEN odds = 0 THEN '異常：ゼロ'
        ELSE '正常'
    END as status
FROM trifecta_odds
WHERE odds < 1.0 OR odds > 5000 OR odds = 0;

-- 展示タイム異常値の検出
SELECT
    rd.race_id, rd.pit_number, rd.exhibition_time,
    r.race_date, r.venue_code
FROM race_details rd
JOIN races r ON rd.race_id = r.id
WHERE rd.exhibition_time IS NOT NULL
    AND (rd.exhibition_time < 6.0 OR rd.exhibition_time > 8.0);
```

**工数**: 2時間
**期待効果**: データクレンジングによる予測精度向上

---

## 2. 統計指標の信頼性検証

### 2-1. 選手成績統計の精度検証

**現状の問題**:
- `racers`テーブルの`win_rate`, `second_rate`は定期更新
- 2021年・2023年のデータ欠損で正確性に疑問

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| win_rate の算出根拠 | entriesテーブルとの照合 | 算出期間の確認 |
| 選手別のレース数分布 | 2021年・2023年のレース数集計 | データ欠損の影響 |
| 級別判定への影響 | 欠損期間のレース成績評価 | 級別スコアの歪み |

**調査SQL例**:
```sql
-- 選手別の年度別レース数（欠損影響確認）
SELECT
    e.racer_number,
    strftime('%Y', r.race_date) as year,
    COUNT(*) as race_count,
    AVG(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as actual_win_rate
FROM entries e
JOIN races r ON e.race_id = r.id
LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
WHERE r.race_date >= '2020-01-01'
GROUP BY e.racer_number, year
HAVING race_count > 10
ORDER BY racer_number, year;
```

**工数**: 3時間
**期待効果**: 選手評価の信頼性向上

---

### 2-2. モーター成績の信頼性検証

**現状の問題**:
- `entries.motor_second_rate`はレース時点の公式データを使用
- モーター入れ替え（約10ヶ月周期）で統計リセット

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| motor_second_rate の分布 | ヒストグラム分析 | 異常値・欠損パターン |
| 会場×期間でのモーター成績変動 | 月別・会場別集計 | モーター入替の影響 |
| 予測精度とモーター2連率の相関 | 的中レースでのモーター成績 | 有効な特徴量か確認 |

**調査SQL例**:
```sql
-- モーター2連率の分布
SELECT
    CASE
        WHEN motor_second_rate IS NULL THEN 'NULL'
        WHEN motor_second_rate < 20 THEN '0-20'
        WHEN motor_second_rate < 30 THEN '20-30'
        WHEN motor_second_rate < 40 THEN '30-40'
        WHEN motor_second_rate < 50 THEN '40-50'
        ELSE '50+'
    END as rate_range,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM entries WHERE motor_second_rate IS NOT NULL), 1) as pct
FROM entries
GROUP BY rate_range
ORDER BY rate_range;
```

**工数**: 2時間
**期待効果**: モーター特徴量の有効性確認

---

### 2-3. 会場別統計値の信頼性検証

**調査内容**:
| チェック項目 | テーブル | 調査方法 |
|-------------|---------|---------|
| venue_data のcourse_win_rate | venue_data | 実データとの照合 |
| stadium_attack_stats の精度 | stadium_attack_stats | 実際の決まり手分布との比較 |
| player_escape_stats の精度 | player_escape_stats | 実際の1着率との比較 |
| racer_venue_features の精度 | racer_venue_features | 会場別勝率の妥当性 |

**工数**: 2時間
**期待効果**: 会場特性評価の正確性向上

---

## 3. 未活用データカラムの完全洗い出し

### 3-1. 現在活用しているカラムの整理

**予測ロジック（PREDICTION_LOGIC.md）で使用中**:

| テーブル | 使用カラム | 用途 |
|---------|-----------|------|
| entries | win_rate, second_rate, motor_second_rate, boat_second_rate, avg_st, racer_rank | スコアリング |
| race_details | exhibition_time, st_time, actual_course, tilt_angle | 展示・直前情報 |
| races | race_grade, venue_code, is_nighter, is_ladies | レース条件 |
| race_conditions | weather, wind_direction, wind_speed, wave_height | 気象条件 |

### 3-2. 未活用カラムの一覧と評価

| テーブル | カラム | データ充足率 | 活用可能性 | 優先度 |
|---------|--------|:----------:|:--------:|:-----:|
| entries | local_win_rate | 要確認 | **高** | 1 |
| entries | local_second_rate | 要確認 | **高** | 1 |
| entries | local_third_rate | 要確認 | 中 | 2 |
| entries | boat_third_rate | 要確認 | 低 | 3 |
| entries | f_count | 要確認 | **高** | 1 |
| entries | l_count | 要確認 | 中 | 2 |
| race_details | chikusen_time | 低い（NULL多） | 中 | 2 |
| race_details | isshu_time | 低い（NULL多） | 中 | 2 |
| race_details | mawariashi_time | 低い（NULL多） | 中 | 2 |
| race_details | adjusted_weight | 要確認 | 低 | 3 |
| race_details | exhibition_course | 要確認 | **高** | 1 |
| race_details | prev_race_course | 要確認 | 中 | 2 |
| race_details | prev_race_st | 要確認 | 中 | 2 |
| race_details | prev_race_rank | 要確認 | 中 | 2 |
| race_conditions | temperature | 要確認 | 中 | 2 |
| race_conditions | water_temperature | 要確認 | 中 | 2 |
| races | is_rookie | 要確認 | 中 | 2 |
| races | is_shinnyuu_kotei | 要確認 | 低 | 3 |
| tide | tide_level | 要確認 | **高** | 1 |
| rdmdb_tide | sea_level_cm | 高（647万件） | **高** | 1 |

**調査SQL例**:
```sql
-- カラム別の充足率確認
SELECT
    'local_win_rate' as column_name,
    COUNT(*) as total,
    SUM(CASE WHEN local_win_rate IS NOT NULL THEN 1 ELSE 0 END) as non_null,
    ROUND(100.0 * SUM(CASE WHEN local_win_rate IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as fill_rate
FROM entries
UNION ALL
SELECT
    'f_count',
    COUNT(*),
    SUM(CASE WHEN f_count IS NOT NULL THEN 1 ELSE 0 END),
    ROUND(100.0 * SUM(CASE WHEN f_count IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM entries;
-- ... 他のカラムも同様
```

**工数**: 4時間
**期待効果**: 新規特徴量の発見、予測精度向上

---

## 4. 環境要因・外部要因の活用度チェック

### 4-1. 天候データの活用状況

**現状**:
- `race_conditions`テーブルに天候データ（130,792件）
- `WeatherAdjuster`クラスで風向き×風速補正を実装

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| 天候別の予測精度 | 天候区分×的中率のクロス集計 | 天候要因の影響度 |
| 風速別の予測精度 | 風速区分（0-3m, 3-5m, 5m+）×的中率 | 風速の閾値最適化 |
| 風向き別の予測精度 | 8方位×的中率 | 風向き補正の有効性 |

**調査SQL例**:
```sql
-- 風速別の予測精度分析
SELECT
    CASE
        WHEN rc.wind_speed IS NULL THEN '不明'
        WHEN rc.wind_speed < 3 THEN '弱(0-3m)'
        WHEN rc.wind_speed < 5 THEN '中(3-5m)'
        ELSE '強(5m+)'
    END as wind_category,
    COUNT(*) as race_count,
    AVG(CASE WHEN rp.rank_prediction = 1 AND res.rank = '1' AND rp.pit_number = res.pit_number THEN 1 ELSE 0 END) as hit_rate
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id AND rp.rank_prediction = 1
JOIN race_conditions rc ON r.id = rc.race_id
JOIN results res ON r.id = res.race_id AND res.rank = '1'
WHERE r.race_date >= '2025-01-01'
GROUP BY wind_category;
```

**工数**: 3時間
**期待効果**: 気象条件の予測への活用最適化

---

### 4-2. 潮位データの活用状況

**現状**:
- `rdmdb_tide`テーブルに647万件の潮位データ
- `TideAdjuster`クラスが実装済み
- 効果検証は **未実施**（DATA_COMPLETION_REVIEW_ITEMS.mdで言及）

**調査内容**:
| チェック項目 | 対象会場 | 調査方法 |
|-------------|---------|---------|
| 潮位補正ON/OFF比較 | 海水面9会場 | バックテスト比較 |
| 満潮/干潮別の精度 | 海水面9会場 | 潮位区分×的中率 |
| 潮位×風向きの交互作用 | 海水面9会場 | 複合条件分析 |

**海水面会場一覧**:
- 丸亀(15), 鳴門(14), 宮島(17), 徳山(18), 下関(19), 若松(20), 芦屋(21), 唐津(23), 大村(24)

**工数**: 3時間
**期待効果**: 潮位補正の効果確定（採用or廃止の判断）

---

### 4-3. 水質（淡水/汽水/海水）の活用状況

**現状**:
- `venue_data.water_type`に淡水/汽水/海水の情報
- 予測ロジックでの明示的な使用は **確認されず**

**水質別会場**:
- 淡水: 桐生(01), 戸田(02), 多摩川(05), びわこ(11), 住之江(12)
- 汽水: 江戸川(03), 平和島(04), 浜名湖(06), 蒲郡(07), 常滑(08), 津(09), 三国(10)
- 海水: 丸亀(15), 鳴門(14), 宮島(17), 徳山(18), 下関(19), 若松(20), 芦屋(21), 唐津(23), 大村(24)

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| 水質別の予測精度 | 水質×的中率 | 水質の影響度 |
| 水質×体重の相関 | 重量級選手の成績比較 | 体重ペナルティの調整 |
| 水質×モーター性能 | モーター2連率×水質×勝率 | 水質特性の活用 |

**工数**: 2時間
**期待効果**: 新規特徴量としての水質活用

---

## 5. 予測精度の経年変化・会場別変化

### 5-1. 年度別予測精度の詳細分析

**現状**（YEARLY_PERFORMANCE.md）:
- 2025年ROI: 171.8%
- 2025年的中率: 約8%

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| 1着的中率の経年変化 | 年度別集計 | 予測精度のトレンド |
| 信頼度別の的中率変化 | 信頼度×年度×的中率 | 信頼度判定の安定性 |
| 2021年・2023年の精度 | 補完前後の比較 | データ欠損の影響 |

**工数**: 2時間

---

### 5-2. 会場別予測精度のばらつき分析

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| 会場別の的中率 | 24会場×年度×的中率 | 苦手会場の特定 |
| 会場別のROI | 24会場×年度×ROI | 赤字会場の特定 |
| 会場特性との相関 | イン強/弱×的中率 | 会場調整の妥当性 |

**調査SQL例**:
```sql
-- 会場別の予測精度（2025年）
SELECT
    r.venue_code,
    v.name as venue_name,
    vd.water_type,
    COUNT(*) as race_count,
    SUM(CASE WHEN rp.pit_number = res.pit_number AND res.rank = '1' THEN 1 ELSE 0 END) as hits,
    ROUND(100.0 * SUM(CASE WHEN rp.pit_number = res.pit_number AND res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id AND rp.rank_prediction = 1 AND rp.prediction_type = 'before'
JOIN results res ON r.id = res.race_id AND res.rank = '1'
LEFT JOIN venues v ON r.venue_code = v.code
LEFT JOIN venue_data vd ON r.venue_code = vd.venue_code
WHERE r.race_date >= '2025-01-01'
GROUP BY r.venue_code
ORDER BY hit_rate DESC;
```

**工数**: 3時間
**期待効果**: 会場別購入条件の最適化

---

## 6. 競艇のトレンド・ルール変更の影響

### 6-1. 2020年〜2025年のルール変更・トレンド変化

**調査内容**:
| 調査項目 | 調査方法 | 期待される発見 |
|---------|---------|--------------|
| モーター性能の変化 | 年度別モーター2連率分布 | モーター均質化傾向 |
| 1コース勝率の変化 | 年度別1コース勝率 | イン有利化/不利化傾向 |
| 決まり手分布の変化 | 年度別決まり手割合 | まくり/差しの傾向変化 |
| 選手層の変化 | 年度別A1/A2/B1/B2分布 | 新人増加の影響 |

**調査SQL例**:
```sql
-- 年度別1コース勝率の変化
SELECT
    strftime('%Y', r.race_date) as year,
    COUNT(*) as total_races,
    SUM(CASE WHEN res.pit_number = 1 AND res.rank = '1' THEN 1 ELSE 0 END) as in1_wins,
    ROUND(100.0 * SUM(CASE WHEN res.pit_number = 1 AND res.rank = '1' THEN 1 ELSE 0 END) / COUNT(*), 2) as in1_win_rate
FROM races r
JOIN results res ON r.id = res.race_id AND res.rank = '1'
WHERE r.race_date >= '2020-01-01'
GROUP BY year
ORDER BY year;

-- 年度別決まり手分布
SELECT
    strftime('%Y', r.race_date) as year,
    res.kimarite,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY strftime('%Y', r.race_date)), 2) as pct
FROM races r
JOIN results res ON r.id = res.race_id AND res.rank = '1'
WHERE r.race_date >= '2020-01-01' AND res.kimarite IS NOT NULL
GROUP BY year, res.kimarite
ORDER BY year, count DESC;
```

**工数**: 3時間
**期待効果**: トレンド変化への適応、年度依存性の理解

---

### 6-2. モーター入替サイクルの影響

**現状認識**:
- モーターは年1回（約10ヶ月周期）で入替
- 入替直後はモーター2連率の信頼性が低下

**調査内容**:
| 調査項目 | 調査方法 | 期待される発見 |
|---------|---------|--------------|
| モーター入替時期の特定 | 会場別のモーター2連率リセットタイミング | 入替月の特定 |
| 入替直後の予測精度 | 入替後1-2ヶ月の的中率 | 信頼性低下期間の特定 |
| 入替前後での条件調整 | 入替前後でのROI比較 | 条件調整の必要性 |

**工数**: 2時間
**期待効果**: モーター特徴量の信頼性区間の設定

---

## 7. バックテストの妥当性検証

### 7-1. standard_backtest.py のロジック検証

**現状**（コードレビュー済み）:
- 3点買いパターンH（200円/100円/100円）と1点買い（100円）を条件別に使い分け
- オッズ取得は予測順位ベース（`rp1.pit_number || '-' || rp2.pit_number || '-' || rp3.pit_number`）で正しい

**追加検証項目**:
| チェック項目 | 検証方法 | リスク |
|-------------|---------|-------|
| オッズ取得タイミング | fetched_at の確認 | 締切直前オッズとの乖離 |
| 払戻金との照合 | payouts.amount と計算値の比較 | 計算ロジックの誤り |
| 的中判定の正確性 | results との照合 | 失格・除外の扱い |

**検証SQL例**:
```sql
-- 払戻金との照合検証
SELECT
    r.id as race_id,
    r.race_date,
    CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT) as predicted_combo,
    t.odds as backtest_odds,
    p.amount / 100 as actual_payout_odds,
    ABS(t.odds - p.amount / 100) as diff
FROM races r
JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
JOIN payouts p ON r.id = p.race_id AND p.bet_type = 'trifecta'
    AND p.combination = CAST(res1.pit_number AS TEXT) || '-' || CAST(res2.pit_number AS TEXT) || '-' || CAST(res3.pit_number AS TEXT)
WHERE rp1.pit_number = res1.pit_number
    AND rp2.pit_number = res2.pit_number
    AND rp3.pit_number = res3.pit_number
    AND r.race_date >= '2025-01-01'
LIMIT 100;
```

**工数**: 3時間
**期待効果**: バックテスト信頼性の確認

---

### 7-2. オーバーフィッティングリスクの評価

**現状のリスク要因**:
- 購入条件が細分化されている（10条件）
- 会場フィルター・月除外・逃げ率など複数フィルター
- 2021年・2023年のデータ欠損で有効サンプル減少

**調査内容**:
| チェック項目 | 調査方法 | リスク指標 |
|-------------|---------|----------|
| 条件別サンプル数 | 各条件の6年間サンプル数 | 100件未満は過学習リスク |
| 黒字年数の安定性 | 条件別の黒字年数 | 4/6年未満は不安定 |
| 補完前後の変動 | データ補完後のROI変動 | 大幅変動は過学習の証拠 |

**工数**: 2時間
**期待効果**: 過学習条件の特定と除外

---

## 8. 機械学習モデルの見直し

### 8-1. LightGBMモデルの学習データ確認

**現状**（conditional_meta.json）:
- Stage1: 155,484サンプル、AUC 0.901
- Stage2: 129,581サンプル、AUC 0.742
- Stage3: 103,684サンプル、AUC 0.668
- 作成日: 2025-12-04

**調査内容**:
| チェック項目 | 調査方法 | 期待される発見 |
|-------------|---------|--------------|
| 学習データの年度分布 | モデルメタデータ確認 | 2021年・2023年の比率 |
| 特徴量重要度 | feature_importance分析 | 有効な特徴量の確認 |
| 検証データの選定 | CV分割方法の確認 | 時系列リークの有無 |

**工数**: 2時間

---

### 8-2. モデル再学習の必要性評価

**再学習の検討条件**:
1. データ補完で学習サンプルが大幅増加（現在155k → 推定300k+）
2. 2021年・2023年のデータが学習に含まれていない場合
3. 特徴量の追加・変更がある場合

**再学習の手順**:
```bash
# 1. 特徴量生成
python scripts/training/generate_features.py --start 2020 --end 2025

# 2. モデル学習
python scripts/training/train_conditional_model.py

# 3. 効果検証
python scripts/backtest/standard_backtest.py --full --compare
```

**工数**: 6時間（学習時間含む）
**期待効果**: 予測精度+2-5%

---

## 9. システム全体のボトルネック分析

### 9-1. 予測精度のボトルネック特定

**分析観点**:
| ボトルネック候補 | 現状 | 改善可能性 |
|----------------|------|----------|
| **データ品質** | 2021年・2023年欠損 | **高**（補完で解決） |
| **特徴量** | 未活用カラムあり | **高**（追加可能） |
| **モデル** | AUC 0.90（Stage1） | 中（既に高い） |
| **購入条件** | 10条件、ROI 160% | 中（精緻化余地あり） |

---

### 9-2. 改善効果の期待値マトリクス

| 改善項目 | 工数 | 期待ROI改善 | 優先度 |
|---------|:---:|:----------:|:-----:|
| データ補完（2021年・2023年） | 8h | +10-30pt | **最高** |
| 未活用カラムの特徴量化 | 4h | +3-10pt | 高 |
| モデル再学習 | 6h | +2-5pt | 中 |
| 購入条件の精緻化 | 4h | +5-15pt | 高 |
| 潮位補正の効果検証 | 3h | +2-5pt | 中 |

---

## 10. 長期的な改善ロードマップ

### 10-1. 短期（1-2週間）

1. **データ補完の実行**
   - 2021年・2023年のレース基本情報・結果・オッズを補完
   - 工数: 8時間

2. **ベースラインの再取得**
   - 補完後のROI・的中率を確認
   - 工数: 1時間

3. **前回調査項目（DATA_COMPLETION_REVIEW_ITEMS.md）の実施**
   - Phase 1: RJ-1, RJ-2, 潮位補正
   - 工数: 8時間

### 10-2. 中期（1ヶ月）

1. **本ドキュメントの調査項目の実施**
   - データ品質チェック（セクション1）: 9時間
   - 統計指標検証（セクション2）: 7時間
   - 未活用カラム分析（セクション3）: 4時間
   - 環境要因分析（セクション4）: 8時間

2. **購入条件の全面見直し**
   - 補完データを用いた再評価
   - 工数: 10時間

3. **LightGBMモデル再学習**
   - 補完データを含む6年間で学習
   - 工数: 6時間

### 10-3. 長期（3-6ヶ月）

1. **ROI 200%達成戦略**
   - 高ROI条件の追加発見
   - 低ROI条件の除外
   - 目標: ROI 185% → 200%

2. **予測精度の向上**
   - 新規特徴量の追加
   - モデルアーキテクチャの改善
   - 目標: 1着的中率 50% → 55%

3. **自動化・安定運用**
   - 日次バッチの安定化
   - 監視・アラートの強化

---

## 11. 実施優先順位と工数見積もり

| 優先度 | 項目 | 工数 | 期待効果 | セクション |
|:-----:|------|:---:|---------|:--------:|
| 1 | データ充足率の詳細確認 | 2h | 補完戦略の最適化 | 1-1 |
| 2 | テーブル間整合性チェック | 3h | データ不整合の発見 | 1-2 |
| 3 | 未活用カラムの充足率確認 | 4h | 新規特徴量の発見 | 3-2 |
| 4 | 会場別予測精度のばらつき | 3h | 苦手会場の特定 | 5-2 |
| 5 | 潮位データの活用検証 | 3h | 潮位補正の効果確定 | 4-2 |
| 6 | バックテストの妥当性検証 | 3h | 信頼性の確認 | 7-1 |
| 7 | 天候データの活用検証 | 3h | 気象条件の最適化 | 4-1 |
| 8 | 年度別予測精度の詳細分析 | 2h | トレンドの把握 | 5-1 |
| 9 | LightGBMモデルの確認 | 2h | 再学習の必要性判断 | 8-1 |
| 10 | オーバーフィッティング評価 | 2h | 過学習条件の特定 | 7-2 |
| **合計** | | **27h** | | |

---

## 12. 総合的なリスク評価

### データ補完前の現システムが抱えるリスク

| リスク | 影響度 | 発生確率 | 対策 |
|-------|:-----:|:------:|------|
| **2021年・2023年データ欠損による評価の歪み** | 高 | 確定 | データ補完 |
| **購入条件の過学習** | 中 | 中 | サンプル数増加後の再評価 |
| **統計指標の不正確さ** | 中 | 中 | 補完データでの再計算 |
| **トレンド変化への不適応** | 中 | 低 | 経年変化の分析 |
| **モデルの陳腐化** | 低 | 中 | 定期的な再学習 |

---

## 13. 期待される総合的な改善効果

### 前回調査（DATA_COMPLETION_REVIEW_ITEMS.md）と本調査の統合効果

| 項目 | 現状 | 改善後目標 | 改善幅 |
|------|------|----------|-------|
| **ROI** | 160.7% | **185-200%** | +25-40pt |
| **6年間収支** | +332,380円 | **+450,000-550,000円** | +120,000-220,000円 |
| **1着的中率** | 4.56% | **5.5-6.5%** | +1-2pt |
| **黒字年数** | 6/6年 | 6/6年維持 | - |
| **月間黒字率** | 67% | **75-80%** | +8-13pt |
| **購入レース数** | 3,666件 | **4,500-5,500件** | +800-1,800件 |

### 改善効果の内訳

| 施策カテゴリ | 期待ROI改善 | 根拠 |
|------------|:---------:|------|
| データ補完（2021年・2023年） | +10-20pt | サンプル数5倍増による評価精度向上 |
| 不採用案の再評価（前回調査） | +10-30pt | 計算ミス案件の救済 |
| 未活用カラムの特徴量化 | +3-10pt | 新規有効特徴量の発見 |
| 購入条件の精緻化 | +5-15pt | 会場・閾値の最適化 |
| モデル再学習 | +2-5pt | 補完データでの学習 |
| **合計** | **+30-80pt** | |

---

## 14. まとめ

### 最優先実施項目

1. **データ補完の実行**（2021年・2023年）
2. **データ充足率の詳細確認**（セクション1-1）
3. **テーブル間整合性チェック**（セクション1-2）

### 本調査のスコープ

- 前回調査（DATA_COMPLETION_REVIEW_ITEMS.md）: 不採用案の再評価、購入条件の精緻化、新規分析提案
- **本調査**: データ品質、統計指標信頼性、未活用カラム、環境要因、バックテスト妥当性、モデル見直し

### 総合実施工数

- **前回調査**: 43.5時間
- **本調査**: 27時間
- **合計**: **約70時間**（約9人日）

---

**作成日**: 2026-01-30
**作成者**: Claude Opus 4.5
**次回更新予定**: データ補完完了後
