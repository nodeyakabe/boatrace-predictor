#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年の事前予想・直前予想を両方生成するスクリプト
"""
import sys
import os
import io
import sqlite3
from datetime import datetime
import subprocess

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

def get_2024_dates():
    """2024年のレースがある日付リストを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT race_date
        FROM races
        WHERE race_date LIKE '2024%'
        ORDER BY race_date
    ''')

    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def get_races_for_date(date):
    """指定日の全レースIDを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, venue_code, race_number
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
    ''', (date,))

    races = cursor.fetchall()
    conn.close()
    return races

def main():
    print("=" * 70)
    print("2024年 事前予想・直前予想 両方生成")
    print("=" * 70)

    dates = get_2024_dates()
    print(f"対象日数: {len(dates)}日")
    print(f"期間: {dates[0]} 〜 {dates[-1]}")
    print()

    predictor = RacePredictor()
    data_manager = DataManager()

    total_races = 0
    advance_success = 0
    advance_failed = 0
    before_success = 0
    before_failed = 0

    start_time = datetime.now()

    for i, date in enumerate(dates, 1):
        print(f"\n[{i}/{len(dates)}] {date} を処理中...")

        races = get_races_for_date(date)
        if not races:
            print(f"  レースなし")
            continue

        total_races += len(races)
        date_advance_ok = 0
        date_advance_ng = 0
        date_before_ok = 0
        date_before_ng = 0

        for race_id, venue_code, race_number in races:
            # 1. 事前予想（use_beforeinfo=False）
            try:
                predictions_advance = predictor.predict_race(race_id, use_beforeinfo=False)
                if predictions_advance:
                    # prediction_type='advance'でDB保存
                    data_manager.save_race_predictions(
                        race_id, predictions_advance, prediction_type='advance'
                    )
                    date_advance_ok += 1
                    advance_success += 1
                else:
                    date_advance_ng += 1
                    advance_failed += 1
            except Exception as e:
                date_advance_ng += 1
                advance_failed += 1

            # 2. 直前予想（use_beforeinfo=True）
            try:
                predictions_before = predictor.predict_race(race_id, use_beforeinfo=True)
                if predictions_before:
                    # prediction_type='before'でDB保存
                    data_manager.save_race_predictions(
                        race_id, predictions_before, prediction_type='before'
                    )
                    date_before_ok += 1
                    before_success += 1
                else:
                    date_before_ng += 1
                    before_failed += 1
            except Exception as e:
                date_before_ng += 1
                before_failed += 1

        print(f"  {len(races)}レース: 事前({date_advance_ok}成功/{date_advance_ng}失敗), 直前({date_before_ok}成功/{date_before_ng}失敗)")

        # 進捗表示
        elapsed = (datetime.now() - start_time).total_seconds()
        avg_time = elapsed / i
        remaining = avg_time * (len(dates) - i)
        print(f"  進捗: {i}/{len(dates)} ({i/len(dates)*100:.1f}%), 残り推定: {remaining/60:.1f}分")

    print("\n" + "=" * 70)
    print("完了")
    print("=" * 70)
    print(f"総処理時間: {(datetime.now() - start_time).total_seconds()/60:.1f}分")
    print(f"総レース数: {total_races}レース")
    print(f"事前予想: {advance_success}成功, {advance_failed}失敗")
    print(f"直前予想: {before_success}成功, {before_failed}失敗")
    print("=" * 70)

if __name__ == '__main__':
    main()
