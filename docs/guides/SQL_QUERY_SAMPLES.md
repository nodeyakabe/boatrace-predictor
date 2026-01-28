# SQLクエリサンプル集

**作成日**: 2026-01-21
**目的**: Claude Codeが効率的にデータを活用できるように、頻繁に使うSQLクエリをまとめる

---

## 📊 データベース概要

**総テーブル数**: 47テーブル
**総レコード数**: 約2,000万件
**対象期間**: 2020年～現在（6年分）

### 主要テーブル

| テーブル名 | レコード数 | 用途 |
|-----------|-----------|------|
| `races` | 228,027件 | レース基本情報 |
| `entries` | 1,020,418件 | 出走情報 |
| `results` | 987,461件 | レース結果 |
| `race_predictions` | 1,064,140件 | 予測データ |
| `trifecta_odds` | 9,776,586件 | 3連単オッズ |
| `race_details` | 804,348件 | レース詳細 |
| `exhibition_data` | 2,890件 | オリジナル展示データ |

---

## 🎯 1. 購入対象レース抽出

### 1-1. 本日の購入対象レース（最新ロジック）

```sql
SELECT
    r.id as race_id,
    r.venue_code,
    r.race_date,
    r.race_number,
    r.race_time,
    rp.confidence_level,
    rp.expected_return,
    rp.predicted_rank_1,
    rp.predicted_rank_2,
    rp.predicted_rank_3,
    t.odds as trifecta_odds,
    t.combination
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
LEFT JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp.predicted_rank_1 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_2 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_3 AS TEXT)
WHERE r.race_date = DATE('now', 'localtime')
  AND rp.is_target = 1
ORDER BY r.race_time;
```

**ポイント**:
- `is_target = 1`: 購入対象フラグ
- `LEFT JOIN`でオッズ結合（オッズ未取得の場合もNULLで表示）
- `DATE('now', 'localtime')`: 本日の日付

---

### 1-2. 信頼度別の購入対象レース数（本日）

```sql
SELECT
    rp.confidence_level,
    COUNT(*) as race_count,
    AVG(rp.expected_return) as avg_expected_return,
    AVG(t.odds) as avg_odds
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
LEFT JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp.predicted_rank_1 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_2 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_3 AS TEXT)
WHERE r.race_date = DATE('now', 'localtime')
  AND rp.is_target = 1
GROUP BY rp.confidence_level
ORDER BY rp.confidence_level;
```

---

### 1-3. パターンH適用レース抽出

```sql
SELECT
    r.id as race_id,
    r.venue_code,
    r.race_number,
    rp.confidence_level,
    rp.multi_bet_pattern,
    rp.expected_return
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
WHERE r.race_date = DATE('now', 'localtime')
  AND rp.is_target = 1
  AND rp.multi_bet_pattern = 'PATTERN_H';
```

---

## 📈 2. 選手分析クエリ

### 2-1. 選手の基本統計

```sql
SELECT
    r.racer_id,
    r.name,
    r.grade,
    rs.all_1_rate,
    rs.all_2_rate,
    rs.all_3_rate,
    rs.nationwide_win_rate,
    rs.nationwide_second_rate,
    rs.nationwide_third_rate
FROM racers r
LEFT JOIN racer_features rs ON r.racer_id = rs.racer_id
WHERE r.racer_id = 1234  -- 選手登録番号で指定
LIMIT 1;
```

---

### 2-2. 選手×会場の相性

```sql
SELECT
    rvf.venue_code,
    v.name as venue_name,
    rvf.local_win_rate,
    rvf.local_second_rate,
    rvf.local_third_rate,
    (rvf.local_win_rate - rf.nationwide_win_rate) as affinity_score
FROM racer_venue_features rvf
JOIN racer_features rf ON rvf.racer_id = rf.racer_id
JOIN venues v ON rvf.venue_code = v.code
WHERE rvf.racer_id = 1234
ORDER BY affinity_score DESC;
```

**ポイント**:
- `affinity_score`: 当地勝率 - 全国勝率（会場相性スコア）
- 正の値が大きいほど得意会場

---

### 2-3. 選手のコース別成績

