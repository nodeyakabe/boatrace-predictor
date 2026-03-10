#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prediction_features テーブル並列生成スクリプト

目的:
    generate_features.py の単一プロセス版を N 並列に拡張し、
    25時間/年 → 3〜4時間/年 に短縮する。

仕組み:
    Phase 1: 対象レースを日付で分割 → N ワーカーが並列にCSV書き出し（DBに触れない）
    Phase 2: CSVファイルを順次 prediction_features テーブルに UPSERT 投入

使用方法:
    # 特定年度（デフォルト6並列）
    python scripts/prediction/generate_features_parallel.py --year 2024

    # ワーカー数指定
    python scripts/prediction/generate_features_parallel.py --year 2024 --workers 8

    # 全年度
    python scripts/prediction/generate_features_parallel.py --start 2020-01-01 --end 2025-12-31

    # 強制再生成
    python scripts/prediction/generate_features_parallel.py --year 2024 --force

    # Phase 1のみ（CSV書き出し）
    python scripts/prediction/generate_features_parallel.py --year 2024 --csv-only

    # Phase 2のみ（CSV→DB投入）
    python scripts/prediction/generate_features_parallel.py --year 2024 --import-only

注意:
    - 各ワーカーが独立した RacePredictor + BatchDataLoader を使用
    - メモリ使用量: ワーカー数 × 約500MB〜1GB
    - Phase 1 はDB読み取りのみ（WALモードで並行アクセス可能）
    - Phase 2 はシングルプロセスで順次投入（書き込み競合を回避）
    - CSVは data/prediction_features_csv/YYYY/YYYY-MM-DD.csv に保存
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

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

CSV_BASE_DIR = os.path.join(PROJECT_ROOT, 'data', 'prediction_features_csv')

CSV_FIELDNAMES = [
    'race_id', 'pit_number',
    'racer_number', 'racer_name', 'racer_rank', 'motor_number',
    'venue_code', 'race_grade', 'race_date', 'data_quality',
    'exhibition_time', 'st_time',
    'course_score_raw', 'racer_score_raw', 'motor_score_raw',
    'kimarite_score_raw', 'grade_score_raw', 'extended_score_raw', 'compound_buff',
    'ext_class_score', 'ext_fl_penalty', 'ext_capsizing_penalty',
    'ext_session_score', 'ext_prev_race_score', 'ext_course_entry_score',
    'ext_matchup_score', 'ext_motor_score', 'ext_start_timing_score',
    'ext_exhibition_score', 'ext_tilt_score', 'ext_chikusen_time_score',
    'ext_recent_form_score', 'ext_venue_affinity_score',
    'ext_place_rate_score', 'ext_motor_second_rate_score',
    'total_score_final',
    'racer_overall_races', 'motor_total_races',
    'feature_version', 'updated_at',
    'original_confidence', 'original_rank_prediction',
]

