#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全プロセス完了後の後続処理パイプライン
========================================

実行中の複数プロセス（予測生成・kimarite補完・払戻金収集等）の完了を待ち、
後続のデータ補完・予測再生成・標準テストまでを一括自動実行する。

背景（2026-02-24時点）:
  - run_prediction_parallel.py（advance 2021/2024/2025）
  - generate_before_fast.py --year 2023 --csv-only
  - run_prediction_recovery.py（kimarite補完 2020→2021→2022）
  - followup_2023_import.py（PID 71388完了後に自動起動）
  - phase2_pipeline.py（払戻金収集 2023→2024→2025）
  以上が並行実行中。全完了後に以下を順次実行する:
    - データ充足率確認（情報表示）
    - trifecta_odds収集（シェルレース分 2020-2022年）
    - indicator_stats 再生成
    - 2020/2021/2022年 advance/before 予測再生成
    - 標準テスト実行
    - HANDOVER.md 自動更新

usage:
  python scripts/automation/post_recovery_pipeline.py
  python scripts/automation/post_recovery_pipeline.py --dry-run --skip-wait
  python scripts/automation/post_recovery_pipeline.py --start-from 3 --skip-odds
  python scripts/automation/post_recovery_pipeline.py --skip-2020 --skip-2021
  python scripts/automation/post_recovery_pipeline.py --continue-on-error
