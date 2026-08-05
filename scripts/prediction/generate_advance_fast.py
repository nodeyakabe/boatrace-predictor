#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
advance予測を高速生成するスクリプト（CSV方式対応版）

【動作モード】
  通常モード（デフォルト）:
    予測計算 → CSVに書き出し → CSV→DB UPSERT の2フェーズで実行。
    DB一括削除が不要になり、中断しても生成済みCSVが残るため安全。

  --csv-only:
    Phase 1（予測計算→CSV書き出し）のみ実行。DB投入は後で手動実行。

  --import-only <csv_dir>:
    Phase 2（CSV→DB UPSERT）のみ実行。既存CSVを再投入する場合に使用。

【CSVファイル配置】
  data/predictions_csv/advance/{YYYY}/{YYYY-MM-DD}.csv  （1日1ファイル）

【その他】
- 未生成分のみ処理（既存DBのadvance予測が存在する日付はスキップ）
- コマンドライン引数で年度・期間指定
"""
import sys
import os
import io
import csv
import sqlite3
import warnings
import argparse
from datetime import datetime
from pathlib import Path

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.prediction.predictor_helpers import create_standard_predictor
from src.database.data_manager import DataManager
from config.settings import DATABASE_PATH

CSV_BASE_DIR = os.path.join(PROJECT_ROOT, 'data', 'predictions_csv', 'advance')


def get_csv_path(race_date: str) -> str:
    """日付からCSVパスを生成: data/predictions_csv/advance/YYYY/YYYY-MM-DD.csv"""
    year = race_date[:4]
    return os.path.join(CSV_BASE_DIR, year, f"{race_date}.csv")


def get_remaining_races(year, start_date=None, end_date=None, force=False):
    """未生成のレースを一括取得（DB上のadvance予測が存在しない日付が対象）

    Args:
        force: True の場合、生成済みレースも対象に含める（DB DELETEなしで全件再計算）
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    sd = start_date or f'{year}-01-01'
    ed = end_date   or f'{year}-12-31'

    if force:
        existing_ids = set()  # 全件を対象にする（--force 時はスキップしない）
    else:
        # 既存のadvance予測があるrace_idを一括取得
        cursor.execute('''
            SELECT DISTINCT race_id FROM race_predictions
            WHERE prediction_type = 'advance'
            AND race_id IN (SELECT id FROM races WHERE race_date >= ? AND race_date <= ?)
        ''', (sd, ed))
        existing_ids = set(row[0] for row in cursor.fetchall())

    # 対象範囲の全レースを取得（entriesが存在するもののみ）
    # entries欠損レース（brute force等で races/race_details/oddsのみ入ったもの）は
    # predict_race()が[]を返すため、事前にスキップして効率化する
    cursor.execute('''
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date >= ? AND race_date <= ?
        AND EXISTS (SELECT 1 FROM entries e WHERE e.race_id = races.id)
        ORDER BY race_date, venue_code, race_number
    ''', (sd, ed))
    all_races = cursor.fetchall()
    conn.close()

    remaining = [(r[0], r[1], r[2], r[3]) for r in all_races if r[0] not in existing_ids]
    return remaining, len(all_races), len(existing_ids)


