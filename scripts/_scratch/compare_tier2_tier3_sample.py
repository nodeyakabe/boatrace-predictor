#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tier 2とTier 3の判定差異を調査"""
import sqlite3
from config.settings import DATABASE_PATH
from src.betting.evaluator_helpers import create_standard_evaluator
from src.betting.bet_target_evaluator import BetStatus

# Evaluator作成
evaluator = create_standard_evaluator()

# DB接続
conn = sqlite3.connect(DATABASE_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# サンプルレース（B×50-100条件）を取得
cursor.execute("""
    SELECT
        r.id,
        r.race_date,
        r.venue_code,
        r.race_number,
        rp.confidence,
        GROUP_CONCAT(rp.pit_number ORDER BY rp.rank_prediction) as pred_pits
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN entries e ON r.id = e.race_id AND e.pit_number = 1
    WHERE rp.confidence = 'B'
      AND e.racer_rank IN ('A1', 'B1')
      AND r.venue_code IN ('01', '02', '04', '07', '08', '09', '11', '19', '21', '22')
      AND r.race_date BETWEEN '2024-01-01' AND '2024-12-31'
    GROUP BY r.id
    HAVING COUNT(rp.pit_number) >= 5
    LIMIT 10
""")

sample_races = cursor.fetchall()

print("=" * 100)
print("Tier 2 (SQL) vs Tier 3 (BetTargetEvaluator) 判定比較")
print("=" * 100)
print()

tier2_bets = 0
tier3_bets = 0
match_count = 0

for race_row in sample_races:
    race_id = race_row['id']
    pred_pits_str = race_row['pred_pits']
    pred_pits = [int(p) for p in pred_pits_str.split(',')]

    # Tier 2のSQL判定（simplified version）
    # B×50-100条件: オッズ50-100倍、1コースA1/B1、会場フィルター
    cursor.execute("""
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ? AND combination IN (?, ?, ?)
    """, (race_id,
          f"{pred_pits[0]}-{pred_pits[1]}-{pred_pits[2]}",
          f"{pred_pits[0]}-{pred_pits[1]}-{pred_pits[3]}",
          f"{pred_pits[0]}-{pred_pits[1]}-{pred_pits[4]}"))

    odds_rows = cursor.fetchall()
    tier2_match = any(50 <= row['odds'] < 100 for row in odds_rows)

    # Tier 3の判定（BetTargetEvaluator）
    # レースデータ取得
    cursor.execute("SELECT * FROM races WHERE id = ?", (race_id,))
    race_data_row = cursor.fetchone()

    cursor.execute("SELECT wind_speed FROM race_conditions WHERE race_id = ?", (race_id,))
    cond_row = cursor.fetchone()
    wind_speed = cond_row['wind_speed'] if cond_row else 0.0

    cursor.execute("""
        SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
        FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))
    entries = [dict(row) for row in cursor.fetchall()]

    race_data = {
        'id': race_id,
        'venue_code': race_data_row['venue_code'],
        'race_number': race_data_row['race_number'],
        'race_date': race_data_row['race_date'],
        'race_time': race_data_row['race_time'],
        'wind_speed': wind_speed,
        'entries': entries
    }

    predictions = {
        'confidence': race_row['confidence'],
        'old_prediction': pred_pits,
        'new_prediction': pred_pits
    }

    odds_data = {row['combination']: row['odds'] for row in odds_rows}

    try:
        bet_target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions,
            odds_data=odds_data,
            has_beforeinfo=True
        )

        tier3_match = bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]

        if tier2_match:
            tier2_bets += 1
        if tier3_match:
            tier3_bets += 1
        if tier2_match == tier3_match:
            match_count += 1

        status = "OK" if tier2_match == tier3_match else "DIFF"
        print(f"[{status}] レースID={race_id}, 日付={race_data_row['race_date']}, 会場={race_data_row['venue_code']}")
        print(f"      Tier 2 (SQL): {'購入' if tier2_match else '対象外'}")
        print(f"      Tier 3 (Eval): {'購入' if tier3_match else '対象外'} - {bet_target.reason if tier3_match else '条件不一致'}")

        if tier2_match != tier3_match:
            print(f"      オッズ: {odds_data}")
            print(f"      予測: {pred_pits}")

        print()

    except Exception as e:
        print(f"[ERROR] レースID={race_id}: {e}")
        print()

print("=" * 100)
print(f"Tier 2購入件数: {tier2_bets}/{len(sample_races)}")
print(f"Tier 3購入件数: {tier3_bets}/{len(sample_races)}")
print(f"一致件数: {match_count}/{len(sample_races)} ({100.0 * match_count / len(sample_races):.1f}%)")
print("=" * 100)

conn.close()
