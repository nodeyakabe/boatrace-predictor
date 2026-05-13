#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ユニーク版Tier 2とTier 3の一致率検証

目的:
    重複除外後のTier 2（ユニーク版）とTier 3（実運用）の一致率を検証
    目標: 95%以上の一致率

使用方法:
    # 6年間全体検証
    python scripts/validation/verify_unique_consistency.py \
        --start 2020-01-01 --end 2026-01-01 \
        --tier2-results data/tier2_unique_results.json

出力:
    - 全体一致率
    - ミスマッチの詳細
"""
import sqlite3
import sys
import os
import json
import argparse
from typing import Dict, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.betting.evaluator_helpers import create_custom_evaluator

def get_tier3_bet_race_ids(start_date: str, end_date: str) -> Set[int]:
    """Tier 3で購入対象となるrace_idのセットを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Tier 3で購入判定（風速フィルター有効化: Tier 2 enable_wind_filter=True と整合）
    evaluator = create_custom_evaluator(
        enable_venue_wind_filter=True,
        db_path=DATABASE_PATH
    )

    # 期間内の全レースを取得
    cursor.execute("""
        SELECT id, venue_code, race_number, race_date, race_grade, is_rookie, is_ladies
        FROM races
        WHERE race_date >= ? AND race_date < ?
        ORDER BY race_date, race_time
    """, (start_date, end_date))

    races = [dict(row) for row in cursor.fetchall()]
    print(f"Total races: {len(races):,}")

    bet_race_ids = set()
    evaluated = 0

    for race in races:
        race_id = race['id']

        # 予測データを取得（before）
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence, racer_number, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))

        predictions_rows = [dict(row) for row in cursor.fetchall()]
        if len(predictions_rows) < 3:
            continue

        old_pred = [p['pit_number'] for p in predictions_rows]

        # advance予測を取得（advance_before_matchチェック用）
        cursor.execute("""
            SELECT pit_number
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
            LIMIT 3
        """, (race_id,))
        advance_rows = cursor.fetchall()
        advance_top3 = [r['pit_number'] for r in advance_rows] if advance_rows else None

        predictions = {
            'confidence': predictions_rows[0]['confidence'],
            'old_prediction': old_pred,
            'new_prediction': old_pred,
            'first_racer_number': predictions_rows[0]['racer_number'],
            'total_score': predictions_rows[0].get('total_score'),
        }

        # オッズデータを取得（全パターン対応: p1-p2-p3 / p132 / p142 / p143 / p124 / pattern_h）
        p = old_pred
        combinations = [f"{p[0]}-{p[1]}-{p[2]}"]  # 1点買い / p123
        if len(p) >= 3:
            combinations.append(f"{p[0]}-{p[2]}-{p[1]}")  # p132
        if len(p) >= 4:
            combinations.append(f"{p[0]}-{p[3]}-{p[1]}")  # p142
            combinations.append(f"{p[0]}-{p[3]}-{p[2]}")  # p143
            combinations.append(f"{p[0]}-{p[1]}-{p[3]}")  # p124 / pattern_h(4th)
        if len(p) >= 5:
            combinations.append(f"{p[0]}-{p[1]}-{p[4]}")  # pattern_h(5th)
        combinations = list(dict.fromkeys(combinations))  # 重複除去・順序保持

        placeholders = ','.join(['?'] * len(combinations))
        cursor.execute(f"""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination IN ({placeholders})
        """, [race_id] + combinations)

        fetched_odds = {row['combination']: row['odds'] for row in cursor.fetchall()}
        odds_dict = {combo: fetched_odds.get(combo, 0) for combo in combinations}

        if not odds_dict:
            continue

        # エントリー情報を取得
        cursor.execute("""
            SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
            FROM entries WHERE race_id = ? ORDER BY pit_number
        """, (race_id,))
        entries = [dict(row) for row in cursor.fetchall()]

        # 風速を取得（Tier 2の enable_wind_filter=True と整合させる）
        cursor.execute("SELECT wind_speed FROM race_conditions WHERE race_id = ?", (race_id,))
        wind_row = cursor.fetchone()
        wind_speed = wind_row['wind_speed'] if wind_row and wind_row['wind_speed'] is not None else 0.0

        race_data = {
            'id': race_id,
            'venue_code': race['venue_code'],
            'race_number': race['race_number'],
            'race_date': race['race_date'],
            'race_grade': race.get('race_grade'),
            'is_rookie': race.get('is_rookie', 0),
            'is_ladies': race.get('is_ladies', 0),
            'wind_speed': wind_speed,
            'entries': entries
        }

        # BetTargetEvaluatorで購入判定
        bet_target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions,
            odds_data=odds_dict,
            has_beforeinfo=True,
            advance_top3=advance_top3
        )

        from src.betting.bet_target_evaluator import BetStatus
        is_tier3_bet = bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]

        if is_tier3_bet:
            bet_race_ids.add(race_id)

        evaluated += 1
        if evaluated % 10000 == 0:
            print(f"Evaluated: {evaluated:,} races, Tier 3 bets: {len(bet_race_ids):,}")

    conn.close()
    print(f"Tier 3 total bets: {len(bet_race_ids):,}")
    return bet_race_ids

