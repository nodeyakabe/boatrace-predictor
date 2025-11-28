#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パフォーマンステストスクリプト

キャッシュ有効時と無効時の処理時間を比較
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.race_predictor import RacePredictor


def get_recent_race_date():
    """最近のレース日を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT race_date FROM races ORDER BY race_date DESC LIMIT 5')
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates


def get_race_ids_for_date(target_date, limit=10):
    """指定日のレースIDを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
        LIMIT ?
    ''', (target_date, limit))
    race_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return race_ids


def test_without_cache(race_ids):
    """キャッシュなしでのテスト"""
    print("\n" + "="*70)
    print("【キャッシュなし】従来版のテスト")
    print("="*70)

    predictor = RacePredictor(use_cache=False)

    start_time = time.time()
    success_count = 0

    for idx, race_id in enumerate(race_ids, 1):
        try:
            predictions = predictor.predict_race(race_id)
            if predictions:
                success_count += 1
            print(f"  [{idx}/{len(race_ids)}] Race ID {race_id}: OK ({len(predictions) if predictions else 0}艇)")
        except Exception as e:
            print(f"  [{idx}/{len(race_ids)}] Race ID {race_id}: エラー - {str(e)[:50]}")

    elapsed = time.time() - start_time

    print(f"\n処理時間: {elapsed:.2f}秒")
    print(f"平均: {elapsed/len(race_ids):.2f}秒/レース")
    print(f"成功: {success_count}/{len(race_ids)}")

    return elapsed


def test_with_cache(race_ids, target_date):
    """キャッシュありでのテスト"""
    print("\n" + "="*70)
    print("【キャッシュあり】高速化版のテスト")
    print("="*70)

    predictor = RacePredictor(use_cache=True)

    # データをプリロード
    print("データを一括ロード中...")
    load_start = time.time()
    predictor.batch_loader.load_daily_data(target_date)
    load_time = time.time() - load_start
    print(f"ロード完了: {load_time:.2f}秒")

    start_time = time.time()
    success_count = 0

    for idx, race_id in enumerate(race_ids, 1):
        try:
            predictions = predictor.predict_race(race_id)
            if predictions:
                success_count += 1
            print(f"  [{idx}/{len(race_ids)}] Race ID {race_id}: OK ({len(predictions) if predictions else 0}艇)")
        except Exception as e:
            print(f"  [{idx}/{len(race_ids)}] Race ID {race_id}: エラー - {str(e)[:50]}")

    elapsed = time.time() - start_time
    total_time = load_time + elapsed

    print(f"\n予想生成時間: {elapsed:.2f}秒")
    print(f"総時間(ロード込み): {total_time:.2f}秒")
    print(f"平均: {elapsed/len(race_ids):.2f}秒/レース")
    print(f"成功: {success_count}/{len(race_ids)}")

    return total_time, load_time, elapsed


def main():
    print("="*70)
    print("予想生成パフォーマンステスト")
    print("="*70)

    # 最近のレース日を取得
    dates = get_recent_race_date()
    print("\n利用可能なレース日:")
    for i, date in enumerate(dates, 1):
        print(f"  {i}. {date}")

    # 最新の日付を使用
    target_date = dates[0]
    print(f"\nテスト対象日: {target_date}")

    # テスト用のレースIDを取得（1レース）
    race_ids = get_race_ids_for_date(target_date, limit=1)
    print(f"テストレース数: {len(race_ids)}レース")

    if not race_ids:
        print("テスト対象のレースが見つかりませんでした")
        return

    # キャッシュなしでテスト
    time_without_cache = test_without_cache(race_ids)

    # キャッシュありでテスト
    time_with_cache, load_time, predict_time = test_with_cache(race_ids, target_date)

    # 結果比較
    print("\n" + "="*70)
    print("【結果比較】")
    print("="*70)
    print(f"キャッシュなし: {time_without_cache:.2f}秒 ({time_without_cache/len(race_ids):.2f}秒/レース)")
    print(f"キャッシュあり: {time_with_cache:.2f}秒 ({predict_time/len(race_ids):.2f}秒/レース)")
    print(f"  - データロード: {load_time:.2f}秒")
    print(f"  - 予想生成: {predict_time:.2f}秒")

    speedup = time_without_cache / time_with_cache
    reduction = (1 - time_with_cache / time_without_cache) * 100

    print(f"\n高速化率: {speedup:.2f}倍")
    print(f"処理時間削減: {reduction:.1f}%")

    # 144レース想定での推定時間
    print(f"\n【144レース(1日分)の推定時間】")
    print(f"キャッシュなし: {time_without_cache/len(race_ids)*144/60:.1f}分")
    print(f"キャッシュあり: {time_with_cache/len(race_ids)*144/60:.1f}分")
    print("="*70)


if __name__ == "__main__":
    main()
