#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測再生成 並列リカバリースクリプト
--------------------------------------
Phase 1: advance/before 各年を --csv-only で並列実行（DB読み取りのみ・安全）
Phase 2: 各年のCSVをDBに逐次 UPSERT 投入

DB削除なし・不足分のみ補完
WALモード有効なので並列読み取りは安全

usage:
  python scripts/automation/run_prediction_parallel.py
  python scripts/automation/run_prediction_parallel.py --pred-type advance
  python scripts/automation/run_prediction_parallel.py --pred-type before
  python scripts/automation/run_prediction_parallel.py --phase2-only
"""
import sys
import io
import os
import subprocess
import argparse
import time
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

PY = sys.executable
GENERATE_ADV = ROOT_DIR / 'scripts' / 'prediction' / 'generate_advance_fast.py'
GENERATE_BEF = ROOT_DIR / 'scripts' / 'prediction' / 'generate_before_fast.py'
IMPORT_CSV   = ROOT_DIR / 'scripts' / 'prediction' / 'import_predictions_csv.py'

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

TS = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_FILE = LOG_DIR / f'prediction_parallel_{TS}.log'


def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def run_phase1_parallel(pred_type: str):
    """全年を --csv-only で同時起動し、全完了を待つ"""
    script = GENERATE_ADV if pred_type == 'advance' else GENERATE_BEF
    log(f'=== Phase 1 並列開始: {pred_type} {YEARS} ===')

    procs = {}
    for year in YEARS:
        child_log = LOG_DIR / f'parallel_child_{pred_type}_{year}_{TS}.log'
        cmd = [PY, str(script), '--year', str(year), '--csv-only']
        log(f'  起動: {pred_type} {year}年  ログ: {child_log.name}')
        f = open(child_log, 'w', encoding='utf-8')
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT_DIR))
        procs[year] = (proc, f, child_log, datetime.now())

    log(f'  {len(YEARS)}年分を並列実行中... 完了まで待機')

    # 全プロセス完了を待つ（60秒ごとに進捗ログ）
    while True:
        done = {}
        alive = {}
        for year, (proc, f, child_log, start) in procs.items():
            rc = proc.poll()
            if rc is not None:
                done[year] = rc
            else:
                alive[year] = (proc, f, child_log, start)

        if alive:
            elapsed = {y: int((datetime.now() - s).total_seconds() / 60)
                       for y, (_, _, _, s) in alive.items()}
            log(f'  実行中: {list(alive.keys())} (経過: {elapsed}分)')
            time.sleep(60)
        else:
            break

    # ファイルクローズ
    for year, (proc, f, child_log, start) in procs.items():
        f.close()
        elapsed = int((datetime.now() - start).total_seconds() / 60)
        status = 'OK' if done.get(year, -1) == 0 else f'RC={done.get(year, "?")}'
        log(f'  完了: {pred_type} {year}年 ({elapsed}分) [{status}]')

    errors = [y for y, rc in done.items() if rc != 0]
    if errors:
        log(f'  [WARN] 異常終了年: {errors}')
    log(f'=== Phase 1 完了: {pred_type} ===')


def run_phase2_sequential(pred_type: str):
    """全年のCSVをDBに逐次 import (--import-only)"""
    script = GENERATE_ADV if pred_type == 'advance' else GENERATE_BEF
    log(f'=== Phase 2 逐次DB投入: {pred_type} {YEARS} ===')

    for year in YEARS:
        csv_dir = ROOT_DIR / 'data' / 'predictions_csv' / pred_type / str(year)
        if not csv_dir.exists() or not list(csv_dir.glob('*.csv')):
            log(f'  {pred_type} {year}年: CSVなし（スキップ）')
            continue

        cnt = len(list(csv_dir.glob('*.csv')))
        log(f'  {pred_type} {year}年: {cnt}ファイル投入開始')
        child_log = LOG_DIR / f'parallel_import_{pred_type}_{year}_{TS}.log'
        cmd = [PY, str(script), '--import-only', str(csv_dir)]
        start = datetime.now()
        with open(child_log, 'w', encoding='utf-8') as f:
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT_DIR))
            proc.wait()
        elapsed = int((datetime.now() - start).total_seconds())
        status = 'OK' if proc.returncode == 0 else f'RC={proc.returncode}'
        log(f'  {pred_type} {year}年: 投入完了 ({elapsed}秒) [{status}]')

    log(f'=== Phase 2 完了: {pred_type} ===')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pred-type', choices=['advance', 'before', 'both'],
                        default='both', help='処理対象（advance/before/both）')
    parser.add_argument('--phase2-only', action='store_true',
                        help='Phase 2（CSV→DB投入）のみ実行')
    args = parser.parse_args()

    log('=' * 60)
    log('予測並列リカバリー開始')
    log(f'対象年度: {YEARS}')
    log(f'対象種別: {args.pred_type}')
    log(f'ログ: {LOG_FILE}')
    log('=' * 60)

    types = ['advance', 'before'] if args.pred_type == 'both' else [args.pred_type]

    for pred_type in types:
        if not args.phase2_only:
            run_phase1_parallel(pred_type)
        run_phase2_sequential(pred_type)

    log('=' * 60)
    log('全処理完了！')
    log('次のステップ:')
    log('  python scripts/automation/collect_all_data_complete.py --check-only')
    log('  python scripts/backtest/standard_backtest_unique.py --full')
    log('=' * 60)


if __name__ == '__main__':
    main()
