#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020-2025年 全データ完全補完スクリプト（CSV方式・確実版）

【DB書き込み競合ゼロ】
  CSV収集フェーズはDBを一切触らないため、
  advance/before予想生成（ウォッチャー）と同時並行で実行可能。

【実行フロー】
  年ごとに以下を順番に実行（2020 → 2021 → ... → 2025）:
    Step 1 [fetch_csv]   : CSVにレース/結果/出走表を収集（DB書き込みなし）
    Step 2 [import_db]   : CSVをDBにインポート（要: ウォッチャー一時停止を推奨）
    Step 3 [kimarite]    : 決まり手をオンラインから補完
    Step 4 [race_details]: ST時間・実走コースを補完

【安全な並行実行パターン】
  # ウォッチャー起動中でも実行可能（DB書き込みなし）
  python scripts/automation/collect_all_data_complete.py --step fetch_csv

  # ウォッチャー完了後に実行
  python scripts/automation/collect_all_data_complete.py --step import_db
  python scripts/automation/collect_all_data_complete.py --step kimarite
  python scripts/automation/collect_all_data_complete.py --step race_details

【使い方】
  # 初回実行（全ステップ・全年度）
  python scripts/automation/collect_all_data_complete.py

  # 中断後の再開
  python scripts/automation/collect_all_data_complete.py --resume

  # 特定年だけ実行
  python scripts/automation/collect_all_data_complete.py --year 2020

  # 特定ステップだけ実行（全年度）
  python scripts/automation/collect_all_data_complete.py --step fetch_csv

  # 現在の状況確認のみ
  python scripts/automation/collect_all_data_complete.py --check-only

  # 進捗リセット（最初からやり直し）
  python scripts/automation/collect_all_data_complete.py --reset
