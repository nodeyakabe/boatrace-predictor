#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
シェルレースCSV DB投入 + 後続処理 リカバリースクリプト
======================================================

shellrace CSV（2020/2021/2022年のブルートフォース収集済みCSV）をDBに投入し、
後続の補完・予測生成までを一括自動実行する。

背景:
  - shellrace_2020/2021/2022 のCSVは収集完了済み（2月21-23日）
  - しかしDB投入が行われていなかった
    - phase2_pipeline.py は --skip-brute-force で起動されていた
      → STEP 4-6（CSV収集 → bulk_insert → kimarite → race_details）がすべてスキップ
    - CSV収集は完了していたが、DB投入ステップが skip された

現在のDB状態（2026-02-24時点）:
  - 2020年 entries: 54.1% (15,660/28,932) → 不足 13,272レース（主に9-12月）
  - 2021年 entries: 87.7% (48,900/55,728) → 不足 6,828レース（主に11-12月）
  - 2022年 entries: 68.4% (38,593/56,435) → 不足 17,842レース（主に8-12月）
  - race_details: 2021=100%, 2022=100%（補完不要）
  - trifecta_odds: entries有りレースに対しては既に収集済み

処理順序:
  STEP 1: 実行中プロセスの完了確認（オプション）
  STEP 2: shellrace CSV → DB投入（bulk_insert_from_csv.py: INSERT OR IGNORE）
  STEP 3: kimarite補完（新規投入レース分）
  STEP 4: trifecta_odds収集（新規投入レース分: 2020-2022年全体）
  STEP 5: indicator_stats 再生成（--yearly）
  STEP 6: 2022年 advance予測生成（CSV方式）
  STEP 7: 2022年 before予測生成（CSV方式）
  STEP 8: 標準テスト実行（最終確認）

usage:
  python scripts/automation/run_prediction_recovery.py
  python scripts/automation/run_prediction_recovery.py --dry-run
  python scripts/automation/run_prediction_recovery.py --skip-wait --start-from 3
  python scripts/automation/run_prediction_recovery.py --skip-wait --skip-odds --skip-indicator-stats
