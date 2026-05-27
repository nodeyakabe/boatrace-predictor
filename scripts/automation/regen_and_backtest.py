# -*- coding: utf-8 -*-
"""
regen_and_backtest.py
2020-2022をバグ修正後コードで再生成し、全6年度をDBインポート→バックテストまで全自動実行

【背景】
  - escape_rate temporal fix バグ: player_escape_stats に歴史スナップショットがないため
    target_date フィルターが全年度で escape_rate を無効化していた
  - race_predictor.py は修正済み（target_date=None）
  - 2020・2021は バグ入り予測がDBに入済み → 再インポートで上書き
  - 2022・2023・2024・2025は run_before_csv_all_years.py が生成中

【手順】
  Step A: run_before_csv_all_years.py の完了を待機
          (2023/2024/2025の .completed マーカーが揃うまで)
  Step B: 2020-2022 の CSV ディレクトリと .completed マーカーを削除
  Step C: 2020, 2021, 2022 を修正後コードで再生成 (csv-only)
  Step D: 23:00-02:30 安全時間帯に全6年度を DB インポート
  Step E: 信頼度分布 A率チェック
  Step F: 標準バックテスト → data/baselines/ に保存
  Step G: 完了レポート生成

再起動耐性: data/progress_regen.json でステップ管理
"""

import sys
import io
import os
import json
import shutil
import subprocess
import time
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
CSV_BASE     = ROOT_DIR / 'data' / 'predictions_csv' / 'before'
PROGRESS_FILE = ROOT_DIR / 'data' / 'progress_regen.json'
LOG_FILE     = ROOT_DIR / 'logs' / 'regen_and_backtest.log'
BASELINES_DIR = ROOT_DIR / 'data' / 'baselines'

SAFE_START_H = 23   # 23:00 以降
SAFE_END_H   = 2    # 02:30 まで
SAFE_END_M   = 30

YEARS_ALL    = [2020, 2021, 2022, 2023, 2024, 2025]
YEARS_REGEN  = [2020, 2021, 2022]   # 再生成が必要な年度
YEARS_WAIT   = [2023, 2024, 2025]   # run_before_csv_all_years.py が生成中の年度


# =============================================================================
# ユーティリティ
# =============================================================================

def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_progress(progress: dict):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8'
    )


def is_done(progress: dict, step: str) -> bool:
    return progress.get(step, {}).get('done', False)


def mark_done(progress: dict, step: str, note: str = ''):
    progress[step] = {
        'done': True,
        'completed_at': datetime.now().isoformat(),
        'note': note,
    }
    save_progress(progress)


def run_python(args: list, timeout=None) -> int:
    cmd = [sys.executable] + [str(a) for a in args]
    log(f'  実行: {" ".join(cmd)}')
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT_DIR,
            text=True, encoding='utf-8', errors='replace',
            timeout=timeout,
        )
        return proc.returncode
    except subprocess.TimeoutExpired:
        log('  タイムアウト')
        return -1
    except Exception as e:
        log(f'  エラー: {e}')
        return -1


def marker_path(year: int) -> Path:
    return CSV_BASE / str(year) / '.completed'


def is_safe_import_time() -> bool:
    h, m = datetime.now().hour, datetime.now().minute
    total = h * 60 + m
    return total >= SAFE_START_H * 60 or total <= SAFE_END_H * 60 + SAFE_END_M


def wait_safe_import():
    if is_safe_import_time():
        return
    now = datetime.now()
    wait_min = (SAFE_START_H - now.hour) * 60 - now.minute
    if wait_min < 0:
        wait_min += 24 * 60
    log(f'⏳ 安全時間帯待機中... 次の23:00まで約 {wait_min} 分')
    while not is_safe_import_time():
        time.sleep(300)
        remaining = (SAFE_START_H * 60 - datetime.now().hour * 60 - datetime.now().minute) % (24 * 60)
        log(f'  待機中... 残り約 {remaining} 分')


