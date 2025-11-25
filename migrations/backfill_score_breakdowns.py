"""
既存のrace_predictionsのスコア内訳を再計算して埋める
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor

def backfill_score_breakdowns():
    """既存の予測のスコア内訳を再計算"""

    print("=" * 80)
    print("既存予測のスコア内訳を再計算")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # スコア内訳がないレースを確認
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id)
        FROM race_predictions
        WHERE course_score = 0 AND racer_score = 0 AND motor_score = 0
    """)

    race_count = cursor.fetchone()[0]
    print(f"\nスコア内訳がないレース数: {race_count}")

    if race_count == 0:
        print("すべてのレースにスコア内訳があります")
        conn.close()
        return

    # 対象のレースIDを取得
    cursor.execute("""
        SELECT DISTINCT race_id
        FROM race_predictions
        WHERE course_score = 0 AND racer_score = 0 AND motor_score = 0
        ORDER BY race_id
    """)

    race_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    print(f"\n{len(race_ids)}レースのスコア内訳を再計算します")
    print("この処理には時間がかかる場合があります...")
    print("-" * 80)

    predictor = RacePredictor()
    success_count = 0
    error_count = 0

    for i, race_id in enumerate(race_ids, 1):
        try:
            # 予測を再生成
            predictions = predictor.predict_race(race_id)

            if predictions:
                # データベースに保存（既存のrace_predictionsを更新）
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()

                for pred in predictions:
                    cursor.execute("""
                        UPDATE race_predictions
                        SET
                            course_score = ?,
                            racer_score = ?,
                            motor_score = ?,
                            kimarite_score = ?,
                            grade_score = ?
                        WHERE race_id = ? AND pit_number = ?
                    """, (
                        pred['course_score'],
                        pred['racer_score'],
                        pred['motor_score'],
                        pred['kimarite_score'],
                        pred['grade_score'],
                        race_id,
                        pred['pit_number']
                    ))

                conn.commit()
                conn.close()
                success_count += 1
            else:
                error_count += 1

            if i % 100 == 0 or i == len(race_ids):
                print(f"進捗: {i}/{len(race_ids)} ({i/len(race_ids)*100:.1f}%) | "
                      f"成功: {success_count}, エラー: {error_count}")

        except Exception as e:
            error_count += 1
            if error_count <= 5:  # 最初の5件のみ表示
                print(f"エラー (race_id={race_id}): {e}")

    print("-" * 80)
    print(f"\n完了: 成功 {success_count}, エラー {error_count}")
    print("=" * 80)


if __name__ == "__main__":
    backfill_score_breakdowns()
