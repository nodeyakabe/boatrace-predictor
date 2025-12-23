#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
advance予測を超高速生成するスクリプト
- hierarchical_predictorを一時的に無効化して高速化
- 未生成分のみ処理（UPSERT方式で安全・削除なし）
- バッチコミットで高速化
"""
import sys
import os
import io
import sqlite3
import warnings
import argparse
import json
from datetime import datetime

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# hierarchical_predictorを一時的に無効化
import config.feature_flags as ff
original_flags = ff.FEATURE_FLAGS.copy()
ff.FEATURE_FLAGS['hierarchical_predictor'] = False
print("hierarchical_predictor を一時的に無効化（高速モード）")

from src.analysis.race_predictor import RacePredictor
from config.settings import DATABASE_PATH


def get_remaining_races(year):
    """未生成のレースを一括取得"""
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


def save_predictions_batch(conn, cursor, race_id, predictions, generated_at):
    """バッチでINSERT OR REPLACE（削除なし）"""
    for pred in predictions:
        applied = json.dumps(pred.get('applied_rules', []), ensure_ascii=False) if pred.get('applied_rules') else '[]'
        cursor.execute('''
            INSERT OR REPLACE INTO race_predictions (
                race_id, pit_number, rank_prediction, total_score,
                confidence, racer_name, racer_number, applied_rules,
                course_score, racer_score, motor_score, kimarite_score, grade_score,
                prediction_type, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            race_id,
            pred.get('pit_number'),
            pred.get('rank_prediction'),
            pred.get('total_score', 0),
            pred.get('confidence', ''),
            pred.get('racer_name', ''),
            pred.get('racer_number', ''),
            applied,
            pred.get('course_score', 0),
            pred.get('racer_score', 0),
            pred.get('motor_score', 0),
            pred.get('kimarite_score', 0),
            pred.get('grade_score', 0),
            'advance',
            generated_at
        ))


def main():
    parser = argparse.ArgumentParser(description='advance予測を超高速生成')
    parser.add_argument('--year', type=int, required=True, help='対象年度（例: 2022）')
    parser.add_argument('--batch-size', type=int, default=100, help='コミット間隔')
    args = parser.parse_args()
    year = args.year
    batch_size = args.batch_size

    print("=" * 70)
    print(f"{year}年 advance予測 超高速生成")
    print("未生成分のみ処理（既存データは保持・削除なし）")
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
    print("Predictor初期化中（軽量モード）...")
    predictor = RacePredictor()
    print("初期化完了")
    print()

    # DB接続を維持
    conn = sqlite3.connect(DATABASE_PATH, timeout=60)
    cursor = conn.cursor()

    success_count = 0
    failed_count = 0
    start_time = datetime.now()
    last_date = None
    generated_at = start_time.strftime('%Y-%m-%d %H:%M:%S')

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

        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=False)
            if predictions:
                save_predictions_batch(conn, cursor, race_id, predictions, generated_at)
                success_count += 1

                # バッチコミット
                if success_count % batch_size == 0:
                    conn.commit()
                    print('.', end='', flush=True)
            else:
                failed_count += 1
        except Exception as e:
            failed_count += 1

    # 最終コミット
    conn.commit()
    conn.close()

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

    # フラグを元に戻す
    ff.FEATURE_FLAGS.update(original_flags)


if __name__ == '__main__':
    main()
