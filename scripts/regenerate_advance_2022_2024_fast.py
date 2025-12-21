#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2022-2024年の事前予想（advance）を高速再生成するスクリプト
- 未生成分のみ処理（UPSERT方式で安全）
- DB接続を再利用
- バッチコミット
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


def get_remaining_races(start_year='2022', end_year='2024'):
    """未生成のレースを一括取得（安全なUPSERT方式）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 既存のadvance予測があるrace_idを一括取得
    cursor.execute(f'''
        SELECT DISTINCT race_id FROM race_predictions
        WHERE prediction_type = 'advance'
        AND race_id IN (
            SELECT id FROM races
            WHERE race_date >= '{start_year}-01-01' AND race_date <= '{end_year}-12-31'
        )
    ''')
    existing_ids = set(row[0] for row in cursor.fetchall())

    # 対象年の全レースを取得
    cursor.execute(f'''
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date >= '{start_year}-01-01' AND race_date <= '{end_year}-12-31'
        ORDER BY race_date, venue_code, race_number
    ''')
    all_races = cursor.fetchall()
    conn.close()

    # 未生成のレースのみ抽出
    remaining = [(r[0], r[1], r[2], r[3]) for r in all_races if r[0] not in existing_ids]
    return remaining, len(all_races), len(existing_ids)


def main():
    print("=" * 70)
    print("2022-2024年 事前予想（advance）高速再生成")
    print("未生成分のみ処理（既存データは保持）")
    print("=" * 70)

    remaining_races, total_races, already_done = get_remaining_races()

    print(f"対象期間: 2022-01-01 ~ 2024-12-31")
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
        # 日付が変わったら進捗表示
        if race_date != last_date:
            if last_date:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = success_count / elapsed if elapsed > 0 else 0
                remaining_count = len(remaining_races) - i + 1
                remaining_time = remaining_count / rate / 60 if rate > 0 else 0
                print(f" [{success_count}/{i-1}] {rate:.1f}/s, 残り{remaining_time:.0f}分")
            print(f"[{race_date}]", end='', flush=True)
            last_date = race_date

        # 事前予想生成（use_beforeinfo=False）
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

    # 最終結果
    elapsed = (datetime.now() - start_time).total_seconds()
    print()
    print()
    print("=" * 70)
    print("再生成完了")
    print("=" * 70)
    print(f"成功: {success_count:,}件")
    print(f"失敗: {failed_count:,}件")
    print(f"所要時間: {elapsed/60:.1f}分")
    print(f"処理速度: {success_count/elapsed:.1f}件/秒" if elapsed > 0 else "N/A")
    print("=" * 70)


if __name__ == '__main__':
    main()
