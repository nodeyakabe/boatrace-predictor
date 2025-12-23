# -*- coding: utf-8 -*-
"""A/B Rank Analysis v2"""
import sys
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings('ignore')
import logging
logging.disable(logging.CRITICAL)

import sqlite3
from collections import defaultdict
from src.analysis.race_predictor import RacePredictor

DB_PATH = 'data/boatrace.db'

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        INNER JOIN results res ON res.race_id = r.id
        WHERE r.race_date BETWEEN '2024-01-01' AND '2025-12-18'
            AND res.is_invalid = 0
            AND EXISTS (
                SELECT 1 FROM entries e WHERE e.race_id = r.id
                GROUP BY e.race_id HAVING COUNT(*) = 6
            )
        ORDER BY RANDOM()
        LIMIT 800
    ''')
    races = cursor.fetchall()
    print(f"Sample: {len(races)} races")

    predictor = RacePredictor(db_path=DB_PATH, use_cache=False)

    results = []
    errors = 0

    for i, (race_id, race_date) in enumerate(races):
        if (i + 1) % 100 == 0:
            print(f"Progress: {i+1}/{len(races)}")

        try:
            predictions = predictor.predict_race(race_id)
            if not predictions or len(predictions) < 3:
                errors += 1
                continue

            confidence = predictions[0].get('confidence', 'D')

            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank IS NOT NULL
                ORDER BY CAST(rank AS INTEGER) LIMIT 3
            ''', (race_id,))
            res = cursor.fetchall()
            if len(res) < 3:
                errors += 1
                continue

            actual = [int(r[0]) for r in res]

            actual_comb = f"{actual[0]}-{actual[1]}-{actual[2]}"
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                          (race_id, actual_comb))
            row = cursor.fetchone()
            actual_odds = float(row[0]) if row else 0.0

            pred_1st = predictions[0]['pit_number']
            pred_2nd = predictions[1]['pit_number']
            pred_3rd = predictions[2]['pit_number']

            pred_comb = f"{pred_1st}-{pred_2nd}-{pred_3rd}"
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                          (race_id, pred_comb))
            row = cursor.fetchone()
            pred_odds = float(row[0]) if row else 0.0

            cursor.execute('''
                SELECT racer_rank FROM entries
                WHERE race_id = ? AND pit_number = 1
            ''', (race_id,))
            row = cursor.fetchone()
            course1_class = row[0] if row else 'X'

            hit = (pred_1st == actual[0] and pred_2nd == actual[1] and pred_3rd == actual[2])

            results.append({
                'confidence': confidence,
                'pred_odds': pred_odds,
                'course1_class': course1_class,
                'hit': hit,
                'payout': actual_odds * 100 if hit else 0,
                'pred_1st': pred_1st
            })

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"Error at race {race_id}: {e}")
            continue

    conn.close()

    print(f"Valid: {len(results)}, Errors: {errors}")
    print()

    if not results:
        print("No data!")
        return

    # 1. A/B as betting target
    print("=" * 70)
    print("1. A/B RANK AS BETTING TARGET")
    print("=" * 70)
    print()

    for conf in ['A', 'B', 'C', 'D']:
        data = [r for r in results if r['confidence'] == conf]
        if not data:
            continue

        total = len(data)
        hits = sum(1 for r in data if r['hit'])
        payout = sum(r['payout'] for r in data)
        bet = total * 100
        roi = payout / bet * 100 if bet > 0 else 0

        marker = " *** PROFITABLE ***" if roi >= 100 else (" (marginal)" if roi >= 80 else "")
        print(f"[{conf}] n={total}, hit={hits} ({hits/total*100:.2f}%), ROI={roi:.1f}%{marker}")

    print()

    # 2. Odds range analysis
    print("=" * 70)
    print("2. ODDS RANGE ANALYSIS")
    print("=" * 70)
    print()

    odds_ranges = [(0, 10, '0-10'), (10, 20, '10-20'), (20, 30, '20-30'),
                   (30, 50, '30-50'), (50, 100, '50-100'), (100, 9999, '100+')]

    for conf in ['A', 'B']:
        print(f"--- {conf} Rank by Odds ---")
        conf_data = [r for r in results if r['confidence'] == conf]
        if not conf_data:
            print("No data")
            print()
            continue

        print(f"{'Odds':^8} | {'N':^5} | {'Hit':^4} | {'Rate':^7} | {'ROI':^7}")
        print("-" * 45)

        for low, high, label in odds_ranges:
            subset = [r for r in conf_data if low <= r['pred_odds'] < high]
            if len(subset) < 2:
                continue

            total = len(subset)
            hits = sum(1 for r in subset if r['hit'])
            payout = sum(r['payout'] for r in subset)
            bet = total * 100
            roi = payout / bet * 100 if bet > 0 else 0
            marker = "***" if roi >= 100 else ""
            print(f"{label:^8} | {total:>5} | {hits:>4} | {hits/total*100:>5.2f}% | {roi:>5.1f}% {marker}")

        total = len(conf_data)
        hits = sum(1 for r in conf_data if r['hit'])
        payout = sum(r['payout'] for r in conf_data)
        bet = total * 100
        print("-" * 45)
        print(f"{'TOTAL':^8} | {total:>5} | {hits:>4} | {hits/total*100:>5.2f}% | {payout/bet*100:>5.1f}%")
        print()

    # Class analysis
    print("--- A+B by Course1 Class ---")
    ab_data = [r for r in results if r['confidence'] in ['A', 'B']]
    print(f"{'Class':^8} | {'N':^5} | {'Hit':^4} | {'Rate':^7} | {'ROI':^7}")
    print("-" * 45)

    for cls in ['A1', 'A2', 'B1', 'B2']:
        subset = [r for r in ab_data if r['course1_class'] == cls]
        if len(subset) < 2:
            continue
        total = len(subset)
        hits = sum(1 for r in subset if r['hit'])
        payout = sum(r['payout'] for r in subset)
        bet = total * 100
        roi = payout / bet * 100 if bet > 0 else 0
        marker = "***" if roi >= 100 else ""
        print(f"{cls:^8} | {total:>5} | {hits:>4} | {hits/total*100:>5.2f}% | {roi:>5.1f}% {marker}")

    print()

    # Course prediction analysis
    print("--- A+B by Prediction Target ---")
    course1_pred = [r for r in ab_data if r['pred_1st'] == 1]
    non_course1 = [r for r in ab_data if r['pred_1st'] != 1]

    for label, subset in [("1 Course Pred", course1_pred), ("Non-1 Course", non_course1)]:
        if not subset:
            continue
        total = len(subset)
        hits = sum(1 for r in subset if r['hit'])
        payout = sum(r['payout'] for r in subset)
        bet = total * 100
        roi = payout / bet * 100 if bet > 0 else 0
        marker = "***" if roi >= 100 else ""
        print(f"{label}: n={total}, hit={hits} ({hits/total*100:.2f}%), ROI={roi:.1f}% {marker}")

    print()

    # 3. Integration proposal
    print("=" * 70)
    print("3. INTEGRATION PROPOSAL")
    print("=" * 70)
    print()

    print("Best conditions (ROI >= 100%):")
    best = []
    for conf in ['A', 'B']:
        conf_data = [r for r in results if r['confidence'] == conf]
        for low, high, label in odds_ranges:
            subset = [r for r in conf_data if low <= r['pred_odds'] < high]
            if len(subset) < 5:
                continue
            total = len(subset)
            hits = sum(1 for r in subset if r['hit'])
            payout = sum(r['payout'] for r in subset)
            bet = total * 100
            roi = payout / bet * 100 if bet > 0 else 0
            if roi >= 100:
                best.append((conf, label, total, hits/total*100, roi))

    if best:
        best.sort(key=lambda x: x[4], reverse=True)
        for conf, odds, n, rate, roi in best[:10]:
            print(f"  {conf} x {odds}: n={n}, rate={rate:.2f}%, ROI={roi:.1f}%")
    else:
        print("  No conditions with ROI >= 100%")

    print()
    print("-" * 50)
    print("RECOMMENDATION:")
    print()

    a_data = [r for r in results if r['confidence'] == 'A']
    b_data = [r for r in results if r['confidence'] == 'B']

    a_roi = sum(r['payout'] for r in a_data) / (len(a_data) * 100) * 100 if a_data else 0
    b_roi = sum(r['payout'] for r in b_data) / (len(b_data) * 100) * 100 if b_data else 0

    if a_roi >= 100:
        print(f"A Rank: ADD to betting targets (ROI {a_roi:.1f}%)")
    elif a_roi >= 80:
        print(f"A Rank: Consider with filters (ROI {a_roi:.1f}%)")
    else:
        print(f"A Rank: DO NOT add (ROI {a_roi:.1f}%)")

    if b_roi >= 100:
        print(f"B Rank: Already profitable (ROI {b_roi:.1f}%)")
    elif b_roi >= 80:
        print(f"B Rank: Keep current strategy (ROI {b_roi:.1f}%)")
    else:
        print(f"B Rank: Need better filters (ROI {b_roi:.1f}%)")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    conf_counts = defaultdict(int)
    for r in results:
        conf_counts[r['confidence']] += 1

    print("Sample distribution:")
    for conf in ['A', 'B', 'C', 'D']:
        if conf_counts[conf] > 0:
            print(f"  {conf}: {conf_counts[conf]} ({conf_counts[conf]/len(results)*100:.1f}%)")

    scale = 97000 / len(results)
    print()
    print("Estimated full period (2020-2025):")
    for conf in ['A', 'B']:
        est = int(conf_counts[conf] * scale)
        print(f"  {conf}: ~{est:,} races ({est//6:,}/year)")


if __name__ == '__main__':
    main()