def is_generation_running() -> bool:
    """run_before_csv_all_years.py / generate_before_fast.py が実行中か"""
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='python.exe'", 'get', 'commandline'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15
        )
        return ('run_before_csv_all_years' in result.stdout or
                'generate_before_fast' in result.stdout)
    except Exception:
        return True  # 確認できない場合は安全側（生成中とみなす）


# =============================================================================
# Step A: run_before_csv_all_years.py の完了待機
# =============================================================================

def step_a_wait(progress: dict):
    if is_done(progress, 'step_a'):
        log('[Step A] 完了済み（スキップ）')
        return

    log('[Step A] 2023/2024/2025 CSV生成完了を待機中...')
    log('  (run_before_csv_all_years.py が 2023-2025 を生成し終えるまで待ちます)')

    while True:
        # .completed マーカーが全年度揃ったか確認
        waiting = [y for y in YEARS_WAIT if not marker_path(y).exists()]
        running = is_generation_running()

        if not waiting and not running:
            log('  ✅ 2023/2024/2025 の生成完了を確認')
            break

        status_parts = []
        if waiting:
            status_parts.append(f'未完了: {waiting}')
        if running:
            status_parts.append('生成プロセス実行中')
        log(f'  待機中... ({" / ".join(status_parts)}) → 5分後に再チェック')
        time.sleep(300)

    mark_done(progress, 'step_a', f'years_wait={YEARS_WAIT} completed')


# =============================================================================
# Step A5: ETシグナル分析（Step A完了直後・generate_before_fast.py 起動前の隙間）
# =============================================================================

def step_a5_et_analysis(progress: dict):
    if is_done(progress, 'step_a5'):
        log('[Step A5] ET分析 完了済み（スキップ）')
        return

    et_script = ROOT_DIR / 'temp' / 'independent_signal_et.py'
    et_output  = ROOT_DIR / 'temp' / 'et_output.txt'

    if not et_script.exists():
        log(f'[Step A5] ET スクリプト不在 → スキップ: {et_script}')
        mark_done(progress, 'step_a5', 'script not found')
        return

    log('[Step A5] ETシグナル分析実行中... (generate_before_fast.py 起動前の隙間)')
    try:
        with open(et_output, 'w', encoding='utf-8', buffering=1) as out:  # line buffering
            proc = subprocess.run(
                [sys.executable, '-u', str(et_script)],  # -u: unbuffered stdout
                stdout=out, stderr=subprocess.STDOUT,
                cwd=ROOT_DIR,
                timeout=7200,  # 2h（37M行trifecta_odds対応）
            )
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        log('  ⚠️ ET分析タイムアウト（継続）')
        rc = -1
    except Exception as e:
        log(f'  ⚠️ ET分析エラー: {e}（継続）')
        rc = -1

    log(f'[Step A5] ET分析完了 (rc={rc}) → {et_output}')
    try:
        with open(et_output, encoding='utf-8', errors='replace') as f:
            for i, line in enumerate(f):
                if i >= 80: break
                log(f'  {line.rstrip()}')
    except Exception:
        pass

    mark_done(progress, 'step_a5', f'rc={rc}, output={et_output.name}')


# =============================================================================
# Step B: 2020-2022 の CSV と .completed マーカーを削除
# =============================================================================

def step_b_delete(progress: dict):
    if is_done(progress, 'step_b'):
        log('[Step B] 完了済み（スキップ）')
        return

    log('[Step B] バグ入り 2020-2022 CSV を削除...')
    for year in YEARS_REGEN:
        csv_dir = CSV_BASE / str(year)
        if csv_dir.exists():
            shutil.rmtree(csv_dir)
            log(f'  削除: {csv_dir}')
        else:
            log(f'  存在しない（スキップ）: {csv_dir}')

    mark_done(progress, 'step_b', f'deleted years={YEARS_REGEN}')


# =============================================================================
# Step C: 2020-2022 を修正後コードで再生成
# =============================================================================

