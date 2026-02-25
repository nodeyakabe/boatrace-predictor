#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
夜間自動パイプライン

起動したら放置でOK。以下を順番に自動実行する：
  1. fetch_csv完了待ち（2024+2025年収集終了まで）
  2. import_db（2024+2025年）
  3. generate_advance完了待ち（2023/2024年予想生成プロセスが終わるまで）
  4. ウォッチャー一時停止
  5. kimarite補完（2024+2025年）
  6. race_details補完（2024+2025年）
  7. シェルレース補完（2020年9-12月・2021年11-12月・2022年8-12月 計36,683件）
  7b. kimarite補完（2020/2021/2022年 ─ STEP 7で追加分）
  7c. race_details補完（2020/2021/2022年 ─ STEP 7で追加分）
  8. advance/before予測生成（2020〜2025年、年度順に順次実行）

【シェルレース問題について】
  2020年9月〜2022年12月の一部の月に、races行はあるがentries/resultsが
  存在しない「シェルレース」が合計36,683件存在する。
  日付フォーマットは正常（YYYY-MM-DD）。
  過去の収集スクリプト実行時にスケジュール登録だけされて
  実データ取得が失敗したと推測される。
  fetch_historical_data_parallel.pyでAPIから直接取得して補完する。

使い方:
    python scripts/automation/overnight_pipeline.py

オプション:
    --skip-2020-補完     2020年9-12月の補完をスキップ（高速化）
    --skip-import        import_dbをスキップ（デバッグ用）