def get_tier2_unique_bet_race_ids(start_date: str, end_date: str) -> Set[int]:
    """ユニーク版Tier 2の購入対象race_idを取得

    standard_backtest_unique.pyのassign_races_to_conditions()ロジックを再現
    """
    from config.bet_conditions import STANDARD_BET_CONDITIONS
    from scripts.backtest.backtest_helpers import get_race_ids_for_condition

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 優先度順にソート（priorityが同じ場合はリスト順）
    sorted_conditions = sorted(
        STANDARD_BET_CONDITIONS,
        key=lambda x: (x.get('priority', 999), STANDARD_BET_CONDITIONS.index(x))
    )

    all_race_ids = set()
    race_to_condition = {}

    print("Assigning races to conditions by priority...")
    for cond in sorted_conditions:
        race_ids = get_race_ids_for_condition(cursor, cond, start_date, end_date, require_odds=True, enable_wind_filter=True)

        new_assignments = 0
        for race_id in race_ids:
            if race_id not in all_race_ids:
                all_race_ids.add(race_id)
                race_to_condition[race_id] = cond['id']
                new_assignments += 1

        print(f"  {cond['id']:20s} Priority {cond.get('priority', 999):2d}: {len(race_ids):4d} candidates, {new_assignments:4d} assigned")

    conn.close()
    print(f"Tier 2 Unique total bets: {len(all_race_ids):,}")
    return all_race_ids

def main():
    parser = argparse.ArgumentParser(description='Verify Tier 2 Unique vs Tier 3 consistency')
    parser.add_argument('--start', type=str, required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    print("=" * 80)
    print("Tier 2 (Unique) vs Tier 3 Consistency Verification")
    print("=" * 80)
    print()

    # Tier 2（ユニーク版）の購入対象race_idを取得
    print("[Step 1] Getting Tier 2 Unique bet race IDs...")
    tier2_bet_ids = get_tier2_unique_bet_race_ids(args.start, args.end)
    print()

    # Tier 3の購入対象race_idを取得
    print("[Step 2] Getting Tier 3 bet race IDs...")
    tier3_bet_ids = get_tier3_bet_race_ids(args.start, args.end)
    print()

    # 一致率計算
    print("=" * 80)
    print("[Result] Consistency Analysis")
    print("=" * 80)
    print()

    # セット比較
    both = tier2_bet_ids & tier3_bet_ids  # 両方で購入
    only_tier2 = tier2_bet_ids - tier3_bet_ids  # Tier 2のみ
    only_tier3 = tier3_bet_ids - tier2_bet_ids  # Tier 3のみ

    # 一致率計算（全レース母数）
    total_unique_races = len(tier2_bet_ids | tier3_bet_ids)
    match_count = len(both)
    match_rate = 100.0 * match_count / total_unique_races if total_unique_races > 0 else 0.0

    print(f"Tier 2 Unique bets: {len(tier2_bet_ids):,}")
    print(f"Tier 3 bets:        {len(tier3_bet_ids):,}")
    print(f"Both (matched):     {len(both):,}")
    print(f"Only Tier 2:        {len(only_tier2):,}")
    print(f"Only Tier 3:        {len(only_tier3):,}")
    print()
    print(f"Match rate: {match_rate:.2f}%")
    print()

    # 判定
    if match_rate >= 95.0:
        print("[OK] Match rate >= 95% achieved!")
    else:
        print(f"[WARNING] Match rate {match_rate:.2f}% < 95%")
        print()
        print("Investigating mismatches...")
        print()

        # ミスマッチの詳細分析
        if only_tier2:
            print(f"[Only Tier 2] {len(only_tier2)} races")
            print("Sample race IDs:", list(only_tier2)[:10])
            print()

        if only_tier3:
            print(f"[Only Tier 3] {len(only_tier3)} races")
            print("Sample race IDs:", list(only_tier3)[:10])
            print()

if __name__ == '__main__':
    main()
