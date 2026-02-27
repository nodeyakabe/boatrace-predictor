#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PID 11260（advance 2023）完了後に自動で最適化コードへ移行するスクリプト

動作フロー:
  1. PID 11260 の完了を監視（30秒ごとにポーリング）
  2. 完了を検知したら:
     a. 残プロセス停止（3812, 8056, 4572, 4316, 9868, 272）
     b. 各CSV を最終ファイル除いて DB 投入（Phase 2 先行実行）
        ※ 最終ファイルは書き込み中断の可能性があるためスキップ
     c. 最適化コード × 各年度を前半/後半に分割して計10プロセスで再起動
        ※ --start-date/--end-date で年を2分割 → 最長プロセスを半分に短縮
     d. post_recovery_pipeline を新PIDで再起動
  3. 全操作をログ記録

実行方法:
  nohup python scripts/automation/migrate_to_optimized.py > logs/migrate_watcher.log 2>&1 &
"""
import os
import sys
import io
import time
import subprocess
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

PYTHON = sys.executable

# ========= 設定 =========

# このPIDの完了を待ってから移行を開始
WAIT_PID = 11260  # advance 2023

# 完了後に停止するプロセスのPID
STOP_PIDS = [3812, 8056, 4572, 4316, 9868, 272]

# Phase 2 インポート対象（pred_type, year, csv_dir）
CSV_DIRS_TO_IMPORT = [
    ('advance', 2021, 'data/predictions_csv/advance/2021'),
    ('advance', 2024, 'data/predictions_csv/advance/2024'),
    ('advance', 2025, 'data/predictions_csv/advance/2025'),
    ('before',  2023, 'data/predictions_csv/before/2023'),
    ('before',  2024, 'data/predictions_csv/before/2024'),
]

# 再起動対象: 各年を前半・後半に分割して並列実行（計10プロセス）
# (pred_type, year, script, start_date, end_date, label)
# ※ DB登録済み日付はget_remaining_races()が自動スキップするため安全
RESTART_TARGETS = [
    # advance 2021: 前半（H1）後半（H2）
    ('advance', 2021, 'generate_advance_fast.py', '2021-01-01', '2021-06-30', 'H1'),
    ('advance', 2021, 'generate_advance_fast.py', '2021-07-01', '2021-12-31', 'H2'),
    # advance 2024: 前半後半
    ('advance', 2024, 'generate_advance_fast.py', '2024-01-01', '2024-06-30', 'H1'),
    ('advance', 2024, 'generate_advance_fast.py', '2024-07-01', '2024-12-31', 'H2'),
    # advance 2025: 前半後半
    ('advance', 2025, 'generate_advance_fast.py', '2025-01-01', '2025-06-30', 'H1'),
    ('advance', 2025, 'generate_advance_fast.py', '2025-07-01', '2025-12-31', 'H2'),
    # before 2023: 前半後半（最長プロセス → 分割効果が最大）
    ('before',  2023, 'generate_before_fast.py', '2023-01-01', '2023-06-30', 'H1'),
    ('before',  2023, 'generate_before_fast.py', '2023-07-01', '2023-12-31', 'H2'),
    # before 2024: 前半後半
    ('before',  2024, 'generate_before_fast.py', '2024-01-01', '2024-06-30', 'H1'),
    ('before',  2024, 'generate_before_fast.py', '2024-07-01', '2024-12-31', 'H2'),
]

LOG_DATE = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_PATH = PROJECT_ROOT / 'logs' / f'migrate_to_optimized_{LOG_DATE}.log'


# ========= ユーティリティ =========

def log(msg, also_print=True):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    if also_print:
        print(line, flush=True)


def is_alive(pid):
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != 'zombie'
    except Exception:
        return False


def kill_pid(pid):
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=10)
            log(f"  PID {pid}: 正常停止（SIGTERM）")
        except psutil.TimeoutExpired:
            proc.kill()
            log(f"  PID {pid}: 強制停止（SIGKILL）")
        return True
    except Exception as e:
        if 'NoSuchProcess' in type(e).__name__:
            log(f"  PID {pid}: 既に停止済み")
        else:
            log(f"  PID {pid}: 停止失敗 - {e}")
        return True


def get_csv_files_except_last(csv_dir):
    """
    ディレクトリ内のCSVを日付昇順でソートし、最終ファイルを除いた一覧を返す。
    最終ファイルは停止直前まで書き込み中だった可能性があるためスキップ。
    """
    csv_dir = Path(csv_dir)
    if not csv_dir.exists():
        return []
    files = sorted(csv_dir.glob('*.csv'))
    if len(files) <= 1:
        return []
    excluded = files[-1]
    log(f"    最終ファイルをスキップ: {excluded.name}（未完の可能性）")
    return files[:-1]


def import_csvs(pred_type, year, csv_dir):
    """CSVを最終ファイル除いてDB投入"""
    log(f"\n  [{pred_type}/{year}] CSVインポート開始")
    files = get_csv_files_except_last(csv_dir)
    if not files:
        log(f"    → インポート対象ファイルなし（スキップ）")
        return

    log(f"    → {len(files)}ファイルをインポート（〜{files[-1].name}）")
    file_args = [str(f) for f in files]
    cmd = [PYTHON, 'scripts/prediction/import_predictions_csv.py'] + file_args

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding='utf-8', errors='replace', cwd=str(PROJECT_ROOT)
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if any(kw in line for kw in ['DB投入', '成功', '失敗', '完了', 'ERROR']):
            log(f"    {line}")
    if result.returncode != 0:
        log(f"    [WARNING] インポートがエラーで終了（returncode={result.returncode}）")


def start_process(pred_type, year, script, start_date, end_date, label):
    """予測生成プロセスを起動してPIDを返す"""
    script_path = str(PROJECT_ROOT / 'scripts' / 'prediction' / script)
    log_name = f'{pred_type}_{year}_{label}_optimized_{LOG_DATE}.log'
    log_path = str(PROJECT_ROOT / 'logs' / log_name)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_file = open(log_path, 'w', encoding='utf-8')

    cmd = [PYTHON, script_path, '--year', str(year),
           '--start-date', start_date, '--end-date', end_date]

    kwargs = {}
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd, stdout=log_file, stderr=subprocess.STDOUT,
        cwd=str(PROJECT_ROOT), **kwargs
    )
    log(f"  {pred_type} {year} {label}: PID={proc.pid} "
        f"（{start_date}〜{end_date}） → {log_name}")
    return proc.pid


# ========= メイン処理 =========

def main():
    os.makedirs(PROJECT_ROOT / 'logs', exist_ok=True)

    log("=" * 60)
    log("migrate_to_optimized.py 開始（年度内分割版）")
    log(f"  監視PID: {WAIT_PID}（advance 2023）")
    log(f"  停止対象: {STOP_PIDS}")
    log(f"  再起動: {len(RESTART_TARGETS)}プロセス（各年を前半/後半に分割）")
    log("=" * 60)

    # --- STEP 1: PID 11260 の完了を監視 ---
    log(f"\n[STEP 1] PID {WAIT_PID} の完了を監視中...")
    while True:
        if not is_alive(WAIT_PID):
            log(f"  ✅ PID {WAIT_PID} の完了を確認。移行処理を開始します。")
            break
        log(f"  PID {WAIT_PID} 実行中... 次のチェックまで30秒", also_print=False)
        time.sleep(30)

    log("  バッファフラッシュ待機（30秒）...")
    time.sleep(30)

    # --- STEP 2: 残プロセスを停止 ---
    log(f"\n[STEP 2] 残プロセスを停止")
    for pid in STOP_PIDS:
        kill_pid(pid)
    log("  停止後の安定待機（15秒）...")
    time.sleep(15)

    # --- STEP 3: 生成済みCSVをDBにインポート ---
    log(f"\n[STEP 3] 生成済みCSVをDBにインポート（最終ファイルはスキップ）")
    for pred_type, year, csv_dir in CSV_DIRS_TO_IMPORT:
        import_csvs(pred_type, year, csv_dir)
    log("\n  インポート完了。3秒待機...")
    time.sleep(3)

    # --- STEP 4: 最適化コード × 前半/後半 分割で再起動 ---
    log(f"\n[STEP 4] 最適化コード × 日付分割で再起動（計{len(RESTART_TARGETS)}プロセス）")
    new_pids = []
    for pred_type, year, script, start_date, end_date, label in RESTART_TARGETS:
        pid = start_process(pred_type, year, script, start_date, end_date, label)
        new_pids.append(pid)
        time.sleep(3)  # 起動間隔（DB接続競合を避ける）

    log(f"\n  起動完了 PID一覧: {new_pids}")

    # --- STEP 5: post_recovery_pipeline を新PIDで再起動 ---
    log(f"\n[STEP 5] post_recovery_pipeline を新PIDで再起動")
    pids_str = ','.join(str(p) for p in new_pids)
    pr_log = str(PROJECT_ROOT / 'logs' / f'post_recovery_pipeline_migrated_{LOG_DATE}.log')
    pr_log_file = open(pr_log, 'w', encoding='utf-8')

    kwargs = {}
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    pr_proc = subprocess.Popen(
        [PYTHON, 'scripts/automation/post_recovery_pipeline.py',
         '--wait-pids', pids_str,
         '--skip-odds', '--continue-on-error'],
        stdout=pr_log_file, stderr=subprocess.STDOUT,
        cwd=str(PROJECT_ROOT), **kwargs
    )
    log(f"  post_recovery_pipeline: PID={pr_proc.pid} 起動 → {os.path.basename(pr_log)}")

    # --- 完了サマリー ---
    log("\n" + "=" * 60)
    log("✅ 移行完了")
    log(f"  新規プロセスPID: {new_pids}")
    log(f"  post_recovery PID: {pr_proc.pid}")
    log(f"  ログ: {LOG_PATH.name}")
    log("=" * 60)
    log("（このスクリプトは終了します。各プロセスはバックグラウンドで継続）")


if __name__ == '__main__':
    main()
