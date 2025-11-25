"""
指定日付の予測を生成
"""

import sys
import os
import time

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor
from src.database.data_manager import DataManager

target_date = sys.argv[1] if len(sys.argv) > 1 else '2025-08-01'

print("=" * 80, flush=True)
print(f"{target_date}の予測を生成", flush=True)
print("=" * 80, flush=True)

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT COUNT(*)
    FROM races
    WHERE race_date = ?
""", (target_date,))

total_races = cursor.fetchone()[0]
print(f"\n全レース数: {total_races}", flush=True)

cursor.execute("""
    SELECT id, venue_code, race_number
    FROM races
    WHERE race_date = ?
    ORDER BY venue_code, race_number
""", (target_date,))

races = cursor.fetchall()
conn.close()

predictor = RacePredictor()
data_manager = DataManager()

success = 0
errors = 0
start_time = time.time()

print("\n予測生成中...", flush=True)
print("-" * 80, flush=True)

for i, (race_id, venue_code, race_number) in enumerate(races, 1):
    try:
        predictions = predictor.predict_race(race_id)
        if predictions:
            if data_manager.save_race_predictions(race_id, predictions):
                success += 1
            else:
                errors += 1
        else:
            errors += 1

        if i % 20 == 0 or i == total_races:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (total_races - i) / rate if rate > 0 else 0

            print(f"進捗: {i:3d}/{total_races} ({i/total_races*100:5.1f}%) | "
                  f"成功: {success:3d}, エラー: {errors} | "
                  f"残り時間: {remaining/60:4.1f}分", flush=True)

    except Exception as e:
        errors += 1

elapsed_total = time.time() - start_time
print("-" * 80, flush=True)
print(f"\n完了: 成功 {success}, エラー {errors}", flush=True)
print(f"処理時間: {elapsed_total:.1f}秒 ({elapsed_total/60:.1f}分)", flush=True)
print("=" * 80, flush=True)