"""

import sys
import os
import io
import time
import subprocess
import argparse
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

LOG_DIR = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"overnight_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

COLLECT_ALL     = ROOT_DIR / 'scripts' / 'automation' / 'collect_all_data_complete.py'
WATCHER_SCRIPT  = ROOT_DIR / 'scripts' / 'automation' / 'watch_and_generate_advance.py'
FETCH_HIST      = ROOT_DIR / 'scripts' / 'data_collection' / 'fetch_historical_data_parallel.py'
GENERATE_ADV    = ROOT_DIR / 'scripts' / 'prediction' / 'generate_advance_fast.py'
GENERATE_BEF    = ROOT_DIR / 'scripts' / 'prediction' / 'generate_before_fast.py'

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

# ─────────────── プロセス検索 ───────────────
def find_pids(keyword):
    """コマンドライン中にkeywordを含むPythonプロセスのPIDリスト"""
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

def is_running(pid):
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False

# ─────────────── 待機 ───────────────
def wait_for_pids(pids, label, check_interval=60, timeout_hours=None):
    """指定PIDが全て終了するまで待つ"""
    if not pids:
        log(f"{label}: 対象プロセスなし（スキップ）")
        return True

    start = time.time()
    log(f"{label}: PID={pids} の完了を待機中...")
    while True:
        alive = [pid for pid in pids if is_running(pid)]
        if not alive:
            elapsed = (time.time() - start) / 60
            log(f"{label}: 完了 ({elapsed:.0f}分経過)", 'OK')
            return True

        elapsed = (time.time() - start) / 3600
        if timeout_hours and elapsed >= timeout_hours:
            log(f"{label}: タイムアウト ({timeout_hours}時間) PID={alive} はまだ動いています", 'WARN')
            return False

        log(f"  待機中... 残存PID={alive} (経過{elapsed*60:.0f}分)")
        time.sleep(check_interval)

def wait_for_keyword(keyword, label, check_interval=60, timeout_hours=6):
    """keywordに一致するプロセスが全て終了するまで待つ"""
    start = time.time()
    pids = find_pids(keyword)
    if not pids:
        log(f"{label}: 実行中プロセスなし（スキップ）")
        return True
    log(f"{label}: PID={pids} の完了を待機中...")
    while True:
        alive = find_pids(keyword)
        if not alive:
            elapsed = (time.time() - start) / 60
            log(f"{label}: 全プロセス完了 ({elapsed:.0f}分経過)", 'OK')
            return True
        elapsed_h = (time.time() - start) / 3600
        if elapsed_h >= timeout_hours:
            log(f"{label}: タイムアウト ({timeout_hours}h) 残存={alive}", 'WARN')
            return False
        log(f"  待機中... PID={alive} (経過{elapsed_h*60:.0f}分)")
        time.sleep(check_interval)

# ─────────────── ウォッチャー操作 ───────────────
def stop_watcher():
    """ウォッチャーを停止（完了を待つ）"""
    pids = find_pids('watch_and_generate_advance')
    if not pids:
        log("ウォッチャー: 既に停止済み")
        return []
    log(f"ウォッチャー停止: PID={pids}")
    for pid in pids:
        try:
            p = psutil.Process(pid)
            p.terminate()
            log(f"  PID={pid} terminate送信")
        except Exception as e:
            log(f"  PID={pid} 停止エラー: {e}", 'WARN')
    # 最大30秒待つ
    deadline = time.time() + 30
    while time.time() < deadline:
        alive = [p for p in pids if is_running(p)]
        if not alive:
            log("ウォッチャー: 停止完了", 'OK')
            return pids
        time.sleep(2)
    log("ウォッチャー: 強制kill", 'WARN')
    for pid in find_pids('watch_and_generate_advance'):
        try:
            psutil.Process(pid).kill()
        except Exception:
            pass
    return pids

def start_watcher():
    """ウォッチャーをバックグラウンド起動"""
    log("ウォッチャー再起動中...")
    cmd = [sys.executable, str(WATCHER_SCRIPT)]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
    )
    time.sleep(3)
    if is_running(proc.pid):
        log(f"ウォッチャー起動完了 PID={proc.pid}", 'OK')
    else:
        log("ウォッチャー起動失敗", 'ERR')

# ─────────────── スクリプト実行 ───────────────
def _kill_process_tree(pid):
    """プロセスツリーを丸ごとkill（孤児プロセス防止）

    タイムアウト時にproc.kill()だけでは子プロセスが孤児として残る問題への対策。
    psutilを使って子プロセスを再帰的に列挙し、全てkillする。

    2026-02-20追加: race_details補完がタイムアウト後も孤児として動き続け、
    次のSTEPと競合するインシデントが発生したため。
    """
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        # 子プロセスから先にterminate
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        # 親もterminate
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
        # 3秒待ってまだ生きていたらkill
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


def run(cmd, label, timeout_hours=3):
    """サブスクリプトを実行して結果を返す"""
    log(f"[{label}] 開始...")
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            encoding='utf-8',
            errors='replace',
        )
        proc.wait(timeout=timeout_hours * 3600)
        elapsed = (time.time() - t0) / 60
        if proc.returncode == 0:
            log(f"[{label}] 完了 ({elapsed:.0f}分)", 'OK')
            return True
        else:
            log(f"[{label}] 終了コード {proc.returncode} ({elapsed:.0f}分)", 'WARN')
            return False
    except subprocess.TimeoutExpired:
        log(f"[{label}] タイムアウト ({timeout_hours}h) - プロセスツリーを停止中...", 'ERR')
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

# ─────────────── メイン ───────────────
def main():
    parser = argparse.ArgumentParser(description='夜間自動パイプライン')
    parser.add_argument('--skip-2020-补完', dest='skip_2020', action='store_true',
                        help='2020年9-12月の補完をスキップ')
    parser.add_argument('--skip-import', action='store_true', help='import_dbをスキップ')
    args = parser.parse_args()

    log_sep('夜間自動パイプライン 開始')
    log(f'ログ: {LOG_FILE}')
    log('')

    py = sys.executable

    # =========================================================
    # STEP 1: fetch_csv (2024+2025) 完了待ち
    # =========================================================
    log_sep('STEP 1: fetch_csv完了待ち (2024+2025)')
    wait_for_keyword('collect_all_data_complete', 'fetch_csv', timeout_hours=8)

    # =========================================================
    # STEP 2: import_db (2024+2025)
    # ─ fetch_csvはDB触らないのでウォッチャー動作中でも実行可
    # =========================================================
    if not args.skip_import:
        log_sep('STEP 2: import_db (2024+2025年)')
        for year in [2024, 2025]:
            run(
                [py, str(COLLECT_ALL), '--step', 'import_db', '--year', str(year), '--resume'],
                f'import_db {year}年',
                timeout_hours=1,
            )

    # =========================================================
    # STEP 3: generate_advance完了待ち
    # ─ kimarite/race_detailsはresultsテーブルに書くので
    #   生成プロセスが終わってから実行する
    # =========================================================
    log_sep('STEP 3: generate_advance完了待ち')
    wait_for_keyword('generate_advance_fast', 'generate_advance', timeout_hours=4)

    # =========================================================
    # STEP 4: ウォッチャー一時停止
    # =========================================================
    log_sep('STEP 4: ウォッチャー一時停止')
    stop_watcher()
    time.sleep(5)

    # =========================================================
    # STEP 5: kimarite補完 (2024+2025)
    # =========================================================
    log_sep('STEP 5: kimarite補完 (2024+2025年)')
    for year in [2024, 2025]:
        run(
            [py, str(COLLECT_ALL), '--step', 'kimarite', '--year', str(year)],
            f'kimarite {year}年',
            timeout_hours=3,
        )

    # =========================================================
    # STEP 6: race_details補完 (2024+2025)
    # =========================================================
    log_sep('STEP 6: race_details補完 (2024+2025年)')
    for year in [2024, 2025]:
        run(
            [py, str(COLLECT_ALL), '--step', 'race_details', '--year', str(year)],
            f'race_details {year}年',
            timeout_hours=3,
        )

    # =========================================================
    # STEP 7: 2020年9-12月の欠損データ補完
    # ─ APIから直接取得（shell races → 実データに更新）
    #
    # ⚠️ 注意（2026-02-20追記）:
    #   fetch_historical_data_parallel.pyはスケジュールAPIに依存するため、
    #   過去データ（2020-2022年）ではスケジュールAPIが不完全な会場をスキップする。
    #   この結果、補完効果が限定的になる可能性がある。
    #   スケジュールAPIが不完全な場合は、代わりに
    #   fetch_to_csv_parallel_improved.py --brute-force を使用すること。
    #   詳細: docs/guides/DATA_DEPENDENCY_CHAIN.md「スケジュールAPIの制約」
    # =========================================================
    # シェルレース補完対象（日付フォーマットは全てYYYY-MM-DD形式で問題なし）
    # 2020年9-12月: 13,272件、2021年11-12月: 6,828件、2022年8-12月: 16,583件
    shell_targets = [
        ('2020-09-01', '2020-12-31', '2020年9-12月', 13272),
        ('2021-11-01', '2021-12-31', '2021年11-12月', 6828),
        ('2022-08-01', '2022-12-31', '2022年8-12月', 16583),
    ]

    if not args.skip_2020:
        log_sep('STEP 7: シェルレース欠損データ補完（2020-2022年）')
        log('  対象: 合計36,683件のシェルレース（entries/results未取得）')
        log('  推定所要時間: 合計3〜5時間')
        for start, end, label, count in shell_targets:
            log(f'  [{label}] {count:,}件のシェルレースを補完中...')
            run(
                [py, str(FETCH_HIST), '--start', start, '--end', end, '--workers', '12'],
                f'{label}補完',
                timeout_hours=4,
            )

        # =====================================================
        # STEP 7b: kimarite補完（2020/2021/2022年）
        # ─ STEP 7でentries/resultsが追加されたレース分を補完
        # =====================================================
        log_sep('STEP 7b: kimarite補完（2020/2021/2022年）')
        for year in [2020, 2021, 2022]:
            run(
                [py, str(COLLECT_ALL), '--step', 'kimarite', '--year', str(year)],
                f'kimarite {year}年',
                timeout_hours=4,
            )

        # =====================================================
        # STEP 7c: race_details補完（2020/2021/2022年）
        # ─ STEP 7でentries/resultsが追加されたレース分を補完
        # =====================================================
        log_sep('STEP 7c: race_details補完（2020/2021/2022年）')
        # 2026-02-20修正: 2021年が4hタイムアウトで失敗した反省から8hに拡張
        # collect_all_data_complete内で4h×2リトライ=最大8hが動作できるよう調整
        for year in [2020, 2021, 2022]:
            run(
                [py, str(COLLECT_ALL), '--step', 'race_details', '--year', str(year)],
                f'race_details {year}年',
                timeout_hours=8,
            )
    else:
        log('STEP 7/7b/7c: シェルレース補完スキップ（--skip-2020-補完）')

    # =========================================================
    # STEP 8: advance/before予測生成（2020〜2025年）
    # ─ 年度順に advance → before を順次実行
    # =========================================================
    log_sep('STEP 8: advance/before予測生成（2020〜2025年）')
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        run(
            [py, str(GENERATE_ADV), '--year', str(year)],
            f'advance予測 {year}年',
            timeout_hours=6,
        )
        run(
            [py, str(GENERATE_BEF), '--year', str(year)],
            f'before予測 {year}年',
            timeout_hours=6,
        )

    # =========================================================
    # 完了
    # =========================================================
    log('')
    log_sep('夜間パイプライン 全完了！')
    log('次回セッション開始時に以下を確認してください:')
    log('  python scripts/automation/collect_all_data_complete.py --check-only')
    log('')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log('')
        log('Ctrl+C で中断', 'WARN')
    except Exception as e:
        log(f'致命的エラー: {e}', 'ERR')
        import traceback
        traceback.print_exc()
