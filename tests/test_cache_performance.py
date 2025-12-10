#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キャッシュシステムのパフォーマンステスト

目標: 1000レース分析を60分→15分に短縮（75%削減）
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import time
import sqlite3
from src.analysis.race_predictor import RacePredictor


def test_cache_performance():
    """キャッシュ性能をテスト"""

    print("=" * 80)
    print("キャッシュシステム パフォーマンステスト")
    print("=" * 80)
    print()

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2025年の最新100レースを取得
    cursor.execute("""
        SELECT r.id
        FROM races r
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
          AND EXISTS (
              SELECT 1 FROM results res
              WHERE res.race_id = r.id AND res.rank IS NOT NULL
          )
          AND EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
                AND rd.exhibition_time IS NOT NULL
                AND rd.st_time IS NOT NULL
          )
        ORDER BY r.race_date DESC, r.race_number DESC
        LIMIT 100
    """)

    race_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    print(f"[テスト対象] {len(race_ids)}レース")
    print()

    # 予測器初期化
    predictor = RacePredictor()

    # === テスト1: 初回実行（キャッシュなし） ===
    print("=" * 80)
    print("【テスト1】初回実行（キャッシュなし）")
    print("=" * 80)

    start_time = time.time()
    success_count = 0

    for i, race_id in enumerate(race_ids[:20], 1):  # 最初の20レース
        try:
            predictions = predictor.predict_race(race_id)
            if predictions:
                success_count += 1

            # 進捗表示
            if i % 5 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                print(f"  {i}/20レース完了 | 平均: {avg_time:.2f}秒/レース | 経過: {elapsed:.1f}秒")
        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    first_run_time = time.time() - start_time
    avg_first_run = first_run_time / 20

    print()
    print(f"初回実行完了: {first_run_time:.2f}秒 ({avg_first_run:.2f}秒/レース)")
    print(f"成功: {success_count}/20レース")
    print()

    # キャッシュ統計を表示
    cache_stats = predictor.race_data_cache.get_all_stats()
    print("【キャッシュ統計】")
    for cache_type, stats in cache_stats.items():
        if stats['hits'] + stats['misses'] > 0:
            print(f"{cache_type}: Hit Rate {stats['hit_rate']:.1%} (Hits: {stats['hits']}, Misses: {stats['misses']}, Size: {stats['size']})")
    print()

    # === テスト2: 再実行（キャッシュあり） ===
    print("=" * 80)
    print("【テスト2】再実行（キャッシュヒット期待）")
    print("=" * 80)

    start_time = time.time()
    success_count = 0

    for i, race_id in enumerate(race_ids[:20], 1):
        try:
            predictions = predictor.predict_race(race_id)
            if predictions:
                success_count += 1

            # 進捗表示
            if i % 5 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                print(f"  {i}/20レース完了 | 平均: {avg_time:.2f}秒/レース | 経過: {elapsed:.1f}秒")
        except Exception as e:
            print(f"  [警告] レース{race_id}でエラー: {e}")

    second_run_time = time.time() - start_time
    avg_second_run = second_run_time / 20

    print()
    print(f"再実行完了: {second_run_time:.2f}秒 ({avg_second_run:.2f}秒/レース)")
    print(f"成功: {success_count}/20レース")
    print()

    # キャッシュ統計を表示
    cache_stats = predictor.race_data_cache.get_all_stats()
    print("【キャッシュ統計（再実行後）】")
    for cache_type, stats in cache_stats.items():
        if stats['hits'] + stats['misses'] > 0:
            print(f"{cache_type}: Hit Rate {stats['hit_rate']:.1%} (Hits: {stats['hits']}, Misses: {stats['misses']}, Size: {stats['size']})")
    print()

    # === 結果サマリー ===
    print("=" * 80)
    print("【パフォーマンス改善サマリー】")
    print("=" * 80)

    speedup = (first_run_time - second_run_time) / first_run_time * 100 if first_run_time > 0 else 0
    time_saved = first_run_time - second_run_time

    print(f"初回実行: {first_run_time:.2f}秒 ({avg_first_run:.2f}秒/レース)")
    print(f"再実行:   {second_run_time:.2f}秒 ({avg_second_run:.2f}秒/レース)")
    print(f"高速化:   {speedup:.1f}% ({time_saved:.2f}秒削減)")
    print()

    # 1000レース換算
    projected_first = avg_first_run * 1000 / 60  # 分
    projected_second = avg_second_run * 1000 / 60  # 分

    print(f"【1000レース換算】")
    print(f"初回実行: {projected_first:.1f}分")
    print(f"再実行:   {projected_second:.1f}分")
    print(f"削減:     {projected_first - projected_second:.1f}分")
    print()

    # 目標達成判定
    target_time = 15  # 分
    if projected_second <= target_time:
        print(f"✓ 目標達成: {projected_second:.1f}分 ≤ {target_time}分")
    else:
        print(f"⚠ 目標未達: {projected_second:.1f}分 > {target_time}分 (あと{projected_second - target_time:.1f}分削減必要)")

    print()
    print("=" * 80)

    return speedup > 0


if __name__ == "__main__":
    success = test_cache_performance()
    sys.exit(0 if success else 1)
