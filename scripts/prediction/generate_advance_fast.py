#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
advance予測を高速生成するスクリプト（最適化版）
- 未生成分のみ処理（UPSERT方式で安全）
- コマンドライン引数で年度指定
- DB接続を再利用して高速化
"""
import sys
import os
import io
import sqlite3
import warnings
import argparse
from datetime import datetime

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

# 安全チェック（D/Eのみ生成を防ぐ）
from scripts.safety_check import safety_check
safety_check()

from src.analysis.race_predictor import RacePredictor
from src.database.data_manager import DataManager
from config.settings import DATABASE_PATH


def get_remaining_races(year):
    """未生成のレースを一括取得（削除せずUPSERT）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 既存のadvance予測があるrace_idを一括取得
    cursor.execute('''
        SELECT DISTINCT race_id FROM race_predictions
        WHERE prediction_type = 'advance'
        AND race_id IN (SELECT id FROM races WHERE race_date LIKE ?)
    ''', (f'{year}%',))
    existing_ids = set(row[0] for row in cursor.fetchall())

    # 対象年の全レースを取得
    cursor.execute('''
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date LIKE ?
        ORDER BY race_date, venue_code, race_number
    ''', (f'{year}%',))
    all_races = cursor.fetchall()
    conn.close()

    # 未生成のレースのみ抽出
    remaining = [(r[0], r[1], r[2], r[3]) for r in all_races if r[0] not in existing_ids]
    return remaining, len(all_races), len(existing_ids)


def main():
    parser = argparse.ArgumentParser(description='advance予測を高速生成')
    parser.add_argument('--year', type=int, required=True, help='対象年度（例: 2023）')
    args = parser.parse_args()
    year = args.year

    print("=" * 70)
    print(f"{year}年 advance予測 高速生成")
    print("未生成分のみ処理（既存データは保持）")
    print("=" * 70)

    remaining_races, total_races, already_done = get_remaining_races(year)

    print(f"総レース数: {total_races:,}件")
    print(f"生成済み: {already_done:,}件")
    print(f"残り: {len(remaining_races):,}件")
    print()

    if not remaining_races:
        print("全レース生成済みです。")
        return

    # 1回だけ初期化
    print("Predictor初期化中...")
    predictor = RacePredictor()
    data_manager = DataManager()
    print("初期化完了")
    print()

    success_count = 0
    failed_count = 0
    start_time = datetime.now()
    last_date = None

    for i, (race_id, race_date, venue_code, race_number) in enumerate(remaining_races, 1):
        if race_date != last_date:
            if last_date:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = success_count / elapsed if elapsed > 0 else 0
                remaining_count = len(remaining_races) - i + 1
                remaining_time = remaining_count / rate / 60 if rate > 0 else 0
                print(f" [{success_count}/{i-1}] {rate:.1f}/s, {remaining_time:.0f}min left")
            print(f"[{race_date}]", end='', flush=True)
            last_date = race_date
            # 日付が変わったらキャッシュを一括ロード（DBアクセス大幅削減）
            if predictor.batch_loader:
                predictor.batch_loader.load_daily_data(race_date)

        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=False)
            if predictions:
                data_manager.save_race_predictions(race_id, predictions, prediction_type='advance')
                success_count += 1
                if success_count % 100 == 0:
                    print('.', end='', flush=True)
            else:
                failed_count += 1
        except Exception as e:
            failed_count += 1

    elapsed = (datetime.now() - start_time).total_seconds()
    print()
    print()
    print("=" * 70)
    print("完了")
    print("=" * 70)
    print(f"成功: {success_count:,}件")
    print(f"失敗: {failed_count:,}件")
    print(f"所要時間: {elapsed/60:.1f}分")
    if elapsed > 0:
        print(f"処理速度: {success_count/elapsed:.1f}件/秒")
    print("=" * 70)


if __name__ == '__main__':
    main()
