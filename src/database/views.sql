-- 階層的確率モデル用 DBビュー定義
-- Phase 1: 相対特徴量計算のためのビュー

-- 1. 選手直近成績ビュー（直近5走の統計）
DROP VIEW IF EXISTS racer_recent_stats;
CREATE VIEW racer_recent_stats AS
WITH recent_races AS (
    SELECT
        e.racer_number,
        r.race_date,
        CAST(res.rank AS INTEGER) as rank,
        rd.start_timing as st_time,
        ROW_NUMBER() OVER (
            PARTITION BY e.racer_number
            ORDER BY r.race_date DESC, r.race_number DESC
        ) as race_order
    FROM entries e
    JOIN races r ON e.race_id = r.id
    JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE res.rank IN ('1', '2', '3', '4', '5', '6')
)
SELECT
    racer_number,
    COUNT(*) as recent_race_count,
    AVG(rank) as recent_avg_rank,
    SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as recent_win_rate,
    SUM(CASE WHEN rank <= 2 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as recent_place2_rate,
    SUM(CASE WHEN rank <= 3 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as recent_place3_rate,
    AVG(st_time) as recent_avg_st,
    -- 標準偏差（STの安定性）
    CASE
        WHEN COUNT(*) > 1 THEN
            SQRT(SUM((st_time - (SELECT AVG(st_time) FROM recent_races rr WHERE rr.racer_number = recent_races.racer_number AND rr.race_order <= 5)) *
                     (st_time - (SELECT AVG(st_time) FROM recent_races rr WHERE rr.racer_number = recent_races.racer_number AND rr.race_order <= 5))) / COUNT(*))
        ELSE 0
    END as recent_st_std
FROM recent_races
WHERE race_order <= 5
GROUP BY racer_number;

-- 2. レース内展示タイム相対評価ビュー
DROP VIEW IF EXISTS exhibition_relative;
CREATE VIEW exhibition_relative AS
SELECT
    rd.race_id,
    rd.pit_number,
    rd.exhibition_time,
    -- レース内順位（1が最速）
    RANK() OVER (PARTITION BY rd.race_id ORDER BY rd.exhibition_time ASC) as exh_rank,
    -- レース平均との差分
    rd.exhibition_time - AVG(rd.exhibition_time) OVER (PARTITION BY rd.race_id) as exh_diff,
    -- レース最速との差
    rd.exhibition_time - MIN(rd.exhibition_time) OVER (PARTITION BY rd.race_id) as exh_gap_to_best,
    -- レース内相対位置（0=最速、1=最遅）
    CASE
        WHEN MAX(rd.exhibition_time) OVER (PARTITION BY rd.race_id) = MIN(rd.exhibition_time) OVER (PARTITION BY rd.race_id)
        THEN 0.5
        ELSE (rd.exhibition_time - MIN(rd.exhibition_time) OVER (PARTITION BY rd.race_id)) * 1.0 /
             (MAX(rd.exhibition_time) OVER (PARTITION BY rd.race_id) - MIN(rd.exhibition_time) OVER (PARTITION BY rd.race_id))
    END as exh_relative_position
FROM race_details rd
WHERE rd.exhibition_time IS NOT NULL AND rd.exhibition_time > 0;

-- 3. 会場別選手成績ビュー
DROP VIEW IF EXISTS racer_venue_stats;
CREATE VIEW racer_venue_stats AS
SELECT
    e.racer_number,
    r.venue_code,
    COUNT(*) as venue_race_count,
    AVG(CAST(res.rank AS FLOAT)) as venue_avg_rank,
    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as venue_win_rate,
    SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as venue_place2_rate,
    SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as venue_place3_rate
FROM entries e
JOIN races r ON e.race_id = r.id
JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
WHERE res.rank IN ('1', '2', '3', '4', '5', '6')
GROUP BY e.racer_number, r.venue_code;

-- 4. 条件付き着順学習用ベースビュー
DROP VIEW IF EXISTS race_entries_with_results;
CREATE VIEW race_entries_with_results AS
SELECT
    r.id as race_id,
    r.race_date,
    r.venue_code,
    r.race_number,
    e.pit_number,
    e.racer_number,
    e.win_rate,
    e.second_rate,
    e.motor_second_rate,
    e.boat_second_rate,
    e.motor_number,
    e.boat_number,
    rd.exhibition_time,
    rd.start_timing as avg_st,
    COALESCE(rd.actual_course, e.pit_number) as actual_course,
    CAST(res.rank AS INTEGER) as rank
FROM races r
JOIN entries e ON r.id = e.race_id
JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
WHERE res.rank IN ('1', '2', '3', '4', '5', '6');

-- 5. Stage2学習用（1着確定後の2着予測）
DROP VIEW IF EXISTS stage2_training_view;
CREATE VIEW stage2_training_view AS
SELECT
    base.*,
    winner.pit_number as winner_pit,
    winner.win_rate as winner_win_rate,
    winner.exhibition_time as winner_exhibition_time,
    winner.avg_st as winner_avg_st,
    winner.actual_course as winner_course,
    CASE WHEN base.rank = 2 THEN 1 ELSE 0 END as is_second
FROM race_entries_with_results base
JOIN race_entries_with_results winner
    ON base.race_id = winner.race_id AND winner.rank = 1
WHERE base.rank != 1;  -- 1着艇を除外

-- 6. Stage3学習用（1着・2着確定後の3着予測）
DROP VIEW IF EXISTS stage3_training_view;
CREATE VIEW stage3_training_view AS
SELECT
    base.*,
    winner.pit_number as winner_pit,
    winner.win_rate as winner_win_rate,
    winner.exhibition_time as winner_exhibition_time,
    winner.actual_course as winner_course,
    second.pit_number as second_pit,
    second.win_rate as second_win_rate,
    second.exhibition_time as second_exhibition_time,
    second.actual_course as second_course,
    CASE WHEN base.rank = 3 THEN 1 ELSE 0 END as is_third
FROM race_entries_with_results base
JOIN race_entries_with_results winner
    ON base.race_id = winner.race_id AND winner.rank = 1
JOIN race_entries_with_results second
    ON base.race_id = second.race_id AND second.rank = 2
WHERE base.rank NOT IN (1, 2);  -- 1着・2着艇を除外

-- 7. モーター・ボート会場別成績ビュー
DROP VIEW IF EXISTS equipment_venue_stats;
CREATE VIEW equipment_venue_stats AS
SELECT
    r.venue_code,
    e.motor_number,
    e.boat_number,
    COUNT(*) as race_count,
    AVG(CAST(res.rank AS FLOAT)) as avg_rank,
    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate,
    SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as place2_rate
FROM entries e
JOIN races r ON e.race_id = r.id
JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
WHERE res.rank IN ('1', '2', '3', '4', '5', '6')
  AND e.motor_number IS NOT NULL
  AND e.boat_number IS NOT NULL
GROUP BY r.venue_code, e.motor_number, e.boat_number;