```sql
SELECT
    e.course,
    COUNT(*) as race_count,
    SUM(CASE WHEN res.finish_order = 1 THEN 1 ELSE 0 END) as win_count,
    ROUND(AVG(CASE WHEN res.finish_order = 1 THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate,
    ROUND(AVG(CASE WHEN res.finish_order <= 2 THEN 1.0 ELSE 0.0 END) * 100, 2) as place_rate_2,
    ROUND(AVG(CASE WHEN res.finish_order <= 3 THEN 1.0 ELSE 0.0 END) * 100, 2) as place_rate_3
FROM entries e
JOIN races r ON e.race_id = r.id
JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
WHERE e.racer_id = 1234
  AND r.race_date >= DATE('now', '-1 year')
GROUP BY e.course
ORDER BY e.course;
```

---

## 🏁 3. レース分析クエリ

### 3-1. レースの出走表（エントリー情報）

```sql
SELECT
    e.pit_number,
    r.name as racer_name,
    r.grade,
    e.motor_number,
    e.boat_number,
    e.course,
    rf.nationwide_win_rate,
    rf.all_1_rate,
    rf.all_2_rate,
    rf.all_3_rate
FROM entries e
JOIN racers r ON e.racer_id = r.racer_id
LEFT JOIN racer_features rf ON r.racer_id = rf.racer_id
WHERE e.race_id = 123456
ORDER BY e.pit_number;
```

---

### 3-2. レース結果と予測の比較

```sql
SELECT
    r.venue_code,
    r.race_date,
    r.race_number,
    rp.predicted_rank_1,
    rp.predicted_rank_2,
    rp.predicted_rank_3,
    rp.confidence_level,
    res1.pit_number as actual_1st,
    res2.pit_number as actual_2nd,
    res3.pit_number as actual_3rd,
    CASE
        WHEN rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1 ELSE 0
    END as is_correct,
    p.payout_amount as actual_payout
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
LEFT JOIN results res1 ON r.id = res1.race_id AND res1.finish_order = 1
LEFT JOIN results res2 ON r.id = res2.race_id AND res2.finish_order = 2
LEFT JOIN results res3 ON r.id = res3.race_id AND res3.finish_order = 3
LEFT JOIN payouts p ON r.id = p.race_id AND p.betting_type = '3連単'
WHERE r.race_date = '2026-01-21'
ORDER BY r.race_time;
```

---

### 3-3. 展示タイム・ST・チルト角の取得（race_details）

**重要**: 公式データの展示タイムは`race_details`テーブルにあります（`exhibition_data`ではない）

```sql
SELECT
    rd.pit_number,
    r.name as racer_name,
    rd.chikusen_time,        -- 展示タイム（6.XX秒）
    rd.exhibition_time,      -- 展示タイム（別名）
    rd.st_time,              -- スタートタイミング（±0.XX秒）
    rd.tilt_angle,           -- チルト角（-0.5〜3.0度）
    rd.isshu_time,           -- 一周タイム
    rd.mawariashi_time,      -- 回り足タイム
    rd.actual_course,        -- 実際のコース
    rd.exhibition_course     -- 展示コース
FROM race_details rd
JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
JOIN racers r ON e.racer_id = r.racer_id
WHERE rd.race_id = 123456
ORDER BY rd.pit_number;
```

**データ充足率（2020-2025年）**:
- `chikusen_time`: 0.6%（552/244,794レース）→ 補完可能
- `st_time`: 50%程度
- `tilt_angle`: 80%程度

**補完方法**:
```bash
python scripts/data_collection/補完_レース詳細データ_改善版v4.py \
  --start-date 2020-01-01 --end-date 2025-12-31
```

---

### 3-4. オリジナル展示データ取得（exhibition_data - Boatersサイト独自）

**注意**: `exhibition_data`はBoatersサイト独自データで、前日分のみ取得可能（過去補完不可）

```sql
SELECT
    e.pit_number,
    r.name as racer_name,
    ed.isshu_time,           -- 一周タイム（Boaters版）
    ed.mawariashi_time,      -- 回り足タイム（Boaters版）
    ed.chikusen_time,        -- 展示タイム（Boaters版）
    ed.exhibition_time,      -- 展示タイム
    ed.start_timing,         -- スタートタイミング
    ed.turn_quality,         -- ターン品質
    ed.weight_change,        -- 体重変化
    ed.data_source           -- データソース（'boaters'）
FROM exhibition_data ed
JOIN entries e ON ed.race_id = e.race_id AND ed.pit_number = e.pit_number
JOIN racers r ON e.racer_id = r.racer_id
WHERE ed.race_id = 123456
ORDER BY ed.pit_number;
```

