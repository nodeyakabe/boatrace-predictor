#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
診断スクリプト：どこがボトルネックか特定
"""
import sys
import os
import time

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH


def get_latest_race():
    """最新のレース情報を取得"""
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
    return row if row else (None, None, None, None)


def test_imports():
    """インポートテスト"""
    print("\n" + "="*70)
    print("【1】インポートテスト")
    print("="*70)

    start = time.time()
    try:
        from src.database.batch_data_loader import BatchDataLoader
        print(f"  BatchDataLoader: OK ({time.time()-start:.2f}秒)")

        start = time.time()
        from src.analysis.extended_scorer import ExtendedScorer
        print(f"  ExtendedScorer: OK ({time.time()-start:.2f}秒)")

        start = time.time()
        from src.analysis.race_predictor import RacePredictor
        print(f"  RacePredictor: OK ({time.time()-start:.2f}秒)")

        return True
    except Exception as e:
        print(f"  エラー: {e}")
        return False


def test_batch_loader(target_date):
    """BatchDataLoaderのロード時間"""
    print("\n" + "="*70)
    print("【2】BatchDataLoader ロード時間")
    print("="*70)

    from src.database.batch_data_loader import BatchDataLoader

    loader = BatchDataLoader(DATABASE_PATH)

    start = time.time()
    try:
        loader.load_daily_data(target_date)
        elapsed = time.time() - start

        print(f"  ロード時間: {elapsed:.2f}秒")

        cache_keys = list(loader._cache.keys())
        print(f"  キャッシュキー数: {len(cache_keys)}")
        for key in cache_keys:
            data = loader._cache[key]
            if isinstance(data, dict):
                print(f"    {key}: {len(data)} 件")

        return loader
    except Exception as e:
        elapsed = time.time() - start
        print(f"  エラー ({elapsed:.2f}秒): {e}")
        import traceback
        traceback.print_exc()
        return None


def test_race_predictor_init():
    """RacePredictor初期化時間"""
    print("\n" + "="*70)
    print("【3】RacePredictor 初期化時間")
    print("="*70)

    from src.analysis.race_predictor import RacePredictor

    # キャッシュなし
    start = time.time()
    try:
        predictor_no_cache = RacePredictor(use_cache=False)
        elapsed = time.time() - start
        print(f"  キャッシュなし: {elapsed:.2f}秒")
    except Exception as e:
        print(f"  エラー: {e}")

    # キャッシュあり
    start = time.time()
    try:
        predictor_with_cache = RacePredictor(use_cache=True)
        elapsed = time.time() - start
        print(f"  キャッシュあり: {elapsed:.2f}秒")
        return predictor_with_cache
    except Exception as e:
        print(f"  エラー: {e}")
        return None


def test_prediction(race_id, race_date, predictor):
    """予想生成時間（キャッシュあり）"""
    print("\n" + "="*70)
    print("【4】予想生成時間テスト")
    print("="*70)

    if not predictor:
        print("  Predictorがありません")
        return

    # データをプリロード
    print(f"  対象: Race ID {race_id} ({race_date})")
    print("  データを一括ロード中...")

    load_start = time.time()
    try:
        predictor.batch_loader.load_daily_data(race_date)
        load_elapsed = time.time() - load_start
        print(f"    ロード時間: {load_elapsed:.2f}秒")
    except Exception as e:
        print(f"    ロードエラー: {e}")
        return

    # 予想生成
    print("  予想を生成中...")
    start = time.time()
    try:
        predictions = predictor.predict_race(race_id)
        elapsed = time.time() - start

        if predictions:
            print(f"    予想生成成功: {len(predictions)}艇")
            print(f"    予想生成時間: {elapsed:.2f}秒")
            print(f"    総時間: {load_elapsed + elapsed:.2f}秒")

            # 144レース推定
            total_for_144 = (load_elapsed + elapsed * 144) / 60
            print(f"    144レース推定: {total_for_144:.1f}分")
        else:
            print(f"    予想生成失敗 ({elapsed:.2f}秒)")

    except Exception as e:
        elapsed = time.time() - start
        print(f"    エラー ({elapsed:.2f}秒): {str(e)[:100]}")
        import traceback
        traceback.print_exc()


def main():
    print("="*70)
    print("パフォーマンス診断スクリプト")
    print("="*70)

    # 1. インポート
    if not test_imports():
        return

    # 2. テスト対象レースを取得
    race_id, race_date, venue_code, race_number = get_latest_race()
    if not race_id:
        print("\nレースが見つかりませんでした")
        return

    print(f"\nテスト対象: {race_date} {venue_code} {race_number}R (ID: {race_id})")

    # 3. BatchDataLoaderテスト
    loader = test_batch_loader(race_date)

    # 4. RacePredictorテスト
    predictor = test_race_predictor_init()

    # 5. 予想生成テスト
    test_prediction(race_id, race_date, predictor)

    print("\n" + "="*70)
    print("診断完了")
    print("="*70)


if __name__ == "__main__":
    main()