def step_c_regen(progress: dict):
    if is_done(progress, 'step_c'):
        log('[Step C] 完了済み（スキップ）')
        return

    log(f'[Step C] 2020-2022 を修正後コードで再生成...')
    log('  (race_predictor.py は target_date=None 版。escape_rate が全年度で機能する)')
    log('  (再起動耐性: 年度別マーカーで完了済み年度をスキップ)')

    script = ROOT_DIR / 'scripts' / 'prediction' / 'generate_before_fast.py'
    errors = []
    for year in YEARS_REGEN:
        year_key = f'step_c_{year}'
        if is_done(progress, year_key):
            log(f'  === {year}年 完了済み（スキップ） ===')
            continue
        log(f'  === {year}年 CSV生成 開始 ===')
        rc = run_python([script, '--year', str(year), '--force', '--csv-only'], timeout=None)
        if rc != 0:
            log(f'  ⚠️ {year}年 生成失敗 (rc={rc})')
            errors.append(year)
        else:
            log(f'  === {year}年 CSV生成 完了 ===')
            mark_done(progress, year_key, f'regen year={year}')

    if errors:
        raise RuntimeError(f'[Step C] 再生成失敗: {errors}')

    mark_done(progress, 'step_c', f'regen completed for {YEARS_REGEN}')


# =============================================================================
# Step C5: ET シグナル分析（Step C 完了後・generate_before_fast.py 停止後の隙間）
# Step A5 がタイムアウトした場合のリトライ用。既に成功済みならスキップ。
# =============================================================================

def step_c5_et_retry(progress: dict):
    if is_done(progress, 'step_c5'):
        log('[Step C5] ET分析リトライ 完了済み（スキップ）')
        return

    # Step A5 が正常完了（rc=0）していればスキップ
    a5 = progress.get('step_a5', {})
    if a5.get('done') and 'rc=0' in a5.get('note', ''):
        log('[Step C5] Step A5 が正常完了済み → スキップ')
        mark_done(progress, 'step_c5', 'skipped: step_a5 already succeeded')
        return

    et_script = ROOT_DIR / 'temp' / 'independent_signal_et.py'
    et_output  = ROOT_DIR / 'temp' / 'et_output.txt'

    if not et_script.exists():
        log(f'[Step C5] ET スクリプト不在 → スキップ: {et_script}')
        mark_done(progress, 'step_c5', 'script not found')
        return

    log('[Step C5] ETシグナル分析リトライ (generate_before_fast.py 停止後)')
    try:
        with open(et_output, 'w', encoding='utf-8', buffering=1) as out:
            proc = subprocess.run(
                [sys.executable, '-u', str(et_script)],
                stdout=out, stderr=subprocess.STDOUT,
                cwd=ROOT_DIR,
                timeout=7200,  # 2h（37M行trifecta_odds対応）
            )
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        log('  ⚠️ ET分析タイムアウト（継続）')
        rc = -1
    except Exception as e:
        log(f'  ⚠️ ET分析エラー: {e}（継続）')
        rc = -1

    log(f'[Step C5] ET分析完了 (rc={rc}) → {et_output}')
    try:
        with open(et_output, encoding='utf-8', errors='replace') as f:
            for i, line in enumerate(f):
                if i >= 80:
                    break
                log(f'  {line.rstrip()}')
    except Exception:
        pass

    mark_done(progress, 'step_c5', f'rc={rc}, output={et_output.name}')


# =============================================================================
# Step D: 全6年度を DB インポート（安全時間帯）
# =============================================================================

def step_d_import(progress: dict):
    if is_done(progress, 'step_d'):
        log('[Step D] 完了済み（スキップ）')
        return

    log('[Step D] DBインポート準備...')
    wait_safe_import()
    log('[Step D] 安全時間帯。全6年度をDBインポート開始...')

    script = ROOT_DIR / 'scripts' / 'prediction' / 'import_predictions_csv.py'
    errors = []
    for year in YEARS_ALL:
        csv_dir = CSV_BASE / str(year)
        if not csv_dir.exists():
            log(f'  ⚠️ {year}: CSVディレクトリが存在しません → スキップ')
            continue
        log(f'  {year}年 インポート中...')
        rc = run_python([script, '--dir', str(csv_dir)], timeout=14400)
        if rc != 0:
            log(f'  ⚠️ {year}年 インポート失敗 (rc={rc})')
            errors.append(year)
        else:
            log(f'  ✅ {year}年 インポート完了')

    if errors:
        raise RuntimeError(f'[Step D] インポート失敗: {errors}')

    log('[Step D] ✅ 全6年度 DBインポート完了')
    mark_done(progress, 'step_d', f'imported={YEARS_ALL}')


