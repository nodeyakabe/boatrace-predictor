#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
advance予測を高速生成（統計ファイルエラー回避版）
"""
import sys
import os
import io
import sqlite3
import warnings
import argparse
from datetime import datetime
from pathlib import Path

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor
from src.database.data_manager import DataManager
from config.settings import DATABASE_PATH
from config.feature_flags import FEATURE_FLAGS


def get_remaining_races(year):
    """未生成のレースを一括取得（entriesがあるレースのみ）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 既存のadvance予測があるrace_idを一括取得
    cursor.execute('''
        SELECT DISTINCT race_id FROM race_predictions
        WHERE prediction_type = 'advance'
        AND race_id IN (SELECT id FROM races WHERE race_date LIKE ?)
    ''', (f'{year}%',))
    existing_ids = set(row[0] for row in cursor.fetchall())

    # 対象年の全レース（entriesがあるもののみ）を取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        WHERE r.race_date LIKE ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (f'{year}%',))
    all_races = cursor.fetchall()
    conn.close()

    # 未生成のレースのみ抽出
    remaining = [(r[0], r[1], r[2], r[3]) for r in all_races if r[0] not in existing_ids]
    return remaining, len(all_races), len(existing_ids)


def main():
    parser = argparse.ArgumentParser(description='advance予測を高速生成')
    parser.add_argument('--year', type=int, required=True, help='対象年度（例: 2022）')
    args = parser.parse_args()
    year = args.year

    print("=" * 70)
    print(f"{year}年 advance予測 高速生成")
    print("=" * 70)
    print()

    # hierarchical_predictor チェック
    if not FEATURE_FLAGS.get('hierarchical_predictor', False):
        print("ERROR: hierarchical_predictor is OFF")
        print("A/B/C 信頼度が生成されません")
        sys.exit(1)

    print("✅ hierarchical_predictor: ON")
    print()

    remaining_races, total_races, already_done = get_remaining_races(year)

    print(f"総レース数: {total_races:,}件")
    print(f"生成済み: {already_done:,}件")
    print(f"残り: {len(remaining_races):,}件")
    print()

    if not remaining_races:
        print("全レース生成済みです。")
        return

    # Predictor初期化
    print("Predictor初期化中...", flush=True)
    predictor = RacePredictor()
    print("RacePredictor OK", flush=True)
    data_manager = DataManager()
    print("DataManager OK", flush=True)
    print("初期化完了", flush=True)
    print()

    success_count = 0
    failed_count = 0
    start_time = datetime.now()
    last_date = None

    for i, (race_id, race_date, venue_code, race_number) in enumerate(remaining_races, 1):
        if race_date != last_date:
            if last_date:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = i / elapsed if elapsed > 0 else 0
                remaining_time = (len(remaining_races) - i) / rate if rate > 0 else 0
                print(f"  [{race_date}] {i:>5}/{len(remaining_races)} ({i/len(remaining_races)*100:.1f}%) "
                      f"[{elapsed/60:.1f}分経過, 残り{remaining_time/60:.1f}分]")
            last_date = race_date

        try:
            # 予測実行（advance = use_beforeinfo=False）
            predictions = predictor.predict_race(
                race_id=race_id,
                use_beforeinfo=False  # advance予測
            )

            if predictions:
                # DB保存（UPSERT方式）
                saved = data_manager.save_race_predictions(
                    race_id=race_id,
                    predictions=predictions,
                    prediction_type='advance'
                )
                if saved:
                    success_count += 1
                else:
                    failed_count += 1
                    if failed_count <= 10:
                        print(f"  保存失敗 #{failed_count}: race_id={race_id}")
            else:
                failed_count += 1
                if failed_count <= 10:
                    print(f"  予測結果なし #{failed_count}: race_id={race_id}")

        except Exception as e:
            failed_count += 1
            if failed_count <= 10:
                print(f"  エラー #{failed_count}: {str(e)[:100]}")
            elif failed_count % 100 == 0:
                print(f"  エラー累計: {failed_count}件 (最新: {str(e)[:50]})")

    elapsed = (datetime.now() - start_time).total_seconds()

    print()
    print("=" * 70)
    print("完了")
    print("=" * 70)
    print(f"成功: {success_count:,}件")
    print(f"失敗: {failed_count:,}件")
    print(f"所要時間: {elapsed/60:.1f}分 ({elapsed/3600:.2f}時間)")
    print(f"処理速度: {success_count/elapsed:.1f}件/秒")
    print()


if __name__ == '__main__':
    main()
