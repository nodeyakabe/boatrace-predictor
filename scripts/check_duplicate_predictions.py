#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測データの重複・異常チェック
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
db_path = ROOT / "data" / "boatrace.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 80)
print("予測データ重複・異常チェック")
print("=" * 80)
print()

# 1. 総数とユニーク数
cursor.execute("""
    SELECT COUNT(*), COUNT(DISTINCT race_id)
    FROM race_predictions
    WHERE prediction_type = 'advance'
      AND race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')
""")
total, distinct_races = cursor.fetchone()

print(f"総予測データ数: {total:,}件")
print(f"ユニークなレース数: {distinct_races:,}件")
print(f"1レースあたり平均: {total/distinct_races:.1f}件（正常値: 6.0件）")
print()

# 2. 6件以外のレースをチェック
cursor.execute("""
    SELECT race_id, COUNT(*) as cnt
    FROM race_predictions
    WHERE prediction_type = 'advance'
      AND race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')
    GROUP BY race_id
    HAVING cnt <> 6
    LIMIT 20
""")

problem_races = cursor.fetchall()

if problem_races:
    print("【異常】6件以外のレース:")
    for race_id, cnt in problem_races:
        print(f"  race_id={race_id}: {cnt}件")
    print(f"\n異常レース数: {len(problem_races)}件")
else:
    print("OK: 全レースが正しく6件の予測を持っています")

print()

# 3. 1位的中率の詳細チェック
cursor.execute("""
    SELECT
        rp.race_id,
        r.race_date,
        rp.pit_number as predicted_pit,
        (SELECT pit_number FROM results WHERE race_id = rp.race_id AND rank = 1 AND is_invalid = 0) as actual_pit
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE rp.prediction_type = 'advance'
      AND rp.rank_prediction = 1
      AND r.race_date = '2020-01-01'
    LIMIT 10
""")

print("【検証】2020-01-01の1位予測vs実際の1着")
print(f"{'race_id':<10} {'予測':<6} {'実際':<6} {'的中':<6}")
print("-" * 80)

hit = 0
total_check = 0

for race_id, date, predicted, actual in cursor.fetchall():
    total_check += 1
    is_hit = (predicted == actual)
    if is_hit:
        hit += 1
    print(f"{race_id:<10} 艇{predicted:<4} 艇{actual if actual else '?':<4} {'○' if is_hit else '×':<6}")

print()
print(f"サンプル的中率: {hit}/{total_check} = {hit/total_check*100:.1f}%" if total_check > 0 else "データなし")

conn.close()

print()
print("=" * 80)
