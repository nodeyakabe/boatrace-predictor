# -*- coding: utf-8 -*-
"""
本日の予測を再生成（新スコアリングシステム対応）
"""
import sys
import io
import os
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor
from src.database.data_manager import DataManager

def regenerate():
    print("=" * 60)
    print("本日の予測を再生成（新スコアリングシステム）")
    print("=" * 60)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 今日のレースを取得
    target_date = datetime.now().strftime('%Y-%m-%d')
    print(f"対象日: {target_date}")

    cursor.execute("""
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
    """, (target_date,))

    races = cursor.fetchall()
    print(f"\n対象レース: {len(races)}件")

    if not races:
        print("本日のレースが見つかりません")
        conn.close()
        return

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

    total = len(races)
    for i, (race_id, venue_code, race_number) in enumerate(races, 1):
        if i % 20 == 0:
            print(f"  進捗: {i}/{total} ({i*100//total}%)")

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
            if errors <= 3:  # 最初の3件だけエラー表示
                print(f"  エラー [{venue_code} {race_number}R]: {e}")

    print(f"\n再生成結果: 成功 {success}, エラー {errors}")

    # 結果確認
    print("\n[予測分布確認 - 1位予測の艇番]")
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
        bar = "█" * int(pct / 2)
        print(f"  {pit}号艇: {count:3d}回 ({pct:5.1f}%) {bar}")

    conn.close()

    print("\n" + "=" * 60)
    print("完了 - UIで「レース予想一覧」を確認してください")
    print("=" * 60)


if __name__ == "__main__":
    regenerate()
