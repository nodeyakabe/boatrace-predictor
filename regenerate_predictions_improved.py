"""
修正後の予測ロジックで予想を再生成（進捗表示付き）
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

def regenerate():
    print("=" * 80)
    print("予測を再生成（最新ロジック適用）")
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
    """, (target_date,))

    races = cursor.fetchall()
    total_races = len(races)
    print(f"\n対象レース: {total_races}件")

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
    start_time = time.time()

    print("\n予測生成中...")
    print("-" * 80)

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

            # 進捗表示（10レースごと）
            if i % 10 == 0 or i == total_races:
                elapsed = time.time() - start_time
                rate = i / elapsed
                remaining = (total_races - i) / rate if rate > 0 else 0
                print(f"進捗: {i}/{total_races} ({i/total_races*100:.1f}%) | "
                      f"成功: {success}, エラー: {errors} | "
                      f"残り時間: {remaining:.0f}秒")

        except Exception as e:
            errors += 1
            print(f"エラー (race_id={race_id}): {e}")

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

    # サンプルレースのスコア確認
    print("\n" + "=" * 80)
    print("サンプルレースのスコア")
    print("=" * 80)

    cursor.execute("""
        SELECT
            rp.pit_number,
            rp.total_score,
            rp.rank_prediction,
            e.racer_name,
            rp.confidence
        FROM race_predictions rp
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        WHERE rp.race_id = (
            SELECT id FROM races WHERE race_date = ? LIMIT 1
        )
        ORDER BY rp.rank_prediction
    """, (target_date,))

    sample = cursor.fetchall()
    if sample:
        print("\n最初のレース:")
        print("  順位 | 枠 | 選手名 | スコア | 信頼度")
        print("  " + "-" * 50)
        for pit, score, rank, name, confidence in sample:
            print(f"  {rank:2d}位 | {pit}号艇 | {name:8s} | {score:5.1f} | {confidence}")

    conn.close()

    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)


if __name__ == "__main__":
    regenerate()