**データ充足率（2020-2025年）**:
- カバレッジ: 0.4%（726レース、2023年11月以降のみ）
- 補完不可（前日分のみ公開、過去データは削除済み）

---

## 🌊 4. 気象・水面条件クエリ

### 4-1. レースの気象条件取得（race_conditions）

```sql
SELECT
    r.venue_code,
    r.race_date,
    r.race_number,
    rc.weather,              -- 天候（晴、曇、雨など）
    rc.wind_direction,       -- 風向（北、南東など）
    rc.wind_speed,           -- 風速（m/s）
    rc.wave_height,          -- 波高（cm）
    rc.temperature,          -- 気温（℃）
    rc.water_temperature     -- 水温（℃）
FROM races r
LEFT JOIN race_conditions rc ON r.id = rc.race_id
WHERE r.id = 123456;
```

**データ充足率（2020-2025年）**:
- `wave_height`: 51.0%（124,856/244,794レース）→ 補完可能
- `wind_speed`: 80%程度
- `water_temperature`: 70%程度

**補完方法**: race_conditions収集スクリプト実行

---

### 4-2. 波高別のレース成績分析（海水面9場のみ）

```sql
SELECT
    CASE
        WHEN rc.wave_height IS NULL THEN 'データなし'
        WHEN rc.wave_height <= 5 THEN '穏やか(5cm以下)'
        WHEN rc.wave_height <= 10 THEN '標準(6-10cm)'
        WHEN rc.wave_height <= 20 THEN 'やや荒れ(11-20cm)'
        ELSE '荒れ(21cm以上)'
    END as wave_condition,
    COUNT(*) as race_count,
    AVG(t.odds) as avg_odds,
    SUM(CASE WHEN rp.predicted_rank_1 = res1.pit_number THEN 1 ELSE 0 END) as correct_count
FROM races r
LEFT JOIN race_conditions rc ON r.id = rc.race_id
JOIN race_predictions rp ON r.id = rp.race_id
LEFT JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp.predicted_rank_1 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_2 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_3 AS TEXT)
LEFT JOIN results res1 ON r.id = res1.race_id AND res1.finish_order = 1
WHERE r.venue_code IN (3, 4, 5, 9, 13, 21, 22, 23, 24)  -- 海水面9場
  AND r.race_date >= '2020-01-01'
GROUP BY 1
ORDER BY 1;
```

**海水面9場**: 江戸川(3)、平和島(4)、多摩川(5)、津(9)、住之江(13)、芦屋(21)、福岡(22)、唐津(23)、大村(24)

---

### 7-3. 風速×コース別の影響分析

```sql
SELECT
    e.pit_number,
    CASE
        WHEN rc.wind_speed IS NULL THEN 'データなし'
        WHEN rc.wind_speed <= 2 THEN '微風(2m以下)'
        WHEN rc.wind_speed <= 4 THEN '普通(3-4m)'
        WHEN rc.wind_speed <= 6 THEN '強風(5-6m)'
        ELSE '暴風(7m以上)'
    END as wind_condition,
    COUNT(*) as race_count,
    ROUND(AVG(CASE WHEN res.finish_order = 1 THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
FROM races r
JOIN entries e ON r.id = e.race_id
LEFT JOIN race_conditions rc ON r.id = rc.race_id
JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
WHERE r.race_date >= '2020-01-01'
GROUP BY e.pit_number, 2
ORDER BY e.pit_number, 2;
```

---

## 🎰 5. オッズ分析クエリ

### 8-1. レースの全3連単オッズ（人気順）

```sql
SELECT
    t.combination,
    t.odds,
    ROW_NUMBER() OVER (ORDER BY t.odds ASC) as popularity
FROM trifecta_odds t
WHERE t.race_id = 123456
ORDER BY t.odds ASC
LIMIT 20;
```

---

### 8-2. 予測買い目のオッズ取得

```sql
SELECT
    r.venue_code,
    r.race_number,
    rp.predicted_rank_1 || '-' || rp.predicted_rank_2 || '-' || rp.predicted_rank_3 as combination,
    t.odds,
    rp.confidence_level,
    rp.expected_return
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
LEFT JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp.predicted_rank_1 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_2 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_3 AS TEXT)
WHERE r.race_date = DATE('now', 'localtime')
  AND rp.is_target = 1;
```

