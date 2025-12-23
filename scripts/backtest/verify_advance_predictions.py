#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020-2023年 advance予測の品質検証スクリプト
"""
import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
db_path = ROOT / "data" / "boatrace.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 100)
print("2020-2023年 advance予測データ品質検証")
print("=" * 100)
print()

# 1. 2020-01-01のサンプルデータを確認
print("【検証1】2020-01-01の予測データサンプル（最初の3レース）")
print("-" * 100)

cursor.execute("""
    SELECT
        rp.race_id, r.race_date, r.venue_code, r.race_number,
        rp.pit_number, rp.rank_prediction, rp.total_score, rp.confidence,
        rp.racer_name, rp.course_score, rp.racer_score, rp.motor_score,
        rp.prediction_type
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE rp.prediction_type = 'advance'
      AND r.race_date = '2020-01-01'
    ORDER BY rp.race_id, rp.rank_prediction
    LIMIT 18
""")

rows = cursor.fetchall()
prev_race = None
race_count = 0

for row in rows:
    race_id, date, venue, rnum, pit, rank, score, conf, name, c_score, r_score, m_score, pred_type = row

    if race_id != prev_race:
        race_count += 1
        if race_count > 3:
            break
        print(f"\n[{date} 会場{int(venue):02d} R{rnum:2d}] race_id={race_id}")
        prev_race = race_id

    print(f"  {rank}位予測: 艇{pit} {name:8s} (信頼度{conf}, スコア{score:5.1f}pt = "
          f"コース{c_score:4.1f} + 選手{r_score:4.1f} + モーター{m_score:4.1f})")

print()
print("-" * 100)
print()

# 2. スコアの統計を確認（ゼロ値チェック）
print("【検証2】スコア統計（ゼロ値や異常値のチェック）")
print("-" * 100)

cursor.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN total_score = 0 THEN 1 END) as zero_total,
        COUNT(CASE WHEN course_score = 0 THEN 1 END) as zero_course,
        COUNT(CASE WHEN racer_score = 0 THEN 1 END) as zero_racer,
        COUNT(CASE WHEN motor_score = 0 THEN 1 END) as zero_motor,
        AVG(total_score) as avg_total,
        AVG(course_score) as avg_course,
        AVG(racer_score) as avg_racer,
        AVG(motor_score) as avg_motor,
        MIN(total_score) as min_total,
        MAX(total_score) as max_total
    FROM race_predictions
    WHERE prediction_type = 'advance'
      AND race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')
""")

stats = cursor.fetchone()
total, zero_total, zero_course, zero_racer, zero_motor, avg_total, avg_course, avg_racer, avg_motor, min_total, max_total = stats

print(f"総予測数: {total:,}件")
print()
print(f"ゼロ値チェック:")
print(f"  total_score = 0: {zero_total}件 ({zero_total/total*100:.2f}%)")
print(f"  course_score = 0: {zero_course}件 ({zero_course/total*100:.2f}%)")
print(f"  racer_score = 0: {zero_racer}件 ({zero_racer/total*100:.2f}%)")
print(f"  motor_score = 0: {zero_motor}件 ({zero_motor/total*100:.2f}%)")
print()
print(f"スコア統計:")
print(f"  平均 total_score: {avg_total:.1f}pt")
print(f"  平均 course_score: {avg_course:.1f}pt")
print(f"  平均 racer_score: {avg_racer:.1f}pt")
print(f"  平均 motor_score: {avg_motor:.1f}pt")
print(f"  スコア範囲: {min_total:.1f}pt 〜 {max_total:.1f}pt")

print()
print("-" * 100)
print()

# 3. 信頼度分布を確認
print("【検証3】信頼度分布")
print("-" * 100)

cursor.execute("""
    SELECT
        confidence,
        COUNT(DISTINCT race_id) as race_count,
        COUNT(*) as prediction_count
    FROM race_predictions
    WHERE prediction_type = 'advance'
      AND race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')
      AND rank_prediction = 1
    GROUP BY confidence
    ORDER BY confidence
""")

print(f"{'信頼度':<10} {'レース数':<15} {'割合':<10}")
total_races = 7710
for conf, race_count, pred_count in cursor.fetchall():
    print(f"{conf:<10} {race_count:>10,}件 {race_count/total_races*100:>7.1f}%")

print()
print("-" * 100)
print()

# 4. 実際の結果と照合（1位予測的中率）
print("【検証4】1位予測的中率（サンプル確認）")
print("-" * 100)

cursor.execute("""
    SELECT
        COUNT(DISTINCT rp.race_id) as total_races,
        COUNT(DISTINCT CASE
            WHEN rp.pit_number = (
                SELECT pit_number FROM results
                WHERE race_id = rp.race_id AND rank = 1 AND is_invalid = 0
            ) THEN rp.race_id
        END) as hit_races
    FROM race_predictions rp
    WHERE rp.prediction_type = 'advance'
      AND rp.rank_prediction = 1
      AND rp.race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')
""")

total_races, hit_races = cursor.fetchone()
hit_rate = hit_races / total_races * 100 if total_races > 0 else 0

print(f"対象レース数: {total_races:,}件")
print(f"1位的中: {hit_races:,}件")
print(f"1位的中率: {hit_rate:.1f}%")
print()
print("※ 参考: 2025年データの1位的中率は約20-25%")
print("※ 2020-2023年は直前情報なしのため、15-20%程度が妥当")

print()
print("-" * 100)
print()

# 5. 年別の生成状況
print("【検証5】年別生成状況")
print("-" * 100)

cursor.execute("""
    SELECT
        SUBSTR(r.race_date, 1, 4) as year,
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT rp.race_id) as predicted_races,
        COUNT(*) as prediction_count
    FROM races r
    LEFT JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'advance'
    WHERE r.race_date >= '2020-01-01' AND r.race_date < '2024-01-01'
    GROUP BY year
    ORDER BY year
""")

print(f"{'年':<8} {'全レース':<12} {'予測済み':<12} {'カバー率':<10} {'予測データ':<12}")
for year, total, predicted, pred_count in cursor.fetchall():
    coverage = predicted / total * 100 if total > 0 else 0
    print(f"{year:<8} {total:>10,}件 {predicted:>10,}件 {coverage:>7.1f}% {pred_count:>10,}件")

conn.close()

print()
print("=" * 100)
print("検証完了")
print("=" * 100)
