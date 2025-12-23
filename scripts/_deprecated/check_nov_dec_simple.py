#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""11月・12月のデータ簡易確認"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 2025年全期間の月別レース数
print("=" * 80)
print("2025年 月別総レース数")
print("=" * 80)
cursor.execute("""
    SELECT
        substr(race_date, 1, 7) as month,
        COUNT(*) as race_count
    FROM races
    WHERE race_date >= '2025-01-01' AND race_date < '2026-01-01'
    GROUP BY substr(race_date, 1, 7)
    ORDER BY month
""")
for row in cursor.fetchall():
    print(f"{row['month']}: {row['race_count']:,}レース")

# 11月・12月の予測・オッズ・結果の有無
print("\n" + "=" * 80)
print("11月・12月のデータ詳細")
print("=" * 80)
cursor.execute("""
    SELECT
        r.race_date,
        COUNT(DISTINCT r.id) as races,
        COUNT(DISTINCT rp.race_id) as with_pred,
        COUNT(DISTINCT o.race_id) as with_odds,
        COUNT(DISTINCT res.race_id) as with_results
    FROM races r
    LEFT JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    LEFT JOIN trifecta_odds o ON r.id = o.race_id
    LEFT JOIN results res ON r.id = res.race_id
    WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-12-31'
    GROUP BY r.race_date
    ORDER BY r.race_date
""")
print(f"{'日付':<12} {'レース数':>8} {'予測':>6} {'オッズ':>6} {'結果':>6}")
print("-" * 80)
for row in cursor.fetchall():
    print(f"{row['race_date']:<12} {row['races']:>8} {row['with_pred']:>6} {row['with_odds']:>6} {row['with_results']:>6}")

# 11月の信頼度C/Dレース数
print("\n" + "=" * 80)
print("11月の信頼度C/Dレース数（1号艇予測）")
print("=" * 80)
cursor.execute("""
    SELECT
        rp.confidence,
        COUNT(DISTINCT r.id) as race_count
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-11-30'
      AND rp.pit_number = 1
      AND rp.confidence IN ('C', 'D')
    GROUP BY rp.confidence
""")
print(f"{'信頼度':>6} {'レース数':>10}")
print("-" * 80)
for row in cursor.fetchall():
    print(f"{row['confidence']:>6} {row['race_count']:>10}")

# 11月の購入対象レース（条件チェック）
print("\n" + "=" * 80)
print("11月の購入対象候補レース（信頼度C/D、オッズあり）")
print("=" * 80)
cursor.execute("""
    SELECT
        r.race_date,
        r.venue_code,
        r.race_number,
        rp.confidence,
        e.racer_rank as c1_rank,
        rp.racer_name,
        GROUP_CONCAT(CASE WHEN rp2.rank_prediction = 1 THEN rp2.pit_number END) as pred_1st,
        GROUP_CONCAT(CASE WHEN rp2.rank_prediction = 2 THEN rp2.pit_number END) as pred_2nd,
        GROUP_CONCAT(CASE WHEN rp2.rank_prediction = 3 THEN rp2.pit_number END) as pred_3rd
    FROM races r
    INNER JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.pit_number = 1
    INNER JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before'
    INNER JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
    INNER JOIN trifecta_odds o ON r.id = o.race_id
    WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-11-30'
      AND rp.confidence IN ('C', 'D')
    GROUP BY r.id, r.race_date, r.venue_code, r.race_number, rp.confidence, e.racer_rank, rp.racer_name
    ORDER BY r.race_date, r.venue_code, r.race_number
    LIMIT 30
""")
print(f"{'日付':<12} {'会場':>4} {'R':>3} {'信頼度':>6} {'1C級別':>6} {'予測':>10}")
print("-" * 80)
count = 0
for row in cursor.fetchall():
    pred = f"{row['pred_1st']}-{row['pred_2nd']}-{row['pred_3rd']}"
    print(f"{row['race_date']:<12} {row['venue_code']:>4} {row['race_number']:>3}R {row['confidence']:>6} {row['c1_rank']:>6} {pred:>10}")
    count += 1
print(f"\n計: {count}レース")

conn.close()
print("\n確認完了")
