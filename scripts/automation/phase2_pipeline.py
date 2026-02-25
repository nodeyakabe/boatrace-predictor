#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 2 パイプライン（overnight_pipeline後続・3日間放置対応）

overnight_pipeline完了後に以下を順次自動実行する。
起動してそのまま放置でOK。

実行順序:
  STEP 1:  overnight_pipeline 完了待ち
  STEP 2:  race_details 再補完（overnight失敗分: 2021/2022/2024/2025年）
  STEP 3:  trifecta_odds 2020-2022年収集（overnight STEP 7追加分）
  STEP 4:  ブルートフォースCSV 2020年完了待ち → import → kimarite → race_details
  STEP 5:  ブルートフォースCSV 2021年収集 → import → kimarite → race_details
  STEP 6:  ブルートフォースCSV 2022年収集 → import → kimarite → race_details
  STEP 7:  trifecta_odds 2020-2022年 全体再収集（brute force import後）
  STEP 8:  indicator_stats 再生成（全期間統計 + 年別）
  STEP 9:  advance/before予測再生成（2020/2021/2022/2024/2025年: 既存削除→再生成）
  STEP 10: 払戻金データ収集（2023/2024/2025年: fetch_to_csv → bulk_insert）

起動方法:
  python scripts/automation/phase2_pipeline.py

オプション:
  --overnight-pid 12920    overnight_pipelineのPID（デフォルト: 12920）
  --skip-overnight-wait    overnight完了待ちをスキップ（既に完了している場合）
  --skip-race-details      race_details再補完をスキップ
  --skip-brute-force       ブルートフォースCSV収集をスキップ
  --skip-odds              trifecta_odds収集をスキップ
  --skip-indicator-stats   indicator_stats再生成をスキップ
  --skip-predictions       予測再生成をスキップ

作成日: 2026-02-20
背景:
  overnight_pipelineで2021年race_detailsがタイムアウト失敗。
  ブルートフォースCSV収集（2020/2021/2022年）が別途必要。
  ユーザーが3日間離席するため全工程を自動化。
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

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

DB_PATH  = ROOT_DIR / 'data' / 'boatrace.db'
LOG_DIR  = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"phase2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ─────────────── スクリプトパス ───────────────
COLLECT_ALL     = ROOT_DIR / 'scripts' / 'automation'     / 'collect_all_data_complete.py'
FETCH_TO_CSV    = ROOT_DIR / 'scripts' / 'data_collection' / 'fetch_to_csv_parallel_improved.py'
BULK_INSERT     = ROOT_DIR / 'scripts' / 'maintenance'    / 'bulk_insert_from_csv.py'
FETCH_ODDS      = ROOT_DIR / 'scripts' / 'data_collection' / 'fetch_odds_parallel_safe.py'
BUILD_STATS     = ROOT_DIR / 'scripts' / 'data_collection' / 'build_indicator_stats.py'
GENERATE_ADV    = ROOT_DIR / 'scripts' / 'prediction'     / 'generate_advance_fast.py'
GENERATE_BEF    = ROOT_DIR / 'scripts' / 'prediction'     / 'generate_before_fast.py'
KIMARITE_SCRIPT = ROOT_DIR / 'scripts' / 'data_collection' / '補完_決まり手データ_改善版.py'
DETAILS_SCRIPT  = ROOT_DIR / 'scripts' / 'data_collection' / '補完_レース詳細データ_改善版v4.py'


# ─────────────── ログ ───────────────
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


# ─────────────── プロセス管理 ───────────────
def is_running(pid):
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def find_pids(keyword):
    pids = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' not in (p.info['name'] or '').lower():
                continue
            cmd = ' '.join(p.info['cmdline'] or [])
            if keyword in cmd:
                pids.append(p.pid)
        except Exception:
            pass
    return pids


def wait_for_pid(pid, label, check_interval=60, timeout_hours=None):
    """指定PIDが終了するまで待つ"""
    if not is_running(pid):
        log(f"{label}: 既に完了（PID={pid}不在）")
        return True
    start = time.time()
    log(f"{label}: PID={pid} の完了を待機中...")
    while True:
        if not is_running(pid):
            elapsed = (time.time() - start) / 60
            log(f"{label}: 完了 ({elapsed:.0f}分経過)", 'OK')
            return True
        elapsed = (time.time() - start) / 3600
        if timeout_hours and elapsed >= timeout_hours:
            log(f"{label}: タイムアウト ({timeout_hours}h)", 'WARN')
            return False
        log(f"  待機中... 経過{elapsed*60:.0f}分")
        time.sleep(check_interval)