---

### 7-3. オッズ帯別の的中率

```sql
SELECT
    CASE
        WHEN t.odds < 10 THEN '10倍未満'
        WHEN t.odds < 30 THEN '10-30倍'
        WHEN t.odds < 50 THEN '30-50倍'
        WHEN t.odds < 100 THEN '50-100倍'
        ELSE '100倍以上'
    END as odds_range,
    COUNT(*) as race_count,
    SUM(CASE
        WHEN rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1 ELSE 0
    END) as correct_count,
    ROUND(AVG(CASE
        WHEN rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1.0 ELSE 0.0
    END) * 100, 2) as hit_rate
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp.predicted_rank_1 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_2 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_3 AS TEXT)
LEFT JOIN results res1 ON r.id = res1.race_id AND res1.finish_order = 1
LEFT JOIN results res2 ON r.id = res2.race_id AND res2.finish_order = 2
LEFT JOIN results res3 ON r.id = res3.race_id AND res3.finish_order = 3
WHERE r.race_date >= DATE('now', '-1 year')
  AND rp.is_target = 1
GROUP BY 1
ORDER BY MIN(t.odds);
```

---

## 🏆 6. パフォーマンス分析クエリ

### 8-1. 年度別パフォーマンス

```sql
SELECT
    SUBSTR(r.race_date, 1, 4) as year,
    COUNT(*) as total_races,
    SUM(CASE WHEN rp.is_target = 1 THEN 1 ELSE 0 END) as target_count,
    SUM(CASE
        WHEN rp.is_target = 1
         AND rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1 ELSE 0
    END) as correct_count,
    ROUND(AVG(CASE
        WHEN rp.is_target = 1
         AND rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1.0 ELSE 0.0
    END) * 100, 2) as hit_rate,
    SUM(CASE WHEN rp.is_target = 1 THEN p.payout_amount ELSE 0 END) as total_payout,
    SUM(CASE WHEN rp.is_target = 1 THEN 100 ELSE 0 END) as total_bet,
    ROUND(SUM(CASE WHEN rp.is_target = 1 THEN p.payout_amount ELSE 0 END) * 100.0 /
          NULLIF(SUM(CASE WHEN rp.is_target = 1 THEN 100 ELSE 0 END), 0), 2) as roi
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
LEFT JOIN results res1 ON r.id = res1.race_id AND res1.finish_order = 1
LEFT JOIN results res2 ON r.id = res2.race_id AND res2.finish_order = 2
LEFT JOIN results res3 ON r.id = res3.race_id AND res3.finish_order = 3
LEFT JOIN payouts p ON r.id = p.race_id AND p.betting_type = '3連単'
GROUP BY 1
ORDER BY 1 DESC;
```

---

### 8-2. 会場別パフォーマンス（直近1年）

```sql
SELECT
    r.venue_code,
    v.name as venue_name,
    COUNT(*) as target_count,
    SUM(CASE
        WHEN rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1 ELSE 0
    END) as correct_count,
    ROUND(AVG(CASE
        WHEN rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1.0 ELSE 0.0
    END) * 100, 2) as hit_rate,
    SUM(p.payout_amount) as total_payout,
    COUNT(*) * 100 as total_bet,
    ROUND(SUM(p.payout_amount) * 100.0 / (COUNT(*) * 100), 2) as roi
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
JOIN venues v ON r.venue_code = v.code
LEFT JOIN results res1 ON r.id = res1.race_id AND res1.finish_order = 1
LEFT JOIN results res2 ON r.id = res2.race_id AND res2.finish_order = 2
LEFT JOIN results res3 ON r.id = res3.race_id AND res3.finish_order = 3
LEFT JOIN payouts p ON r.id = p.race_id AND p.betting_type = '3連単'
WHERE r.race_date >= DATE('now', '-1 year')
  AND rp.is_target = 1
GROUP BY r.venue_code, v.name
ORDER BY roi DESC;
```

---

### 7-3. 信頼度別パフォーマンス（全期間）

