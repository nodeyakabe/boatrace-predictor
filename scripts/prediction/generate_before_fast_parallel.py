#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
before予測を並列生成するスクリプト（CSV方式対応版）

generate_before_fast.py のN並列版。
generate_features_parallel.py と同じパターンで multiprocessing.Pool を使用。

【動作】
  Phase 1: 対象レースを日付で分割 → N ワーカーが並列にCSV書き出し（DBは読み取りのみ）
  Phase 2: CSVファイルをシングルプロセスでDB UPSERT投入（書き込み競合回避）

【速度改善】
  単一プロセス版: ~10分/日 → 365日で~60時間
  6並列版: ~10時間見込み（6倍速）

【使用方法】
  # 6並列（デフォルト）
  python scripts/prediction/generate_before_fast_parallel.py --year 2025 --force

  # ワーカー数指定
  python scripts/prediction/generate_before_fast_parallel.py --year 2025 --force --workers 4

  # CSVのみ（DB投入なし）
  python scripts/prediction/generate_before_fast_parallel.py --year 2025 --force --csv-only

  # DB投入のみ（既存CSVから）
  python scripts/prediction/generate_before_fast_parallel.py --year 2025 --import-only

【注意】
  - 各ワーカーが独立した RacePredictor + BatchDataLoader + DataManager を使用
  - メモリ使用量: ワーカー数 × 約500MB〜1GB
  - Phase 1 はDB読み取りのみ（WALモードで並行アクセス可能）
  - Phase 2 はシングルプロセスで順次投入（書き込み競合を回避）
  - CSVは data/predictions_csv/before/YYYY/YYYY-MM-DD.csv に保存
"""
import sys
import os
import io
import csv
import sqlite3
import warnings
import argparse
import multiprocessing as mp
from datetime import datetime
from pathlib import Path
from collections import OrderedDict

warnings.filterwarnings('ignore')

# NOTE: sys.stdout/stderr の TextIOWrapper 置き換えは __main__ ガード内で行う。
# Windows の multiprocessing spawn でモジュール再実行時に
# サブプロセスの閉じたバッファに TextIOWrapper を被せるとクラッシュするため。

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

CSV_BASE_DIR = os.path.join(PROJECT_ROOT, 'data', 'predictions_csv', 'before')

CSV_FIELDNAMES = [
    'race_id', 'pit_number', 'rank_prediction', 'total_score',
    'confidence', 'racer_name', 'racer_number', 'applied_rules',
    'course_score', 'racer_score', 'motor_score', 'kimarite_score', 'grade_score',
    'prediction_type', 'generated_at',
]


def get_csv_path(race_date: str) -> str:
    """日付からCSVパスを生成"""
    year = race_date[:4]
    return os.path.join(CSV_BASE_DIR, year, f"{race_date}.csv")


def get_remaining_races(year, start_date=None, end_date=None, force=False):
    """before未生成のレースを一括取得（exhibition_timeありのみ）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    sd = start_date or f'{year}-01-01'
    ed = end_date   or f'{year}-12-31'

    # exhibition_timeがあるrace_idを一括取得
    cursor.execute('''
        SELECT DISTINCT rd.race_id
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.exhibition_time IS NOT NULL
    ''', (sd, ed))
    has_beforeinfo_ids = set(row[0] for row in cursor.fetchall())

    if force:
        existing_ids = set()
    else:
        cursor.execute('''
            SELECT DISTINCT race_id FROM race_predictions
            WHERE prediction_type = 'before'
            AND race_id IN (SELECT id FROM races WHERE race_date >= ? AND race_date <= ?)
        ''', (sd, ed))
        existing_ids = set(row[0] for row in cursor.fetchall())

    cursor.execute('''
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date >= ? AND race_date <= ?
        AND EXISTS (SELECT 1 FROM entries e WHERE e.race_id = races.id)
        ORDER BY race_date, venue_code, race_number
    ''', (sd, ed))
    all_races = cursor.fetchall()
    conn.close()

    total_with_beforeinfo = sum(1 for r in all_races if r[0] in has_beforeinfo_ids)
    already_done = len(has_beforeinfo_ids & existing_ids)
    remaining = [(r[0], r[1], r[2], r[3]) for r in all_races
                 if r[0] in has_beforeinfo_ids and r[0] not in existing_ids]
    return remaining, total_with_beforeinfo, already_done