# =============================================================================
# Step E: A率品質チェック
# =============================================================================

def step_e_quality(progress: dict):
    if is_done(progress, 'step_e'):
        log('[Step E] 完了済み（スキップ）')
        return

    log('[Step E] 信頼度分布 A率品質チェック...')
    script = ROOT_DIR / 'scripts' / 'analysis' / 'check_confidence_distribution.py'
    if not script.exists():
        log(f'  スクリプトが存在しません: {script} → スキップ')
        mark_done(progress, 'step_e', 'script not found')
        return

    rc = run_python([script], timeout=300)
    if rc != 0:
        log(f'  ⚠️ 品質チェック rc={rc}（継続）')
    mark_done(progress, 'step_e', f'rc={rc}')


# =============================================================================
# Step F: 標準バックテスト
# =============================================================================

def step_f_backtest(progress: dict):
    if is_done(progress, 'step_f'):
        log('[Step F] 完了済み（スキップ）')
        return

    log('[Step F] 標準バックテスト (standard_backtest_unique.py --full)...')
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    baseline_path = BASELINES_DIR / f'regen_result_{ts}.json'

    script = ROOT_DIR / 'scripts' / 'backtest' / 'standard_backtest_unique.py'
    rc = run_python([script, '--full', '--save-json', str(baseline_path)], timeout=1800)
    if rc != 0:
        raise RuntimeError(f'[Step F] バックテスト失敗 (rc={rc})')

    log(f'[Step F] ✅ バックテスト完了 → {baseline_path}')
    mark_done(progress, 'step_f', f'baseline={baseline_path.name}')


# =============================================================================
# Step F5: prediction_features 更新（fast_backtest との整合性確保）
# =============================================================================

def step_f5_import_features(progress: dict):
    if is_done(progress, 'step_f5'):
        log('[Step F5] prediction_features 更新 完了済み（スキップ）')
        return

    script = ROOT_DIR / 'scripts' / 'prediction' / 'import_features_from_predictions.py'
    if not script.exists():
        log(f'[Step F5] スクリプト不在 → スキップ: {script}')
        mark_done(progress, 'step_f5', 'script not found')
        return

    log('[Step F5] prediction_features テーブル更新中 (--full --force)...')
    rc = run_python([script, '--full', '--force'], timeout=3600)
    if rc != 0:
        log(f'  ⚠️ 更新失敗 rc={rc}（継続）')
    else:
        log('[Step F5] ✅ prediction_features 更新完了')
    mark_done(progress, 'step_f5', f'rc={rc}')


# =============================================================================
# Step G: 完了レポート
# =============================================================================