"""

import sys
import os
import io
import time
import subprocess
import argparse
import sqlite3
import re
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

DB_PATH = ROOT_DIR / 'data' / 'boatrace.db'
LOG_DIR = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

TS = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_FILE = LOG_DIR / f'post_recovery_{TS}.log'

# ────────────── スクリプトパス ──────────────
FETCH_ODDS      = ROOT_DIR / 'scripts' / 'data_collection' / 'fetch_odds_parallel_safe.py'
BUILD_STATS     = ROOT_DIR / 'scripts' / 'data_collection' / 'build_indicator_stats.py'
GENERATE_ADV    = ROOT_DIR / 'scripts' / 'prediction' / 'generate_advance_fast.py'
GENERATE_BEF    = ROOT_DIR / 'scripts' / 'prediction' / 'generate_before_fast.py'
BACKTEST        = ROOT_DIR / 'scripts' / 'backtest' / 'standard_backtest_unique.py'
HANDOVER_MD     = ROOT_DIR / 'docs' / 'HANDOVER.md'

# ────────────── 待機対象PID ──────────────
DEFAULT_WAIT_PIDS = {
    71388: 'run_prediction_parallel（advance 2021/2024/2025）',
    88028: 'generate_before_fast --year 2023 --csv-only',
    90860: 'run_prediction_recovery（kimarite補完 2020→2021→2022）',
    94448: 'followup_2023_import（PID 71388完了後に自動起動）',
}

# ────────────── trifecta_odds収集対象期間 ──────────────
ODDS_TARGETS = [
    {'label': '2020年9-12月', 'start': '2020-09-01', 'end': '2020-12-31'},
    {'label': '2021年11-12月', 'start': '2021-11-01', 'end': '2021-12-31'},
    {'label': '2022年1-12月', 'start': '2022-01-01', 'end': '2022-12-31'},
]

# ────────────── 予測再生成対象年 ──────────────
PREDICTION_YEARS = [2020, 2021, 2022]

# ────────────── STEP定義 ──────────────
TOTAL_STEPS = 9


# ════════════════════════════════════════════════════════════════
# ログ
# ════════════════════════════════════════════════════════════════
def log(msg, level=''):
    ts = datetime.now().strftime('%H:%M:%S')
    prefix = {
        'OK':   '[OK] ',
        'WARN': '[!!] ',
        'ERR':  '[EE] ',
        'SKIP': '[--] ',
        'INFO': '[..] ',
    }.get(level, '     ')
    line = f"[{ts}] {prefix}{msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def log_sep(title=''):
    log('=' * 65)
    if title:
        log(f"  {title}")
        log('=' * 65)


def log_step_header(step_num, title):
    log('')
    log_sep(f'STEP {step_num}/{TOTAL_STEPS}: {title}')


# ════════════════════════════════════════════════════════════════
# プロセス管理
# ════════════════════════════════════════════════════════════════
def is_running(pid):
    """PIDが実行中かどうかを確認（psutil使用）"""
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        # アクセス拒否 = プロセスは存在する
        return True
    except Exception:
        return False


def _kill_process_tree(pid):
    """プロセスツリーを停止"""
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


# ════════════════════════════════════════════════════════════════
# サブスクリプト実行
# ════════════════════════════════════════════════════════════════
def run(cmd, label, timeout_hours=None, dry_run=False):
    """サブスクリプトを実行して結果を返す。

    Args:
        cmd: 実行するコマンド（リスト形式）
        label: ログ表示用のラベル
        timeout_hours: タイムアウト（時間単位）。Noneでタイムアウトなし
        dry_run: Trueの場合、コマンドを表示するだけ

    Returns:
        True=成功、False=失敗
    """
    if dry_run:
        log(f"[{label}] DRY-RUN: {' '.join(str(c) for c in cmd)}")
        return True

    log(f"[{label}] 開始...")
    t0 = time.time()
    timeout_sec = timeout_hours * 3600 if timeout_hours else None

    # 子プロセスログファイル名を生成（安全な文字のみ使用）
    safe_label = label.replace(' ', '_').replace('/', '_')
    for ch in ['（', '）', '(', ')', '→', '〜', '～']:
        safe_label = safe_label.replace(ch, '')
    child_log = LOG_DIR / f"post_recovery_child_{safe_label}_{TS}.log"
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
        elapsed_h = timeout_hours if timeout_hours else 0
        log(f"[{label}] タイムアウト ({elapsed_h}h) - 停止中...", 'ERR')
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


# ════════════════════════════════════════════════════════════════
# DB確認
# ════════════════════════════════════════════════════════════════
def check_db_coverage(dry_run=False):
    """2020-2022年のDB充足率を表示"""
    if dry_run:
        log("  DRY-RUN: DB充足率チェックをスキップ")
        return

    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            c = conn.cursor()

            # entries充足率
            log('--- entries充足率（2020-2022年） ---')
            c.execute('''
                SELECT substr(r.race_date,1,4) as year,
                    COUNT(DISTINCT r.id) as total,
                    COUNT(DISTINCT e.race_id) as done,
                    ROUND(COUNT(DISTINCT e.race_id)*100.0/NULLIF(COUNT(DISTINCT r.id),0),1) as pct
                FROM races r LEFT JOIN entries e ON r.id = e.race_id
                WHERE substr(r.race_date,1,4) BETWEEN '2020' AND '2022'
                GROUP BY year ORDER BY year
            ''')
            for row in c.fetchall():
                log(f"  {row[0]}年: {row[2]:,}/{row[1]:,} ({row[3]}%)")

            # results充足率
            log('')
            log('--- results充足率（2020-2022年） ---')
            c.execute('''
                SELECT substr(r.race_date,1,4) as year,
                    COUNT(DISTINCT r.id) as total,
                    COUNT(DISTINCT res.race_id) as done,
                    ROUND(COUNT(DISTINCT res.race_id)*100.0/NULLIF(COUNT(DISTINCT r.id),0),1) as pct
                FROM races r LEFT JOIN results res ON r.id = res.race_id
                WHERE substr(r.race_date,1,4) BETWEEN '2020' AND '2022'
                GROUP BY year ORDER BY year
            ''')
            for row in c.fetchall():
                log(f"  {row[0]}年: {row[2]:,}/{row[1]:,} ({row[3]}%)")

            # kimarite充足率
            log('')
            log('--- kimarite充足率（2020-2022年、rank=1） ---')
            c.execute('''
                SELECT substr(ra.race_date,1,4) as year,
                    COUNT(*) as total,
                    SUM(CASE WHEN res.kimarite IS NOT NULL AND res.kimarite != '' THEN 1 ELSE 0 END) as done,
                    ROUND(SUM(CASE WHEN res.kimarite IS NOT NULL AND res.kimarite != '' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(*),0),1) as pct
                FROM results res
                JOIN races ra ON res.race_id = ra.id
                WHERE substr(ra.race_date,1,4) BETWEEN '2020' AND '2022'
                  AND res.rank = '1'
                GROUP BY year ORDER BY year
            ''')
            for row in c.fetchall():
                log(f"  {row[0]}年: {row[2]:,}/{row[1]:,} ({row[3]}%)")

            # trifecta_odds充足率
            log('')
            log('--- trifecta_odds充足率（2020-2022年） ---')
            c.execute('''
                SELECT substr(r.race_date,1,4) as year,
                    COUNT(DISTINCT r.id) as total_races,
                    COUNT(DISTINCT t.race_id) as has_odds,
                    ROUND(COUNT(DISTINCT t.race_id)*100.0/NULLIF(COUNT(DISTINCT r.id),0),1) as pct
                FROM races r LEFT JOIN trifecta_odds t ON r.id = t.race_id
                WHERE substr(r.race_date,1,4) BETWEEN '2020' AND '2022'
                GROUP BY year ORDER BY year
            ''')
            for row in c.fetchall():
                log(f"  {row[0]}年: {row[2]:,}/{row[1]:,} ({row[3]}%)")

    except Exception as e:
        log(f"  DB確認エラー: {e}", 'WARN')


# ════════════════════════════════════════════════════════════════
# HANDOVER.md 自動更新
# ════════════════════════════════════════════════════════════════
def update_handover(backtest_log_path, dry_run=False):
    """標準テストの子プロセスログからバックテスト結果を読み取り、
    HANDOVER.mdの該当セクションを更新する。

    Args:
        backtest_log_path: 標準テストの子プロセスログファイルパス
        dry_run: Trueの場合、更新内容を表示するだけ
    """
    if dry_run:
        log("  DRY-RUN: HANDOVER.md更新をスキップ")
        return True

    if not backtest_log_path or not Path(backtest_log_path).exists():
        log("  バックテストログが見つかりません", 'WARN')
        return False

    try:
        with open(backtest_log_path, 'r', encoding='utf-8', errors='replace') as f:
            backtest_output = f.read()
    except Exception as e:
        log(f"  バックテストログ読み取りエラー: {e}", 'WARN')
        return False

    # バックテスト結果から主要指標を抽出
    # パターン: "全体サマリー" や "合計" 行を探す
    roi_match = re.search(r'(?:全体|合計|6年間).*?ROI[:\s]*([0-9.]+)%', backtest_output)
    count_match = re.search(r'(?:全体|合計|6年間).*?(?:件数|購入)[:\s]*([0-9,]+)', backtest_output)
    profit_match = re.search(r'(?:全体|合計|6年間).*?(?:収支|損益)[:\s]*([+-]?[0-9,]+)', backtest_output)

    if not roi_match:
        log("  バックテストログからROIを抽出できませんでした", 'WARN')
        log("  HANDOVER.mdの手動更新をお勧めします", 'INFO')
        return False

    roi = roi_match.group(1)
    count = count_match.group(1) if count_match else '不明'
    profit = profit_match.group(1) if profit_match else '不明'

    log(f"  抽出結果: ROI={roi}%, 件数={count}, 収支={profit}円")

    # HANDOVER.mdを読み込み
    try:
        with open(HANDOVER_MD, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        log(f"  HANDOVER.md読み取りエラー: {e}", 'WARN')
        return False

    # 最終更新日を更新
    today = datetime.now().strftime('%Y-%m-%d')
    old_date_pattern = r'\*\*最終更新\*\*: [0-9]{4}-[0-9]{2}-[0-9]{2}（[^）]*）'
    new_date_str = f'**最終更新**: {today}（post_recovery_pipeline完了: ROI {roi}%）'
    content_updated = re.sub(old_date_pattern, new_date_str, content, count=1)

    if content_updated == content:
        log("  HANDOVER.mdの最終更新日パターンが見つかりません", 'WARN')
        # パターンに合致しなくても続行（別パターンの可能性）

    # 更新内容をバックテスト結果コメントとして追記
    # （既存のテーブルを直接書き換えるのはリスクが高いため、
    #   コメント形式で最新結果を追記する）
    update_marker = '\n<!-- post_recovery_pipeline auto-update -->\n'
    update_block = (
        f'{update_marker}'
        f'> **{today} post_recovery_pipeline自動更新**: '
        f'ユニーク版 6年間ROI={roi}%, 件数={count}, 収支={profit}円\n'
    )

    # 既存のauto-updateマーカーがあれば置換、なければ追記
    if '<!-- post_recovery_pipeline auto-update -->' in content_updated:
        # 既存マーカーから次の空行まで置換
        pattern = r'\n<!-- post_recovery_pipeline auto-update -->\n>.*?\n'
        content_updated = re.sub(pattern, update_block, content_updated, count=1)
    else:
        # "## 現在のプロジェクト方針" の直前に挿入
        insert_before = '## 🎯 現在のプロジェクト方針'
        if insert_before in content_updated:
            content_updated = content_updated.replace(
                insert_before,
                update_block + '\n' + insert_before
            )

    try:
        with open(HANDOVER_MD, 'w', encoding='utf-8') as f:
            f.write(content_updated)
        log("  HANDOVER.md更新完了", 'OK')
        return True
    except Exception as e:
        log(f"  HANDOVER.md書き込みエラー: {e}", 'WARN')
        return False


# ════════════════════════════════════════════════════════════════
# メイン処理
# ════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description='全プロセス完了後の後続処理パイプライン',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 通常実行（全STEP実行）
  python scripts/automation/post_recovery_pipeline.py

  # ドライラン（コマンド確認のみ）
  python scripts/automation/post_recovery_pipeline.py --dry-run --skip-wait

  # STEP 3から再開
  python scripts/automation/post_recovery_pipeline.py --start-from 3

  # オッズ収集と2020年再生成をスキップ
  python scripts/automation/post_recovery_pipeline.py --skip-odds --skip-2020
        """,
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='実際には実行せず、コマンドをログに出力するのみ')
    parser.add_argument('--skip-wait', action='store_true',
                        help='STEP 1: プロセス完了待機をスキップ')
    parser.add_argument('--skip-odds', action='store_true',
                        help='STEP 3: trifecta_odds収集をスキップ')
    parser.add_argument('--skip-indicator-stats', action='store_true',
                        help='STEP 4: indicator_stats再生成をスキップ')
    parser.add_argument('--skip-2020', action='store_true',
                        help='STEP 5: 2020年予測再生成をスキップ')
    parser.add_argument('--skip-2021', action='store_true',
                        help='STEP 6: 2021年予測再生成をスキップ')
    parser.add_argument('--skip-2022', action='store_true',
                        help='STEP 7: 2022年予測再生成をスキップ')
    parser.add_argument('--skip-backtest', action='store_true',
                        help='STEP 8: 標準テストをスキップ')
    parser.add_argument('--skip-handover', action='store_true',
                        help='STEP 9: HANDOVER.md自動更新をスキップ')
    parser.add_argument('--start-from', type=int, default=1,
                        help='指定STEP番号から開始（再開用）。例: --start-from 3')
    parser.add_argument('--continue-on-error', action='store_true',
                        help='STEPが失敗しても次のSTEPに進む（デフォルト: 失敗時停止）')
    parser.add_argument('--wait-pids', type=str, default=None,
                        help='完了を待つPIDリスト（カンマ区切り）。例: --wait-pids 71388,88028')
    args = parser.parse_args()

    py = sys.executable

    # ── ヘッダー出力 ──
    log_sep('後続処理パイプライン（post_recovery_pipeline）開始')
    log(f'ログファイル: {LOG_FILE}')
    log(f'開始時刻: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    log(f'Dry-run: {args.dry_run}')
    log(f'開始STEP: {args.start_from}')
    log(f'エラー時続行: {args.continue_on_error}')
    skip_info = []
    if args.skip_wait: skip_info.append('wait')
    if args.skip_odds: skip_info.append('odds')
    if args.skip_indicator_stats: skip_info.append('indicator_stats')
    if args.skip_2020: skip_info.append('2020')
    if args.skip_2021: skip_info.append('2021')
    if args.skip_2022: skip_info.append('2022')
    if args.skip_backtest: skip_info.append('backtest')
    if args.skip_handover: skip_info.append('handover')
    log(f'スキップ: {", ".join(skip_info) if skip_info else "なし"}')
    log('')

    # ── STEP成否の追跡 ──
    step_results = {}  # {step_num: ('成功'|'失敗'|'スキップ', elapsed_minutes)}
    pipeline_start = time.time()
    backtest_child_log = None  # STEP 8のログファイルパス（STEP 9で使用）

    def record_step(step_num, status, elapsed_min=0):
        step_results[step_num] = (status, elapsed_min)

    def should_stop(step_num):
        """前STEPが失敗して --continue-on-error でない場合、停止すべきか"""
        if args.continue_on_error:
            return False
        # 直前のSTEPの結果を確認
        for prev in range(step_num - 1, 0, -1):
            if prev in step_results and step_results[prev][0] == '失敗':
                return True
        return False

    # ==========================================================
    # STEP 1: 実行中プロセスの完了待機
    # ==========================================================
    if args.start_from <= 1:
        log_step_header(1, '実行中プロセスの完了待機')
        step1_start = time.time()

        if args.skip_wait:
            log('  プロセス待機スキップ（--skip-wait）', 'SKIP')
            record_step(1, 'スキップ')
        else:
            # 待機対象PIDの決定
            if args.wait_pids:
                pids = [int(p.strip()) for p in args.wait_pids.split(',')]
                wait_targets = {pid: f'PID={pid}' for pid in pids}
            else:
                wait_targets = DEFAULT_WAIT_PIDS

            if args.dry_run:
                log(f"  DRY-RUN: 以下のPIDの完了を待機する予定:")
                for pid, desc in wait_targets.items():
                    log(f"    PID={pid}: {desc}")
                record_step(1, '成功', 0)
            else:
                log(f'  待機対象: {len(wait_targets)}プロセス')
                for pid, desc in wait_targets.items():
                    running = is_running(pid)
                    log(f'    PID={pid} ({desc}): {"実行中" if running else "不在（完了済み）"}')

                # 全PID完了まで待機（タイムアウト72時間）
                timeout_sec = 72 * 3600
                wait_start = time.time()
                last_detail_log = time.time()
                DETAIL_INTERVAL = 600  # 10分ごとに詳細ログ

                while True:
                    alive_pids = {pid: desc for pid, desc in wait_targets.items() if is_running(pid)}

                    if not alive_pids:
                        elapsed_min = (time.time() - wait_start) / 60
                        log(f'  全プロセス完了確認 ({elapsed_min:.0f}分)', 'OK')
                        break

                    elapsed_total = time.time() - wait_start
                    if elapsed_total > timeout_sec:
                        log(f'  タイムアウト（72時間）: 残存PID={list(alive_pids.keys())}', 'ERR')
                        record_step(1, '失敗', elapsed_total / 60)
                        if not args.continue_on_error:
                            _print_summary(step_results, pipeline_start)
                            sys.exit(1)
                        break

                    # 10分ごとに詳細ログ
                    now = time.time()
                    if now - last_detail_log >= DETAIL_INTERVAL:
                        elapsed_min = elapsed_total / 60
                        log(f'  --- 待機状況 ({elapsed_min:.0f}分経過) ---')
                        for pid, desc in alive_pids.items():
                            log(f'    PID={pid} ({desc}): 実行中')
                        done_pids = set(wait_targets.keys()) - set(alive_pids.keys())
                        if done_pids:
                            log(f'    完了済み: {list(done_pids)}')
                        last_detail_log = now

                    time.sleep(30)  # 30秒ごとにポーリング

                step1_elapsed = (time.time() - step1_start) / 60
                if 1 not in step_results:
                    record_step(1, '成功', step1_elapsed)

    # ==========================================================
    # STEP 2: データ充足確認（情報表示のみ）
    # ==========================================================
    if args.start_from <= 2 and not should_stop(2):
        log_step_header(2, 'データ充足確認（情報表示のみ）')
        step2_start = time.time()

        check_db_coverage(dry_run=args.dry_run)

        step2_elapsed = (time.time() - step2_start) / 60
        record_step(2, '成功', step2_elapsed)

    # ==========================================================
    # STEP 3: trifecta_odds収集（シェルレース分 2020-2022年）
    # ==========================================================
    if args.start_from <= 3 and not should_stop(3):
        log_step_header(3, 'trifecta_odds収集（シェルレース分）')
        step3_start = time.time()

        if args.skip_odds:
            log('  trifecta_odds収集スキップ（--skip-odds）', 'SKIP')
            record_step(3, 'スキップ')
        else:
            step3_ok = True
            for target in ODDS_TARGETS:
                ok = run(
                    [py, str(FETCH_ODDS),
                     '--start-date', target['start'],
                     '--end-date', target['end']],
                    f'trifecta_odds {target["label"]}',
                    timeout_hours=12,
                    dry_run=args.dry_run,
                )
                if not ok:
                    step3_ok = False
                    if not args.continue_on_error:
                        break

            step3_elapsed = (time.time() - step3_start) / 60
            record_step(3, '成功' if step3_ok else '失敗', step3_elapsed)

            if not step3_ok and not args.continue_on_error:
                log('  STEP 3失敗: パイプライン停止', 'ERR')
                _print_summary(step_results, pipeline_start)
                sys.exit(1)

    # ==========================================================
    # STEP 4: indicator_stats 再生成
    # ==========================================================
    if args.start_from <= 4 and not should_stop(4):
        log_step_header(4, 'indicator_stats 再生成')
        step4_start = time.time()

        if args.skip_indicator_stats:
            log('  indicator_stats再生成スキップ（--skip-indicator-stats）', 'SKIP')
            record_step(4, 'スキップ')
        else:
            ok = run(
                [py, str(BUILD_STATS), '--yearly'],
                'indicator_stats 全期間+年別',
                timeout_hours=6,
                dry_run=args.dry_run,
            )
            step4_elapsed = (time.time() - step4_start) / 60
            record_step(4, '成功' if ok else '失敗', step4_elapsed)

            if not ok and not args.continue_on_error:
                log('  STEP 4失敗: パイプライン停止', 'ERR')
                _print_summary(step_results, pipeline_start)
                sys.exit(1)

    # ==========================================================
    # STEP 5: 2020年 advance/before 予測再生成（--force）
    # ==========================================================
    if args.start_from <= 5 and not should_stop(5):
        log_step_header(5, '2020年 advance/before 予測再生成')
        step5_start = time.time()

        if args.skip_2020:
            log('  2020年予測再生成スキップ（--skip-2020）', 'SKIP')
            record_step(5, 'スキップ')
        else:
            ok_adv = run(
                [py, str(GENERATE_ADV), '--year', '2020', '--force'],
                '2020年 advance予測',
                timeout_hours=None,
                dry_run=args.dry_run,
            )
            ok_bef = run(
                [py, str(GENERATE_BEF), '--year', '2020', '--force'],
                '2020年 before予測',
                timeout_hours=None,
                dry_run=args.dry_run,
            )
            step5_elapsed = (time.time() - step5_start) / 60
            ok = ok_adv and ok_bef
            record_step(5, '成功' if ok else '失敗', step5_elapsed)

            if not ok and not args.continue_on_error:
                log('  STEP 5失敗: パイプライン停止', 'ERR')
                _print_summary(step_results, pipeline_start)
                sys.exit(1)

    # ==========================================================
    # STEP 6: 2021年 advance/before 予測再生成（--force）
    # ==========================================================
    if args.start_from <= 6 and not should_stop(6):
        log_step_header(6, '2021年 advance/before 予測再生成')
        step6_start = time.time()

        if args.skip_2021:
            log('  2021年予測再生成スキップ（--skip-2021）', 'SKIP')
            record_step(6, 'スキップ')
        else:
            ok_adv = run(
                [py, str(GENERATE_ADV), '--year', '2021', '--force'],
                '2021年 advance予測',
                timeout_hours=None,
                dry_run=args.dry_run,
            )
            ok_bef = run(
                [py, str(GENERATE_BEF), '--year', '2021', '--force'],
                '2021年 before予測',
                timeout_hours=None,
                dry_run=args.dry_run,
            )
            step6_elapsed = (time.time() - step6_start) / 60
            ok = ok_adv and ok_bef
            record_step(6, '成功' if ok else '失敗', step6_elapsed)

            if not ok and not args.continue_on_error:
                log('  STEP 6失敗: パイプライン停止', 'ERR')
                _print_summary(step_results, pipeline_start)
                sys.exit(1)

    # ==========================================================
    # STEP 7: 2022年 advance/before 予測再生成（--force）
    # ==========================================================
    if args.start_from <= 7 and not should_stop(7):
        log_step_header(7, '2022年 advance/before 予測再生成')
        step7_start = time.time()

        if args.skip_2022:
            log('  2022年予測再生成スキップ（--skip-2022）', 'SKIP')
            record_step(7, 'スキップ')
        else:
            ok_adv = run(
                [py, str(GENERATE_ADV), '--year', '2022', '--force'],
                '2022年 advance予測',
                timeout_hours=None,
                dry_run=args.dry_run,
            )
            ok_bef = run(
                [py, str(GENERATE_BEF), '--year', '2022', '--force'],
                '2022年 before予測',
                timeout_hours=None,
                dry_run=args.dry_run,
            )
            step7_elapsed = (time.time() - step7_start) / 60
            ok = ok_adv and ok_bef
            record_step(7, '成功' if ok else '失敗', step7_elapsed)

            if not ok and not args.continue_on_error:
                log('  STEP 7失敗: パイプライン停止', 'ERR')
                _print_summary(step_results, pipeline_start)
                sys.exit(1)

    # ==========================================================
    # STEP 8: 標準テスト実行
    # ==========================================================
    if args.start_from <= 8 and not should_stop(8):
        log_step_header(8, '標準テスト実行（ユニーク版）')
        step8_start = time.time()

        if args.skip_backtest:
            log('  標準テストスキップ（--skip-backtest）', 'SKIP')
            record_step(8, 'スキップ')
        else:
            # バックテスト結果ログのパスを事前に構築
            safe_label = '標準テストユニーク版'
            backtest_child_log = LOG_DIR / f"post_recovery_child_{safe_label}_{TS}.log"
            ok = run(
                [py, str(BACKTEST), '--full'],
                '標準テスト（ユニーク版）',
                timeout_hours=1,
                dry_run=args.dry_run,
            )
            # 実際の子プロセスログのパスを特定
            # run()関数内で生成されるファイル名と一致させる
            actual_child_log = LOG_DIR / f"post_recovery_child_標準テストユニーク版_{TS}.log"
            if actual_child_log.exists():
                backtest_child_log = actual_child_log

            step8_elapsed = (time.time() - step8_start) / 60
            record_step(8, '成功' if ok else '失敗', step8_elapsed)

            if not ok and not args.continue_on_error:
                log('  STEP 8失敗: パイプライン停止', 'ERR')
                _print_summary(step_results, pipeline_start)
                sys.exit(1)

    # ==========================================================
    # STEP 9: HANDOVER.md 自動更新
    # ==========================================================
    if args.start_from <= 9 and not should_stop(9):
        log_step_header(9, 'HANDOVER.md 自動更新')
        step9_start = time.time()

        if args.skip_handover:
            log('  HANDOVER.md更新スキップ（--skip-handover）', 'SKIP')
            record_step(9, 'スキップ')
        else:
            if args.skip_backtest or backtest_child_log is None:
                log('  標準テストがスキップまたは未実行のため、HANDOVER.md更新をスキップ', 'SKIP')
                record_step(9, 'スキップ')
            else:
                ok = update_handover(backtest_child_log, dry_run=args.dry_run)
                step9_elapsed = (time.time() - step9_start) / 60
                record_step(9, '成功' if ok else '失敗', step9_elapsed)

    # ==========================================================
    # 最終サマリー
    # ==========================================================
    _print_summary(step_results, pipeline_start)


def _print_summary(step_results, pipeline_start):
    """パイプライン実行サマリーを表示"""
    log('')
    log_sep('パイプライン実行サマリー')

    step_names = {
        1: 'プロセス完了待機',
        2: 'データ充足確認',
        3: 'trifecta_odds収集',
        4: 'indicator_stats再生成',
        5: '2020年予測再生成',
        6: '2021年予測再生成',
        7: '2022年予測再生成',
        8: '標準テスト',
        9: 'HANDOVER.md更新',
    }

    success_count = 0
    fail_count = 0
    skip_count = 0

    for step_num in range(1, TOTAL_STEPS + 1):
        if step_num in step_results:
            status, elapsed = step_results[step_num]
            if status == '成功':
                mark = '[OK]'
                success_count += 1
            elif status == '失敗':
                mark = '[NG]'
                fail_count += 1
            else:
                mark = '[--]'
                skip_count += 1
            name = step_names.get(step_num, f'STEP {step_num}')
            log(f"  STEP {step_num}: {mark} {name} ({elapsed:.0f}分)")
        else:
            name = step_names.get(step_num, f'STEP {step_num}')
            log(f"  STEP {step_num}: [  ] {name} (未実行)")

    total_elapsed = (time.time() - pipeline_start) / 60
    log('')
    log(f'  成功: {success_count}  失敗: {fail_count}  スキップ: {skip_count}')
    log(f'  総所要時間: {total_elapsed:.0f}分')
    log(f'  完了時刻: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    log('')

    if fail_count == 0:
        log_sep('後続処理パイプライン 全完了！')
    else:
        log_sep(f'後続処理パイプライン 完了（{fail_count}件の失敗あり）')

    log('')
    log('次のステップ:')
    log('  1. DB状態確認:')
    log('       python scripts/automation/collect_all_data_complete.py --check-only')
    if fail_count > 0:
        log(f'  2. 失敗STEPの再実行:')
        for step_num, (status, _) in step_results.items():
            if status == '失敗':
                log(f'       python scripts/automation/post_recovery_pipeline.py --start-from {step_num}')
    log('')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log('')
        log('Ctrl+C で中断', 'WARN')
        sys.exit(130)
    except Exception as e:
        import traceback
        log(f'致命的エラー: {e}', 'ERR')
        log(traceback.format_exc(), 'ERR')
        sys.exit(1)
