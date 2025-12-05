"""
全レースをバッチで順次再生成
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
    print("全レース予測再生成（バッチ処理）", flush=True)
    print("=" * 80, flush=True)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 全レース数を取得
    target_date = '2025-11-19'
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

    # 予測を再生成
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
                      f"バッチ時間: {batch_elapsed:4.1f}秒 | "
                      f"残り時間: {remaining/60:4.1f}分 | "
                      f"最終: 会場{venue_str} {race_str}R", flush=True)

                batch_start = time.time()

        except Exception as e:
            errors += 1
            print(f"  エラー (race_id={race_id}): {e}")

    elapsed_total = time.time() - start_time
    print("-" * 80)
    print(f"\n再生成完了: 成功 {success}, エラー {errors}")
    print(f"処理時間: {elapsed_total:.1f}秒 ({elapsed_total/60:.1f}分)")

    # 結果確認
    print("\n" + "=" * 80)
    print("予測分布確認")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pit_number, COUNT(*) as count
        FROM race_predictions
        WHERE rank_prediction = 1
          AND race_id IN (SELECT id FROM races WHERE race_date = ?)
        GROUP BY pit_number
        ORDER BY pit_number
    """, (target_date,))

    predictions = cursor.fetchall()
    total = sum(p[1] for p in predictions)

    print(f"\n1着予測の分布（{total}レース）:")
    for pit, count in predictions:
        pct = count / total * 100 if total > 0 else 0
        print(f"  {pit}号艇: {count:3d}回 ({pct:5.1f}%)")

    print("\n参考: 実際の全国平均勝率")
    print("  1号艇: 約 55%")
    print("  2号艇: 約 14%")
    print("  3号艇: 約 12%")
    print("  4号艇: 約 10%")
    print("  5号艇: 約  6%")
    print("  6号艇: 約  3%")

    conn.close()

    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
