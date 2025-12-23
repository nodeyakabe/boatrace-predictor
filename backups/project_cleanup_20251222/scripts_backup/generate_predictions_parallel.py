#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予想データ並列生成スクリプト

マルチプロセスで高速に予想を生成します。
SQLite書き込みはキューで制御し、安全性を確保。

実行方法:
  python scripts/generate_predictions_parallel.py --start 2025-01-01 --end 2025-09-30
  python scripts/generate_predictions_parallel.py --start 2025-01-01 --end 2025-09-30 --workers 4
"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

import time
import sqlite3
import argparse
import warnings
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager, cpu_count
import queue

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def process_single_day(args):
    """
    1日分の予想を生成（ワーカープロセス用）

    Args:
        args: (race_date, db_path, force)

    Returns:
        dict: 処理結果
    """
    race_date, db_path, force = args

    # ワーカー内でインポート（プロセス分離のため）
    import sqlite3
    import warnings
    warnings.filterwarnings('ignore')

    sys.path.insert(0, PROJECT_ROOT)
    from src.analysis.race_predictor import RacePredictor

    result = {
        'date': race_date,
        'total_races': 0,
        'advance_generated': 0,
        'before_generated': 0,
        'skipped': 0,
        'errors': 0,
        'predictions': []  # 予測結果を一時保存
    }

    try:
        # Predictorを初期化（各ワーカーで1回のみ）
        predictor = RacePredictor(use_cache=True)

        # BatchDataLoaderにデータをロード
        if predictor.batch_loader:
            predictor.batch_loader.load_daily_data(race_date)

        # その日のレースを取得
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number
            FROM races r
            WHERE r.race_date = ?
            ORDER BY r.venue_code, r.race_number
        """, (race_date,))

        races = cursor.fetchall()
        conn.close()

        if not races:
            return result

        result['total_races'] = len(races)

        for race_id, venue_code, race_num in races:
            # 既存チェック
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COUNT(*) FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'advance'
            """, (race_id,))
            advance_exists = cursor.fetchone()[0] > 0

            cursor.execute("""
                SELECT COUNT(*) FROM race_details
                WHERE race_id = ? AND exhibition_time IS NOT NULL
            """, (race_id,))
            has_before_data = cursor.fetchone()[0] > 0

            cursor.execute("""
                SELECT COUNT(*) FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'before'
            """, (race_id,))
            before_exists = cursor.fetchone()[0] > 0

            conn.close()

            # 事前予想
            if force or not advance_exists:
                try:
                    predictions = predictor.predict_race(race_id)
                    if predictions and len(predictions) > 0:
                        result['predictions'].append({
                            'race_id': race_id,
                            'type': 'advance',
                            'data': predictions
                        })
                        result['advance_generated'] += 1
                except:
                    result['errors'] += 1
            else:
                result['skipped'] += 1

            # 直前予想
            if has_before_data and (force or not before_exists):
                try:
                    predictions = predictor.predict_race(race_id)
                    if predictions and len(predictions) > 0:
                        result['predictions'].append({
                            'race_id': race_id,
                            'type': 'before',
                            'data': predictions
                        })
                        result['before_generated'] += 1
                except:
                    pass

    except Exception as e:
        result['errors'] = result['total_races']

    return result


def save_predictions_batch(predictions_list, db_path):
    """
    予測結果をバッチでDBに保存（メインプロセスで実行）
    """
    if not predictions_list:
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    saved = 0

    try:
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for item in predictions_list:
            race_id = item['race_id']
            prediction_type = item['type']
            predictions = item['data']

            for pred in predictions:
                cursor.execute("""
                    INSERT OR REPLACE INTO race_predictions (
                        race_id, pit_number, rank_prediction, total_score,
                        confidence, racer_name, racer_number, applied_rules,
                        course_score, racer_score, motor_score, kimarite_score,
                        grade_score, prediction_type, generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    race_id,
                    pred.get('pit_number'),
                    pred.get('predicted_rank', pred.get('rank_prediction')),
                    pred.get('total_score', 0),
                    pred.get('confidence', 'medium'),
                    pred.get('racer_name', ''),
                    pred.get('racer_number', ''),
                    str(pred.get('applied_rules', '')),
                    pred.get('course_score', 0),
                    pred.get('racer_score', 0),
                    pred.get('motor_score', 0),
                    pred.get('kimarite_score', 0),
                    pred.get('grade_score', 0),
                    prediction_type,
                    generated_at
                ))
                saved += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"DB保存エラー: {e}")
    finally:
        conn.close()

    return saved


def main():
    parser = argparse.ArgumentParser(description='予想データ並列生成')
    parser.add_argument('--start', type=str, required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=4, help='並列ワーカー数（デフォルト: 4）')
    parser.add_argument('--force', action='store_true', help='既存の予想を上書き')

    args = parser.parse_args()

    # 日付リストを生成
    start = datetime.strptime(args.start, '%Y-%m-%d')
    end = datetime.strptime(args.end, '%Y-%m-%d')

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    print("=" * 70)
    print("予想データ並列生成")
    print("=" * 70)
    print(f"期間: {args.start} 〜 {args.end}")
    print(f"対象日数: {len(dates)}日間")
    print(f"並列ワーカー: {args.workers}")
    print(f"強制上書き: {'有効' if args.force else '無効'}")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    start_time = time.time()

    # 統計
    total_stats = {
        'total_races': 0,
        'advance_generated': 0,
        'before_generated': 0,
        'skipped': 0,
        'errors': 0
    }

    # タスクを準備
    tasks = [(date, DATABASE_PATH, args.force) for date in dates]

    completed = 0

    # 並列処理
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # フューチャーを送信
        futures = {executor.submit(process_single_day, task): task[0] for task in tasks}

        for future in as_completed(futures):
            date = futures[future]
            completed += 1

            try:
                result = future.result()

                # 統計更新
                total_stats['total_races'] += result['total_races']
                total_stats['advance_generated'] += result['advance_generated']
                total_stats['before_generated'] += result['before_generated']
                total_stats['skipped'] += result['skipped']
                total_stats['errors'] += result['errors']

                # 予測結果をDBに保存（メインプロセスで安全に）
                if result['predictions']:
                    save_predictions_batch(result['predictions'], DATABASE_PATH)

                # 進捗表示
                elapsed = time.time() - start_time
                print(f"[{completed:3}/{len(dates)}] {result['date']}: {result['total_races']:3}R "
                      f"(事前:{result['advance_generated']:3} 直前:{result['before_generated']:3} "
                      f"Skip:{result['skipped']:3} Err:{result['errors']:2}) "
                      f"[{elapsed/60:.1f}分経過]", flush=True)

            except Exception as e:
                elapsed = time.time() - start_time
                print(f"[{completed:3}/{len(dates)}] {date}: エラー - {str(e)[:30]} [{elapsed/60:.1f}分経過]", flush=True)

    elapsed = time.time() - start_time

    # 結果サマリー
    print()
    print("=" * 70)
    print("予想生成完了")
    print("=" * 70)
    print(f"総レース数: {total_stats['total_races']:,}件")
    print(f"事前予想生成: {total_stats['advance_generated']:,}件")
    print(f"直前予想生成: {total_stats['before_generated']:,}件")
    print(f"スキップ: {total_stats['skipped']:,}件")
    print(f"エラー: {total_stats['errors']:,}件")
    print(f"処理時間: {elapsed/60:.1f}分")
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 速度比較
    if elapsed > 0:
        races_per_min = total_stats['total_races'] / (elapsed / 60)
        print(f"処理速度: {races_per_min:.1f} レース/分")


if __name__ == '__main__':
    main()
