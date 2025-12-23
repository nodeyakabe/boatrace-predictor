#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020年データの予測生成テスト（1週間のみ）

本格的な生成前に、少量データでテストを実施
"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import sqlite3
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor


def main():
    print("=" * 80)
    print("2020年データ予測生成テスト（2020-01-01〜2020-01-07）")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2020年1月1〜7日のレースを取得
    cursor.execute("""
        SELECT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2020-01-07'
        ORDER BY r.race_date, r.venue_code, r.race_number
    """)

    races = cursor.fetchall()
    print(f"対象レース数: {len(races)}件")
    print()

    if len(races) == 0:
        print("エラー: 2020年1月1-7日のレースデータが見つかりません")
        conn.close()
        return

    # Predictorを初期化
    try:
        predictor = RacePredictor(use_cache=True)
        print("✓ RacePredictor初期化成功")
    except Exception as e:
        print(f"✗ RacePredictor初期化失敗: {e}")
        conn.close()
        return

    print()
    print("予測生成テスト開始...")
    print()

    succeeded = 0
    failed = 0
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for i, (race_id, race_date, venue_code, race_num) in enumerate(races[:20], 1):  # 最初の20レースのみ
        try:
            # 予測を生成（直前情報なし = advance予測）
            predictions = predictor.predict_race(race_id, use_beforeinfo=False)

            if predictions and len(predictions) >= 6:
                # DBに保存
                cursor.execute(
                    "DELETE FROM race_predictions WHERE race_id = ? AND prediction_type = 'advance'",
                    (race_id,)
                )

                for pred in predictions:
                    cursor.execute("""
                        INSERT INTO race_predictions (
                            race_id, pit_number, rank_prediction, total_score,
                            confidence, racer_name, racer_number, applied_rules,
                            course_score, racer_score, motor_score, kimarite_score,
                            grade_score, prediction_type, generated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        race_id,
                        pred.get('pit_number'),
                        pred.get('rank_prediction'),
                        pred.get('total_score', 0),
                        pred.get('confidence', 'E'),
                        pred.get('racer_name', ''),
                        pred.get('racer_number', ''),
                        str(pred.get('applied_rules', '')),
                        pred.get('course_score', 0),
                        pred.get('racer_score', 0),
                        pred.get('motor_score', 0),
                        pred.get('kimarite_score', 0),
                        pred.get('grade_score', 0),
                        'advance',
                        generated_at
                    ))

                conn.commit()
                succeeded += 1

                # 1位予測の情報を表示
                top_pred = predictions[0]
                print(f"[{i:2}] {race_date} {int(venue_code):02d}R{race_num:2d}: "
                      f"1位予測=艇{top_pred['pit_number']} "
                      f"({top_pred['racer_name']}, {top_pred['confidence']}信頼度) "
                      f"✓")
            else:
                failed += 1
                print(f"[{i:2}] {race_date} {int(venue_code):02d}R{race_num:2d}: 予測失敗（データ不足） ✗")

        except Exception as e:
            failed += 1
            print(f"[{i:2}] {race_date} {int(venue_code):02d}R{race_num:2d}: エラー - {str(e)[:40]} ✗")

    print()
    print("=" * 80)
    print("テスト結果")
    print("=" * 80)
    print(f"成功: {succeeded}件")
    print(f"失敗: {failed}件")
    print(f"成功率: {succeeded/(succeeded+failed)*100:.1f}%" if (succeeded+failed) > 0 else "成功率: 0%")
    print()

    # 保存されたデータを確認
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) as race_count,
               COUNT(*) as prediction_count
        FROM race_predictions
        WHERE race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2020-01-01' AND race_date <= '2020-01-07'
        )
        AND prediction_type = 'advance'
    """)

    race_count, pred_count = cursor.fetchone()
    print(f"DB保存確認: {race_count}レース, {pred_count}件の予測データ")
    print()

    if succeeded > 0:
        print("✓ テスト成功 - 本格的な生成を開始できます")
    else:
        print("✗ テスト失敗 - 問題を解決してから本格生成を実行してください")

    conn.close()


if __name__ == "__main__":
    main()
