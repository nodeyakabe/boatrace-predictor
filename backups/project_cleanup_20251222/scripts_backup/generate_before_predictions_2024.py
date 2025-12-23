#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年の直前予想（before）のみを生成するスクリプト
use_beforeinfo=True で展示タイム・直前情報を使った予想
"""
import sys
import os
import io
import sqlite3
from datetime import datetime

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

def get_2024_races():
    """2024年の全レースIDを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date LIKE '2024%'
        ORDER BY race_date, venue_code, race_number
    ''')

    races = cursor.fetchall()
    conn.close()
    return races

def main():
    print("=" * 70)
    print("2024年 直前予想（before）生成")
    print("use_beforeinfo=True（展示タイム・直前情報あり）")
    print("=" * 70)

    races = get_2024_races()
    print(f"対象レース数: {len(races):,}レース")
    print()

    predictor = RacePredictor()
    data_manager = DataManager()

    success_count = 0
    failed_count = 0
    skipped_count = 0

    start_time = datetime.now()
    last_date = None

    for i, (race_id, race_date, venue_code, race_number) in enumerate(races, 1):
        # 日付が変わったら表示
        if race_date != last_date:
            if last_date:
                print()  # 改行
            print(f"\n[{race_date}]", end=' ')
            last_date = race_date

        # 既存のbefore予測をチェック
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
        ''', (race_id,))
        exists = cursor.fetchone()[0] > 0
        conn.close()

        if exists:
            skipped_count += 1
            print('.', end='', flush=True)
            continue

        # 直前予想生成
        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if predictions:
                # prediction_type='before'でDB保存
                data_manager.save_race_predictions(
                    race_id, predictions, prediction_type='before'
                )
                success_count += 1
                print('o', end='', flush=True)
            else:
                failed_count += 1
                print('x', end='', flush=True)
        except Exception as e:
            failed_count += 1
            print('X', end='', flush=True)

        # 100レースごとに進捗表示
        if i % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            avg_time = elapsed / i
            remaining = avg_time * (len(races) - i)
            print(f" [{i:,}/{len(races):,}] 成功:{success_count} 失敗:{failed_count} スキップ:{skipped_count} 残り:{remaining/60:.1f}分", end='')

    print("\n")
    print("=" * 70)
    print("完了")
    print("=" * 70)
    print(f"総処理時間: {(datetime.now() - start_time).total_seconds()/60:.1f}分")
    print(f"総レース数: {len(races):,}レース")
    print(f"生成成功: {success_count:,}レース")
    print(f"生成失敗: {failed_count:,}レース")
    print(f"既存スキップ: {skipped_count:,}レース")
    print(f"成功率: {success_count/(success_count+failed_count)*100 if (success_count+failed_count) > 0 else 0:.1f}%")
    print("=" * 70)

if __name__ == '__main__':
    main()
