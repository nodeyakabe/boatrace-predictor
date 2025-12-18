#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""2着・3着オッズ校正の100レース検証（簡易版）"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

from src.analysis.scorers.odds_calibrator import OddsCalibrator
from src.analysis.race_predictor import RacePredictor
import sqlite3

DB_PATH = "data/boatrace_backup_20251212_145413.db"

def quick_verification():
    print("2着・3着オッズ校正 100レース検証")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT r.id FROM races r
        INNER JOIN results res ON res.race_id = r.id
        INNER JOIN trifecta_odds odds ON odds.race_id = r.id
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2024-02-15'
            AND res.is_invalid = 0
        ORDER BY r.id LIMIT 100
    ''')
    race_ids = [row[0] for row in cursor.fetchall()]

    print(f"検証レース数: {len(race_ids)}")
    print()

    predictor = RacePredictor(DB_PATH, use_cache=False)
    calibrator = OddsCalibrator(DB_PATH, alpha=0.5, temperature=4.0, rank23_alpha=0.3)

    # ベースライン
    print("[1/2] ベースライン測定...")
    b_hits, b_total = 0, 0
    b_1st_hits, b_1st_total = 0, 0

    for i, race_id in enumerate(race_ids):
        if i % 25 == 0:
            print(f"  {i}/{len(race_ids)}", end="\r")

        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            pred_1st = predictions[0]['pit_number']
            pred_combo = f"{predictions[0]['pit_number']}-{predictions[1]['pit_number']}-{predictions[2]['pit_number']}"

            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as combo,
                       (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as first
                FROM (SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank <= 3 ORDER BY rank)
            ''', (race_id, race_id))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            b_total += 1
            if pred_combo == row[0]:
                b_hits += 1

            b_1st_total += 1
            if pred_1st == row[1]:
                b_1st_hits += 1
        except:
            pass

    b_rate = b_hits / b_total if b_total > 0 else 0
    b_1st_rate = b_1st_hits / b_1st_total if b_1st_total > 0 else 0
    print(f"  三連単: {b_rate:.2%} ({b_hits}/{b_total})")
    print(f"  1着:    {b_1st_rate:.2%} ({b_1st_hits}/{b_1st_total})")

    # オッズ校正
    print("\n[2/2] オッズ校正測定...")
    c_hits, c_total = 0, 0
    c_1st_hits, c_1st_total = 0, 0

    for i, race_id in enumerate(race_ids):
        if i % 25 == 0:
            print(f"  {i}/{len(race_ids)}", end="\r")

        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if len(predictions) < 3:
                continue

            calibrated = calibrator.calibrate_rank23_predictions(predictions, race_id, alpha=0.3)
            if len(calibrated) < 3:
                continue

            pred_1st = calibrated[0]['pit_number']
            pred_combo = f"{calibrated[0]['pit_number']}-{calibrated[1]['pit_number']}-{calibrated[2]['pit_number']}"

            cursor.execute('''
                SELECT GROUP_CONCAT(pit_number, '-') as combo,
                       (SELECT pit_number FROM results WHERE race_id = ? AND rank = 1 AND is_invalid = 0) as first
                FROM (SELECT pit_number FROM results WHERE race_id = ? AND is_invalid = 0 AND rank <= 3 ORDER BY rank)
            ''', (race_id, race_id))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue

            c_total += 1
            if pred_combo == row[0]:
                c_hits += 1

            c_1st_total += 1
            if pred_1st == row[1]:
                c_1st_hits += 1
        except:
            pass

    c_rate = c_hits / c_total if c_total > 0 else 0
    c_1st_rate = c_1st_hits / c_1st_total if c_1st_total > 0 else 0
    print(f"  三連単: {c_rate:.2%} ({c_hits}/{c_total})")
    print(f"  1着:    {c_1st_rate:.2%} ({c_1st_hits}/{c_1st_total})")

    diff = (c_rate - b_rate) * 100
    diff_1st = (c_1st_rate - b_1st_rate) * 100

    print()
    print("=" * 70)
    print(f"レース数: {b_total}")
    print(f"三連単差分: {diff:+.2f}pt ({b_rate:.2%} → {c_rate:.2%})")
    print(f"1着差分:    {diff_1st:+.2f}pt ({b_1st_rate:.2%} → {c_1st_rate:.2%})")
    print("=" * 70)

    if diff > 1.0:
        print("\n[EXCELLENT] 大幅改善 → 本番投入推奨")
    elif diff > 0.5:
        print("\n[GOOD] 改善効果あり")
    else:
        print("\n[NEUTRAL] 効果微小")

    conn.close()

if __name__ == "__main__":
    quick_verification()
