#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2022-2023年の事前予想（advance）を再生成するスクリプト
- 2024年は既存データがあるため対象外
- 現在のフィーチャーフラグ設定で予測を再生成
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


def get_races_to_regenerate():
    """2022-2023年の再生成対象レースを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 2022-2023年のレースを取得
    cursor.execute('''
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date >= '2022-01-01' AND race_date <= '2023-12-31'
        ORDER BY race_date, venue_code, race_number
    ''')
    all_races = cursor.fetchall()

    # 既存のadvance予測数をカウント
    cursor.execute('''
        SELECT COUNT(DISTINCT race_id) FROM race_predictions
        WHERE prediction_type = 'advance'
        AND race_id IN (SELECT id FROM races WHERE race_date >= '2022-01-01' AND race_date <= '2023-12-31')
    ''')
    existing_count = cursor.fetchone()[0]

    conn.close()
    return all_races, existing_count


def delete_existing_predictions(race_ids, batch_size=1000):
    """既存の予測を削除"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    for i in range(0, len(race_ids), batch_size):
        batch = race_ids[i:i+batch_size]
        placeholders = ','.join('?' * len(batch))
        cursor.execute(f'''
            DELETE FROM race_predictions
            WHERE race_id IN ({placeholders}) AND prediction_type = 'advance'
        ''', batch)
        conn.commit()

    conn.close()


def main():
    print("=" * 70)
    print("2022-2023年 事前予想（advance）再生成")
    print("現在のフィーチャーフラグ設定で予測を再生成します")
    print("=" * 70)

    all_races, existing_count = get_races_to_regenerate()
    total_races = len(all_races)

    print(f"対象期間: 2022-01-01 ~ 2023-12-31")
    print(f"対象レース数: {total_races:,}件")
    print(f"既存予測数: {existing_count:,}件（削除して再生成）")
    print()

    if total_races == 0:
        print("対象レースがありません。")
        return

    # 既存予測を削除
    if existing_count > 0:
        print("既存予測を削除中...")
        race_ids = [r[0] for r in all_races]
        delete_existing_predictions(race_ids)
        print("削除完了")
        print()

    # Predictor初期化
    print("Predictor初期化中...")
    predictor = RacePredictor()
    data_manager = DataManager()
    print("初期化完了")
    print()

    success_count = 0
    failed_count = 0
    start_time = datetime.now()
    last_date = None

    for i, (race_id, race_date, venue_code, race_number) in enumerate(all_races, 1):
        # 日付が変わったら進捗表示
        if race_date != last_date:
            if last_date:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (total_races - i) / rate / 60 if rate > 0 else 0
                print(f" [{success_count}/{i-1}] {rate:.1f}/s, 残り{remaining:.0f}分")
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
    print(f"処理速度: {total_races/elapsed:.1f}件/秒")
    print("=" * 70)


if __name__ == '__main__':
    main()
