#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
汎用予測生成スクリプト

目的: 予測ロジック変更後、任意の期間の予測データを高速に生成
使い方:
    # 単一年度
    python scripts/universal_prediction_generator.py --year 2025

    # 複数年度
    python scripts/universal_prediction_generator.py --years 2022,2023,2024,2025

    # 特定期間
    python scripts/universal_prediction_generator.py --start-date 2025-06-01 --end-date 2025-06-30

    # 並列処理（高速）
    python scripts/universal_prediction_generator.py --year 2025 --parallel --workers 8

    # 既存データの上書き
    python scripts/universal_prediction_generator.py --year 2025 --force
"""
import sys
import os
import io
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import argparse

# Windows環境でのエンコーディング設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH


def get_date_range(args):
    """引数から日付範囲を生成"""
    dates = []

    if args.year:
        # 単一年度
        start = datetime.strptime(f'{args.year}-01-01', '%Y-%m-%d')
        end = datetime.strptime(f'{args.year}-12-31', '%Y-%m-%d')

    elif args.years:
        # 複数年度
        year_list = [int(y.strip()) for y in args.years.split(',')]
        min_year = min(year_list)
        max_year = max(year_list)
        start = datetime.strptime(f'{min_year}-01-01', '%Y-%m-%d')
        end = datetime.strptime(f'{max_year}-12-31', '%Y-%m-%d')

    elif args.start_date and args.end_date:
        # 特定期間
        start = datetime.strptime(args.start_date, '%Y-%m-%d')
        end = datetime.strptime(args.end_date, '%Y-%m-%d')

    else:
        # デフォルト: 今年
        current_year = datetime.now().year
        start = datetime.strptime(f'{current_year}-01-01', '%Y-%m-%d')
        end = datetime.strptime(f'{current_year}-12-31', '%Y-%m-%d')

    # 日付リストを生成
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    return dates


def get_races_for_date(db_path, race_date):
    """指定日のレース一覧を取得"""
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

    return races


def predict_single_race(race_id, use_beforeinfo=False):
    """1レースの予測を生成"""
    from src.analysis.race_predictor import RacePredictor

    try:
        predictor = RacePredictor(use_cache=True)
        predictions = predictor.predict_race(race_id, use_beforeinfo=use_beforeinfo)
        return predictions
    except Exception as e:
        return None


def save_predictions_to_db(db_path, race_id, predictions, prediction_type='advance'):
    """予測データをDBに保存"""
    if not predictions or len(predictions) == 0:
        return False

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    try:
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 既存データを削除
        cursor.execute("""
            DELETE FROM race_predictions
            WHERE race_id = ? AND prediction_type = ?
        """, (race_id, prediction_type))

        # 新しいデータを挿入
        for pred in predictions:
            cursor.execute("""
                INSERT INTO race_predictions (
                    race_id, pit_number, rank_prediction, total_score,
                    confidence, racer_name, racer_number, applied_rules,
                    course_score, racer_score, motor_score, kimarite_score,
                    grade_score, prediction_type, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                race_id,
                pred.get('pit_number'),
                pred.get('rank_prediction'),
                pred.get('total_score', 0),
                pred.get('confidence', 'E'),
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

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()


def process_single_date(args_tuple):
    """1日分の予測を生成（並列処理用）"""
    race_date, db_path, use_beforeinfo, force = args_tuple

    result = {
        'date': race_date,
        'total_races': 0,
        'skipped': 0,
        'succeeded': 0,
        'failed': 0
    }

    # ワーカー内でインポート
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from src.analysis.race_predictor import RacePredictor
    import sqlite3

    try:
        predictor = RacePredictor(use_cache=True)

        # その日のレースを取得
        races = get_races_for_date(db_path, race_date)
        result['total_races'] = len(races)

        if len(races) == 0:
            return result

        prediction_type = 'before' if use_beforeinfo else 'advance'

        for race_id, venue_code, race_num in races:
            # 既存チェック
            if not force:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM race_predictions
                    WHERE race_id = ? AND prediction_type = ?
                """, (race_id, prediction_type))
                exists = cursor.fetchone()[0] > 0
                conn.close()

                if exists:
                    result['skipped'] += 1
                    continue

            # 予測生成
            try:
                predictions = predictor.predict_race(race_id, use_beforeinfo=use_beforeinfo)

                if predictions and len(predictions) >= 6:
                    # DB保存
                    if save_predictions_to_db(db_path, race_id, predictions, prediction_type):
                        result['succeeded'] += 1
                    else:
                        result['failed'] += 1
                else:
                    result['failed'] += 1

            except Exception as e:
                result['failed'] += 1

    except Exception as e:
        result['failed'] = result['total_races']

    return result


def process_sequential(dates, db_path, use_beforeinfo, force):
    """逐次処理"""
    from src.analysis.race_predictor import RacePredictor

    predictor = RacePredictor(use_cache=True)
    prediction_type = 'before' if use_beforeinfo else 'advance'

    total_stats = {
        'total_races': 0,
        'skipped': 0,
        'succeeded': 0,
        'failed': 0
    }

    start_time = time.time()

    for idx, race_date in enumerate(dates, 1):
        # その日のレースを取得
        races = get_races_for_date(db_path, race_date)

        if len(races) == 0:
            continue

        total_stats['total_races'] += len(races)

        for race_id, venue_code, race_num in races:
            # 既存チェック
            if not force:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM race_predictions
                    WHERE race_id = ? AND prediction_type = ?
                """, (race_id, prediction_type))
                exists = cursor.fetchone()[0] > 0
                conn.close()

                if exists:
                    total_stats['skipped'] += 1
                    continue

            # 予測生成
            try:
                predictions = predictor.predict_race(race_id, use_beforeinfo=use_beforeinfo)

                if predictions and len(predictions) >= 6:
                    if save_predictions_to_db(db_path, race_id, predictions, prediction_type):
                        total_stats['succeeded'] += 1
                    else:
                        total_stats['failed'] += 1
                else:
                    total_stats['failed'] += 1

            except Exception as e:
                total_stats['failed'] += 1

        # 進捗表示
        elapsed = time.time() - start_time
        races_per_min = total_stats['total_races'] / (elapsed / 60) if elapsed > 0 else 0
        remaining_days = len(dates) - idx
        eta_min = remaining_days / (idx / (elapsed / 60)) if idx > 0 else 0

        print(f"[{idx:3}/{len(dates)}] {race_date}: {len(races):3}R "
              f"(成功:{total_stats['succeeded']:4} 失敗:{total_stats['failed']:3} スキップ:{total_stats['skipped']:4}) "
              f"[{elapsed/60:.1f}分経過, {races_per_min:.1f}R/分, 残り{eta_min:.1f}分]", flush=True)

    return total_stats


