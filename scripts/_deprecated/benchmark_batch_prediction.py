#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
バッチ予測のベンチマーク: predict_races_batch() vs predict_race() の速度比較

2025-01-02 の全レースで計測
"""
import sys
import os
import io
import time
import sqlite3
import warnings

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.prediction.predictor_helpers import create_standard_predictor
from config.settings import DATABASE_PATH


def get_day_races(target_date: str):
    """指定日のレースIDリストを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date = ?
        AND EXISTS (SELECT 1 FROM entries e WHERE e.race_id = races.id)
        ORDER BY venue_code, race_number
    ''', (target_date,))
    races = cursor.fetchall()
    conn.close()
    return races


def main():
    target_date = '2025-01-03'
    races = get_day_races(target_date)
    race_ids = [r[0] for r in races]

    print(f"=" * 70)
    print(f"バッチ予測ベンチマーク: {target_date}")
    print(f"レース数: {len(race_ids)}")
    print(f"=" * 70)

    if not race_ids:
        print("対象レースがありません")
        return

    # Predictor 初期化
    print("\nPredictor初期化中...")
    t0 = time.time()
    predictor = create_standard_predictor(use_cache=True)
    init_time = time.time() - t0
    print(f"初期化完了: {init_time:.1f}秒")

    # ==== ウォームアップ（モデル読み込み + DBキャッシュ構築） ====
    print("\nウォームアップ中（モデル読み込み + キャッシュ構築）...")
    predictor.batch_loader.load_daily_data(target_date)
    # ダミー予測でモデルを読み込ませる
    _ = predictor.predict_race(race_ids[0], use_beforeinfo=False)
    predictor.race_data_cache.clear_all()
    print("ウォームアップ完了")

    # ==== 従来方式: 1レースずつ ====
    print(f"\n--- 従来方式 (predict_race x{len(race_ids)}) ---")

    # BatchDataLoader で日次キャッシュを再読み込み
    predictor.batch_loader.clear_cache()
    predictor.race_data_cache.clear_all()

    t0 = time.time()
    predictor.batch_loader.load_daily_data(target_date)
    load_time = time.time() - t0
    print(f"  BatchDataLoader 日次読込: {load_time:.1f}秒")

    t0 = time.time()
    sequential_results = {}
    for race_id in race_ids:
        try:
            preds = predictor.predict_race(race_id, use_beforeinfo=False)
            sequential_results[race_id] = preds
        except Exception as e:
            sequential_results[race_id] = []
    sequential_time = time.time() - t0
    sequential_success = sum(1 for v in sequential_results.values() if v)

    print(f"  処理時間: {sequential_time:.2f}秒")
    print(f"  成功: {sequential_success}/{len(race_ids)}")
    print(f"  1レースあたり: {sequential_time/len(race_ids)*1000:.0f}ms")

    # ==== バッチ方式: predict_races_batch ====
    print(f"\n--- バッチ方式 (predict_races_batch) ---")

    # キャッシュを再読み込み（公平な比較のため）
    predictor.batch_loader.clear_cache()
    predictor.race_data_cache.clear_all()

    t0 = time.time()
    predictor.batch_loader.load_daily_data(target_date)
    load_time2 = time.time() - t0
    print(f"  BatchDataLoader 日次読込: {load_time2:.1f}秒")

    t0 = time.time()
    batch_results = predictor.predict_races_batch(race_ids, use_beforeinfo=False)
    batch_time = time.time() - t0
    batch_success = sum(1 for v in batch_results.values() if v)

    print(f"  処理時間: {batch_time:.2f}秒")
    print(f"  成功: {batch_success}/{len(race_ids)}")
    print(f"  1レースあたり: {batch_time/len(race_ids)*1000:.0f}ms")

    # ==== 比較結果 ====
    print(f"\n{'=' * 70}")
    print(f"比較結果")
    print(f"{'=' * 70}")
    print(f"  従来方式: {sequential_time:.2f}秒 ({sequential_time/len(race_ids)*1000:.0f}ms/レース)")
    print(f"  バッチ方式: {batch_time:.2f}秒 ({batch_time/len(race_ids)*1000:.0f}ms/レース)")
    if batch_time > 0:
        speedup = sequential_time / batch_time
        print(f"  高速化率: {speedup:.2f}x ({(1-batch_time/sequential_time)*100:.1f}% 短縮)")

    # 結果の一致性確認
    print(f"\n--- 結果一致性確認 ---")
    match_count = 0
    mismatch_count = 0
    for race_id in race_ids:
        seq_preds = sequential_results.get(race_id, [])
        bat_preds = batch_results.get(race_id, [])

        if len(seq_preds) == len(bat_preds) and len(seq_preds) > 0:
            # total_score と rank_prediction が一致するか確認
            all_match = True
            for sp, bp in zip(seq_preds, bat_preds):
                if sp.get('rank_prediction') != bp.get('rank_prediction'):
                    all_match = False
                    break
                if abs(sp.get('total_score', 0) - bp.get('total_score', 0)) > 0.1:
                    all_match = False
                    break
            if all_match:
                match_count += 1
            else:
                mismatch_count += 1
        elif len(seq_preds) == 0 and len(bat_preds) == 0:
            match_count += 1
        else:
            mismatch_count += 1

    total = match_count + mismatch_count
    print(f"  一致: {match_count}/{total} ({match_count/total*100:.1f}%)")
    if mismatch_count > 0:
        print(f"  不一致: {mismatch_count}/{total}")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
