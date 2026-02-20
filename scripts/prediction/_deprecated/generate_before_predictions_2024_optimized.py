#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年の直前予想（before）を生成するスクリプト（最適化版）
- DB接続を再利用
- 既存チェックを一括で実施
- warningsを抑制
"""
import sys
import os
import io
import sqlite3
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.race_predictor import RacePredictor
from src.database.data_manager import DataManager
from config.settings import DATABASE_PATH


def get_remaining_races():
    """未生成の2024年レースを一括取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 既存のbefore予測があるrace_idを一括取得
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


def main():
    print("=" * 70)
    print("2024年 直前予想（before）生成（最適化版）")
    print("use_beforeinfo=True（展示タイム・直前情報あり）")
    print("=" * 70)

    remaining_races, total_races, already_done = get_remaining_races()

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
        # 日付が変わったら表示
        if race_date != last_date:
            if last_date:
                print()
            print(f"\n[{race_date}]", end=' ')
            last_date = race_date

        # 直前予想生成
        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if predictions:
                data_manager.save_race_predictions(race_id, predictions, prediction_type='before')
                success_count += 1
                print('o', end='', flush=True)
            else:
                failed_count += 1
                print('x', end='', flush=True)
        except Exception as e:
            failed_count += 1
            print('X', end='', flush=True)

        # 100レースごとに進捗表示
        if i % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            speed = i / elapsed
            remaining_time = (len(remaining_races) - i) / speed if speed > 0 else 0
            print(f" [{i:,}/{len(remaining_races):,}] "
                  f"成功:{success_count} 失敗:{failed_count} "
                  f"速度:{speed:.1f}件/秒 残り:{remaining_time/60:.1f}分", end='')

    print("\n")
    print("=" * 70)
    print("完了")
    print("=" * 70)
    elapsed_total = (datetime.now() - start_time).total_seconds()
    print(f"総処理時間: {elapsed_total/60:.1f}分")
    print(f"処理レース数: {len(remaining_races):,}件")
    print(f"生成成功: {success_count:,}件")
    print(f"生成失敗: {failed_count:,}件")
    if success_count + failed_count > 0:
        print(f"成功率: {success_count/(success_count+failed_count)*100:.1f}%")
    print(f"平均速度: {len(remaining_races)/elapsed_total:.2f}件/秒")
    print("=" * 70)


if __name__ == '__main__':
    main()