def wait_for_keyword(keyword, label, check_interval=60, timeout_hours=None):
    """keywordに一致するプロセスが全て終了するまで待つ"""
    pids = find_pids(keyword)
    if not pids:
        log(f"{label}: 実行中プロセスなし（スキップ）")
        return True
    start = time.time()
    log(f"{label}: PID={pids} の完了を待機中...")
    while True:
        alive = find_pids(keyword)
        if not alive:
            elapsed = (time.time() - start) / 60
            log(f"{label}: 全プロセス完了 ({elapsed:.0f}分経過)", 'OK')
            return True
        elapsed = (time.time() - start) / 3600
        if timeout_hours and elapsed >= timeout_hours:
            log(f"{label}: タイムアウト ({timeout_hours}h) 残存={alive}", 'WARN')
            return False
        log(f"  待機中... PID={alive} (経過{elapsed*60:.0f}分)")
        time.sleep(check_interval)


# ─────────────── プロセスツリー停止 ───────────────
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
        log(f"  プロセスツリー停止完了: PID={pid}, 子プロセス={len(children)}個")
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        log(f"  プロセスツリー停止エラー: {e}", 'WARN')


# ─────────────── スクリプト実行 ───────────────
def run(cmd, label, timeout_hours=None):
    """サブスクリプトを実行して結果を返す。
    子プロセスの stdout/stderr は専用ログファイルに保存する（BUG-5対応）。
    """
    log(f"[{label}] 開始...")
    t0 = time.time()
    timeout_sec = timeout_hours * 3600 if timeout_hours else None
    safe_label = label.replace(' ', '_').replace('/', '_').replace('（', '').replace('）', '')
    child_log = LOG_DIR / f"phase2_child_{safe_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


