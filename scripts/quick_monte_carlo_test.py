"""
モンテカルロシミュレーション簡易テスト（100レースサンプル）
"""

import sys
import os
import time
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, '.')

import sqlite3
import numpy as np
from collections import defaultdict

from src.analysis.race_predictor import RacePredictor
from config.feature_flags import enable_feature, disable_feature


def get_test_races(db_path, start_date, end_date):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.id, r.race_date, r.venue_code, r.race_number, r.race_grade,
               rc.wind_speed, rc.wave_height, rc.wind_direction
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date BETWEEN ? AND ?
        AND EXISTS (SELECT 1 FROM results res WHERE res.race_id = r.id)
        AND (SELECT COUNT(*) FROM entries e WHERE e.race_id = r.id) = 6
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))
    races = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return races


def get_race_result(db_path, race_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT pit_number, rank FROM results
        WHERE race_id = ? AND is_invalid = 0
        ORDER BY CASE
            WHEN rank LIKE '%1%' THEN 1
            WHEN rank LIKE '%2%' THEN 2
            WHEN rank LIKE '%3%' THEN 3
            ELSE 7
        END
    ''', (race_id,))

    result_dict = {}
    for i, row in enumerate(cursor.fetchall()):
        rank_str = str(row['rank'])
        try:
            rank_num = int(''.join(c for c in rank_str if c.isdigit())[:1])
        except:
            rank_num = i + 1
        result_dict[rank_num] = row['pit_number']

    cursor.execute('''
        SELECT combination, amount FROM payouts
        WHERE race_id = ? AND bet_type = '3連単' LIMIT 1
    ''', (race_id,))
    payout_row = cursor.fetchone()
    if payout_row and payout_row['amount']:
        result_dict['trifecta_payout'] = payout_row['amount']

    cursor.close()
    conn.close()
    return result_dict


def run_backtest(predictor, races, db_path, label, max_races=100):
    results = {
        'label': label, 'total_races': 0, 'purchased_races': 0,
        'total_bet': 0, 'total_payout': 0,
        '1st_correct': 0, '2nd_correct': 0, '3rd_correct': 0, 'trifecta_correct': 0,
        'execution_times': []
    }

    for race in races[:max_races]:
        race_id = race['id']
        try:
            start_time = time.time()
            predictions = predictor.predict_race(race_id)
            elapsed = (time.time() - start_time) * 1000
            results['execution_times'].append(elapsed)

            if not predictions or len(predictions) != 6:
                continue

            results['total_races'] += 1
            top_confidence = predictions[0]['confidence']

            if top_confidence not in ['B', 'C']:
                continue

            results['purchased_races'] += 1
            results['total_bet'] += 100

            actual = get_race_result(db_path, race_id)
            if not actual or 1 not in actual:
                continue

            pred_1st = predictions[0]['pit_number']
            pred_2nd = predictions[1]['pit_number']
            pred_3rd = predictions[2]['pit_number']

            if pred_1st == actual.get(1):
                results['1st_correct'] += 1
            if pred_2nd == actual.get(2):
                results['2nd_correct'] += 1
            if pred_3rd == actual.get(3):
                results['3rd_correct'] += 1

            if (pred_1st == actual.get(1) and
                pred_2nd == actual.get(2) and
                pred_3rd == actual.get(3)):
                results['trifecta_correct'] += 1
                if 'trifecta_payout' in actual:
                    results['total_payout'] += actual['trifecta_payout']
        except Exception as e:
            continue

    if results['purchased_races'] > 0:
        results['roi'] = (results['total_payout'] / results['total_bet']) * 100
        results['1st_accuracy'] = (results['1st_correct'] / results['purchased_races']) * 100
        results['2nd_accuracy'] = (results['2nd_correct'] / results['purchased_races']) * 100
        results['3rd_accuracy'] = (results['3rd_correct'] / results['purchased_races']) * 100
        results['trifecta_accuracy'] = (results['trifecta_correct'] / results['purchased_races']) * 100
    else:
        results['roi'] = 0
        results['1st_accuracy'] = 0
        results['2nd_accuracy'] = 0
        results['3rd_accuracy'] = 0
        results['trifecta_accuracy'] = 0

    if results['execution_times']:
        results['avg_time'] = np.mean(results['execution_times'])
    else:
        results['avg_time'] = 0

    return results


if __name__ == '__main__':
    print('=' * 60)
    print('Monte Carlo Simulation Backtest (100 races sample)')
    print('=' * 60)

    db_path = 'data/boatrace.db'
    start_date = '2025-11-28'
    end_date = '2025-12-08'

    races = get_test_races(db_path, start_date, end_date)
    print(f'Available races: {len(races)}')
    print(f'Testing first 100 races...')

    # Baseline
    print('\n=== Baseline (without Monte Carlo) ===')
    disable_feature('monte_carlo_simulation')
    predictor_baseline = RacePredictor(db_path=db_path, use_cache=False)
    baseline = run_backtest(predictor_baseline, races, db_path, 'Baseline', max_races=100)
    print(f"Total races: {baseline['total_races']}")
    print(f"Purchased: {baseline['purchased_races']}")
    print(f"ROI: {baseline['roi']:.1f}%")
    print(f"1st accuracy: {baseline['1st_accuracy']:.1f}%")
    print(f"2nd accuracy: {baseline['2nd_accuracy']:.1f}%")
    print(f"3rd accuracy: {baseline['3rd_accuracy']:.1f}%")
    print(f"Trifecta accuracy: {baseline['trifecta_accuracy']:.2f}%")
    print(f"Trifecta hits: {baseline['trifecta_correct']}")
    print(f"Avg execution time: {baseline['avg_time']:.1f}ms")

    # With Monte Carlo
    print('\n=== With Monte Carlo Simulation ===')
    enable_feature('monte_carlo_simulation')
    predictor_mc = RacePredictor(db_path=db_path, use_cache=False)
    mc = run_backtest(predictor_mc, races, db_path, 'Monte Carlo', max_races=100)
    print(f"Total races: {mc['total_races']}")
    print(f"Purchased: {mc['purchased_races']}")
    print(f"ROI: {mc['roi']:.1f}%")
    print(f"1st accuracy: {mc['1st_accuracy']:.1f}%")
    print(f"2nd accuracy: {mc['2nd_accuracy']:.1f}%")
    print(f"3rd accuracy: {mc['3rd_accuracy']:.1f}%")
    print(f"Trifecta accuracy: {mc['trifecta_accuracy']:.2f}%")
    print(f"Trifecta hits: {mc['trifecta_correct']}")
    print(f"Avg execution time: {mc['avg_time']:.1f}ms")

    # Comparison
    print('\n=== Comparison ===')
    print(f"ROI change: {mc['roi'] - baseline['roi']:+.1f}pt")
    print(f"1st accuracy change: {mc['1st_accuracy'] - baseline['1st_accuracy']:+.1f}pt")
    print(f"2nd accuracy change: {mc['2nd_accuracy'] - baseline['2nd_accuracy']:+.1f}pt")
    print(f"3rd accuracy change: {mc['3rd_accuracy'] - baseline['3rd_accuracy']:+.1f}pt")
    print(f"Trifecta accuracy change: {mc['trifecta_accuracy'] - baseline['trifecta_accuracy']:+.2f}pt")
    print(f"Time overhead: {mc['avg_time'] - baseline['avg_time']:+.1f}ms")

    disable_feature('monte_carlo_simulation')