UPSERT_SQL = """
INSERT INTO prediction_features (
    race_id, pit_number,
    racer_number, racer_name, racer_rank, motor_number,
    venue_code, race_grade, race_date, data_quality,
    exhibition_time, st_time,
    course_score_raw, racer_score_raw, motor_score_raw,
    kimarite_score_raw, grade_score_raw, extended_score_raw, compound_buff,
    ext_class_score, ext_fl_penalty, ext_capsizing_penalty,
    ext_session_score, ext_prev_race_score, ext_course_entry_score,
    ext_matchup_score, ext_motor_score, ext_start_timing_score,
    ext_exhibition_score, ext_tilt_score, ext_chikusen_time_score,
    ext_recent_form_score, ext_venue_affinity_score,
    ext_place_rate_score, ext_motor_second_rate_score,
    total_score_final,
    racer_overall_races, motor_total_races,
    feature_version, updated_at,
    original_confidence, original_rank_prediction
) VALUES (
    ?,?,  ?,?,?,?,  ?,?,?,?,  ?,?,
    ?,?,?,  ?,?,?,?,
    ?,?,?,  ?,?,?,  ?,?,?,  ?,?,?,  ?,?,  ?,?,
    ?,  ?,?,  ?,?,  ?,?
)
ON CONFLICT(race_id, pit_number) DO UPDATE SET
    racer_number=excluded.racer_number, racer_name=excluded.racer_name,
    racer_rank=excluded.racer_rank, motor_number=excluded.motor_number,
    venue_code=excluded.venue_code, race_grade=excluded.race_grade,
    race_date=excluded.race_date, data_quality=excluded.data_quality,
    exhibition_time=excluded.exhibition_time, st_time=excluded.st_time,
    course_score_raw=excluded.course_score_raw, racer_score_raw=excluded.racer_score_raw,
    motor_score_raw=excluded.motor_score_raw, kimarite_score_raw=excluded.kimarite_score_raw,
    grade_score_raw=excluded.grade_score_raw, extended_score_raw=excluded.extended_score_raw,
    compound_buff=excluded.compound_buff,
    ext_class_score=excluded.ext_class_score, ext_fl_penalty=excluded.ext_fl_penalty,
    ext_capsizing_penalty=excluded.ext_capsizing_penalty,
    ext_session_score=excluded.ext_session_score, ext_prev_race_score=excluded.ext_prev_race_score,
    ext_course_entry_score=excluded.ext_course_entry_score,
    ext_matchup_score=excluded.ext_matchup_score, ext_motor_score=excluded.ext_motor_score,
    ext_start_timing_score=excluded.ext_start_timing_score,
    ext_exhibition_score=excluded.ext_exhibition_score, ext_tilt_score=excluded.ext_tilt_score,
    ext_chikusen_time_score=excluded.ext_chikusen_time_score,
    ext_recent_form_score=excluded.ext_recent_form_score,
    ext_venue_affinity_score=excluded.ext_venue_affinity_score,
    ext_place_rate_score=excluded.ext_place_rate_score,
    ext_motor_second_rate_score=excluded.ext_motor_second_rate_score,
    total_score_final=excluded.total_score_final,
    racer_overall_races=excluded.racer_overall_races,
    motor_total_races=excluded.motor_total_races,
    feature_version=excluded.feature_version,
    updated_at=excluded.updated_at,
    original_confidence=excluded.original_confidence,
    original_rank_prediction=excluded.original_rank_prediction;
"""


def get_csv_path(race_date: str) -> str:
    year = race_date[:4]
    return os.path.join(CSV_BASE_DIR, year, f"{race_date}.csv")


def get_target_races(year=None, start_date=None, end_date=None, force=False):
    """特徴量生成対象のレースを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    sd = start_date or f'{year}-01-01'
    ed = end_date   or f'{year}-12-31'

    if force:
        existing_ids = set()
    else:
        cursor.execute("""
            SELECT DISTINCT race_id FROM prediction_features
            WHERE race_id IN (SELECT id FROM races WHERE race_date >= ? AND race_date <= ?)
        """, (sd, ed))
        existing_ids = set(row[0] for row in cursor.fetchall())

    cursor.execute("""
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date >= ? AND race_date <= ?
        AND EXISTS (SELECT 1 FROM entries e WHERE e.race_id = races.id)
        ORDER BY race_date, venue_code, race_number
    """, (sd, ed))
    all_races = cursor.fetchall()
    conn.close()

    remaining = [(r[0], r[1], r[2], r[3]) for r in all_races if r[0] not in existing_ids]
    return remaining, len(existing_ids)


def get_race_meta(conn, race_ids):
    """race_ids に対してメタ情報を一括取得"""
    if not race_ids:
        return {}
    placeholders = ','.join('?' * len(race_ids))
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT r.id, r.venue_code, r.race_grade, r.race_date,
               e.pit_number, e.racer_rank, e.motor_number,
               rd.exhibition_time, rd.st_time
        FROM races r
        JOIN entries e ON r.id = e.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        WHERE r.id IN ({placeholders})
    """, race_ids)
    result = {}
    for row in cursor.fetchall():
        rid, venue_code, race_grade, race_date, pit, racer_rank, motor_number, exhibition_time, st_time = row
        if rid not in result:
            result[rid] = {}
        result[rid][pit] = {
            'venue_code': venue_code or '',
            'race_grade': race_grade or '一般',
            'race_date': race_date or '',
            'racer_rank': racer_rank or 'B2',
            'motor_number': motor_number,
            'exhibition_time': exhibition_time,
            'st_time': st_time,
        }
    cursor.close()
    return result


