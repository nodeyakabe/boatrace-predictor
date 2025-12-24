# -*- coding: utf-8 -*-
"""
Motor 40%+ conditions backtest
- Uses BetTargetEvaluator with motor_second_rate parameter
- Uses trifecta_odds for odds filtering
- Compares with/without motor conditions
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def run_backtest(years, use_motor=True):
    """Run backtest with or without motor conditions"""
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    year_conditions = " OR ".join([f"r.race_date LIKE '{y}%'" for y in years])

    cursor.execute(f'''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE ({year_conditions})
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    stats = {
        'total': 0,
        'target': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
        'by_confidence': {
            'A': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'B': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'C': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'D': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        },
        'motor_hits': {
            'A_B1': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'A_A2': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'D_A1': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'D_A2': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        }
    }

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 1course info
        cursor.execute('''
            SELECT racer_rank, motor_second_rate
            FROM entries
            WHERE race_id = ? AND pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'
        motor_second_rate = c1['motor_second_rate'] if c1 and use_motor else None

        # Prediction info (use before prediction)
        cursor.execute('''
            SELECT pit_number, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        stats['total'] += 1

        confidence = preds[0]['confidence']
        old_pred = [p['pit_number'] for p in preds[:3]]
        new_pred = old_pred

        old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        new_combo = f"{new_pred[0]}-{new_pred[1]}-{new_pred[2]}"

        # Get odds
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        odds_rows = cursor.fetchall()
        odds_data = {row['combination']: row['odds'] for row in odds_rows}

        old_odds = odds_data.get(old_combo, 0)
        new_odds = odds_data.get(new_combo, 0)

        # Evaluate with motor condition
        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=old_combo,
            new_combo=new_combo,
            old_odds=old_odds,
            new_odds=new_odds,
            has_beforeinfo=True,
            venue_code=venue_code,
            motor_second_rate=motor_second_rate
        )

        if result.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            stats['target'] += 1
            stats['bet'] += result.bet_amount
            stats['by_confidence'][confidence]['target'] += 1
            stats['by_confidence'][confidence]['bet'] += result.bet_amount

            # Track motor condition hits
            motor_key = f"{confidence}_{c1_rank}"
            if motor_key in stats['motor_hits'] and motor_second_rate and motor_second_rate >= 40:
                stats['motor_hits'][motor_key]['target'] += 1
                stats['motor_hits'][motor_key]['bet'] += result.bet_amount

            # Check actual result
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            if len(results) >= 3:
                actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

                if result.combination == actual_combo:
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        stats['hit'] += 1
                        actual_payout = (result.bet_amount / 100) * payout_row['amount']
                        stats['payout'] += actual_payout
                        stats['by_confidence'][confidence]['hit'] += 1
                        stats['by_confidence'][confidence]['payout'] += actual_payout

                        if motor_key in stats['motor_hits'] and motor_second_rate and motor_second_rate >= 40:
                            stats['motor_hits'][motor_key]['hit'] += 1
                            stats['motor_hits'][motor_key]['payout'] += actual_payout

    conn.close()
    return stats


def main():
    print("=" * 70)
    print("Motor 40%+ Conditions Backtest")
    print("=" * 70)

    years = ['2025']

    # Test WITH motor conditions
    print("\n--- WITH Motor Conditions ---")
    stats_with = run_backtest(years, use_motor=True)

    if stats_with['target'] > 0:
        roi = stats_with['payout'] / stats_with['bet'] * 100
        profit = stats_with['payout'] - stats_with['bet']
        print(f"Total: {stats_with['target']} bets, {stats_with['hit']} hits")
        print(f"Bet: {stats_with['bet']:,} yen, Payout: {stats_with['payout']:,.0f} yen")
        print(f"Profit: {profit:+,.0f} yen, ROI: {roi:.1f}%")

        print("\nBy Confidence:")
        for conf in ['A', 'B', 'C', 'D']:
            cs = stats_with['by_confidence'][conf]
            if cs['target'] > 0:
                croi = cs['payout'] / cs['bet'] * 100 if cs['bet'] > 0 else 0
                cprofit = cs['payout'] - cs['bet']
                print(f"  {conf}: {cs['target']} bets, {cs['hit']} hits, ROI {croi:.1f}%, profit {cprofit:+,.0f}")

        print("\nMotor 40%+ Condition Breakdown:")
        for key, ms in stats_with['motor_hits'].items():
            if ms['target'] > 0:
                mroi = ms['payout'] / ms['bet'] * 100 if ms['bet'] > 0 else 0
                mprofit = ms['payout'] - ms['bet']
                print(f"  {key}: {ms['target']} bets, {ms['hit']} hits, ROI {mroi:.1f}%, profit {mprofit:+,.0f}")

    # Test WITHOUT motor conditions
    print("\n--- WITHOUT Motor Conditions (baseline) ---")
    stats_without = run_backtest(years, use_motor=False)

    if stats_without['target'] > 0:
        roi = stats_without['payout'] / stats_without['bet'] * 100
        profit = stats_without['payout'] - stats_without['bet']
        print(f"Total: {stats_without['target']} bets, {stats_without['hit']} hits")
        print(f"Bet: {stats_without['bet']:,} yen, Payout: {stats_without['payout']:,.0f} yen")
        print(f"Profit: {profit:+,.0f} yen, ROI: {roi:.1f}%")

    # Comparison
    print("\n" + "=" * 70)
    print("Comparison")
    print("=" * 70)

    if stats_with['bet'] > 0 and stats_without['bet'] > 0:
        roi_with = stats_with['payout'] / stats_with['bet'] * 100
        roi_without = stats_without['payout'] / stats_without['bet'] * 100
        profit_with = stats_with['payout'] - stats_with['bet']
        profit_without = stats_without['payout'] - stats_without['bet']

        print(f"With Motor:    {stats_with['target']} bets, ROI {roi_with:.1f}%, profit {profit_with:+,.0f}")
        print(f"Without Motor: {stats_without['target']} bets, ROI {roi_without:.1f}%, profit {profit_without:+,.0f}")
        print(f"Difference:    {stats_with['target'] - stats_without['target']:+d} bets, ROI {roi_with - roi_without:+.1f}pt, profit {profit_with - profit_without:+,.0f}")


if __name__ == "__main__":
    main()
