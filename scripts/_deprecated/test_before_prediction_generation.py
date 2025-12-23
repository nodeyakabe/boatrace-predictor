#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
before予測生成のテストスクリプト

2020年の最初の10レースで動作確認
"""
import sys
import os
import io
import sqlite3

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.race_predictor import RacePredictor
from src.database.data_manager import DataManager
from config.settings import DATABASE_PATH


def test_prediction_generation():
    """予測生成のテスト"""

    print("=" * 70)
    print("before予測生成テスト")
    print("=" * 70)

    # 1. 初期化テスト
    print("\n[1] 初期化テスト")
    try:
        predictor = RacePredictor()
        data_manager = DataManager()
        print("[OK] RacePredictor初期化成功")
        print("[OK] DataManager初期化成功")
    except Exception as e:
        print(f"[ERROR] 初期化失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 2. 2020年の最初の10レースを取得
    print("\n[2] テスト対象レース取得")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2020-12-31'
          AND EXISTS (SELECT 1 FROM race_details WHERE race_id = r.id)
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id)
          AND EXISTS (
              SELECT 1 FROM entries
              WHERE race_id = r.id
              GROUP BY race_id
              HAVING COUNT(DISTINCT pit_number) = 6
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 10
    ''')

    test_races = cursor.fetchall()
    conn.close()

    if len(test_races) == 0:
        print("[ERROR] テスト対象レースが見つかりません")
        return False

    print(f"[OK] テスト対象: {len(test_races)}件")
    for race_id, race_date, venue_code, race_number in test_races:
        print(f"  - {race_date} {venue_code}場 {race_number}R (ID: {race_id})")

    # 3. 予測生成テスト
    print("\n[3] 予測生成テスト")
    success_count = 0
    fail_count = 0

    for race_id, race_date, venue_code, race_number in test_races:
        try:
            print(f"  {race_date} {venue_code}場 {race_number}R ... ", end='', flush=True)

            # 予測実行
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if predictions:
                # DB保存
                data_manager.save_race_predictions(
                    race_id, predictions, prediction_type='before'
                )
                print("[OK]")
                success_count += 1
            else:
                print("[ERROR] 予測結果がNone")
                fail_count += 1

        except Exception as e:
            print(f"[ERROR] {str(e)[:50]}")
            fail_count += 1

    # 4. 結果確認
    print("\n[4] 結果確認")
    print(f"成功: {success_count}/10件")
    print(f"失敗: {fail_count}/10件")

    if success_count >= 8:  # 80%以上成功でOK
        print("\n[OK] テスト合格（80%以上成功）")
        print("本番実行を開始できます")
        return True
    else:
        print("\n[ERROR] テスト不合格（成功率が低い）")
        print("エラーを確認してください")
        return False


if __name__ == '__main__':
    result = test_prediction_generation()
    sys.exit(0 if result else 1)
