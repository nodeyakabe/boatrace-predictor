#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2023年予測フォローアップスクリプト
------------------------------------
WINPID=71388（並列リカバリー）完了後に自動で以下を実行:
  1. 2023年 advance 未生成分の補完
  2. 2023年 before CSV → DB UPSERT投入

【起動方法】
  python scripts/automation/followup_2023_import.py

  --wait-winpid 71388  # WINPIDが消えるまで待機
  --skip-advance       # advance補完をスキップ
  --skip-before-import # before CSV importをスキップ

作成日: 2026-02-24
背景: run_prediction_parallel.py の YEARS に 2023 が含まれていなかったため
      2023年の補完を別途実行する。
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

TS = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_FILE = LOG_DIR / f'followup_2023_{TS}.log'


def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def is_winpid_alive(winpid: int) -> bool:
    """WINPIDが実行中かどうかを確認"""
    try:
        result = subprocess.run(
            ['tasklist.exe', '/FI', f'PID eq {winpid}', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, errors='replace'
        )
        return str(winpid) in result.stdout
    except Exception:
        return False


def wait_for_winpid(winpid: int):
    """指定WINPIDが終了するまで待機"""
    log(f'WINPID={winpid} の完了を待機中...')
    check_interval = 60  # 60秒ごとにチェック
    start = datetime.now()
    while True:
        if not is_winpid_alive(winpid):
            elapsed = int((datetime.now() - start).total_seconds() / 60)
            log(f'WINPID={winpid} 終了確認 (待機時間: {elapsed}分)')
            return
        elapsed = int((datetime.now() - start).total_seconds() / 60)
        log(f'  まだ実行中 (経過: {elapsed}分)... {check_interval}秒後に再確認')
        time.sleep(check_interval)


def run_cmd(cmd, label):
    """コマンドを実行してログに記録"""
    child_log = LOG_DIR / f'followup_child_{label.replace(" ", "_")}_{TS}.log'
    log(f'[{label}] 開始 → {child_log.name}')
    start = datetime.now()
    with open(child_log, 'w', encoding='utf-8') as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT_DIR))
        proc.wait()
    elapsed = int((datetime.now() - start).total_seconds() / 60)
    status = 'OK' if proc.returncode == 0 else f'RC={proc.returncode}'
    log(f'[{label}] 完了 ({elapsed}分) [{status}]')
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(description='2023年予測フォローアップ')
    parser.add_argument('--wait-winpid', type=int, default=71388,
                        help='完了を待つWINPID（デフォルト: 71388）')
    parser.add_argument('--no-wait', action='store_true',
                        help='WINPID待機をスキップ（即時実行）')
    parser.add_argument('--skip-advance', action='store_true',
                        help='2023年 advance 補完をスキップ')
    parser.add_argument('--skip-before-import', action='store_true',
                        help='2023年 before CSV import をスキップ')
    args = parser.parse_args()

    log('=' * 60)
    log('2023年 予測フォローアップ開始')
    log(f'ログ: {LOG_FILE}')
    log('=' * 60)

    # WINPID待機
    if not args.no_wait:
        wait_for_winpid(args.wait_winpid)
    else:
        log('WINPID待機スキップ（--no-wait）')

    # 1. 2023年 advance 未生成分の補完
    if not args.skip_advance:
        log('')
        log('=== 2023年 advance 未生成分の補完 ===')
        run_cmd(
            [PY, str(GENERATE_ADV), '--year', '2023'],
            '2023_advance補完'
        )
    else:
        log('2023年 advance 補完スキップ（--skip-advance）')

    # 2. 2023年 before CSV → DB import
    if not args.skip_before_import:
        log('')
        log('=== 2023年 before CSV → DB import ===')
        before_csv_dir = ROOT_DIR / 'data' / 'predictions_csv' / 'before' / '2023'
        if before_csv_dir.exists():
            csv_count = len(list(before_csv_dir.glob('*.csv')))
            log(f'  CSVファイル数: {csv_count}ファイル')
            if csv_count > 0:
                run_cmd(
                    [PY, str(GENERATE_BEF), '--import-only', str(before_csv_dir)],
                    '2023_before_import'
                )
            else:
                log('  [WARN] CSVファイルが見つかりません（2023年 before CSV生成が未完了の可能性）')
        else:
            log(f'  [WARN] CSVディレクトリなし: {before_csv_dir}')
    else:
        log('2023年 before import スキップ（--skip-before-import）')

    log('')
    log('=' * 60)
    log('2023年フォローアップ完了！')
    log('次のステップ:')
    log('  python scripts/backtest/standard_backtest_unique.py --full')
    log('=' * 60)


if __name__ == '__main__':
    main()
