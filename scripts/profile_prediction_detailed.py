#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測処理の詳細プロファイリング

各処理ステップの実行時間を詳細に計測
"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import time
import sqlite3
import warnings
from pathlib import Path

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor


def profile_single_race(race_id: int):
    """1レースの予測を詳細にプロファイリング"""

    timings = {}

    # Predictor初期化
    t0 = time.time()
    predictor = RacePredictor(use_cache=True)
    timings['predictor_init'] = time.time() - t0

    # BatchDataLoaderにデータをロード
    t0 = time.time()
    if predictor.batch_loader:
        predictor.batch_loader.load_daily_data('2025-01-01')
    timings['batch_loader'] = time.time() - t0

    # 予測実行（内部をトレース）
    t_total = time.time()

    # predict_race内部の各ステップを手動で計測
    # 実際にはpredict_raceメソッド内にタイミングコードを追加する必要がある
    # ここでは全体時間のみ計測
    predictions = predictor.predict_race(race_id)

    timings['predict_race_total'] = time.time() - t_total

    return timings, predictions


def main():
    print("=" * 80)
    print("予測処理詳細プロファイリング")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # テスト用レースを1件取得
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date = '2025-01-01'
        ORDER BY r.venue_code, r.race_number
        LIMIT 1
    """)

    race = cursor.fetchone()
    conn.close()

    if not race:
        print("テスト用レースが見つかりません")
        return

    race_id = race[0]
    print(f"テスト対象レースID: {race_id}")
    print()

    # プロファイリング実行
    timings, predictions = profile_single_race(race_id)

    print("=" * 80)
    print("タイミング結果")
    print("=" * 80)
    for key, value in timings.items():
        print(f"{key:30s}: {value:8.3f}秒")

    print()
    print(f"予測結果: {len(predictions) if predictions else 0}件")
    print()

    # より詳細な分析のため、cProfileを使用
    print("=" * 80)
    print("cProfileによる詳細分析（上位20件）")
    print("=" * 80)

    import cProfile
    import pstats
    from io import StringIO

    profiler = cProfile.Profile()

    # BatchDataLoaderにデータをロード済みの状態で計測
    predictor = RacePredictor(use_cache=True)
    if predictor.batch_loader:
        predictor.batch_loader.load_daily_data('2025-01-01')

    profiler.enable()
    predictions = predictor.predict_race(race_id)
    profiler.disable()

    s = StringIO()
    stats = pstats.Stats(profiler, stream=s)
    stats.strip_dirs()
    stats.sort_stats('cumulative')
    stats.print_stats(20)

    print(s.getvalue())

    print()
    print("=" * 80)
    print("次のステップ:")
    print("  1. 上記の結果から最も時間がかかっている関数を特定")
    print("  2. その関数内部をさらに最適化")
    print("=" * 80)


if __name__ == "__main__":
    main()