```sql
SELECT
    rp.confidence_level,
    COUNT(*) as race_count,
    SUM(CASE
        WHEN rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1 ELSE 0
    END) as correct_count,
    ROUND(AVG(CASE
        WHEN rp.predicted_rank_1 = res1.pit_number
         AND rp.predicted_rank_2 = res2.pit_number
         AND rp.predicted_rank_3 = res3.pit_number
        THEN 1.0 ELSE 0.0
    END) * 100, 2) as hit_rate,
    ROUND(AVG(t.odds), 2) as avg_odds,
    SUM(p.payout_amount) as total_payout,
    COUNT(*) * 100 as total_bet,
    ROUND(SUM(p.payout_amount) * 100.0 / (COUNT(*) * 100), 2) as roi
FROM races r
JOIN race_predictions rp ON r.id = rp.race_id
JOIN trifecta_odds t ON r.id = t.race_id
    AND t.combination = CAST(rp.predicted_rank_1 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_2 AS TEXT) || '-'
                     || CAST(rp.predicted_rank_3 AS TEXT)
LEFT JOIN results res1 ON r.id = res1.race_id AND res1.finish_order = 1
LEFT JOIN results res2 ON r.id = res2.race_id AND res2.finish_order = 2
LEFT JOIN results res3 ON r.id = res3.race_id AND res3.finish_order = 3
LEFT JOIN payouts p ON r.id = p.race_id AND p.betting_type = '3連単'
WHERE rp.is_target = 1
GROUP BY rp.confidence_level
ORDER BY rp.confidence_level;
```

---

## 🔍 7. データ品質チェッククエリ

### 8-1. オリジナル展示データのカバー率

```sql
SELECT
    SUBSTR(r.race_date, 1, 7) as year_month,
    COUNT(DISTINCT r.id) as total_races,
    COUNT(DISTINCT ed.race_id) as has_tenji,
    ROUND(COUNT(DISTINCT ed.race_id) * 100.0 / COUNT(DISTINCT r.id), 2) as coverage_rate
FROM races r
LEFT JOIN exhibition_data ed ON r.id = ed.race_id
WHERE r.race_date >= '2025-01-01'
GROUP BY year_month
ORDER BY year_month DESC;
```

---

### 8-2. オッズデータの欠損チェック

```sql
SELECT
    r.race_date,
    r.venue_code,
    COUNT(DISTINCT r.id) as total_races,
    COUNT(DISTINCT t.race_id) as has_odds,
    COUNT(DISTINCT r.id) - COUNT(DISTINCT t.race_id) as missing_odds
FROM races r
LEFT JOIN trifecta_odds t ON r.id = t.race_id
WHERE r.race_date >= '2025-01-01'
GROUP BY r.race_date, r.venue_code
HAVING missing_odds > 0
ORDER BY r.race_date DESC;
```

---

### 7-3. モーター2連対率の活用状況

```sql
SELECT
    COUNT(*) as total_entries,
    SUM(CASE WHEN motor_second_rate IS NOT NULL THEN 1 ELSE 0 END) as has_motor_second_rate,
    ROUND(AVG(CASE WHEN motor_second_rate IS NOT NULL THEN 1.0 ELSE 0.0 END) * 100, 2) as coverage_rate
FROM entries
WHERE race_id IN (
    SELECT id FROM races WHERE race_date >= DATE('now', '-1 month')
);
```

---

## 💡 8. 高度な分析クエリ

### 8-1. 直近10走の成績トレンド

```sql
WITH recent_races AS (
    SELECT
        e.racer_id,
        r.race_date,
        res.finish_order,
        ROW_NUMBER() OVER (PARTITION BY e.racer_id ORDER BY r.race_date DESC) as race_no
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE e.racer_id = 1234
)
SELECT
    racer_id,
    COUNT(*) as recent_10_races,
    SUM(CASE WHEN finish_order = 1 THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN finish_order <= 2 THEN 1 ELSE 0 END) as place_2,
    SUM(CASE WHEN finish_order <= 3 THEN 1 ELSE 0 END) as place_3,
    ROUND(AVG(finish_order), 2) as avg_finish
FROM recent_races
WHERE race_no <= 10
GROUP BY racer_id;
```

---

### 8-2. モーター成績×選手成績の相関

