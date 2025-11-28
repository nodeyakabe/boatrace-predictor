#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予想生成のプロファイリング
"""
import sys
import os
import time
import cProfile
import pstats
from io import StringIO

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor


def get_test_race():
    """テスト用レースを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, race_date
        FROM races
        ORDER BY race_date DESC
        LIMIT 1
    ''')
    row = cursor.fetchone()
    conn.close()
    return row if row else (None, None)


def profile_prediction():
    """予想生成をプロファイル"""
    race_id, race_date = get_test_race()

    if not race_id:
        print("レースが見つかりませんでした")
        return

    print(f"テスト対象: Race ID {race_id} ({race_date})")

    predictor = RacePredictor(use_cache=True)

    # データロード
    print("\nデータをロード中...")
    start = time.time()
    predictor.batch_loader.load_daily_data(race_date)
    print(f"ロード時間: {time.time() - start:.2f}秒")

    # プロファイリング実行
    print("\n予想を生成中（プロファイリング中）...")

    profiler = cProfile.Profile()
    profiler.enable()

    start = time.time()
    predictions = predictor.predict_race(race_id)
    elapsed = time.time() - start

    profiler.disable()

    print(f"予想生成時間: {elapsed:.2f}秒")
    print(f"結果: {len(predictions) if predictions else 0}艇\n")

    # プロファイル結果を表示（上位20件）
    s = StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)

    print("="*70)
    print("【プロファイル結果 - 累積時間トップ20】")
    print("="*70)
    print(s.getvalue())


if __name__ == "__main__":
    profile_prediction()