def process_parallel(dates, db_path, use_beforeinfo, force, workers):
    """並列処理"""
    total_stats = {
        'total_races': 0,
        'skipped': 0,
        'succeeded': 0,
        'failed': 0
    }

    start_time = time.time()
    completed = 0

    # タスクを準備
    tasks = [(date, str(db_path), use_beforeinfo, force) for date in dates]

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_single_date, task): task[0] for task in tasks}

        for future in as_completed(futures):
            date = futures[future]
            completed += 1

            try:
                result = future.result()

                # 統計更新
                total_stats['total_races'] += result['total_races']
                total_stats['skipped'] += result['skipped']
                total_stats['succeeded'] += result['succeeded']
                total_stats['failed'] += result['failed']

                # 進捗表示
                elapsed = time.time() - start_time
                races_per_min = total_stats['total_races'] / (elapsed / 60) if elapsed > 0 else 0
                remaining_days = len(dates) - completed
                eta_min = remaining_days / (completed / (elapsed / 60)) if completed > 0 else 0

                print(f"[{completed:3}/{len(dates)}] {result['date']}: {result['total_races']:3}R "
                      f"(成功:{result['succeeded']:3} 失敗:{result['failed']:2} スキップ:{result['skipped']:3}) "
                      f"[{elapsed/60:.1f}分経過, {races_per_min:.1f}R/分, 残り{eta_min:.1f}分]", flush=True)

            except Exception as e:
                elapsed = time.time() - start_time
                print(f"[{completed:3}/{len(dates)}] {date}: エラー - {str(e)[:30]} [{elapsed/60:.1f}分経過]", flush=True)

    return total_stats


