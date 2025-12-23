#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測速度テスト（最適化版検証）

モーター分析・選手分析の両方をバッチ化した最適化版の速度を検証
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


def main():
    print("=" * 80)
    print("最適化版 予測速度テスト")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # 2025年1月1日のレースを10件取得
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2025-01-10'
        ORDER BY r.race_date, r.venue_code, r.race_number
        LIMIT 10
    """)

    races = cursor.fetchall()
    conn.close()

    if not races:
        print("テスト用レースが見つかりません")
        return

    print(f"テスト対象: {len(races)}レース")
    print()

    # 予測実行
    predictor = RacePredictor(use_cache=True)

    # BatchDataLoaderにデータをロード（最適化のため）
    if predictor.batch_loader:
        # テスト対象の日付範囲（2025-01-01～2025-01-09）をロード
        for i in range(1, 10):
            date_str = f'2025-01-{i:02d}'
            predictor.batch_loader.load_daily_data(date_str)

    start_time = time.time()
    succeeded = 0
    failed = 0

    for race_id, venue_code, race_num in races:
        try:
            predictions = predictor.predict_race(race_id)
            if predictions and len(predictions) >= 6:
                succeeded += 1
                print(f"✓ レースID {race_id}: 成功", flush=True)
            else:
                failed += 1
                print(f"✗ レースID {race_id}: 失敗（予測数不足）", flush=True)
        except Exception as e:
            failed += 1
            print(f"✗ レースID {race_id}: エラー - {str(e)[:50]}", flush=True)

    elapsed = time.time() - start_time

    print()
    print("=" * 80)
    print("テスト結果")
    print("=" * 80)
    print(f"処理時間: {elapsed:.2f}秒")
    print(f"成功: {succeeded}件")
    print(f"失敗: {failed}件")
    print(f"平均: {elapsed/len(races):.3f}秒/レース")
    print(f"速度: {len(races)/(elapsed/60):.1f}レース/分")
    print()

    # 並列処理時の推定
    workers = 4
    estimated_parallel = (len(races)/(elapsed/60)) * workers
    print(f"4並列時の推定速度: {estimated_parallel:.1f}レース/分")
    print(f"17,131レースの推定時間: {17131/estimated_parallel:.1f}分 ({17131/estimated_parallel/60:.1f}時間)")
    print("=" * 80)


if __name__ == "__main__":
    main()
