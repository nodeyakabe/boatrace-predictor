#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ミスマッチの具体的な原因を詳細デバッグ

使用方法:
    python scripts/validation/debug_mismatch_details.py --condition-id A_A1_10_12

作成日: 2026-02-16
"""
import sqlite3
import sys
import os
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS, get_condition_by_id
from src.betting.evaluator_helpers import create_custom_evaluator
from src.betting.bet_target_evaluator import BetStatus


def debug_condition_mismatch(cond_id: str, start_date: str = '2024-01-01', end_date: str = '2025-01-01'):
    """条件のミスマッチを詳細デバッグ"""
    cond = get_condition_by_id(cond_id)
    if not cond:
        print(f"エラー: 条件ID '{cond_id}' が見つかりません")
        return

    print("=" * 120)
    print(f"条件詳細デバッグ: {cond['name']} ({cond_id})")
    print("=" * 120)
    print()
    print("【条件定義】")
    print(f"  信頼度: {cond.get('confidence')}")
    print(f"  C1級別: {cond.get('c1_rank')}")
    print(f"  オッズ範囲: {cond.get('odds_min')}-{cond.get('odds_max')}倍")
    print(f"  会場フィルター: {cond.get('venue_filter')}")
    print(f"  逃げ率: {cond.get('escape_rate_min')}")
    print(f"  予測コース: {cond.get('predicted_course')}")
    print(f"  パターンH: {cond.get('use_pattern_h')}")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Tier 2のSQLを構築
    c1_rank_str = "','".join(cond['c1_rank'])
    confidence_clause = f"AND rp.confidence = '{cond['confidence']}'" if cond.get('confidence') else ""

    venue_clause = ""
    if cond.get('venue_filter'):
        venue_codes = [f"'{v:02d}'" if isinstance(v, int) else f"'{v}'" for v in cond['venue_filter']]
        venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"

    escape_rate_join = ""
    escape_rate_clause = ""
    if cond.get('escape_rate_min'):
        escape_rate_join = """
        LEFT JOIN entries e_pred ON r.id = e_pred.race_id AND e_pred.pit_number = rp1.pit_number
        LEFT JOIN player_escape_stats pes ON e_pred.racer_number = pes.player_id AND pes.stadium_id IS NULL
        """
        escape_rate_clause = f"AND pes.escape_rate IS NOT NULL AND pes.escape_rate >= {cond['escape_rate_min']}"

    predicted_course_clause = ""
    if cond.get('predicted_course'):
        predicted_course_clause = f"AND rp1.pit_number = {cond['predicted_course']}"

    # Tier 2のSQLで購入対象を取得
    query = f'''
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        rp.confidence,
        e1.racer_rank as c1_rank,
        e1.racer_number as c1_racer_number,
        e1.racer_name as c1_racer_name,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp3.pit_number as p3,
        e_pred.racer_number as pred_racer_number,
        pes.escape_rate as escape_rate,
        COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = r.id
                  AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)), 0) as odds
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    {escape_rate_join}
    WHERE rp.rank_prediction = 1
    {confidence_clause}
    AND e1.racer_rank IN ('{c1_rank_str}')
    AND r.race_date >= '{start_date}'
    AND r.race_date < '{end_date}'
    {venue_clause}
    {escape_rate_clause}
    {predicted_course_clause}
    '''

    cursor.execute(query)
    tier2_races = cursor.fetchall()

    # オッズフィルター適用
    tier2_bets = [r for r in tier2_races if cond['odds_min'] <= r['odds'] < cond['odds_max']]

    print(f"【Tier 2 SQL結果】")
    print(f"  総レース数（フィルター前）: {len(tier2_races)}件")
    print(f"  購入対象（オッズ範囲内）: {len(tier2_bets)}件")
    print()

    # Tier 3で判定
    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=False,
        db_path=DATABASE_PATH
    )

    tier3_bets = []
    tier3_excluded = []

    for race_row in tier2_bets:
        race_id = race_row['race_id']

        # レースデータを構築
        cursor.execute("""
            SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
            FROM entries WHERE race_id = ? ORDER BY pit_number
        """, (race_id,))
        entries = [dict(row) for row in cursor.fetchall()]

        race_data = {
            'id': race_id,
            'venue_code': race_row['venue_code'],
            'race_number': race_row['race_number'],
            'race_date': race_row['race_date'],
            'race_time': '00:00',
            'wind_speed': 0.0,
            'entries': entries,
        }

        # 予測データを構築
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence, racer_number
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))
        pred_rows = cursor.fetchall()

        old_pred = [row[0] for row in pred_rows]
        predictions = {
            'confidence': race_row['confidence'],
            'old_prediction': old_pred,
            'new_prediction': old_pred,
            'first_racer_number': race_row['pred_racer_number'],
        }

        # オッズデータを構築
        combinations = [f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"]
        if len(old_pred) >= 4:
            combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[3]}")
        if len(old_pred) >= 5:
            combinations.append(f"{old_pred[0]}-{old_pred[1]}-{old_pred[4]}")

        placeholders = ','.join(['?'] * len(combinations))
        cursor.execute(f"""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination IN ({placeholders})
        """, (race_id, *combinations))

        odds_data = {row[0]: row[1] for row in cursor.fetchall()}
        for combo in combinations:
            if combo not in odds_data:
                odds_data[combo] = 0

        # Tier 3で判定
        bet_target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions,
            odds_data=odds_data,
            has_beforeinfo=True
        )

        is_tier3_bet = bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]

        if is_tier3_bet:
            tier3_bets.append(race_row)
        else:
            tier3_excluded.append({
                'race_row': race_row,
                'bet_target': bet_target,
                'odds_data': odds_data,
                'predictions': predictions,
            })

    print(f"【Tier 3 Python結果】")
    print(f"  購入対象: {len(tier3_bets)}件")
    print(f"  非購入: {len(tier3_excluded)}件")
    print()

    # ミスマッチの詳細を表示
    if tier3_excluded:
        print("【Tier 2○ / Tier 3× のミスマッチ詳細】")
        print("=" * 120)
        print(f"{'race_id':<16} {'日付':<12} {'会場':<4} {'R':<3} {'信頼度':<4} {'C1級':<5} "
              f"{'逃げ率':<8} {'予測':<12} {'オッズ':<8} {'Tier 3理由':<30}")
        print("-" * 120)

        for item in tier3_excluded:
            race = item['race_row']
            bet_target = item['bet_target']
            odds_data = item['odds_data']

            venue_str = f"{int(race['venue_code']):02d}"
            escape_rate_str = f"{race['escape_rate']:.3f}" if race['escape_rate'] else 'NULL'
            pred_str = f"{race['p1']}-{race['p2']}-{race['p3']}"
            odds_str = f"{race['odds']:.1f}"

            print(f"{race['race_id']:<16} {race['race_date']:<12} {venue_str:<4} {race['race_number']:<3} "
                  f"{race['confidence']:<4} {race['c1_rank']:<5} {escape_rate_str:<8} {pred_str:<12} "
                  f"{odds_str:<8} {bet_target.reason:<30}")

            # 詳細情報
            print(f"    → Tier 3 status: {bet_target.status.value}")
            print(f"    → Tier 3 odds: {bet_target.odds}")
            print(f"    → odds_data: {odds_data}")
            print()

    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--condition-id', type=str, required=True, help='条件ID（例: A_A1_10_12）')
    parser.add_argument('--start', type=str, default='2024-01-01', help='開始日')
    parser.add_argument('--end', type=str, default='2025-01-01', help='終了日')
    args = parser.parse_args()

    debug_condition_mismatch(args.condition_id, args.start, args.end)


if __name__ == '__main__':
    main()