"""

import sys
import os
import io
import json
import subprocess
import time
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

DB_PATH       = ROOT_DIR / 'data' / 'boatrace.db'
LOG_DIR       = ROOT_DIR / 'logs'
CSV_BASE_DIR  = ROOT_DIR / 'data' / 'csv'
KIMARITE_CSV_DIR = ROOT_DIR / 'data' / 'csv' / 'kimarite'
PROGRESS_FILE = ROOT_DIR / 'data' / 'collection_progress.json'

LOG_DIR.mkdir(exist_ok=True)
CSV_BASE_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"collect_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ─────────────── スクリプトパス ───────────────
FETCH_CSV_SCRIPT   = ROOT_DIR / 'scripts' / 'data_collection' / 'fetch_to_csv_parallel_improved.py'
IMPORT_DB_SCRIPT   = ROOT_DIR / 'scripts' / 'maintenance'     / 'bulk_insert_from_csv.py'
KIMARITE_SCRIPT    = ROOT_DIR / 'scripts' / 'data_collection' / '補完_決まり手データ_改善版.py'
DETAILS_SCRIPT     = ROOT_DIR / 'scripts' / 'data_collection' / '補完_レース詳細データ_改善版v4.py'
IMPORT_CSV_SCRIPT  = ROOT_DIR / 'scripts' / 'data_collection' / 'import_kimarite_csv.py'

# ─────────────── 定数 ───────────────
TARGET_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
STEPS = ['fetch_csv', 'import_db', 'kimarite', 'race_details']

# ─────────────── ログ ───────────────
def log(message, level='INFO'):
    prefix = {'WARN': '[WARN] ', 'ERROR': '[ERR]  ', 'OK': '[OK]   '}.get(level, '       ')
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}]{prefix} {message}"
    print(line, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def log_sep(title=''):
    log('=' * 70)
    if title:
        log(f"  {title}")
        log('=' * 70)

# ─────────────── 進捗管理 ───────────────
def load_progress():
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_progress(progress):
    PROGRESS_FILE.parent.mkdir(exist_ok=True)
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def is_done(progress, year, step):
    return progress.get(str(year), {}).get(step) == 'done'

def mark_done(progress, year, step):
    k = str(year)
    if k not in progress:
        progress[k] = {}
    progress[k][step] = 'done'
    save_progress(progress)

def mark_failed(progress, year, step):
    k = str(year)
    if k not in progress:
        progress[k] = {}
    progress[k][step] = 'failed'
    save_progress(progress)

# ─────────────── データ状況確認 ───────────────
def get_data_status(year):
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        s, e = f'{year}-01-01', f'{year}-12-31'

        c.execute('SELECT COUNT(*) FROM races WHERE race_date >= ? AND race_date <= ?', (s, e))
        races = c.fetchone()[0]

        c.execute('''
            SELECT COUNT(DISTINCT r.id) FROM races r
            INNER JOIN results res ON r.id = res.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
        ''', (s, e))
        results = c.fetchone()[0]

        c.execute('''
            SELECT COUNT(*) FROM results res
            JOIN races r ON res.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND res.kimarite IS NOT NULL AND res.kimarite != ''
        ''', (s, e))
        kimarite = c.fetchone()[0]

        return {'races': races, 'results': results, 'kimarite': kimarite}
    except Exception:
        return {'races': 0, 'results': 0, 'kimarite': 0}
    finally:
        conn.close()

def get_csv_status(year):
    """CSV出力ディレクトリの状況確認"""
    csv_dir = CSV_BASE_DIR / f'year_{year}'
    if not csv_dir.exists():
        return {'exists': False, 'files': 0, 'races_csv_rows': 0}

    files = list(csv_dir.glob('*.csv'))
    races_csv = csv_dir / 'races.csv'
    rows = 0
    if races_csv.exists():
        try:
            with open(races_csv, 'r', encoding='utf-8') as f:
                rows = sum(1 for _ in f) - 1  # ヘッダー除く
        except Exception:
            pass

    return {'exists': True, 'files': len(files), 'races_csv_rows': rows}

def print_status_table():
    log('年度  │  races   │ results  │ kimarite │ CSV行数   │ 充足率')
    log('──────┼──────────┼──────────┼──────────┼───────────┼──────')
    EXPECTED = 56000
    for yr in TARGET_YEARS:
        s = get_data_status(yr)
        csv = get_csv_status(yr)
        pct = s['races'] / EXPECTED * 100
        csv_str = f"{csv['races_csv_rows']:>9,}" if csv['exists'] else '    ---   '
        log(f"{yr}年 │{s['races']:>9,} │{s['results']:>9,} │{s['kimarite']:>9,} │{csv_str} │{pct:5.1f}%")

# ─────────────── スクリプト実行 ───────────────
def run_script(cmd, label, timeout_sec=None, max_retries=3):
    for attempt in range(max_retries):
        if attempt > 0:
            wait = 30 * (2 ** (attempt - 1))
            log(f"  [{label}] {wait}秒後にリトライ ({attempt}/{max_retries-1})...", 'WARN')
            time.sleep(wait)

        log(f"  [{label}] 実行中...")
        t0 = time.time()
        proc = None
        try:
            # cwd=ROOT_DIR を明示（子スクリプトの相対パス参照を保証）
            proc = subprocess.Popen(
                cmd,
                encoding='utf-8',
                errors='replace',
                cwd=str(ROOT_DIR),
            )
            proc.wait(timeout=timeout_sec)
            elapsed = time.time() - t0
            if proc.returncode == 0:
                log(f"  [{label}] 完了 ({elapsed/60:.1f}分)", 'OK')
                return True
            else:
                log(f"  [{label}] 終了コード {proc.returncode} ({elapsed/60:.1f}分)", 'WARN')
        except subprocess.TimeoutExpired:
            # タイムアウト時は子プロセスを確実にkill
            if proc is not None:
                proc.kill()
                proc.wait()
            elapsed = time.time() - t0
            log(f"  [{label}] タイムアウト（{timeout_sec//60}分上限）→ 子プロセスをkillしました ({elapsed/60:.1f}分)", 'WARN')
        except KeyboardInterrupt:
            if proc is not None:
                proc.kill()
                proc.wait()
            raise
        except Exception as ex:
            if proc is not None:
                try:
                    proc.kill()
                    proc.wait()
                except Exception:
                    pass
            log(f"  [{label}] 例外: {ex}", 'ERROR')

    log(f"  [{label}] {max_retries}回試行後も失敗", 'ERROR')
    return False

# ─────────────── Step 実行関数 ───────────────
def step_fetch_csv(year):
    """
    Step 1: CSVにデータ収集（DB書き込みなし・ウォッチャーと並行実行可能）
    出力先: data/csv/year_{year}/
    ※ 再実行時は既存CSVをバックアップして新規作成（重複防止）
    """
    if not FETCH_CSV_SCRIPT.exists():
        log(f"  スクリプトが見つかりません: {FETCH_CSV_SCRIPT}", 'ERROR')
        return False

    csv_dir = CSV_BASE_DIR / f'year_{year}'

    # 既存CSVがある場合はバックアップして新規作成（追記による重複を防止）
    csv_st = get_csv_status(year)
    if csv_st['exists'] and csv_st['races_csv_rows'] > 0:
        backup = CSV_BASE_DIR / f'year_{year}_bak_{int(time.time())}'
        try:
            csv_dir.rename(backup)
            log(f"  [{year}年/fetch_csv] 既存CSV({csv_st['races_csv_rows']:,}行)をバックアップ → {backup.name}")
        except Exception as ex:
            log(f"  [{year}年/fetch_csv] バックアップ失敗: {ex} → そのまま追記", 'WARN')

    csv_dir.mkdir(exist_ok=True)

    current_year = datetime.now().year
    end = f'{year}-12-31' if year < current_year else datetime.now().strftime('%Y-%m-%d')

    cmd = [
        sys.executable, str(FETCH_CSV_SCRIPT),
        '--start',   f'{year}-01-01',
        '--end',     end,
        '--output',  str(csv_dir),
        '--workers', '12',
    ]
    # 最大8時間（大量データでも十分）
    return run_script(cmd, f'{year}年/fetch_csv', timeout_sec=28800, max_retries=3)


def step_import_db(year):
    """
    Step 2: CSVをDBにインポート
    ※ ウォッチャー（advance/before生成）が動いていない時に実行推奨
    """
    if not IMPORT_DB_SCRIPT.exists():
        log(f"  スクリプトが見つかりません: {IMPORT_DB_SCRIPT}", 'ERROR')
        return False

    csv_dir = CSV_BASE_DIR / f'year_{year}'
    if not csv_dir.exists() or not any(csv_dir.glob('*.csv')):
        log(f"  [{year}年/import_db] CSVが見つかりません: {csv_dir}", 'ERROR')
        log(f"  先に --step fetch_csv を実行してください", 'WARN')
        return False

    log(f"  [{year}年/import_db] CSV dir: {csv_dir}")
    cmd = [
        sys.executable, str(IMPORT_DB_SCRIPT),
        '--input', str(csv_dir),
    ]
    return run_script(cmd, f'{year}年/import_db', timeout_sec=7200, max_retries=2)


def step_kimarite(year):
    """Step 3: 決まり手補完（NULLのみ対象・冪等）"""
    if not KIMARITE_SCRIPT.exists():
        log(f"  スクリプトが見つかりません: {KIMARITE_SCRIPT}", 'WARN')
        return False

    cmd = [
        sys.executable, str(KIMARITE_SCRIPT),
        '--start-date', f'{year}-01-01',
        '--end-date',   f'{year}-12-31',
    ]
    return run_script(cmd, f'{year}年/kimarite', timeout_sec=7200, max_retries=3)


def step_race_details(year):
    """Step 4: レース詳細補完（ST時間・実走コース・チルト）"""
    if not DETAILS_SCRIPT.exists():
        log(f"  スクリプトが見つかりません: {DETAILS_SCRIPT}", 'WARN')
        return False

    cmd = [
        sys.executable, str(DETAILS_SCRIPT),
        '--start-date', f'{year}-01-01',
        '--end-date',   f'{year}-12-31',
    ]
    # 2026-02-20修正: 2021年が2h×3リトライで外側overnight_pipeline 4hタイムアウトに
    # 引っかかった問題を解消。4h×2リトライ=最大8h（overnight_pipeline STEP 7c: 8h）
    return run_script(cmd, f'{year}年/race_details', timeout_sec=14400, max_retries=2)


# ─────────────── 保留CSV インポート ───────────────
def import_pending_kimarite_csvs():
    if not KIMARITE_CSV_DIR.exists():
        return
    csvs = list(KIMARITE_CSV_DIR.glob('*.csv'))
    if not csvs or not IMPORT_CSV_SCRIPT.exists():
        return
    log(f"保留中のkimarite CSV: {len(csvs)}件 → インポート")
    run_script(
        [sys.executable, str(IMPORT_CSV_SCRIPT), '--csv', str(KIMARITE_CSV_DIR)],
        'kimarite_csv_import', timeout_sec=600, max_retries=2
    )

# ─────────────── メイン ───────────────
def main():
    parser = argparse.ArgumentParser(
        description='2020-2025年 全データ完全補完（CSV方式）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--resume',     action='store_true', help='前回の続きから再開')
    parser.add_argument('--year',       type=int,            help='特定年のみ（例: 2020）')
    parser.add_argument('--step',       choices=STEPS,       help='特定ステップのみ実行')
    parser.add_argument('--reset',      action='store_true', help='進捗リセット')
    parser.add_argument('--check-only', action='store_true', help='状況確認のみ')
    args = parser.parse_args()

    log_sep('2020-2025年 全データ完全補完スクリプト（CSV方式）')
    log(f'ログファイル: {LOG_FILE}')
    log(f'進捗ファイル: {PROGRESS_FILE}')
    log(f'CSV出力先  : {CSV_BASE_DIR}/year_{{年度}}/')
    log('')
    log('【並行実行可否】')
    log('  fetch_csv : ✅ ウォッチャー動作中でも実行可（DBなし）')
    log('  import_db : ⚠️ ウォッチャー停止後に実行推奨')
    log('  kimarite  : ⚠️ ウォッチャー停止後に実行推奨')
    log('  race_details: ⚠️ ウォッチャー停止後に実行推奨')
    log('')

    # 現状確認
    log('=== 現在のデータ状況 ===')
    print_status_table()
    log('')

    if args.check_only:
        return

    # 進捗リセット
    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        log('進捗リセット完了', 'WARN')

    # 進捗読み込み（--resumeなしは進捗ファイルを無視して最初から実行）
    if args.resume:
        progress = load_progress()
        done_count = sum(1 for yr_d in progress.values() for v in yr_d.values() if v == 'done')
        log(f'前回進捗を引き継ぎます（完了済み: {done_count}ステップ）')
    else:
        progress = {}

    # 保留kimarite CSVインポート（DBへ）※ fetch_csv時はDB書き込みなし前提のためスキップ
    if args.step != 'fetch_csv':
        import_pending_kimarite_csvs()

    # 対象年度・ステップ
    years = [args.year] if args.year else TARGET_YEARS
    steps = [args.step] if args.step else STEPS

    step_funcs = {
        'fetch_csv':   step_fetch_csv,
        'import_db':   step_import_db,
        'kimarite':    step_kimarite,
        'race_details': step_race_details,
    }

    log(f'対象年度: {years}')
    log(f'実行ステップ: {steps}')
    log('')

    # ─── 実行 ───
    master_start = time.time()
    all_results = {}

    for year in years:
        log_sep(f'{year}年 処理開始')
        before = get_data_status(year)
        yr_results = {}

        for step in steps:
            if is_done(progress, year, step):
                log(f'  [{year}年/{step}] 完了済みスキップ ✅')
                yr_results[step] = 'skipped'
                continue

            ok = step_funcs[step](year)

            if ok:
                mark_done(progress, year, step)
                yr_results[step] = 'done'
            else:
                mark_failed(progress, year, step)
                yr_results[step] = 'failed'

        after = get_data_status(year)
        log(f'  {year}年 DB差分: races +{after["races"] - before["races"]:,}  '
            f'kimarite +{after["kimarite"] - before["kimarite"]:,}')
        all_results[year] = yr_results

    # ─── 最終サマリー ───
    master_elapsed = time.time() - master_start
    log('')
    log_sep('全処理完了')
    log(f'総所要時間: {master_elapsed/3600:.2f}時間 ({master_elapsed/60:.1f}分)')
    log('')

    has_failure = any(
        r == 'failed'
        for yr_r in all_results.values()
        for r in yr_r.values()
    )

    log('=== 実行結果サマリー ===')
    for year, yr_r in all_results.items():
        statuses = ' / '.join(f'{s}:{v}' for s, v in yr_r.items())
        log(f'  {year}年: {statuses}')

    log('')
    log('=== 最終データ状況 ===')
    print_status_table()

    if has_failure:
        log('')
        log('一部ステップが失敗しました。以下で再実行してください:', 'WARN')
        log('  python scripts/automation/collect_all_data_complete.py --resume', 'WARN')
    else:
        log('')
        log('全ステップ正常完了！', 'OK')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log('')
        log('Ctrl+C で中断。以下で続きから再開できます:', 'WARN')
        log('  python scripts/automation/collect_all_data_complete.py --resume', 'WARN')
    except Exception as ex:
        log(f'致命的エラー: {ex}', 'ERROR')
        import traceback
        traceback.print_exc()
        raise
