#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tier 2とTier 3の購入対象race_idを比較
"""
import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from src.betting.evaluator_helpers import create_standard_evaluator
from src.betting.bet_target_evaluator import BetStatus


def get_tier2_race_ids():
    """Tier 2（SQL）で購入対象となるrace_idを全て取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    race_ids_set = set()

    for cond in STANDARD_BET_CONDITIONS:
        # 簡易的にSQLで購入対象を抽出（オッズチェック含む）
        c1_rank_str = "','".join(cond['c1_rank'])
        confidence_clause = f"AND rp.confidence = '{cond['confidence']}'" if cond.get('confidence') else ""

        venue_clause = ""
        if cond.get('venue_filter'):
            venue_codes = [f"'{v:02d}'" if isinstance(v, int) else f"'{v}'" for v in cond['venue_filter']]
            venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"

        month_exclude_clause = ""
        if cond.get('month_exclude'):
            months = ','.join(map(str, cond['month_exclude']))
            month_exclude_clause = f"AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({months})"

        predicted_course_clause = ""
        if cond.get('predicted_course'):
            predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

        # 基本クエリ
        query = f'''
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                             || CAST(rp2.pit_number AS TEXT) || '-'
                             || CAST(rp3.pit_number AS TEXT)
        WHERE 1=1
        {confidence_clause}
        AND e1.racer_rank IN ('{c1_rank_str}')
        {venue_clause}
        {month_exclude_clause}
        {predicted_course_clause}
        AND t.odds >= {cond['odds_min']}
        AND t.odds < {cond['odds_max']}
        AND r.race_date >= '2024-06-01'
        AND r.race_date < '2024-07-01'
        '''

        cursor.execute(query)
        race_ids = [row[0] for row in cursor.fetchall()]
        race_ids_set.update(race_ids)

    conn.close()
    return race_ids_set


def get_tier3_race_ids():
    """Tier 3（BetTargetEvaluator）で購入対象となるrace_idを全て取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Tier 2と合わせて風速フィルターを無効化
    from src.betting.evaluator_helpers import create_custom_evaluator
    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=False,
        db_path=DATABASE_PATH
    )

    # 全レースを取得
    cursor.execute("""
        SELECT id
        FROM races
        WHERE race_date >= '2024-06-01' AND race_date < '2024-07-01'
        ORDER BY race_date
    """)
    race_ids = [row['id'] for row in cursor.fetchall()]

    tier3_race_ids = []

    for race_id in race_ids:
        # レースデータ取得
        cursor.execute("SELECT id, venue_code, race_number, race_date FROM races WHERE id = ?", (race_id,))
        row = cursor.fetchone()
        if not row:
            continue

        race_data = {
            'id': row['id'],
            'venue_code': row['venue_code'],
            'race_number': row['race_number'],
            'race_date': row['race_date'],
        }

        cursor.execute("SELECT wind_speed FROM race_conditions WHERE race_id = ?", (race_id,))
        conditions_row = cursor.fetchone()
        race_data['wind_speed'] = conditions_row['wind_speed'] if conditions_row and conditions_row['wind_speed'] else 0.0

        cursor.execute("SELECT pit_number, racer_number, racer_rank, motor_second_rate, second_rate FROM entries WHERE race_id = ? ORDER BY pit_number", (race_id,))
        race_data['entries'] = [dict(row) for row in cursor.fetchall()]

        # 予測データ取得
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))
        predictions_raw = [dict(row) for row in cursor.fetchall()]
        if len(predictions_raw) < 3:
            continue

        old_pred = [p['pit_number'] for p in predictions_raw[:3]]
        predictions = {
            'confidence': predictions_raw[0]['confidence'],
            'old_prediction': old_pred,
            'new_prediction': old_pred
        }

        # オッズデータ取得（1点のみ）
        cursor.execute("""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        """, (race_id, f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"))
        odds_row = cursor.fetchone()
        odds_data = {f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}": odds_row['odds']} if odds_row else {}

        # 購入判定
        try:
            bet_target = evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions,
                odds_data=odds_data,
                has_beforeinfo=True
            )

            if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                tier3_race_ids.append(race_id)
        except Exception:
            continue

    conn.close()
    return set(tier3_race_ids)


def main():
    print("Tier 2の購入対象race_idを取得中...")
    tier2_ids = get_tier2_race_ids()
    print(f"  Tier 2購入対象: {len(tier2_ids)}件")

    print("Tier 3の購入対象race_idを取得中...")
    tier3_ids = get_tier3_race_ids()
    print(f"  Tier 3購入対象: {len(tier3_ids)}件")

    print()
    print("=" * 80)
    print("比較結果")
    print("=" * 80)

    # 共通のrace_id
    common = tier2_ids & tier3_ids
    print(f"両方で購入対象: {len(common)}件")

    # Tier 2のみ
    only_tier2 = tier2_ids - tier3_ids
    print(f"Tier 2のみ購入対象: {len(only_tier2)}件")

    # Tier 3のみ
    only_tier3 = tier3_ids - tier2_ids
    print(f"Tier 3のみ購入対象: {len(only_tier3)}件")

    # 一致率
    if len(tier2_ids) > 0:
        match_rate = 100.0 * len(common) / len(tier2_ids)
        print(f"一致率: {match_rate:.2f}%")

    # サンプル表示
    if only_tier2:
        print()
        print("[Tier 2のみ購入対象のサンプル（最初の10件）]")
        for race_id in sorted(only_tier2)[:10]:
            print(f"  race_id: {race_id}")


if __name__ == '__main__':
    main()
