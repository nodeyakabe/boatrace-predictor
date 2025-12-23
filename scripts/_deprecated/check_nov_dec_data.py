#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
11月・12月のデータ正常性確認スクリプト
"""
import sqlite3
from datetime import datetime

db_path = 'data/boatrace.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 80)
print("2025年 月別データ収集状況")
print("=" * 80)

query = """
SELECT
  strftime('%Y-%m', race_date) as month,
  COUNT(DISTINCT r.id) as total_races,
  COUNT(DISTINCT CASE WHEN rp.id IS NOT NULL THEN r.id END) as races_with_prediction,
  COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN r.id END) as races_with_odds,
  COUNT(DISTINCT CASE WHEN res.id IS NOT NULL THEN r.id END) as races_with_results
FROM races r
LEFT JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
LEFT JOIN trifecta_odds o ON r.id = o.race_id
LEFT JOIN results res ON r.id = res.race_id
WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
GROUP BY strftime('%Y-%m', race_date)
ORDER BY month
"""

cursor.execute(query)
rows = cursor.fetchall()

print(f"{'月':<10} {'総レース数':>12} {'予測あり':>12} {'オッズあり':>12} {'結果あり':>12}")
print("-" * 80)
for row in rows:
    month, total, pred, odds, results = row
    print(f"{month:<10} {total:>12,} {pred:>12,} {odds:>12,} {results:>12,}")

print("\n" + "=" * 80)
print("11月・12月の詳細（日別）")
print("=" * 80)

query2 = """
SELECT
  race_date,
  COUNT(DISTINCT r.id) as races,
  COUNT(DISTINCT CASE WHEN rp.id IS NOT NULL THEN r.id END) as with_pred,
  COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN r.id END) as with_odds,
  COUNT(DISTINCT CASE WHEN res.id IS NOT NULL THEN r.id END) as with_results
FROM races r
LEFT JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
LEFT JOIN trifecta_odds o ON r.id = o.race_id
LEFT JOIN results res ON r.id = res.race_id
WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-12-31'
GROUP BY race_date
ORDER BY race_date
"""

cursor.execute(query2)
rows2 = cursor.fetchall()

print(f"{'日付':<12} {'レース数':>10} {'予測':>8} {'オッズ':>8} {'結果':>8}")
print("-" * 80)
for row in rows2:
    date, races, pred, odds, results = row
    print(f"{date:<12} {races:>10} {pred:>8} {odds:>8} {results:>8}")

print("\n" + "=" * 80)
print("11月のサンプルレース確認（信頼度C/Dのみ）")
print("=" * 80)

query3 = """
SELECT
  r.race_date,
  r.venue_code,
  r.race_number,
  r.id as race_id,
  rp.confidence,
  rp.racer_name,
  rp.total_score,
  res.rank,
  res.pit_number as result_pit
FROM races r
INNER JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
INNER JOIN results res ON r.id = res.race_id AND res.rank = '1'
WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-11-30'
  AND rp.pit_number = 1
  AND rp.confidence IN ('C', 'D')
ORDER BY r.race_date, r.venue_code, r.race_number
LIMIT 20
"""

cursor.execute(query3)
rows3 = cursor.fetchall()

print(f"{'日付':<12} {'会場':>4} {'R':>3} {'信頼度':>6} {'選手名':<12} {'スコア':>8} {'1着艇':>6}")
print("-" * 80)
for row in rows3:
    date, venue, race_num, race_id, conf, racer, score, rank, result_pit = row
    print(f"{date:<12} {venue:>4} {race_num:>3}R {conf:>6} {racer:<12} {score:>8.2f} {result_pit:>6}号艇")

print("\n" + "=" * 80)
print("11月の信頼度別レース数（1号艇予測のみ）")
print("=" * 80)

query4 = """
SELECT
  rp.confidence,
  COUNT(*) as race_count,
  COUNT(CASE WHEN res.rank = '1' AND res.pit_number = 1 THEN 1 END) as wins
FROM races r
INNER JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
INNER JOIN results res ON r.id = res.race_id
WHERE r.race_date >= '2025-11-01' AND r.race_date <= '2025-11-30'
  AND rp.pit_number = 1
  AND res.pit_number = 1
GROUP BY rp.confidence
ORDER BY rp.confidence
"""

cursor.execute(query4)
rows4 = cursor.fetchall()

print(f"{'信頼度':>6} {'レース数':>10} {'1号艇1着':>12} {'的中率':>10}")
print("-" * 80)
for row in rows4:
    conf, count, wins = row
    rate = wins / count * 100 if count > 0 else 0
    print(f"{conf:>6} {count:>10} {wins:>12} {rate:>9.2f}%")

conn.close()

print("\n" + "=" * 80)
print("確認完了")
print("=" * 80)
