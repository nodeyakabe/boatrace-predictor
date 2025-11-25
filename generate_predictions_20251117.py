"""
2025-11-17の予測を生成（的中率検証用）
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

def main():
    print("=" * 80, flush=True)
    print("2025-11-17 予測生成（的中率検証用）", flush=True)
    print("=" * 80, flush=True)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    target_date = '2025-11-17'

    # レース数を取得
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date = ?
    """, (target_date,))

    total_races = cursor.fetchone()[0]
    print(f"\n全レース数: {total_races}", flush=True)

    # 全レースを取得
    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
    """, (target_date,))

    races = cursor.fetchall()
    conn.close()

    # 予測を生成
    predictor = RacePredictor()
    data_manager = DataManager()

    success = 0
    errors = 0
    start_time = time.time()
    batch_start = start_time

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

            # 10レースごとに進捗表示
            if i % 10 == 0 or i == total_races:
                batch_elapsed = time.time() - batch_start
                total_elapsed = time.time() - start_time
                rate = i / total_elapsed if total_elapsed > 0 else 0
                remaining = (total_races - i) / rate if rate > 0 else 0

                venue_str = f"{int(venue_code):02d}" if venue_code else "??"
                race_str = f"{int(race_number):2d}" if race_number else "??"

                print(f"進捗: {i:3d}/{total_races} ({i/total_races*100:5.1f}%) | "
                      f"成功: {success:3d}, エラー: {errors} | "
                      f"残り時間: {remaining/60:4.1f}分", flush=True)

                batch_start = time.time()

        except Exception as e:
            errors += 1
            print(f"  エラー (race_id={race_id}): {e}", flush=True)

    elapsed_total = time.time() - start_time
    print("-" * 80, flush=True)
    print(f"\n生成完了: 成功 {success}, エラー {errors}", flush=True)
    print(f"処理時間: {elapsed_total:.1f}秒 ({elapsed_total/60:.1f}分)", flush=True)

    print("\n" + "=" * 80, flush=True)
    print("完了", flush=True)
    print("=" * 80, flush=True)


if __name__ == "__main__":
    main()
