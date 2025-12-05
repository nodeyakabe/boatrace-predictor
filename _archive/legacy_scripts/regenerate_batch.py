"""
予測を10レースずつバッチで再生成
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

def regenerate_batch(start_idx=0, batch_size=10):
    print("=" * 80)
    print(f"予測を再生成（バッチ処理: {start_idx}番目から{batch_size}レース）")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 今日のレースを取得
    target_date = '2025-11-19'
    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
        LIMIT ? OFFSET ?
    """, (target_date, batch_size, start_idx))

    races = cursor.fetchall()
    total_races = len(races)

    if total_races == 0:
        print("処理対象のレースがありません")
        conn.close()
        return False

    print(f"\n対象レース: {total_races}件 ({start_idx+1}番目～{start_idx+total_races}番目)")

    # 対象レースの既存予測を削除
    race_ids = [r[0] for r in races]
    placeholders = ','.join('?' * len(race_ids))
    cursor.execute(f"""
        DELETE FROM race_predictions
        WHERE race_id IN ({placeholders})
    """, race_ids)
    deleted = cursor.rowcount
    conn.commit()
    print(f"既存予測削除: {deleted}件")

    conn.close()

    # 予測を再生成
    predictor = RacePredictor()
    data_manager = DataManager()

    success = 0
    errors = 0
    start_time = time.time()

    print("\n予測生成中...")
    print("-" * 80)

    for i, (race_id, venue_code, race_number) in enumerate(races, 1):
        try:
            predictions = predictor.predict_race(race_id)
            if predictions:
                if data_manager.save_race_predictions(race_id, predictions):
                    success += 1
                    venue_str = f"{int(venue_code):02d}" if venue_code else "??"
                    race_str = f"{int(race_number):2d}" if race_number else "??"
                    print(f"  ✓ {start_idx+i:3d}/{start_idx+total_races} 会場{venue_str} {race_str}R (race_id={race_id})")
                else:
                    errors += 1
                    print(f"  ✗ {start_idx+i:3d}/{start_idx+total_races} 保存エラー (race_id={race_id})")
            else:
                errors += 1
                print(f"  ✗ {start_idx+i:3d}/{start_idx+total_races} 予測失敗 (race_id={race_id})")

        except Exception as e:
            errors += 1
            print(f"  ✗ {start_idx+i:3d}/{start_idx+total_races} エラー (race_id={race_id}): {e}")

    elapsed_total = time.time() - start_time
    print("-" * 80)
    print(f"\nバッチ完了: 成功 {success}, エラー {errors}")
    print(f"処理時間: {elapsed_total:.1f}秒")

    return total_races == batch_size  # まだレースが残っているかどうか


if __name__ == "__main__":
    import sys

    start_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    has_more = regenerate_batch(start_idx, batch_size)

    if has_more:
        print(f"\n次のバッチ: python regenerate_batch.py {start_idx + batch_size}")
    else:
        print("\n全バッチ完了")
