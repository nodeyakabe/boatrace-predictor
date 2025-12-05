"""
修正後の予測ロジックで予想を再生成
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor
from src.database.data_manager import DataManager

def regenerate():
    print("=" * 60)
    print("予測を再生成")
    print("=" * 60)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 今日のレースを取得
    target_date = '2025-11-19'
    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
    """, (target_date,))

    races = cursor.fetchall()
    print(f"\n対象レース: {len(races)}件")

    # 既存の予測を削除
    cursor.execute("""
        DELETE FROM race_predictions
        WHERE race_id IN (SELECT id FROM races WHERE race_date = ?)
    """, (target_date,))
    deleted = cursor.rowcount
    conn.commit()
    print(f"既存予測削除: {deleted}件")

    conn.close()

    # 予測を再生成
    predictor = RacePredictor()
    data_manager = DataManager()

    success = 0
    errors = 0

    for race_id, venue_code, race_number in races:
        try:
            predictions = predictor.predict_race(race_id)
            if predictions:
                if data_manager.save_race_predictions(race_id, predictions):
                    success += 1
                else:
                    errors += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1

    print(f"\n再生成結果: 成功 {success}, エラー {errors}")

    # 結果確認
    print("\n[予測分布確認]")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pit_number, COUNT(*) as count
        FROM race_predictions
        WHERE rank_prediction = 1
          AND race_id IN (SELECT id FROM races WHERE race_date = ?)
        GROUP BY pit_number
        ORDER BY count DESC
    """, (target_date,))

    predictions = cursor.fetchall()
    total = sum(p[1] for p in predictions)

    for pit, count in predictions:
        pct = count / total * 100 if total > 0 else 0
        print(f"  {pit}号艇: {count}回 ({pct:.1f}%)")

    # サンプルレースのスコア確認
    print("\n[サンプルレースのスコア]")
    cursor.execute("""
        SELECT
            rp.pit_number,
            rp.total_score,
            rp.rank_prediction,
            e.racer_name
        FROM race_predictions rp
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        WHERE rp.race_id = (
            SELECT id FROM races WHERE race_date = ? LIMIT 1
        )
        ORDER BY rp.rank_prediction
    """, (target_date,))

    sample = cursor.fetchall()
    if sample:
        print("  順位 | 枠 | 選手名 | スコア")
        print("  " + "-" * 40)
        for pit, score, rank, name in sample:
            print(f"  {rank}位 | {pit}号艇 | {name:8s} | {score:.1f}")

    conn.close()

    print("\n" + "=" * 60)
    print("完了")
    print("=" * 60)


if __name__ == "__main__":
    regenerate()