"""

import sys
import os
import io
import time
import subprocess
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

try:
    import psutil
except ImportError:
    print("psutil未インストール: pip install psutil")
    sys.exit(1)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

DB_PATH  = ROOT_DIR / 'data' / 'boatrace.db'
LOG_DIR  = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"shellrace_recovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ────────────── スクリプトパス ──────────────
BULK_INSERT     = ROOT_DIR / 'scripts' / 'maintenance' / 'bulk_insert_from_csv.py'
KIMARITE_SCRIPT = ROOT_DIR / 'scripts' / 'data_collection' / '補完_決まり手データ_改善版.py'
FETCH_ODDS      = ROOT_DIR / 'scripts' / 'data_collection' / 'fetch_odds_parallel_safe.py'
BUILD_STATS     = ROOT_DIR / 'scripts' / 'data_collection' / 'build_indicator_stats.py'
GENERATE_ADV    = ROOT_DIR / 'scripts' / 'prediction' / 'generate_advance_fast.py'
GENERATE_BEF    = ROOT_DIR / 'scripts' / 'prediction' / 'generate_before_fast.py'
BACKTEST        = ROOT_DIR / 'scripts' / 'backtest' / 'standard_backtest_unique.py'

# ────────────── CSV投入対象 ──────────────
SHELLRACE_TARGETS = [
    {
        'label':     '2020年シェルレース',
        'csv_dir':   ROOT_DIR / 'data' / 'csv' / 'shellrace_2020',
        'start':     '2020-09-01',
        'end':       '2020-12-31',
    },
    {
        'label':     '2021年シェルレース',
        'csv_dir':   ROOT_DIR / 'data' / 'csv' / 'shellrace_2021',
        'start':     '2021-11-01',
        'end':       '2021-12-31',
    },
    {
        'label':     '2022年シェルレース',
        'csv_dir':   ROOT_DIR / 'data' / 'csv' / 'shellrace_2022',
        'start':     '2022-01-01',
        'end':       '2022-12-31',
    },
]

# 待機対象PID（デフォルト）
DEFAULT_WAIT_PIDS = {
    97320: 'phase2_pipeline（払戻金収集中）',
    71388: 'run_prediction_parallel（予測生成中）',
    88028: '2023年before CSV生成',
    94448: 'followup_2023_import',
}


# ────────────── ログ ──────────────
def log(msg, level=''):
    ts = datetime.now().strftime('%H:%M:%S')
    prefix = {'OK': '[OK] ', 'WARN': '[!!] ', 'ERR': '[EE] '}.get(level, '     ')
    line = f"[{ts}] {prefix}{msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def log_sep(title=''):
    log('=' * 60)
    if title:
        log(f"  {title}")
        log('=' * 60)


# ────────────── プロセス管理 ──────────────
def is_running(pid):
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _kill_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
        _, alive = psutil.wait_procs(children + [parent], timeout=3)
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        log(f"  プロセスツリー停止エラー: {e}", 'WARN')


# ────────────── スクリプト実行 ──────────────
def run(cmd, label, timeout_hours=None, dry_run=False):
    """サブスクリプトを実行して結果を返す。"""
    if dry_run:
        log(f"[{label}] DRY-RUN: {' '.join(str(c) for c in cmd)}")
        return True

    log(f"[{label}] 開始...")
    t0 = time.time()
    timeout_sec = timeout_hours * 3600 if timeout_hours else None
    safe_label = label.replace(' ', '_').replace('/', '_')
    for ch in ['（', '）', '(', ')']:
        safe_label = safe_label.replace(ch, '')
    child_log = LOG_DIR / f"recovery_child_{safe_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log(f"  子プロセスログ: {child_log.name}")
    try:
        with open(child_log, 'w', encoding='utf-8', errors='replace') as fh:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=fh,
                stderr=subprocess.STDOUT,
            )
            proc.wait(timeout=timeout_sec)
        elapsed = (time.time() - t0) / 60
        if proc.returncode == 0:
            log(f"[{label}] 完了 ({elapsed:.0f}分)", 'OK')
            return True
        else:
            log(f"[{label}] 終了コード {proc.returncode} ({elapsed:.0f}分)", 'WARN')
            return False
    except subprocess.TimeoutExpired:
        log(f"[{label}] タイムアウト ({timeout_hours}h) - 停止中...", 'ERR')
        _kill_process_tree(proc.pid)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return False
    except Exception as e:
        log(f"[{label}] 例外: {e}", 'ERR')
        return False


# ────────────── DB状態確認 ──────────────
def check_db_status():
    """現在のDB entries充足率を表示"""
    log('--- DB entries充足率 ---')
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT substr(r.race_date,1,4) as year,
                    COUNT(DISTINCT r.id) as total,
                    COUNT(DISTINCT e.race_id) as done,
                    ROUND(COUNT(DISTINCT e.race_id)*100.0/COUNT(DISTINCT r.id),1) as pct
                FROM races r LEFT JOIN entries e ON r.id = e.race_id
                WHERE substr(r.race_date,1,4) BETWEEN '2020' AND '2022'
                GROUP BY year ORDER BY year
            ''')
            for row in c.fetchall():
                log(f"  {row[0]}年: {row[2]:,}/{row[1]:,} ({row[3]}%)")
    except Exception as e:
        log(f"  DB確認エラー: {e}", 'WARN')


# ────────────── メイン ──────────────
def main():
    parser = argparse.ArgumentParser(
        description='シェルレースCSV DB投入 + 後続処理 リカバリースクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='実際には実行せず、コマンドをログに出力するのみ')
    parser.add_argument('--skip-wait', action='store_true',
                        help='実行中プロセスの完了待ちをスキップ')
    parser.add_argument('--skip-odds', action='store_true',
                        help='trifecta_odds収集をスキップ')
    parser.add_argument('--skip-indicator-stats', action='store_true',
                        help='indicator_stats再生成をスキップ')
    parser.add_argument('--skip-predictions', action='store_true',
                        help='予測生成（advance/before）をスキップ')
    parser.add_argument('--skip-backtest', action='store_true',
                        help='標準テストをスキップ')
    parser.add_argument('--start-from', type=int, default=1,
                        help='開始STEP番号（デフォルト: 1）。例: --start-from 3')
    parser.add_argument('--wait-pids', type=str, default=None,
                        help='完了を待つPIDリスト（カンマ区切り）。例: --wait-pids 97320,71388')
    args = parser.parse_args()

    py = sys.executable

    log_sep('シェルレース リカバリー パイプライン 開始')
    log(f'ログ: {LOG_FILE}')
    log(f'開始時刻: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    log(f'Dry-run: {args.dry_run}')
    log(f'開始STEP: {args.start_from}')
    log('')

    # 投入前のDB状態
    check_db_status()
    log('')

    # =========================================================
    # STEP 1: 実行中プロセスの完了確認
    # =========================================================
    if args.start_from <= 1:
        log_sep('STEP 1: 実行中プロセスの完了確認')
        if not args.skip_wait:
            if args.wait_pids:
                pids = [int(p.strip()) for p in args.wait_pids.split(',')]
                wait_targets = {pid: f'PID={pid}' for pid in pids}
            else:
                wait_targets = DEFAULT_WAIT_PIDS

            all_done = True
            for pid, desc in wait_targets.items():
                if is_running(pid):
                    log(f'  {desc} (PID={pid}): 実行中 → 待機...')
                    start = time.time()
                    while is_running(pid):
                        elapsed = (time.time() - start) / 60
                        if elapsed > 60 * 48:  # 48時間タイムアウト
                            log(f'  {desc}: 48時間タイムアウト', 'WARN')
                            all_done = False
                            break
                        log(f'    待機中... ({elapsed:.0f}分経過)')
                        time.sleep(60)
                    else:
                        elapsed = (time.time() - start) / 60
                        log(f'  {desc}: 完了 ({elapsed:.0f}分)', 'OK')
                else:
                    log(f'  {desc} (PID={pid}): 不在（既に完了）')
        else:
            log('  プロセス待機スキップ（--skip-wait）')

    # =========================================================
    # STEP 2: shellrace CSV → DB投入
    # bulk_insert_from_csv.py を使用（INSERT OR IGNORE: 冪等）
    # races.csv → entries.csv → results.csv の順で投入
    # YYYYMMDD日付はスクリプト内で自動変換される
    # =========================================================
    if args.start_from <= 2:
        log_sep('STEP 2: shellrace CSV → DB投入')
        for target in SHELLRACE_TARGETS:
            csv_dir = target['csv_dir']
            label   = target['label']

            if not csv_dir.exists():
                log(f'  {label}: CSVディレクトリなし（スキップ）', 'WARN')
                continue

            # CSVファイル確認
            races_csv   = csv_dir / 'races.csv'
            entries_csv = csv_dir / 'entries.csv'
            results_csv = csv_dir / 'results.csv'

            if not races_csv.exists():
                log(f'  {label}: races.csvなし（スキップ）', 'WARN')
                continue

            log(f'  {label}: CSV投入開始')
            for f in [races_csv, entries_csv, results_csv]:
                if f.exists():
                    size_mb = f.stat().st_size / (1024 * 1024)
                    log(f'    {f.name}: {size_mb:.1f}MB')

            # bulk_insert_from_csv.py を使用
            # INSERT OR IGNORE方式なので既存データはスキップされる（冪等）
            run(
                [py, str(BULK_INSERT), '--input', str(csv_dir)],
                f'DB投入 {label}',
                timeout_hours=4,
                dry_run=args.dry_run,
            )

        # 投入後のDB状態確認
        log('')
        log('--- DB投入後の entries充足率 ---')
        if not args.dry_run:
            check_db_status()

    # =========================================================
    # STEP 3: kimarite補完（新規投入レース分）
    # 投入した期間のkimariteを公式サイトから補完
    # 既に補完済みのレースは自動スキップ（冪等）
    # =========================================================
    if args.start_from <= 3:
        log_sep('STEP 3: kimarite補完（新規投入レース分）')
        for target in SHELLRACE_TARGETS:
            run(
                [py, str(KIMARITE_SCRIPT),
                 '--start-date', target['start'],
                 '--end-date', target['end']],
                f'kimarite {target["label"]}',
                timeout_hours=4,
                dry_run=args.dry_run,
            )

    # =========================================================
    # STEP 4: trifecta_odds収集（2020-2022年全体）
    # 新規投入レース分のオッズを収集。
    # fetch_odds_parallel_safeは冪等（既存分はスキップ）。
    # バックテストに必須。
    # =========================================================
    if args.start_from <= 4:
        log_sep('STEP 4: trifecta_odds収集（2020-2022年）')
        if not args.skip_odds:
            run(
                [py, str(FETCH_ODDS),
                 '--start-date', '2020-01-01',
                 '--end-date', '2022-12-31'],
                'trifecta_odds 2020-2022年',
                timeout_hours=36,
                dry_run=args.dry_run,
            )
        else:
            log('  trifecta_odds収集スキップ（--skip-odds）')

    # =========================================================
    # STEP 5: indicator_stats 再生成（--yearly）
    # entries/resultsが増えたため統計指標を再生成する。
    # --yearly: 全期間統計 + 年別統計を両方実行
    # =========================================================
    if args.start_from <= 5:
        log_sep('STEP 5: indicator_stats 再生成')
        if not args.skip_indicator_stats:
            run(
                [py, str(BUILD_STATS), '--yearly'],
                'indicator_stats 全期間+年別',
                timeout_hours=6,
                dry_run=args.dry_run,
            )
        else:
            log('  indicator_stats再生成スキップ（--skip-indicator-stats）')

    # =========================================================
    # STEP 6: 2022年 advance予測生成（CSV方式）
    # 2020/2021年は run_prediction_parallel.py で既に生成中。
    # 2022年のadvanceは100%だが、新規entries分の再生成が必要。
    # ON CONFLICT DO UPDATEなので冪等。
    # =========================================================
    if args.start_from <= 6:
        log_sep('STEP 6: 2022年 advance予測生成')
        if not args.skip_predictions:
            run(
                [py, str(GENERATE_ADV), '--year', '2022', '--force'],
                '2022年 advance予測',
                timeout_hours=None,  # タイムアウトなし（24h以上の場合あり）
                dry_run=args.dry_run,
            )
        else:
            log('  予測生成スキップ（--skip-predictions）')

    # =========================================================
    # STEP 7: 2022年 before予測生成（CSV方式）
    # --force でCSV書き出し → DB UPSERT投入まで一括実行
    # =========================================================
    if args.start_from <= 7:
        log_sep('STEP 7: 2022年 before予測生成')
        if not args.skip_predictions:
            run(
                [py, str(GENERATE_BEF), '--year', '2022', '--force'],
                '2022年 before予測',
                timeout_hours=None,
                dry_run=args.dry_run,
            )
        else:
            log('  予測生成スキップ（--skip-predictions）')

    # =========================================================
    # STEP 8: 標準テスト実行（最終確認）
    # =========================================================
    if args.start_from <= 8:
        log_sep('STEP 8: 標準テスト（最終確認）')
        if not args.skip_backtest:
            run(
                [py, str(BACKTEST), '--full'],
                '標準テスト（ユニーク版）',
                timeout_hours=1,
                dry_run=args.dry_run,
            )
        else:
            log('  標準テストスキップ（--skip-backtest）')

    # =========================================================
    # 完了
    # =========================================================
    log('')
    log_sep('シェルレース リカバリー パイプライン 全完了！')
    log(f'完了時刻: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    # 最終DB状態
    if not args.dry_run:
        log('')
        check_db_status()

    log('')
    log('次のステップ:')
    log('  1. DB状態確認:')
    log('       python scripts/automation/collect_all_data_complete.py --check-only')
    log('  2. 標準テスト（手動確認）:')
    log('       python scripts/backtest/standard_backtest_unique.py --full')
    log('')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log('')
        log('Ctrl+C で中断', 'WARN')
    except Exception as e:
        import traceback
        log(f'致命的エラー: {e}', 'ERR')
        log(traceback.format_exc(), 'ERR')