# ─────────────── 予測削除 ───────────────
def delete_predictions_for_year(year, prediction_type=None):
    """指定年度の既存予測を削除する（BUG-2対応）。
    prediction_type='advance' または 'before' を指定するとその種別のみ削除。
    None の場合は advance/before 両方を削除する。
    advance と before を別々に削除することで、中断時の before 消失リスクを回避（HIGH-3対応）。
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            if prediction_type:
                cursor.execute('''
                    DELETE FROM race_predictions
                    WHERE race_id IN (
                        SELECT id FROM races
                        WHERE race_date >= ? AND race_date <= ?
                    )
                    AND prediction_type = ?
                ''', (f'{year}-01-01', f'{year}-12-31', prediction_type))
            else:
                cursor.execute('''
                    DELETE FROM race_predictions
                    WHERE race_id IN (
                        SELECT id FROM races
                        WHERE race_date >= ? AND race_date <= ?
                    )
                ''', (f'{year}-01-01', f'{year}-12-31'))
            deleted = cursor.rowcount
            conn.commit()
        type_str = f' ({prediction_type})' if prediction_type else ''
        log(f'  {year}年{type_str}: 既存予測 {deleted:,}件削除完了', 'OK')
        return deleted
    except Exception as e:
        log(f'  {year}年: 予測削除エラー: {e}', 'ERR')
        return 0


# ─────────────── メイン ───────────────
def main():
    parser = argparse.ArgumentParser(
        description='Phase 2 パイプライン（overnight_pipeline後続・3日間放置対応）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--overnight-pid', type=int, default=12920,
                        help='overnight_pipelineのPID（デフォルト: 12920）')
    parser.add_argument('--skip-overnight-wait', action='store_true',
                        help='overnight完了待ちをスキップ（既に完了している場合）')
    parser.add_argument('--skip-race-details', action='store_true',
                        help='race_details再補完をスキップ')
    parser.add_argument('--skip-brute-force', action='store_true',
                        help='ブルートフォースCSV収集をスキップ')
    parser.add_argument('--skip-odds', action='store_true',
                        help='trifecta_odds収集をスキップ')
    parser.add_argument('--skip-indicator-stats', action='store_true',
                        help='indicator_stats再生成をスキップ')
    parser.add_argument('--skip-predictions', action='store_true',
                        help='予測再生成をスキップ')
    parser.add_argument('--skip-payouts', action='store_true',
                        help='払戻金データ収集をスキップ')
    args = parser.parse_args()

    py = sys.executable

    log_sep('Phase 2 パイプライン 開始')
    log(f'ログ: {LOG_FILE}')
    log(f'開始時刻: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    log('')

    # =========================================================
    # STEP 1: overnight_pipeline 完了待ち
    # overnight_pipelineのSTEP 8（予測生成）が数時間かかるため待機
    # =========================================================
    log_sep('STEP 1: overnight_pipeline 完了待ち')
    if not args.skip_overnight_wait:
        # まずPID指定で確認、なければkeyword検索
        if is_running(args.overnight_pid):
            wait_for_pid(args.overnight_pid, 'overnight_pipeline', timeout_hours=16)
        else:
            # PIDs might differ; check by keyword
            if find_pids('overnight_pipeline'):
                wait_for_keyword('overnight_pipeline', 'overnight_pipeline', timeout_hours=16)
            else:
                log(f'overnight_pipeline: PID={args.overnight_pid} 不在、keywordでも見つからず（既に完了と判断）')
    else:
        log('overnight_pipeline 待機スキップ（--skip-overnight-wait）')

    # =========================================================
    # STEP 2: race_details 再補完（overnight失敗分）
    # overnight STEP 6: race_details 2024/2025 がタイムアウト（3h制限）で失敗。
    # overnight STEP 7c: race_details 2021/2022 がタイムアウト（4h制限）で失敗。
    # 全4年分を再補完する。
    # ポイント: collect_all_data_completeの内側タイムアウトを回避するため
    #           補完スクリプトを直接呼び出す（タイムアウト10h）
    # =========================================================
    log_sep('STEP 2: race_details 再補完（overnight失敗分: 2021/2022/2024/2025年）')
    if not args.skip_race_details:
        for year, start, end in [
            (2021, '2021-01-01', '2021-12-31'),
            (2022, '2022-01-01', '2022-12-31'),
            (2024, '2024-01-01', '2024-12-31'),
            (2025, '2025-01-01', '2025-12-31'),
        ]:
            log(f'  {year}年: 直接スクリプト実行（内側タイムアウト回避、最大10h）')
            run(
                [py, str(DETAILS_SCRIPT), '--start-date', start, '--end-date', end],
                f'race_details {year}年（直接実行）',
                timeout_hours=10,
            )
    else:
        log('race_details再補完スキップ（--skip-race-details）')

    # =========================================================
    # STEP 3: trifecta_odds 2020-2022年収集（overnight STEP 7追加分）
    # overnight STEP 7でentries/resultsが追加されたレースのオッズ。
    # バックテストに必須。2020-2022年全体を対象に収集。
    # =========================================================
    log_sep('STEP 3: trifecta_odds 2020-2022年収集（overnight STEP 7追加分）')
    if not args.skip_odds:
        run(
            [py, str(FETCH_ODDS), '--start-date', '2020-01-01', '--end-date', '2022-12-31'],
            'trifecta_odds 2020-2022年（第1回）',
            timeout_hours=36,
        )
    else:
        log('trifecta_odds収集スキップ（--skip-odds）')

    # =========================================================
    # STEP 4-6: ブルートフォースCSV 収集 → import → 補完
    # スケジュールAPIが不完全な過去データをブルートフォースで確実に収集する。
    # 2020年は既に別プロセス（PID=30012）で収集中なので完了待ちのみ。
    # =========================================================
    if not args.skip_brute_force:
        brute_force_targets = [
            {
                'label':           '2020年9-12月',
                'start':           '2020-09-01',
                'end':             '2020-12-31',
                'csv_dir':         ROOT_DIR / 'data' / 'csv' / 'shellrace_2020',
                'already_running': True,
                'wait_keyword':    'shellrace_2020',
            },
            {
                'label':           '2021年11-12月',
                'start':           '2021-11-01',
                'end':             '2021-12-31',
                'csv_dir':         ROOT_DIR / 'data' / 'csv' / 'shellrace_2021',
                'already_running': False,
                'wait_keyword':    None,
            },
            {
                'label':           '2022年8-12月',
                'start':           '2022-08-01',
                'end':             '2022-12-31',
                'csv_dir':         ROOT_DIR / 'data' / 'csv' / 'shellrace_2022',
                'already_running': False,
                'wait_keyword':    None,
            },
        ]

        for i, target in enumerate(brute_force_targets):
            step_num = 4 + i
            label    = target['label']
            start    = target['start']
            end      = target['end']
            csv_dir  = target['csv_dir']

            log_sep(f'STEP {step_num}: ブルートフォースCSV {label}')

            if target['already_running']:
                # 2020年: 既に別プロセスで収集中なので完了を待つ
                log(f'  {label}: 別プロセスで収集中。完了を待機...')
                wait_for_keyword(target['wait_keyword'], f'ブルートフォース {label}', timeout_hours=36)
            else:
                # 2021/2022年: 新規収集
                csv_dir.mkdir(parents=True, exist_ok=True)
                run(
                    [py, str(FETCH_TO_CSV),
                     '--start', start, '--end', end,
                     '--output', str(csv_dir),
                     '--workers', '8', '--brute-force'],
                    f'ブルートフォースCSV {label}',
                    timeout_hours=36,
                )

            # CSVが存在するか確認
            if not csv_dir.exists() or not any(csv_dir.glob('*.csv')):
                log(f'  {label}: CSVが見つかりません（後続処理スキップ）', 'WARN')
                continue

            # import_db
            run(
                [py, str(BULK_INSERT), '--input', str(csv_dir)],
                f'import_db {label}',
                timeout_hours=4,
            )

            # kimarite補完（当該期間のみ対象）
            run(
                [py, str(KIMARITE_SCRIPT), '--start-date', start, '--end-date', end],
                f'kimarite {label}',
                timeout_hours=4,
            )

            # race_details補完（当該期間のみ対象）
            run(
                [py, str(DETAILS_SCRIPT), '--start-date', start, '--end-date', end],
                f'race_details {label}',
                timeout_hours=10,
            )

    else:
        log('STEP 4-6: ブルートフォース収集スキップ（--skip-brute-force）')

    # =========================================================
    # STEP 7: trifecta_odds 2020-2022年 全体再収集
    # ブルートフォースでimportされた新規レース分のオッズを追加収集。
    # 既存分はスキップされる（fetch_odds_parallel_safeは冪等）。
    # =========================================================
    log_sep('STEP 7: trifecta_odds 2020-2022年 全体再収集（brute force import後）')
    if not args.skip_odds:
        run(
            [py, str(FETCH_ODDS), '--start-date', '2020-01-01', '--end-date', '2022-12-31'],
            'trifecta_odds 2020-2022年（第2回・最終）',
            timeout_hours=36,
        )
    else:
        log('trifecta_odds再収集スキップ（--skip-odds）')

    # =========================================================
    # STEP 8: indicator_stats 再生成（2020-2022年）
    # entries/resultsが増えたため統計指標を再生成する。
    # 注意: --start/--end と --yearly の同時指定では --start が優先されて
    #       --yearly が無視される（build_indicator_stats.pyの分岐ロジック仕様）。
    #       年別エントリを確実に生成するため、1年ずつ個別に実行する（BUG-1対応）。
    # =========================================================
    log_sep('STEP 8: indicator_stats 再生成（全期間統計 + 年別）')
    if not args.skip_indicator_stats:
        # --yearly: build_all_period（全期間統計、period_start='2000-01-01'、予測エンジンが参照）
        #         + build_yearly（年別統計）を両方実行する。
        # ※ --start/--end のみでは build_custom_period() のみ実行され全期間統計が更新されないため不可（CRITICAL-1対応）。
        run(
            [py, str(BUILD_STATS), '--yearly'],
            'indicator_stats 全期間 + 年別（2020-2025）',
            timeout_hours=6,
        )
    else:
        log('indicator_stats再生成スキップ（--skip-indicator-stats）')

    # =========================================================
    # STEP 9: advance/before予測再生成（全年度: 2020-2025年）
    #
    # 【再設計 2026-02-24】旧設計の問題点と対策:
    #   問題: DELETE後に6hタイムアウトでKill → データ消失
    #   問題: 2023年がYEARSから除外されovernight不完全のまま放置
    #   対策: --force --csv-only で全件再計算（DB DELETEなし）
    #   対策: 全年度を対象に変更（2023含む）
    #   対策: タイムアウトなし（1年分=10-24h が正常所要時間）
    #   対策: Phase 9a（CSV書き出し）→ Phase 9b（DB UPSERT）の2段階
    #         中断してもCSVが残るため再実行で復旧可能
    # =========================================================
    log_sep('STEP 9: advance/before予測再生成（全年度 2020-2025年）')
    if not args.skip_predictions:
        target_years = [2020, 2021, 2022, 2023, 2024, 2025]
        log(f'  対象年度: {target_years}')
        log('  方式: --force --csv-only → DB UPSERT（DELETEなし・タイムアウトなし）')

        # Phase 9a: 全年度のCSV書き出し（DBに触れない）
        log('  === Phase 9a: CSV書き出し ===')
        for y in target_years:
            log(f'--- {y}年 advance CSV書き出し ---')
            run(
                [py, str(GENERATE_ADV), '--year', str(y), '--csv-only', '--force'],
                f'advance CSV {y}年',
                timeout_hours=None,  # タイムアウトなし（24h以上かかる年もある）
            )
            log(f'--- {y}年 before CSV書き出し ---')
            run(
                [py, str(GENERATE_BEF), '--year', str(y), '--csv-only', '--force'],
                f'before CSV {y}年',
                timeout_hours=None,
            )

        # Phase 9b: CSV → DB UPSERT投入（高速、逐次）
        log('  === Phase 9b: CSV → DB UPSERT投入 ===')
        for y in target_years:
            for pred_type, script in [('advance', GENERATE_ADV), ('before', GENERATE_BEF)]:
                csv_dir = ROOT_DIR / 'data' / 'predictions_csv' / pred_type / str(y)
                if csv_dir.exists() and list(csv_dir.glob('*.csv')):
                    cnt = len(list(csv_dir.glob('*.csv')))
                    log(f'  {pred_type} {y}年: {cnt}ファイル投入')
                    run(
                        [py, str(script), '--import-only', str(csv_dir)],
                        f'{pred_type} DB投入 {y}年',
                        timeout_hours=2,
                    )
                else:
                    log(f'  {pred_type} {y}年: CSVなし（スキップ）', 'WARN')
    else:
        log('予測再生成スキップ（--skip-predictions）')

    # =========================================================
    # STEP 10: 払戻金データ収集（2023/2024/2025年）
    # 2020/2021/2022年はSTEP 4-6のブルートフォースCSVに含まれているため対象外。
    # 2023-2025年はスケジュールAPIが正常なので --brute-force 不要。
    # =========================================================
    log_sep('STEP 10: 払戻金データ収集（2023/2024/2025年）')
    if not args.skip_payouts:
        log('  2020-2022年はSTEP 4-6のブルートフォースで収集済み')
        log('  2023-2025年をfetch_to_csv → bulk_insertで追加収集')
        for yr in [2023, 2024, 2025]:
            csv_dir = ROOT_DIR / 'data' / 'csv' / f'payouts_{yr}'
            csv_dir.mkdir(parents=True, exist_ok=True)
            run(
                [py, str(FETCH_TO_CSV),
                 '--start', f'{yr}-01-01', '--end', f'{yr}-12-31',
                 '--output', str(csv_dir),
                 '--workers', '8'],
                f'払戻金CSV {yr}年',
                timeout_hours=12,
            )
            # HIGH-2対応: fetch_to_csv は entries/results/race_details 等も生成するが、
            # ここでは payouts のみを DB に投入したい。
            # payouts.csv 以外を削除してから bulk_insert を実行する。
            removed = []
            for f in csv_dir.glob('*.csv'):
                if f.name != 'payouts.csv':
                    f.unlink()
                    removed.append(f.name)
            if removed:
                log(f'  payouts専用インポートのため削除: {", ".join(removed)}')
            if not (csv_dir / 'payouts.csv').exists():
                log(f'  払戻金CSV {yr}年: payouts.csv が見つかりません（スキップ）', 'WARN')
                continue
            run(
                [py, str(BULK_INSERT), '--input', str(csv_dir)],
                f'払戻金import {yr}年',
                timeout_hours=4,
            )
    else:
        log('払戻金データ収集スキップ（--skip-payouts）')

    # =========================================================
    # 完了
    # =========================================================
    log('')
    log_sep('Phase 2 パイプライン 全完了！')
    log(f'完了時刻: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    log('')
    log('次のセッション開始時に以下を実行してください:')
    log('  1. データ充足率確認:')
    log('       python scripts/automation/collect_all_data_complete.py --check-only')
    log('  2. 標準テスト:')
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