def step_g_report(progress: dict):
    if is_done(progress, 'step_g'):
        log('[Step G] 完了済み（スキップ）')
        return

    log('[Step G] 完了レポート生成...')
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = LOG_FILE.parent / f'regen_report_{ts}.txt'

    lines = [
        '=' * 60,
        '2020-2022 再生成 + 全6年度バックテスト 完了レポート',
        f'生成日時: {datetime.now().isoformat()}',
        '=' * 60,
        '',
        '【修正内容】',
        '  - バグ: temporal fix が player_escape_stats の歴史スナップショット',
        '         不在を考慮せず、2020-2025 の escape_rate を全て無効化',
        '  - 修正: race_predictor.py から target_date=race_date を削除',
        '         → target_date=None (最新スナップショット=2026-04-24 を常時使用)',
        '',
        '【ステップ完了状況】',
    ]
    step_names = {
        'step_a':  '2023-2025 生成完了待機',
        'step_a5': 'ETシグナル分析',
        'step_b':  'バグ入り 2020-2022 CSV 削除',
        'step_c_2020': '2020年 再生成',
        'step_c_2021': '2021年 再生成',
        'step_c_2022': '2022年 再生成',
        'step_c':  '2020-2022 修正後コードで再生成（全体）',
        'step_c5': 'ETシグナル分析リトライ（Step C完了後）',
        'step_d':  '全6年度 DBインポート',
        'step_e':  'A率品質チェック',
        'step_f':  '標準バックテスト',
        'step_f5': 'prediction_features 更新',
        'step_g':  '完了レポート',
    }
    for key, name in step_names.items():
        d = progress.get(key, {})
        status = '✅' if d.get('done') else '❌'
        ts_str = d.get('completed_at', '-')
        note = d.get('note', '')
        lines.append(f'  {status} [{key}] {name}  完了: {ts_str}  ({note})')

    lines += [
        '',
        '【次のアクション（要人手確認）】',
        '  1. バックテスト結果と前回ベースラインを比較',
        '     前回: v2.61.0 / 4,360件 / ROI 258.0% / +722,740円 / 6/6年黒字',
        '  2. 判定基準（3軸すべて満たすこと）:',
        '     ✅ 収支 >= +700,000円  (前回: +722,740円)',
        '     ✅ 6/6年 黒字          (前回: 6/6年)',
        '     ✅ ROI >= 250%         (前回: 258.0%  ±3pt 以内は同等)',
        '     ✅ 件数変動 ±15% 以内  (前回: 4,360件)',
        '     → 全満たす → v2.62.0 採用確定',
        '     → いずれか不成立 → 効果分離テスト（escape_rate ON/OFF比較）',
        '     → 効果分離後も悪化 → escape_rate 連続化ロールバック',
        '     ※ 必ず C_P132 / D_P143 / A_P142 の件数推移も確認すること',
        '  3. A率が正常範囲内か確認',
        '     before: A%/予測 = 2-9%（>10% → 異常）',
        '  4. MEMORY.md / HANDOVER.md のベースライン更新',
        '',
        '=' * 60,
    ]

    report_path.write_text('\n'.join(lines), encoding='utf-8')
    print('\n' + '\n'.join(lines))
    mark_done(progress, 'step_g', f'report={report_path.name}')


# =============================================================================
# メイン
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--from-step', type=str, default=None,
                        help='このステップからリセットして再実行 (例: step_c)')
    args = parser.parse_args()

    progress = load_progress()

    if args.status:
        log('=== regen_and_backtest 進捗 ===')
        for key in ['step_a','step_a5','step_b','step_c_2020','step_c_2021','step_c_2022','step_c','step_c5','step_d','step_e','step_f','step_f5','step_g']:
            d = progress.get(key, {})
            status = '✅ 完了' if d.get('done') else '⏳ 未完了'
            log(f'  {key}: {status}  {d.get("completed_at","-")}  {d.get("note","")}')
        return

    if args.from_step:
        keys = ['step_a','step_b','step_c','step_d','step_e','step_f','step_g']
        reset_from = args.from_step
        resetting = False
        for k in keys:
            if k == reset_from:
                resetting = True
            if resetting and k in progress:
                del progress[k]
        save_progress(progress)
        log(f'{reset_from} 以降をリセットして再実行')

    log('=' * 60)
    log('regen_and_backtest.py 開始')
    log(f'  進捗ファイル: {PROGRESS_FILE}')
    log(f'  ログ: {LOG_FILE}')
    log('=' * 60)

    try:
        step_a_wait(progress)
        step_a5_et_analysis(progress)   # generate_before_fast.py 起動前の隙間でET分析
        step_b_delete(progress)
        step_c_regen(progress)
        step_c5_et_retry(progress)      # Step C完了後にETリトライ（Step A5失敗分の補完）
        step_d_import(progress)
        step_e_quality(progress)
        step_f_backtest(progress)
        step_f5_import_features(progress)  # fast_backtest 整合性確保
        step_g_report(progress)

        log('=' * 60)
        log('✅ 全ステップ完了！ バックテスト結果を確認してください。')
        log('=' * 60)

    except RuntimeError as e:
        log(f'\n❌ 中断: {e}')
        log(f'  再実行: python scripts/automation/regen_and_backtest.py')
        sys.exit(1)


if __name__ == '__main__':
    main()
