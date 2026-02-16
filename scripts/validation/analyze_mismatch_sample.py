#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tier 2とTier 3の不一致サンプル調査（高速版）

目的: 不一致の原因パターンを特定
"""
import sqlite3
import sys
import os
from typing import Dict, List
from collections import defaultdict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.betting.evaluator_helpers import create_custom_evaluator
from src.betting.bet_target_evaluator import BetStatus
from config.bet_conditions import STANDARD_BET_CONDITIONS

def check_tier2_sql_logic(race_id: str) -> Dict:
    """Tier 2のSQL条件で購入対象になっているか詳細確認"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 基本情報
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number,
               rp.confidence,
               e1.racer_rank as c1_rank, e1.second_rate as c1_second_rate,
               e1.motor_second_rate,
               rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
               rp4.pit_number as p4, rp5.pit_number as p5
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        LEFT JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        LEFT JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE r.id = ?
    """, (race_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    # オッズ取得（パターンH 3点分）
    combos = [
        f"{row['p1']}-{row['p2']}-{row['p3']}",
    ]
    if row['p4']:
        combos.append(f"{row['p1']}-{row['p2']}-{row['p4']}")
    if row['p5']:
        combos.append(f"{row['p1']}-{row['p2']}-{row['p5']}")

    placeholders = ','.join(['?'] * len(combos))
    cursor.execute(f"""
        SELECT combination, odds
        FROM trifecta_odds
        WHERE race_id = ? AND combination IN ({placeholders})
    """, (race_id, *combos))

    odds_data = {r['combination']: r['odds'] for r in cursor.fetchall()}

    # 逃げ率取得
    cursor.execute("""
        SELECT pes.escape_rate
        FROM entries e
        JOIN player_escape_stats pes ON e.racer_number = pes.player_id AND pes.stadium_id IS NULL
        WHERE e.race_id = ? AND e.pit_number = ?
    """, (race_id, row['p1']))
    escape_row = cursor.fetchone()
    escape_rate = escape_row['escape_rate'] if escape_row else None

    # バイアス指数取得
    cursor.execute("""
        SELECT pbs.bias_index
        FROM entries e
        JOIN player_bias_stats pbs ON e.racer_number = pbs.player_id AND pbs.stadium_id IS NULL
        WHERE e.race_id = ? AND e.pit_number = ?
    """, (race_id, row['p1']))
    bias_row = cursor.fetchone()
    bias_index = bias_row['bias_index'] if bias_row else None

    conn.close()

    return {
        'race_id': race_id,
        'venue_code': int(row['venue_code']),
        'race_date': row['race_date'],
        'race_number': row['race_number'],
        'confidence': row['confidence'],
        'c1_rank': row['c1_rank'],
        'c1_second_rate': row['c1_second_rate'],
        'motor_second_rate': row['motor_second_rate'],
        'p1': row['p1'],
        'p2': row['p2'],
        'p3': row['p3'],
        'p4': row['p4'],
        'p5': row['p5'],
        'odds_data': odds_data,
        'escape_rate': escape_rate,
        'bias_index': bias_index,
    }


def check_tier3_evaluator(race_info: Dict) -> Dict:
    """Tier 3のBetTargetEvaluatorで判定"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=False,
        db_path=DATABASE_PATH
    )

    # レースデータ構築
    cursor.execute("""
        SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
        FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_info['race_id'],))
    entries = [dict(row) for row in cursor.fetchall()]

    race_data = {
        'id': race_info['race_id'],
        'venue_code': f"{race_info['venue_code']:02d}",
        'race_number': race_info['race_number'],
        'race_date': race_info['race_date'],
        'wind_speed': 0.0,
        'entries': entries
    }

    # 予測データ構築
    old_pred = [race_info['p1'], race_info['p2'], race_info['p3']]
    if race_info['p4']:
        old_pred.append(race_info['p4'])
    if race_info['p5']:
        old_pred.append(race_info['p5'])

    cursor.execute("""
        SELECT racer_number FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before' AND rank_prediction = 1
    """, (race_info['race_id'],))
    first_racer_row = cursor.fetchone()
    first_racer_number = first_racer_row['racer_number'] if first_racer_row else None

    predictions = {
        'confidence': race_info['confidence'],
        'old_prediction': old_pred,
        'new_prediction': old_pred,
        'first_racer_number': first_racer_number
    }

    conn.close()

    # 購入判定
    try:
        bet_target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions,
            odds_data=race_info['odds_data'],
            has_beforeinfo=True
        )

        return {
            'status': bet_target.status,
            'reason': bet_target.reason,
            'is_purchase': bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]
        }
    except Exception as e:
        return {
            'status': 'ERROR',
            'reason': str(e),
            'is_purchase': False
        }


def analyze_sample_mismatches():
    """サンプル不一致レースを調査"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # A×A1×10-12条件でTier 2購入対象のレースを50件サンプリング
    cond = next(c for c in STANDARD_BET_CONDITIONS if c['id'] == 'A_A1_10_12')

    query = """
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND e1.racer_rank IN ('A1')
        AND r.race_date >= '2020-01-01'
        AND r.race_date < '2026-01-01'
        AND r.venue_code IN ('10', '14', '21', '18', '08', '12')
        AND rp1.pit_number = 1
        AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= 0.70
    ),
    race_with_odds AS (
        SELECT
            rb.race_id,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123
        FROM race_base rb
    )
    SELECT race_id
    FROM race_with_odds
    WHERE odds_123 >= 10 AND odds_123 < 12
    LIMIT 50
    """

    cursor.execute(query)
    tier2_sample = [row[0] for row in cursor.fetchall()]
    conn.close()

    print("=" * 80)
    print(f"A×A1×10-12条件のサンプル調査（Tier 2購入対象 {len(tier2_sample)}件）")
    print("=" * 80)

    tier2_only_count = 0
    tier3_purchase_count = 0
    mismatch_reasons = defaultdict(int)

    for i, race_id in enumerate(tier2_sample):
        race_info = check_tier2_sql_logic(race_id)
        if not race_info:
            continue

        tier3_result = check_tier3_evaluator(race_info)

        if tier3_result['is_purchase']:
            tier3_purchase_count += 1
        else:
            tier2_only_count += 1
            mismatch_reasons[tier3_result['reason']] += 1

            if i < 10:  # 最初の10件を詳細表示
                print(f"\n[不一致 {i+1}] レースID: {race_id}")
                print(f"  日付: {race_info['race_date']}, 会場: {race_info['venue_code']}, {race_info['race_number']}R")
                print(f"  信頼度: {race_info['confidence']}, 1コース級別: {race_info['c1_rank']}")
                print(f"  買い目: {race_info['p1']}-{race_info['p2']}-{race_info['p3']}")
                print(f"  オッズ: {race_info['odds_data']}")
                print(f"  逃げ率: {race_info['escape_rate']}")
                print(f"  Tier 3除外理由: {tier3_result['reason']}")

    print("\n" + "=" * 80)
    print("集計結果")
    print("=" * 80)
    print(f"Tier 2購入対象: {len(tier2_sample)}件")
    print(f"Tier 3でも購入: {tier3_purchase_count}件")
    print(f"Tier 2のみ購入: {tier2_only_count}件")
    print(f"一致率: {100*tier3_purchase_count/len(tier2_sample):.2f}%")

    print("\n除外理由の内訳:")
    for reason, count in sorted(mismatch_reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}件")


if __name__ == '__main__':
    analyze_sample_mismatches()