def _predictions_to_csv_rows(race_id, predictions, prediction_type, generated_at):
    """予測結果をCSV行のリストに変換"""
    rows = []
    for pred in predictions:
        rows.append({
            'race_id': race_id,
            'pit_number': pred.get('pit_number'),
            'rank_prediction': pred.get('rank_prediction'),
            'total_score': pred.get('total_score'),
            'confidence': pred.get('confidence'),
            'racer_name': pred.get('racer_name'),
            'racer_number': pred.get('racer_number'),
            'applied_rules': pred.get('applied_rules'),
            'course_score': pred.get('course_score', 0),
            'racer_score': pred.get('racer_score', 0),
            'motor_score': pred.get('motor_score', 0),
            'kimarite_score': pred.get('kimarite_score', 0),
            'grade_score': pred.get('grade_score', 0),
            'prediction_type': prediction_type,
            'generated_at': generated_at,
        })
    return rows


def _preload_env_data_for_dates(dates):
    """
    環境情報を日付リストに対して一括プリロード。
    DataManager._get_race_environment() のN+1クエリを回避するため、
    ワーカー開始時に担当日付分を一括取得してdict化。
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    placeholders = ','.join('?' * len(dates))
    cursor.execute(f"""
        SELECT
            r.id,
            r.venue_code,
            r.race_time,
            rc.wind_direction,
            rc.wind_speed,
            rc.wave_height,
            rc.weather
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date IN ({placeholders})
    """, dates)

    env_cache = {}
    for row in cursor.fetchall():
        env_cache[row[0]] = {
            'venue_code': row[1],
            'race_time': row[2],
            'wind_direction': row[3],
            'wind_speed': row[4],
            'wave_height': row[5],
            'weather': row[6]
        }
    conn.close()
    return env_cache


def worker_generate(args_tuple):
    """
    ワーカープロセス: 担当日付範囲のレースをCSVに書き出す

    Args:
        args_tuple: (worker_id, date_list, races_by_date)

    Returns:
        {'worker_id': int, 'success': int, 'failed': int, 'csv_files': list, 'elapsed': float}
    """
    worker_id, date_list, races_by_date = args_tuple

    # サブプロセスでは stdout/stderr の TextIOWrapper 置き換えをしない。
    # multiprocessing サブプロセスではバッファが閉じているケースがあり、
    # 置き換えると "I/O operation on closed file" になる。
    # 代わりに devnull にリダイレクトして、print() が例外を出さないようにする。
    try:
        if sys.stdout is None or sys.stdout.closed:
            sys.stdout = open(os.devnull, 'w', encoding='utf-8')
        if sys.stderr is None or sys.stderr.closed:
            sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    except Exception:
        pass

    warnings.filterwarnings('ignore')

    # 各ワーカーで独立した Predictor と DataManager を初期化
    from src.prediction.predictor_helpers import create_standard_predictor
    from src.database.data_manager import DataManager

    predictor = create_standard_predictor(use_cache=True)
    data_manager = DataManager()

    # 環境情報を一括プリロード（_apply_environmental_penalty のN+1回避）
    env_cache = _preload_env_data_for_dates(date_list)
    data_manager._env_cache = env_cache

    use_batch = hasattr(predictor, 'predict_races_batch')

    success_count = 0
    failed_count = 0
    csv_files = []
    start_time = datetime.now()

    for date_idx, race_date in enumerate(date_list):
        day_races = races_by_date.get(race_date, [])
        if not day_races:
            continue

        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 日次キャッシュをロード
        if predictor.batch_loader:
            predictor.batch_loader.load_daily_data(race_date)

        day_race_ids = [r[0] for r in day_races]
        csv_buffer = []

        if use_batch:
            # バッチ処理: 1日分を一括推論
            try:
                batch_results = predictor.predict_races_batch(day_race_ids, use_beforeinfo=True)
            except Exception as e:
                print(f"  [W{worker_id}] batch error {race_date}: {type(e).__name__}: {str(e)[:80]}", flush=True)
                batch_results = {}

            for race_id, race_date_r, venue_code, race_number in day_races:
                predictions = batch_results.get(race_id, [])
                if predictions:
                    predictions = data_manager._apply_environmental_penalty(
                        [dict(p) for p in predictions], race_id
                    )
                    rows = _predictions_to_csv_rows(race_id, predictions, 'before', generated_at)
                    csv_buffer.extend(rows)
                    success_count += 1
                else:
                    failed_count += 1
        else:
            # フォールバック: 1レースずつ処理
            for race_id, race_date_r, venue_code, race_number in day_races:
                try:
                    predictions = predictor.predict_race(race_id, use_beforeinfo=True)
                    if predictions:
                        predictions = data_manager._apply_environmental_penalty(
                            [dict(p) for p in predictions], race_id
                        )
                        rows = _predictions_to_csv_rows(race_id, predictions, 'before', generated_at)
                        csv_buffer.extend(rows)
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1

        # 日単位でCSVに書き出し
        if csv_buffer:
            csv_path = get_csv_path(race_date)
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
                writer.writeheader()
                writer.writerows(csv_buffer)
            csv_files.append(csv_path)

        # 進捗表示（10日ごと）
        if date_idx > 0 and date_idx % 10 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = success_count / elapsed if elapsed > 0 else 0
            remaining_days = len(date_list) - date_idx
            eta_min = remaining_days / (date_idx / elapsed) / 60 if elapsed > 0 else 0
            print(f"  [W{worker_id}] {date_idx}/{len(date_list)}日 "
                  f"({success_count}件, {rate:.1f}/s, ETA:{eta_min:.0f}min)", flush=True)

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"  [Worker{worker_id}] 完了: {success_count}件/{elapsed/60:.1f}分", flush=True)
    return {
        'worker_id': worker_id,
        'success': success_count,
        'failed': failed_count,
        'csv_files': csv_files,
        'elapsed': elapsed,
    }


def phase2_import_csv_to_db(csv_dir: str) -> dict:
    """
    Phase 2: CSVファイルをDB UPSERT投入（シングルプロセス）

    DataManager.import_predictions_from_csv() を使用。
    """
    from src.database.data_manager import DataManager
    data_manager = DataManager()

    csv_files = sorted(Path(csv_dir).glob('*.csv'))
    if not csv_files:
        print(f"[!] CSVファイルなし: {csv_dir}")
        return {'total_rows': 0, 'failed_files': []}

    print(f"\n[Phase 2] {len(csv_files)}ファイルをDB投入中...")
    total_rows = 0
    failed_files = []

    for i, csv_path in enumerate(csv_files):
        count = data_manager.import_predictions_from_csv(str(csv_path))
        if count >= 0:
            total_rows += count
        else:
            failed_files.append(str(csv_path))
            print(f"  [X] 投入失敗: {csv_path.name}", flush=True)

        if (i + 1) % 50 == 0:
            print(f"  ... {i+1}/{len(csv_files)}ファイル完了 ({total_rows:,}行)", flush=True)

    return {'total_rows': total_rows, 'failed_files': failed_files}


def main():
    from scripts.safety_check import safety_check
    safety_check()

    parser = argparse.ArgumentParser(
        description='before予測を並列生成（N並列でCSV方式）'
    )
    parser.add_argument('--year', type=int, help='対象年度（例: 2025）')
    parser.add_argument('--start-date', type=str, default=None, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end-date',   type=str, default=None, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--workers', type=int, default=6,
                        help='並列ワーカー数（デフォルト: 6。メモリ不足時は減らす）')
    parser.add_argument('--force', action='store_true',
                        help='生成済みレースも再計算（DB DELETEなしで全件上書き）')
    parser.add_argument('--csv-only', action='store_true',
                        help='Phase 1のみ（CSV書き出し）。DB投入は後で実行')
    parser.add_argument('--import-only', action='store_true',
                        help='Phase 2のみ（CSV→DB投入）。既存CSVを再投入')
    args = parser.parse_args()

    if not args.year:
        parser.error('--year は必須です')

    year = args.year
    start_date = args.start_date
    end_date   = args.end_date
    range_str = f"{start_date or f'{year}-01-01'} ~ {end_date or f'{year}-12-31'}"

    print("=" * 70)
    print(f"{year}年 before予測 並列生成（{args.workers}並列・CSV方式）  [{range_str}]")
    if args.import_only:
        print("モード: Phase 2のみ（CSV→DB投入）")
    elif args.csv_only:
        print("モード: Phase 1のみ（CSV書き出し）")
    else:
        print("モード: Phase 1（CSV並列書き出し） + Phase 2（DB UPSERT投入）")
    if args.force:
        print("--force: 生成済みを含む全件再計算")
    print(f"DB: {DATABASE_PATH}")
    print("=" * 70)

    # --import-only: CSVからDB投入のみ
    if args.import_only:
        csv_dir = os.path.join(CSV_BASE_DIR, str(year))
        result2 = phase2_import_csv_to_db(csv_dir)
        print(f"\nDB投入: {result2['total_rows']:,}行, 失敗: {len(result2['failed_files'])}ファイル")
        return

    # 対象レース取得
    remaining_races, total_with_beforeinfo, already_done = get_remaining_races(
        year, start_date, end_date, force=args.force
    )

    print(f"展示タイムあり: {total_with_beforeinfo:,}件")
    print(f"生成済み: {already_done:,}件")
    print(f"残り: {len(remaining_races):,}件")
    print()

    if not remaining_races:
        print("全レース生成済みです。")
        return

    # 既存CSVを削除（重複防止）
    dates_to_process = set(r[1] for r in remaining_races)
    deleted_csv = 0
    for race_date in sorted(dates_to_process):
        csv_path = get_csv_path(race_date)
        if os.path.exists(csv_path):
            os.remove(csv_path)
            deleted_csv += 1
    if deleted_csv > 0:
        print(f"既存CSVを削除: {deleted_csv}日分（重複防止）")

    # 日付ごとにグループ化
    races_by_date = OrderedDict()
    for race_id, race_date, venue_code, race_number in remaining_races:
        races_by_date.setdefault(race_date, []).append((race_id, race_date, venue_code, race_number))

    all_dates = list(races_by_date.keys())
    n_workers = min(args.workers, len(all_dates))
    print(f"日付数: {len(all_dates)}日 -> {n_workers}ワーカーに分配")
    print(f"  ※ 各ワーカーが独立した Predictor + DataManager を初期化（メモリ: 約{n_workers}×500MB~1GB）")

    # 日付を連続チャンクでワーカーに分配（インクリメンタルキャッシュを有効化）
    # ラウンドロビンだと各ワーカーが飛び飛び日付を担当→_is_next_day()がFalseになりキャッシュ無効
    chunk_size = (len(all_dates) + n_workers - 1) // n_workers
    chunks = [all_dates[i * chunk_size:(i + 1) * chunk_size] for i in range(n_workers)]

    worker_args = [(i, chunk, dict(races_by_date)) for i, chunk in enumerate(chunks) if chunk]

    print(f"\n[Phase 1] {len(remaining_races):,}レースを{n_workers}並列で処理中...")
    print("-" * 70)

    t0 = datetime.now()
    with mp.Pool(processes=n_workers) as pool:
        results = pool.map(worker_generate, worker_args)

    total_success = sum(r['success'] for r in results)
    total_failed  = sum(r['failed']  for r in results)
    all_csv_files = []
    for r in results:
        all_csv_files.extend(r['csv_files'])

    elapsed1 = (datetime.now() - t0).total_seconds()
    print(f"\n[Phase 1 完了]")
    print(f"  成功: {total_success:,}件, 失敗: {total_failed:,}件")
    print(f"  所要時間: {elapsed1/60:.1f}分 ({elapsed1/3600:.1f}時間)")
    if total_success > 0 and elapsed1 > 0:
        print(f"  処理速度: {total_success/elapsed1:.1f}レース/秒（{n_workers}並列）")
    print(f"  CSVファイル数: {len(all_csv_files)}日分")

    if args.csv_only:
        print(f"\n--csv-only: DB投入はスキップ。")
        print(f"後で投入する場合:")
        print(f"  python scripts/prediction/generate_before_fast_parallel.py --year {year} --import-only")
        return

    if not all_csv_files:
        print("\n[!] CSVなし。DB投入をスキップ。")
        return

    # Phase 2: CSV -> DB UPSERT
    csv_dir = os.path.join(CSV_BASE_DIR, str(year))
    result2 = phase2_import_csv_to_db(csv_dir)
    elapsed_total = (datetime.now() - t0).total_seconds()

    print(f"\n=== 完了 ===")
    print(f"DB投入: {result2['total_rows']:,}行")
    if result2['failed_files']:
        print(f"失敗ファイル: {len(result2['failed_files'])}件")
    print(f"総所要時間: {elapsed_total/60:.1f}分 ({elapsed_total/3600:.1f}時間)")
    print(f"  Phase 1: {elapsed1/60:.1f}分")
    print(f"  Phase 2: {(elapsed_total-elapsed1)/60:.1f}分")


if __name__ == '__main__':
    mp.freeze_support()  # Windows でのマルチプロセス対応
    # メインプロセスでのみ stdout/stderr のエンコーディングを設定
    if sys.platform == 'win32':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass
    main()
