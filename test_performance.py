"""
1レースの予測パフォーマンステスト
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT id FROM races
    WHERE race_date = ?
    LIMIT 1
""", ('2025-11-19',))

race_id = cursor.fetchone()[0]
conn.close()

print(f'Testing race_id: {race_id}')

predictor = RacePredictor()
start = time.time()
predictions = predictor.predict_race(race_id)
elapsed = time.time() - start

print(f'Prediction time: {elapsed:.2f}s')
print(f'Predictions: {len(predictions) if predictions else 0}')

if predictions:
    print('\n予測結果:')
    for p in predictions:
        print(f"  {p['rank_prediction']}位: {p['pit_number']}号艇 {p['racer_name']} ({p['total_score']:.1f}点)")