def predictions_to_csv_rows(race_id, predictions, race_meta, now):
    """predict_race() の結果をCSV行dictに変換"""
    rows = []
    for pred in predictions:
        pit = pred['pit_number']
        meta = race_meta.get(pit, {})
        ed = pred.get('extended_detail') or {}

        def gs(key):
            v = ed.get(key)
            if v is None:
                return 0.0
            return v.get('score', 0.0) if isinstance(v, dict) else 0.0

        def gp(key):
            v = ed.get(key)
            if v is None:
                return 0.0
            return v.get('penalty', 0.0) if isinstance(v, dict) else 0.0

        matchup = ed.get('matchup')
        matchup_score = matchup.get('relative_score', 0.0) if isinstance(matchup, dict) else 0.0

        rows.append({
            'race_id': race_id,
            'pit_number': pit,
            'racer_number': pred.get('racer_number'),
            'racer_name': pred.get('racer_name'),
            'racer_rank': meta.get('racer_rank', 'B2'),
            'motor_number': pred.get('motor_number'),
            'venue_code': meta.get('venue_code', ''),
            'race_grade': meta.get('race_grade', '一般'),
            'race_date': meta.get('race_date', ''),
            'data_quality': '',
            'exhibition_time': meta.get('exhibition_time') or '',   # None→''（CSV経由で"None"文字列にならないよう）
            'st_time': meta.get('st_time') or '',                   # None→''
            'course_score_raw': pred.get('_course_score_raw', pred.get('course_score', 0.0)),
            'racer_score_raw': pred.get('_racer_score_raw', 0.0),
            'motor_score_raw': pred.get('_motor_score_raw', 0.0),
            'kimarite_score_raw': pred.get('_kimarite_score_raw', pred.get('kimarite_score', 0.0)),
            'grade_score_raw': pred.get('_grade_score_raw', pred.get('grade_score', 0.0)),
            'extended_score_raw': pred.get('_extended_score_raw', 0.0),
            'compound_buff': pred.get('compound_buff', 0.0),
            'ext_class_score': gs('class'),
            'ext_fl_penalty': gp('fl_penalty'),
            'ext_capsizing_penalty': gp('capsizing_penalty'),
            'ext_session_score': gs('session'),
            'ext_prev_race_score': gs('prev_race'),
            'ext_course_entry_score': gs('course_entry'),
            'ext_matchup_score': matchup_score,
            'ext_motor_score': gs('motor_extended') or gs('motor'),
            'ext_start_timing_score': gs('start_timing'),
            'ext_exhibition_score': gs('exhibition'),
            'ext_tilt_score': gs('tilt'),
            'ext_chikusen_time_score': gs('chikusen_time'),
            'ext_recent_form_score': gs('recent_form'),
            'ext_venue_affinity_score': gs('venue_affinity'),
            'ext_place_rate_score': gs('place_rate'),
            'ext_motor_second_rate_score': gs('motor_second_rate'),
            'total_score_final': pred.get('total_score', 0.0),
            'racer_overall_races': pred.get('_racer_overall_races', 0),
            'motor_total_races': pred.get('_motor_total_races', 0),
            'feature_version': '1.0-parallel',
            'updated_at': now,
            'original_confidence': pred.get('confidence') if pred.get('rank_prediction') == 1 else '',
            'original_rank_prediction': pred.get('rank_prediction', ''),
        })
    return rows


