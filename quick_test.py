"""
クイックテスト - 結果のみ表示
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor
from collections import Counter

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

target_date = '2025-11-19'
cursor.execute("""
    SELECT id
    FROM races
    WHERE race_date = ?
    ORDER BY venue_code, race_number
    LIMIT 30
""", (target_date,))

races = [r[0] for r in cursor.fetchall()]
conn.close()

predictor = RacePredictor()
predictions_1st = []

for race_id in races:
    try:
        predictions = predictor.predict_race(race_id)
        if predictions:
            first_pred = [p for p in predictions if p['rank_prediction'] == 1][0]
            predictions_1st.append(first_pred['pit_number'])
    except:
        pass

counter = Counter(predictions_1st)
total = len(predictions_1st)

print(f"1着予測の分布（{total}レース、damping_factor=0.5）:")
for pit in sorted(counter.keys()):
    count = counter[pit]
    pct = count / total * 100
    print(f"{pit}号艇: {count:2d}回 ({pct:5.1f}%)")