```sql
SELECT
    CASE
        WHEN ms.two_rate >= 40 THEN '優秀モーター(40%+)'
        WHEN ms.two_rate >= 30 THEN '標準モーター(30-40%)'
        ELSE '低成績モーター(30%未満)'
    END as motor_grade,
    CASE
        WHEN rf.nationwide_win_rate >= 7.0 THEN 'A1級'
        WHEN rf.nationwide_win_rate >= 5.5 THEN 'A2級'
        WHEN rf.nationwide_win_rate >= 4.5 THEN 'B1級'
        ELSE 'B2級'
    END as racer_grade,
    COUNT(*) as race_count,
    ROUND(AVG(CASE WHEN res.finish_order = 1 THEN 1.0 ELSE 0.0 END) * 100, 2) as win_rate
FROM entries e
JOIN races r ON e.race_id = r.id
JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
LEFT JOIN motor_stats ms ON e.motor_number = ms.motor_number
    AND r.venue_code = ms.venue_code
    AND SUBSTR(r.race_date, 1, 4) = ms.year
LEFT JOIN racer_features rf ON e.racer_id = rf.racer_id
WHERE r.race_date >= DATE('now', '-1 year')
  AND ms.two_rate IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2;
```

---

## 🛠️ 9. 便利な汎用クエリ

### テーブル情報取得

```sql
-- テーブル構造確認
PRAGMA table_info(races);

-- レコード数確認
SELECT COUNT(*) FROM races;

-- 最新データの日付確認
SELECT MAX(race_date) FROM races;

-- データ期間確認
SELECT MIN(race_date), MAX(race_date) FROM races;
```

---

## ⚠️ 10. よくある間違いと注意事項

### 10-1. データの場所を間違える

**❌ 間違い**: 展示タイムは`exhibition_data`にある
```sql
-- これは Boatersサイト独自データ（前日分のみ、2023年11月以降）
SELECT chikusen_time FROM exhibition_data WHERE race_id = 123456;
```

**✅ 正しい**: 展示タイムは`race_details`にある
```sql
-- これは公式データ（2020年以降取得可能、補完可能）
SELECT chikusen_time FROM race_details WHERE race_id = 123456;
```

---

### 10-2. カラム名を間違える

**❌ 間違い**: `date`, `waku`
```sql
SELECT * FROM races WHERE date = '2026-01-26';  -- エラー
SELECT * FROM entries WHERE waku = 1;            -- エラー
```

**✅ 正しい**: `race_date`, `pit_number`
```sql
SELECT * FROM races WHERE race_date = '2026-01-26';
SELECT * FROM entries WHERE pit_number = 1;
```

---

### 10-3. 波高データの対象会場を間違える

**❌ 間違い**: 全24場で波高データがある
```sql
-- 淡水面の会場（桐生、戸田など）では wave_height は NULL
SELECT * FROM race_conditions WHERE wave_height IS NOT NULL;
```

**✅ 正しい**: 海水面9場のみ波高データあり
```sql
-- 江戸川、平和島、多摩川、津、住之江、芦屋、福岡、唐津、大村のみ
SELECT * FROM race_conditions
WHERE race_id IN (SELECT id FROM races WHERE venue_code IN (3,4,5,9,13,21,22,23,24))
  AND wave_height IS NOT NULL;
```

---

### 10-4. オッズJOINで予測順位を間違える

**❌ 間違い**: 固定で'1-2-3'を指定
```sql
-- これは常に1号艇-2号艇-3号艇のオッズになってしまう
SELECT t.odds FROM trifecta_odds t WHERE t.combination = '1-2-3';
```

**✅ 正しい**: 予測順位に基づく動的な組み合わせ
```sql
SELECT t.odds FROM trifecta_odds t
WHERE t.combination = CAST(rp.predicted_rank_1 AS TEXT) || '-'
                   || CAST(rp.predicted_rank_2 AS TEXT) || '-'
                   || CAST(rp.predicted_rank_3 AS TEXT);
```

---

### 10-5. データ補完の可否を間違える

| データ種別 | テーブル | 補完可否 | 補完方法 |
|-----------|---------|---------|---------|
| 展示タイム（公式） | race_details | ✅ 可能 | `補完_レース詳細データ_改善版v4.py` |
| 波高 | race_conditions | ✅ 可能 | race_conditions収集スクリプト |
| オリジナル展示 | exhibition_data | ❌ 不可 | 前日分のみ（毎日自動収集必須） |

---

**最終更新**: 2026-01-26
**作成者**: Claude Sonnet 4.5