def worker_generate(args_tuple):
    """
    ワーカープロセス: 担当日付範囲のレースをCSVに書き出す（DBに触れない）

    Args:
        args_tuple: (worker_id, date_list, races_by_date)

    Returns:
        {'worker_id': int, 'success': int, 'failed': int, 'csv_files': list, 'elapsed': float}
    """
    worker_id, date_list, races_by_date = args_tuple

    # サブプロセスでのエンコーディング設定
    if sys.platform == 'win32':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass

    warnings.filterwarnings('ignore')

    # 各ワーカーで独立した Predictor を初期化
    from src.prediction.predictor_helpers import create_standard_predictor
    predictor = create_standard_predictor(use_cache=True)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    success_count = 0
    failed_count = 0
    csv_files = []
    start_time = datetime.now()

    for date_idx, race_date in enumerate(date_list):
        day_races = races_by_date.get(race_date, [])
        if not day_races:
            continue

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 日次キャッシュをロード
        if predictor.batch_loader:
            predictor.batch_loader.load_daily_data(race_date)

        day_race_ids = [r[0] for r in day_races]
        race_meta_all = get_race_meta(conn, day_race_ids)

        # バッチ推論（LightGBM一括推論）
        try:
            batch_results = predictor.predict_races_batch(day_race_ids, use_beforeinfo=True)
        except Exception as e:
            print(f"  [W{worker_id}] バッチエラー {race_date}: {type(e).__name__}: {str(e)[:80]}", flush=True)
            batch_results = {}

        csv_rows = []
        for race_id, _, _, _ in day_races:
            predictions = batch_results.get(race_id, [])
            if predictions:
                meta = race_meta_all.get(race_id, {})
                rows = predictions_to_csv_rows(race_id, predictions, meta, now)
                csv_rows.extend(rows)
                success_count += 1
            else:
                failed_count += 1

        # 日単位でCSVに書き出し
        if csv_rows:
            csv_path = get_csv_path(race_date)
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
                writer.writeheader()
                writer.writerows(csv_rows)
            csv_files.append(csv_path)

        # 30日ごとに進捗表示
        if date_idx > 0 and date_idx % 30 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = success_count / elapsed if elapsed > 0 else 0
            eta_min = (len(date_list) - date_idx) / (date_idx / elapsed) / 60 if elapsed > 0 else 0
            print(f"  [W{worker_id}] {date_idx}/{len(date_list)}日 ({rate:.1f}/s, ETA:{eta_min:.0f}min)", flush=True)

    conn.close()
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"  [Worker{worker_id}] 完了: {success_count}件/{elapsed/60:.1f}分", flush=True)
    return {
        'worker_id': worker_id,
        'success': success_count,
        'failed': failed_count,
        'csv_files': csv_files,
        'elapsed': elapsed,
    }


