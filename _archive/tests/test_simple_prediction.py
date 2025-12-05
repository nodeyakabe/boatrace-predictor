#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
簡易予想生成テスト

1レースの予想生成にかかる時間を測定
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


def get_latest_race_id():
    """最新のレースIDを1件取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, race_date, venue_code, race_number
        FROM races
        ORDER BY race_date DESC, venue_code, race_number DESC
        LIMIT 1
    ''')
    row = cursor.fetchone()
    conn.close()

    if row:
        return row[0], row[1], row[2], row[3]
    return None, None, None, None


def main():
    print("="*70)
    print("簡易予想生成テスト（1レース）")
    print("="*70)

    race_id, race_date, venue_code, race_number = get_latest_race_id()

    if not race_id:
        print("レースが見つかりませんでした")
        return

    print(f"\nテスト対象: {race_date} {venue_code} {race_number}R (ID: {race_id})")

    # キャッシュなしでテスト
    print("\n" + "="*70)
    print("【キャッシュなし】")
    print("="*70)

    predictor_no_cache = RacePredictor(use_cache=False)

    start = time.time()
    try:
        predictions = predictor_no_cache.predict_race(race_id)
        elapsed = time.time() - start

        if predictions:
            print(f"✓ 予想生成成功: {len(predictions)}艇")
            print(f"  処理時間: {elapsed:.2f}秒")
        else:
            print("✗ 予想生成失敗")
    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ エラー: {str(e)[:100]}")
        print(f"  処理時間: {elapsed:.2f}秒")
        import traceback
        traceback.print_exc()

    # キャッシュありでテスト
    print("\n" + "="*70)
    print("【キャッシュあり】")
    print("="*70)

    predictor_with_cache = RacePredictor(use_cache=True)

    # データをプリロード
    print("データを一括ロード中...")
    load_start = time.time()
    predictor_with_cache.batch_loader.load_daily_data(race_date)
    load_elapsed = time.time() - load_start
    print(f"  ロード時間: {load_elapsed:.2f}秒")

    start = time.time()
    try:
        predictions = predictor_with_cache.predict_race(race_id)
        elapsed = time.time() - start

        if predictions:
            print(f"✓ 予想生成成功: {len(predictions)}艇")
            print(f"  予想生成時間: {elapsed:.2f}秒")
            print(f"  総時間(ロード込み): {load_elapsed + elapsed:.2f}秒")
        else:
            print("✗ 予想生成失敗")
    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ エラー: {str(e)[:100]}")
        print(f"  予想生成時間: {elapsed:.2f}秒")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