def _flush_csv_buffer(csv_buffer, csv_path, fieldnames):
    """CSVバッファを一括書き出し（1日分をまとめて書き出す）"""
    if not csv_buffer:
        return True
    try:
        dirname = os.path.dirname(csv_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        file_exists = os.path.exists(csv_path)
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerows(csv_buffer)
        return True
    except Exception as e:
        print(f"  [!] CSV書き出しエラー ({csv_path}): {e}", flush=True)
        return False


CSV_FIELDNAMES = [
    'race_id', 'pit_number', 'rank_prediction', 'total_score',
    'confidence', 'racer_name', 'racer_number', 'applied_rules',
    'course_score', 'racer_score', 'motor_score', 'kimarite_score', 'grade_score',
    'prediction_type', 'generated_at',
]


def _predictions_to_csv_rows(race_id, predictions, prediction_type, generated_at):
    """予測結果をCSV行のリストに変換（DataManager.save_predictions_to_csv相当）"""
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


def _group_races_by_date(remaining_races):
    """レースを日付ごとにグループ化"""
    from collections import OrderedDict
    grouped = OrderedDict()
    for race_id, race_date, venue_code, race_number in remaining_races:
        if race_date not in grouped:
            grouped[race_date] = []
        grouped[race_date].append((race_id, race_date, venue_code, race_number))
    return grouped


def phase1_generate_to_csv(remaining_races, predictor) -> dict:
    """
    Phase 1: 予測計算 → CSVに書き出し（DBに触れない）

    最適化:
    - 日単位でCSVバッファリングし、日付が変わるタイミングで一括書き出し
    - predict_races_batch() による日次バッチ推論（LightGBM一括推論）
    - 従来の「1レースごとにファイルopen/close」を排除し、I/O効率を大幅向上

    Phase 1 開始前に、処理対象日付のCSVを削除してから新規作成する。
    これにより、中断後の再実行で同じ race_id が重複追記されることを防ぐ。

    Returns:
        {'success': int, 'failed': int, 'csv_files': set}
    """
    success_count = 0
    failed_count = 0
    csv_files = set()
    start_time = datetime.now()
    processed_races = 0

    # Phase 1 前処理: 対象日付のCSVを削除（追記による重複防止）
    dates_to_process = set(r[1] for r in remaining_races)
    deleted_csv = 0
    for race_date in sorted(dates_to_process):
        csv_path = get_csv_path(race_date)
        if os.path.exists(csv_path):
            os.remove(csv_path)
            deleted_csv += 1
    if deleted_csv > 0:
        print(f"  [前処理] 既存CSVを削除: {deleted_csv}日分（追記重複防止）")

    # predict_races_batch が利用可能か確認
    use_batch = hasattr(predictor, 'predict_races_batch')

    # 日付ごとにグループ化して処理
    grouped = _group_races_by_date(remaining_races)
    total_dates = len(grouped)

    for date_idx, (race_date, day_races) in enumerate(grouped.items()):
        # 進捗表示
        if processed_races > 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = success_count / elapsed if elapsed > 0 else 0
            remaining_count = len(remaining_races) - processed_races
            remaining_time = remaining_count / rate / 60 if rate > 0 else 0
            print(f" [{success_count}/{processed_races}] {rate:.1f}/s, {remaining_time:.0f}min left")
        print(f"[{race_date}] ({len(day_races)}R)", end='', flush=True)

        csv_path = get_csv_path(race_date)
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        csv_buffer = []

        # 日付が変わったらキャッシュを一括ロード
        if predictor.batch_loader:
            predictor.batch_loader.load_daily_data(race_date)

        if use_batch:
            # ==== バッチ処理: 1日分を一括推論 ====
            day_race_ids = [r[0] for r in day_races]
            try:
                batch_results = predictor.predict_races_batch(day_race_ids, use_beforeinfo=False)
            except Exception as e:
                print(f"\n  [!] バッチ推論エラー: {type(e).__name__}: {str(e)[:100]}", flush=True)
                batch_results = {}

            for race_id, race_date_r, venue_code, race_number in day_races:
                processed_races += 1
                predictions = batch_results.get(race_id, [])
                if predictions:
                    rows = _predictions_to_csv_rows(race_id, predictions, 'advance', generated_at)
                    csv_buffer.extend(rows)
                    success_count += 1
                    if success_count % 100 == 0:
                        print('.', end='', flush=True)
                else:
                    failed_count += 1
        else:
            # ==== フォールバック: 1レースずつ処理（従来方式） ====
            consecutive_errors = 0
            for race_id, race_date_r, venue_code, race_number in day_races:
                processed_races += 1
                try:
                    predictions = predictor.predict_race(race_id, use_beforeinfo=False)
                    if predictions:
                        rows = _predictions_to_csv_rows(race_id, predictions, 'advance', generated_at)
                        csv_buffer.extend(rows)
                        success_count += 1
                        consecutive_errors = 0
                        if success_count % 100 == 0:
                            print('.', end='', flush=True)
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    consecutive_errors += 1
                    if consecutive_errors == 1 or consecutive_errors % 100 == 0:
                        print(f"\n  [!] エラー(race_id={race_id}): {type(e).__name__}: {str(e)[:100]}", flush=True)
                    if consecutive_errors == 50:
                        print(f"\n  [!!] 連続50件エラー。キャッシュ再ロード中...", flush=True)
                        try:
                            if predictor.batch_loader:
                                predictor.batch_loader.clear_cache()
                                predictor.batch_loader.load_daily_data(race_date)
                        except Exception:
                            pass

        # 日単位でCSVフラッシュ
        if csv_buffer:
            if _flush_csv_buffer(csv_buffer, csv_path, CSV_FIELDNAMES):
                csv_files.add(csv_path)

    elapsed = (datetime.now() - start_time).total_seconds()
    print()
    # エラーサマリー
    if failed_count > 0:
        print(f"  [エラーサマリー] 失敗: {failed_count}件 / 処理: {success_count + failed_count}件")
    return {'success': success_count, 'failed': failed_count,
            'csv_files': csv_files, 'elapsed': elapsed}


def phase2_import_csv_to_db(csv_files: set) -> dict:
    """
    Phase 2: CSVファイルを DB に UPSERT 投入

    Args:
        csv_files: 投入対象CSVパスのセット

    Returns:
        {'total_rows': int, 'failed_files': list}
    """
    data_manager = DataManager(DATABASE_PATH)
    total_rows = 0
    failed_files = []

    sorted_files = sorted(csv_files)
    print(f"\n[Phase 2] {len(sorted_files)}ファイルをDB投入中...")

    for csv_path in sorted_files:
        if not os.path.exists(csv_path):
            print(f"  [!] ファイルなし: {csv_path}")
            failed_files.append(csv_path)
            continue
        count = data_manager.import_predictions_from_csv(csv_path)
        if count >= 0:
            total_rows += count
        else:
            failed_files.append(csv_path)
            print(f"  [X] 投入失敗: {csv_path}")

    return {'total_rows': total_rows, 'failed_files': failed_files}


def import_only_mode(csv_dir: str) -> int:
    """
    --import-only モード: 指定ディレクトリ配下のCSVをまとめてDB投入
    """
    data_manager = DataManager(DATABASE_PATH)
    csv_files = sorted(Path(csv_dir).rglob('*.csv'))
    if not csv_files:
        print(f"[!] CSVファイルが見つかりません: {csv_dir}")
        return 1

    print(f"[import-only] {len(csv_files)}ファイルをDB投入")
    total_rows = 0
    failed = 0
    for csv_path in csv_files:
        count = data_manager.import_predictions_from_csv(str(csv_path))
        if count >= 0:
            total_rows += count
            print(f"  [OK] {csv_path.name}: {count}件")
        else:
            failed += 1
            print(f"  [X] {csv_path.name}: 失敗")

    print(f"\n完了: 投入{total_rows}件, 失敗{failed}ファイル")
    return 0 if failed == 0 else 1


def main():
    from scripts.safety_check import safety_check
    safety_check()

    parser = argparse.ArgumentParser(description='advance予測を高速生成（CSV方式）')
    parser.add_argument('--year', type=int, help='対象年度（例: 2023）')
    parser.add_argument('--start-date', type=str, default=None, help='開始日（YYYY-MM-DD）省略時は年初')
    parser.add_argument('--end-date',   type=str, default=None, help='終了日（YYYY-MM-DD）省略時は年末')
    parser.add_argument('--csv-only', action='store_true',
                        help='Phase 1（予測計算→CSV）のみ実行。DB投入は行わない')
    parser.add_argument('--import-only', type=str, metavar='CSV_DIR',
                        help='Phase 2（CSV→DB）のみ実行。指定ディレクトリ配下のCSVを投入')
    parser.add_argument('--force', action='store_true',
                        help='生成済みレースもスキップせず再計算（DB DELETEなしで全件上書き再生成）')
    args = parser.parse_args()

    # --import-only モード
    if args.import_only:
        sys.exit(import_only_mode(args.import_only))

    if not args.year:
        parser.error('--year は必須です（--import-only を使う場合を除く）')

    year = args.year
    start_date = args.start_date
    end_date   = args.end_date
    range_str = f"{start_date or f'{year}-01-01'} 〜 {end_date or f'{year}-12-31'}"

    print("=" * 70)
    print(f"{year}年 advance予測 高速生成（CSV方式）  [{range_str}]")
    if args.csv_only:
        print("モード: Phase 1のみ（CSV書き出し、DB投入なし）")
    else:
        print("モード: Phase 1（CSV書き出し） + Phase 2（DB UPSERT投入）")
    if args.force:
        print("モード: --force 指定（生成済みを含む全件再計算・DB DELETEなし）")
    else:
        print("未生成分のみ処理（既存データは保持）")
    print("=" * 70)

    remaining_races, total_races, already_done = get_remaining_races(year, start_date, end_date, force=args.force)

    print(f"総レース数: {total_races:,}件")
    print(f"生成済み: {already_done:,}件")
    print(f"残り: {len(remaining_races):,}件")
    print()

    if not remaining_races:
        print("全レース生成済みです。")
        return

    # Predictor初期化（1回のみ）
    print("Predictor初期化中...")
    predictor = create_standard_predictor(use_cache=True)
    print("初期化完了")
    print()

    # Phase 1: 予測計算 → CSV書き出し
    print(f"[Phase 1] {len(remaining_races):,}件の予測計算 → CSV書き出し")
    print("-" * 70)
    result1 = phase1_generate_to_csv(remaining_races, predictor)
    print()
    print("=" * 70)
    print(f"Phase 1 完了")
    print(f"  成功: {result1['success']:,}件")
    print(f"  失敗: {result1['failed']:,}件")
    print(f"  所要時間: {result1['elapsed']/60:.1f}分")
    if result1['elapsed'] > 0 and result1['success'] > 0:
        print(f"  処理速度: {result1['success']/result1['elapsed']:.1f}件/秒")
    print(f"  CSVファイル数: {len(result1['csv_files'])}日分")
    print("=" * 70)

    if args.csv_only:
        print("\n--csv-only のため DB投入をスキップします。")
        print(f"DB投入は以下コマンドで実行できます:")
        year_dir = os.path.join(CSV_BASE_DIR, str(year))
        print(f"  python scripts/prediction/generate_advance_fast.py --import-only {year_dir}")
        return

    if not result1['csv_files']:
        print("\n[!] 書き出し成功のCSVがないため、DB投入をスキップします。")
        return

    # Phase 2: CSV → DB UPSERT
    result2 = phase2_import_csv_to_db(result1['csv_files'])
    print()
    print("=" * 70)
    print("Phase 2 完了")
    print(f"  DB投入: {result2['total_rows']:,}件")
    if result2['failed_files']:
        print(f"  失敗ファイル: {len(result2['failed_files'])}件")
        for f in result2['failed_files']:
            print(f"    {f}")
    print("=" * 70)


if __name__ == '__main__':
    main()