def phase2_import_csv_to_db(csv_files: list) -> dict:
    """Phase 2: CSVファイルを prediction_features テーブルに UPSERT 投入"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    total_rows = 0
    failed_files = []
    sorted_files = sorted(csv_files)
    print(f"\n[Phase 2] {len(sorted_files)}ファイルをDB投入中...")

    for i, csv_path in enumerate(sorted_files):
        if not os.path.exists(csv_path):
            print(f"  [!] ファイルなし: {csv_path}")
            failed_files.append(csv_path)
            continue
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = []
                for row in reader:
                    # 空文字列をNoneに変換（NULLとしてDB投入）
                    rows.append(tuple(
                        None if row.get(k, '') == '' else row[k]
                        for k in CSV_FIELDNAMES
                    ))
            if rows:
                conn.executemany(UPSERT_SQL, rows)
                conn.commit()
                total_rows += len(rows)
        except Exception as e:
            print(f"  [X] 投入失敗 {os.path.basename(csv_path)}: {e}", flush=True)
            failed_files.append(csv_path)

        if (i + 1) % 100 == 0:
            print(f"  ... {i+1}/{len(sorted_files)}ファイル完了 ({total_rows:,}行)", flush=True)

    conn.close()
    return {'total_rows': total_rows, 'failed_files': failed_files}


def main():
    parser = argparse.ArgumentParser(
        description='prediction_features 並列生成（N並列で25時間→3〜4時間に短縮）'
    )
    parser.add_argument('--year',    type=int, help='対象年度（例: 2024）')
    parser.add_argument('--start',   type=str, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end',     type=str, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--workers', type=int, default=6,
                        help='並列ワーカー数（デフォルト: 6。メモリ不足時は減らす）')
    parser.add_argument('--force',   action='store_true', help='既存特徴量も再生成（上書き）')
    parser.add_argument('--csv-only', action='store_true',
                        help='Phase 1のみ（CSV書き出し）。DB投入は後で --import-only で実行')
    parser.add_argument('--import-only', action='store_true',
                        help='Phase 2のみ（CSV→DB投入）。既存CSVを再投入する場合に使用')
    args = parser.parse_args()

    if not args.year and not args.start:
        parser.error('--year または --start を指定してください')

    sd = args.start or f'{args.year}-01-01'
    ed = args.end   or (f'{args.year}-12-31' if args.year else '2099-12-31')
    year_label = str(args.year) if args.year else f"{sd}〜{ed}"

    print("=" * 70)
    print(f"prediction_features 並列生成  [{year_label}]")
    print(f"ワーカー数: {args.workers}  DB: {DATABASE_PATH}")
    if args.force:
        print("モード: --force（全件再生成・上書き）")
    print("=" * 70)

    # --import-only: 指定年度のCSVをDB投入するだけ
    if args.import_only:
        year_str = sd[:4]
        csv_dir = os.path.join(CSV_BASE_DIR, year_str)
        csv_files = sorted(str(f) for f in Path(csv_dir).glob('*.csv'))
        if not csv_files:
            print(f"[!] CSVなし: {csv_dir}")
            return
        print(f"[import-only] {len(csv_files)}ファイルを投入")
        result2 = phase2_import_csv_to_db(csv_files)
        print(f"DB投入: {result2['total_rows']:,}行, 失敗: {len(result2['failed_files'])}ファイル")
        return

    # 対象レース取得
    remaining, already_done = get_target_races(
        year=args.year, start_date=args.start, end_date=args.end, force=args.force
    )
    print(f"対象: {len(remaining):,}レース（スキップ済み: {already_done:,}件）")
    if not remaining:
        print("生成対象なし。終了します。")
        return

    # 既存CSVを削除（重複防止）
    dates_to_process = set(r[1] for r in remaining)
    deleted = 0
    for d in dates_to_process:
        p = get_csv_path(d)
        if os.path.exists(p):
            os.remove(p)
            deleted += 1
    if deleted:
        print(f"既存CSV削除: {deleted}日分（重複防止）")

    # 日付ごとにグループ化
    races_by_date = OrderedDict()
    for race_id, race_date, venue_code, race_number in remaining:
        races_by_date.setdefault(race_date, []).append((race_id, race_date, venue_code, race_number))

    all_dates = list(races_by_date.keys())
    n_workers = min(args.workers, len(all_dates))
    print(f"日付数: {len(all_dates)}日 → {n_workers}ワーカーに分配（各{len(all_dates)//n_workers}〜{len(all_dates)//n_workers+1}日）")

    # 日付をラウンドロビンでワーカーに分配（負荷均等化）
    chunks = [[] for _ in range(n_workers)]
    for i, d in enumerate(all_dates):
        chunks[i % n_workers].append(d)

    worker_args = [(i, chunk, dict(races_by_date)) for i, chunk in enumerate(chunks) if chunk]

    print(f"\n[Phase 1] {len(remaining):,}レースを{n_workers}並列で処理中...")
    print(f"  ※ 各ワーカーが独立した Predictor を初期化します（メモリ: 約{n_workers}×500MB〜1GB）")
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
    print(f"  所要時間: {elapsed1/60:.1f}分")
    if total_success > 0 and elapsed1 > 0:
        print(f"  処理速度: {total_success/elapsed1:.1f}レース/秒（{n_workers}並列）")
    print(f"  CSVファイル数: {len(all_csv_files)}日分")

    if args.csv_only:
        print("\n--csv-only: DB投入はスキップ。")
        print(f"後で投入する場合: python scripts/prediction/generate_features_parallel.py --year {args.year} --import-only")
        return

    # Phase 2: CSV → DB UPSERT
    result2 = phase2_import_csv_to_db(all_csv_files)
    elapsed_total = (datetime.now() - t0).total_seconds()

    print(f"\n=== 完了 ===")
    print(f"DB投入: {result2['total_rows']:,}行")
    if result2['failed_files']:
        print(f"失敗ファイル: {len(result2['failed_files'])}件")
    print(f"総所要時間: {elapsed_total/60:.1f}分（Phase1: {elapsed1/60:.1f}分 + Phase2: {(elapsed_total-elapsed1)/60:.1f}分）")
    print(f"\n次のステップ:")
    print(f"  # スコアウェイト変更テスト（fast_backtest full モード）")
    print(f"  python scripts/backtest/fast_backtest.py --full")
    print(f"  python scripts/backtest/fast_backtest.py --full --motor-weight 25")
    print(f"  python scripts/backtest/fast_backtest.py --full --conf-a-gap 12 --motor-weight 25")


if __name__ == '__main__':
    mp.freeze_support()  # Windows でのマルチプロセス対応
    main()
