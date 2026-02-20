#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年の直前予想（before）を高速生成するスクリプト
最適化版：マルチプロセス + バッチ処理 + DB接続再利用
"""
import sys
import os
import io
import sqlite3
from datetime import datetime
from multiprocessing import Pool, cpu_count
from functools import partial

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def get_remaining_races():
    """未生成の2024年レースIDを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 既存のbefore予測があるrace_idを取得
    cursor.execute('''
        SELECT DISTINCT race_id FROM race_predictions
        WHERE prediction_type = 'before'
        AND race_id IN (SELECT id FROM races WHERE race_date LIKE '2024%')
    ''')
    existing_ids = set(row[0] for row in cursor.fetchall())

    # 2024年の全レースを取得
    cursor.execute('''
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date LIKE '2024%'
        ORDER BY race_date, venue_code, race_number
    ''')
    all_races = cursor.fetchall()
    conn.close()

    # 未生成のレースのみ抽出
    remaining = [(r[0], r[1], r[2], r[3]) for r in all_races if r[0] not in existing_ids]
    return remaining, len(all_races), len(existing_ids)


def process_race(race_data):
    """1レースを処理（ワーカープロセス用）"""
    race_id, race_date, venue_code, race_number = race_data

    try:
        # 各プロセスでインポート（プロセス間でオブジェクトを共有できないため）
        from src.analysis.race_predictor import RacePredictor
        from src.database.data_manager import DataManager

        predictor = RacePredictor()
        data_manager = DataManager()

        predictions = predictor.predict_race(race_id, use_beforeinfo=True)
        if predictions:
            data_manager.save_race_predictions(race_id, predictions, prediction_type='before')
            return (race_id, 'success', race_date)
        else:
            return (race_id, 'failed', race_date)
    except Exception as e:
        return (race_id, 'error', race_date, str(e))


def process_batch(races_batch):
    """バッチ処理（同一プロセス内で複数レースを処理）"""
    from src.analysis.race_predictor import RacePredictor
    from src.database.data_manager import DataManager

    # 1回だけ初期化
    predictor = RacePredictor()
    data_manager = DataManager()

    results = []
    for race_id, race_date, venue_code, race_number in races_batch:
        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if predictions:
                data_manager.save_race_predictions(race_id, predictions, prediction_type='before')
                results.append((race_id, 'success', race_date))
            else:
                results.append((race_id, 'failed', race_date))
        except Exception as e:
            results.append((race_id, 'error', race_date, str(e)[:50]))

    return results


def main():
    print("=" * 70)
    print("2024年 直前予想（before）高速生成")
    print("最適化版：バッチ処理 + マルチプロセス")
    print("=" * 70)

    remaining_races, total_races, already_done = get_remaining_races()

    print(f"総レース数: {total_races:,}件")
    print(f"生成済み: {already_done:,}件")
    print(f"残り: {len(remaining_races):,}件")
    print()

    if not remaining_races:
        print("全レース生成済みです。")
        return

    # CPUコア数に基づいてワーカー数を決定
    num_workers = min(cpu_count(), 4)  # 最大4プロセス
    batch_size = 50  # 1バッチあたりのレース数

    print(f"ワーカー数: {num_workers}")
    print(f"バッチサイズ: {batch_size}")
    print()

    # バッチに分割
    batches = []
    for i in range(0, len(remaining_races), batch_size):
        batches.append(remaining_races[i:i+batch_size])

    print(f"総バッチ数: {len(batches)}")
    print()

    start_time = datetime.now()
    success_count = 0
    failed_count = 0
    error_count = 0

    # マルチプロセスで処理
    with Pool(num_workers) as pool:
        for batch_idx, batch_results in enumerate(pool.imap_unordered(process_batch, batches)):
            for result in batch_results:
                if result[1] == 'success':
                    success_count += 1
                elif result[1] == 'failed':
                    failed_count += 1
                else:
                    error_count += 1

            # 進捗表示
            processed = (batch_idx + 1) * batch_size
            if processed > len(remaining_races):
                processed = len(remaining_races)

            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > 0:
                speed = processed / elapsed
                remaining_time = (len(remaining_races) - processed) / speed if speed > 0 else 0

                print(f"\r進捗: {processed:,}/{len(remaining_races):,} "
                      f"({processed/len(remaining_races)*100:.1f}%) "
                      f"成功:{success_count} 失敗:{failed_count} エラー:{error_count} "
                      f"速度:{speed:.1f}件/秒 残り:{remaining_time/60:.1f}分", end='', flush=True)

    print("\n")
    print("=" * 70)
    print("完了")
    print("=" * 70)
    elapsed_total = (datetime.now() - start_time).total_seconds()
    print(f"処理時間: {elapsed_total/60:.1f}分")
    print(f"処理レース数: {len(remaining_races):,}件")
    print(f"生成成功: {success_count:,}件")
    print(f"生成失敗: {failed_count:,}件")
    print(f"エラー: {error_count:,}件")
    print(f"平均速度: {len(remaining_races)/elapsed_total:.2f}件/秒")
    print("=" * 70)


if __name__ == '__main__':
    # Windows対応
    from multiprocessing import freeze_support
    freeze_support()
    main()