def main():
    parser = argparse.ArgumentParser(
        description='汎用予測生成スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 2025年全体
  python scripts/universal_prediction_generator.py --year 2025

  # 複数年度
  python scripts/universal_prediction_generator.py --years 2022,2023,2024,2025

  # 特定期間
  python scripts/universal_prediction_generator.py --start-date 2025-06-01 --end-date 2025-06-30

  # 並列処理（高速）
  python scripts/universal_prediction_generator.py --year 2025 --parallel --workers 8

  # 既存上書き
  python scripts/universal_prediction_generator.py --year 2025 --force

  # 直前情報を使用
  python scripts/universal_prediction_generator.py --year 2025 --use-beforeinfo
        """
    )

    # 期間指定
    parser.add_argument('--year', type=int, help='対象年度（例: 2025）')
    parser.add_argument('--years', type=str, help='複数年度（例: 2022,2023,2024,2025）')
    parser.add_argument('--start-date', type=str, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end-date', type=str, help='終了日（YYYY-MM-DD）')

    # オプション
    parser.add_argument('--parallel', action='store_true', help='並列処理を有効化')
    parser.add_argument('--workers', type=int, default=None, help='並列ワーカー数（デフォルト: CPUコア数）')
    parser.add_argument('--force', action='store_true', help='既存データを上書き')
    parser.add_argument('--use-beforeinfo', action='store_true', help='直前情報を使用（prediction_type=before）')

    args = parser.parse_args()

    # ワーカー数の決定
    if args.workers is None:
        args.workers = min(cpu_count(), 8)

    # 日付範囲を取得
    dates = get_date_range(args)

    prediction_type = 'before' if args.use_beforeinfo else 'advance'

    print("=" * 80)
    print("汎用予測生成スクリプト")
    print("=" * 80)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象期間: {dates[0]} ～ {dates[-1]}")
    print(f"対象日数: {len(dates)}日間")
    print(f"予測タイプ: {prediction_type}")
    print(f"処理モード: {'並列' if args.parallel else '逐次'}")
    if args.parallel:
        print(f"並列ワーカー: {args.workers}")
    print(f"既存データ: {'上書き' if args.force else 'スキップ'}")
    print("=" * 80)
    print()

    start_time = time.time()

    # 処理実行
    if args.parallel:
        stats = process_parallel(dates, DATABASE_PATH, args.use_beforeinfo, args.force, args.workers)
    else:
        stats = process_sequential(dates, DATABASE_PATH, args.use_beforeinfo, args.force)

    elapsed = time.time() - start_time

    # 結果表示
    print()
    print("=" * 80)
    print("処理完了")
    print("=" * 80)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"所要時間: {elapsed/3600:.2f}時間 ({elapsed/60:.1f}分)")
    print()
    print(f"総レース数: {stats['total_races']:,}件")
    print(f"成功: {stats['succeeded']:,}件")
    print(f"失敗: {stats['failed']:,}件")
    print(f"スキップ: {stats['skipped']:,}件")
    if stats['total_races'] > 0:
        print(f"成功率: {stats['succeeded']/(stats['total_races']-stats['skipped'])*100:.1f}%" if (stats['total_races']-stats['skipped']) > 0 else "成功率: N/A")
    print()

    # 速度
    if elapsed > 0:
        races_per_min = stats['total_races'] / (elapsed / 60)
        print(f"処理速度: {races_per_min:.1f} レース/分")
        print()

    # 生成データ確認
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM race_predictions
        WHERE prediction_type = ?
        AND race_id IN (
            SELECT id FROM races
            WHERE race_date >= ? AND race_date <= ?
        )
    """, (prediction_type, dates[0], dates[-1]))

    total_predictions = cursor.fetchone()[0]

    cursor.execute("""
        SELECT rp.confidence, COUNT(DISTINCT rp.race_id) as race_count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = ?
        AND rp.rank_prediction = 1
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    """, (dates[0], dates[-1], prediction_type))

    print("生成データ:")
    print(f"  総件数: {total_predictions:,}件")
    print(f"  信頼度別レース数:")
    for confidence, count in cursor.fetchall():
        print(f"    信頼度{confidence}: {count:,}レース")

    conn.close()

    print()
    print("=" * 80)
    print("次のステップ:")
    print("  1. バックテスト実行")
    print(f"     python scripts/backtest_with_predictions.py --start-date {dates[0]} --end-date {dates[-1]}")
    print("=" * 80)


if __name__ == "__main__":
    main()
