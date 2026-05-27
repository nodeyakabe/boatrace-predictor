# -*- coding: utf-8 -*-
"""
週末放置パイプライン — escape_rate連続スコア + boaters傾向 全年度before再生成

ステップ:
  Step 1: ボーターズ収集プロセス完了待機
  Step 2: boaters傾向分析 (analyze_boaters_signal_v2.py)
  Step 3: 全年度 before予測 CSV生成 (run_before_csv_all_years.py) ~100h
  Step 4: DBインポート（安全時間帯: 23:00-02:30のみ）
  Step 5: 信頼度分布品質チェック
  Step 6: 標準バックテスト → data/baselines/ に保存
  Step 7: 完了レポート生成

再起動耐性: data/progress_weekend.json にステップ完了状態を保存
安全時間帯: 03:00/06:00/08:30（daily_scheduler書き込み）を避け 23:00-02:30 に実行

使い方:
    python scripts/automation/weekend_pipeline.py

    # 状態確認
    python scripts/automation/weekend_pipeline.py --status

    # 特定ステップから強制再開
    python scripts/automation/weekend_pipeline.py --from-step 3

    # ドライラン（実際には実行しない）
    python scripts/automation/weekend_pipeline.py --dry-run
"""

import sys
import io
import os
import json
import subprocess
import argparse
import time
from pathlib import Path
from datetime import datetime, date

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
PROGRESS_FILE = ROOT_DIR / 'data' / 'progress_weekend.json'
LOG_FILE = ROOT_DIR / 'logs' / 'weekend_pipeline.log'
BASELINES_DIR = ROOT_DIR / 'data' / 'baselines'

# daily_scheduler の書き込みタイム（これを避けてDBインポートする）
# 03:00 / 06:00 / 08:30 (Mon/Thu は 04:00 も追加)
# 安全時間帯: 23:00–02:30
SAFE_IMPORT_START_H = 23
SAFE_IMPORT_END_H   = 2   # 翌日 02:30 まで
SAFE_IMPORT_END_M   = 30


# =============================================================================
# ユーティリティ
# =============================================================================

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
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
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')


def is_step_done(progress: dict, step: int) -> bool:
    return progress.get(f"step{step}", {}).get("done", False)


def mark_step_done(progress: dict, step: int, note: str = ""):
    progress[f"step{step}"] = {
        "done": True,
        "completed_at": datetime.now().isoformat(),
        "note": note,
    }
    save_progress(progress)


def run_cmd(cmd: list, cwd=None, timeout=None, dry_run=False) -> int:
    """コマンドを実行してリターンコードを返す"""
    cmd_str = ' '.join(str(c) for c in cmd)
    log(f"  実行: {cmd_str}")
    if dry_run:
        log("  [DRY-RUN] スキップ")
        return 0
    try:
        proc = subprocess.run(
            cmd, cwd=cwd or ROOT_DIR,
            text=True, encoding='utf-8', errors='replace',
            timeout=timeout,
        )
        return proc.returncode
    except subprocess.TimeoutExpired:
        log("  ⚠️ タイムアウト")
        return -1
    except Exception as e:
        log(f"  ⚠️ 実行エラー: {e}")
        return -1


def run_python(script_args: list, timeout=None, dry_run=False) -> int:
    cmd = [sys.executable] + [str(a) for a in script_args]
    return run_cmd(cmd, timeout=timeout, dry_run=dry_run)


# =============================================================================
# 安全時間帯チェック
# =============================================================================

def is_safe_import_time() -> bool:
    """DBインポート安全時間帯かを確認: 23:00–02:30"""
    now = datetime.now()
    h, m = now.hour, now.minute
    total_min = h * 60 + m
    # 23:00 = 1380, 02:30 = 150 (翌日)
    return total_min >= SAFE_IMPORT_START_H * 60 or total_min <= SAFE_IMPORT_END_H * 60 + SAFE_IMPORT_END_M


def wait_for_safe_import_time(dry_run=False):
    """23:00-02:30 の安全時間帯まで待機"""
    if dry_run or is_safe_import_time():
        return
    now = datetime.now()
    h, m = now.hour, now.minute
    # 次の23:00まで待機
    wait_h = SAFE_IMPORT_START_H - h
    if wait_h < 0:
        wait_h += 24
    wait_min = wait_h * 60 - m
    log(f"⏳ DBインポート安全時間帯待機中... 次の23:00まで約 {wait_min} 分")
    log("   (daily_scheduler: 03:00/06:00/08:30 書き込み時間を回避)")
    # 5分ごとに状態表示
    while not is_safe_import_time():
        time.sleep(300)
        remaining = SAFE_IMPORT_START_H * 60 - datetime.now().hour * 60 - datetime.now().minute
        if remaining < 0:
            remaining += 24 * 60
        log(f"  待機中... 残り約 {remaining} 分")


# =============================================================================
# Step 1: ボーターズ収集プロセス完了待機
# =============================================================================

def is_boaters_collecting() -> bool:
    """collect_boaters_race_data.py が実行中かチェック"""
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='python.exe'", 'get', 'commandline'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15
        )
        return 'collect_boaters_race_data' in result.stdout
    except Exception:
        return False


def step1_wait_boaters(progress: dict, dry_run: bool):
    if is_step_done(progress, 1):
        log("[Step 1] ✅ 完了済み（スキップ）")
        return

    log("[Step 1] ボーターズ収集プロセス完了待機...")
    if dry_run:
        log("  [DRY-RUN] スキップ")
        mark_step_done(progress, 1, "dry-run")
        return

    check_interval = 120  # 2分おきにチェック
    while is_boaters_collecting():
        log("  collect_boaters_race_data.py 実行中... 2分後に再チェック")
        time.sleep(check_interval)

    log("  ✅ ボーターズ収集プロセス完了（または未実行）")
    mark_step_done(progress, 1, "boaters process finished")


# =============================================================================
# Step 2: boaters傾向分析
# =============================================================================

def step2_analyze_boaters(progress: dict, dry_run: bool):
    if is_step_done(progress, 2):
        log("[Step 2] ✅ 完了済み（スキップ）")
        return

    log("[Step 2] boaters傾向分析 (analyze_boaters_signal_v2.py)...")
    script = ROOT_DIR / 'temp' / 'analyze_boaters_signal_v2.py'
    if not script.exists():
        log(f"  ⚠️ スクリプトが存在しません: {script}")
        log("  → Step 2 をスキップして継続")
        mark_step_done(progress, 2, "script not found, skipped")
        return

    rc = run_python([script], timeout=3600, dry_run=dry_run)
    if rc != 0:
        log(f"  ⚠️ 分析スクリプト終了コード: {rc}（継続）")
    mark_step_done(progress, 2, f"rc={rc}")


# =============================================================================
# Step 3: 全年度 before予測 CSV生成（~100時間、4日間）
# =============================================================================

def step3_generate_csvs(progress: dict, dry_run: bool):
    if is_step_done(progress, 3):
        log("[Step 3] ✅ 完了済み（スキップ）")
        return

    log("[Step 3] 全年度 before予測 CSV生成 (2020-2025, ~100h)...")
    script = ROOT_DIR / 'scripts' / 'prediction' / 'run_before_csv_all_years.py'

    rc = run_python([script], timeout=None, dry_run=dry_run)  # タイムアウトなし（4日間）
    if rc != 0:
        raise RuntimeError(f"[Step 3] CSV生成失敗 (rc={rc})")

    log("[Step 3] ✅ 全年度 CSV生成完了")
    mark_step_done(progress, 3, "all years CSV generated")


# =============================================================================
# Step 4: DBインポート（安全時間帯のみ）
# =============================================================================

def step4_import_db(progress: dict, dry_run: bool):
    if is_step_done(progress, 4):
        log("[Step 4] ✅ 完了済み（スキップ）")
        return

    log("[Step 4] DBインポート準備...")
    wait_for_safe_import_time(dry_run=dry_run)
    log("[Step 4] 安全時間帯に入りました。DBインポート開始...")

    years = [2020, 2021, 2022, 2023, 2024, 2025]
    import_script = ROOT_DIR / 'scripts' / 'prediction' / 'import_predictions_csv.py'

    errors = []
    for year in years:
        csv_dir = ROOT_DIR / 'data' / 'predictions_csv' / 'before' / str(year)
        if not csv_dir.exists():
            log(f"  ⚠️ {year}: CSVディレクトリが存在しません → スキップ")
            continue

        log(f"  {year} インポート中...")
        rc = run_python(
            [import_script, '--dir', str(csv_dir)],
            timeout=7200,
            dry_run=dry_run,
        )
        if rc != 0:
            log(f"  ⚠️ {year} インポート失敗 (rc={rc})")
            errors.append(year)
        else:
            log(f"  ✅ {year} インポート完了")

    if errors:
        raise RuntimeError(f"[Step 4] インポート失敗年度: {errors}")

    log("[Step 4] ✅ 全年度 DBインポート完了")
    mark_step_done(progress, 4, f"years={years}")


# =============================================================================
# Step 5: 信頼度分布品質チェック
# =============================================================================

def step5_quality_check(progress: dict, dry_run: bool):
    if is_step_done(progress, 5):
        log("[Step 5] ✅ 完了済み（スキップ）")
        return

    log("[Step 5] 信頼度分布品質チェック...")
    script = ROOT_DIR / 'scripts' / 'analysis' / 'check_confidence_distribution.py'
    if not script.exists():
        log(f"  ⚠️ スクリプトが存在しません: {script} → スキップ")
        mark_step_done(progress, 5, "script not found, skipped")
        return

    rc = run_python([script], timeout=300, dry_run=dry_run)
    if rc != 0:
        log(f"  ⚠️ 品質チェック終了コード: {rc}（継続）")
    mark_step_done(progress, 5, f"rc={rc}")


# =============================================================================
# Step 6: 標準バックテスト
# =============================================================================

def step6_backtest(progress: dict, dry_run: bool):
    if is_step_done(progress, 6):
        log("[Step 6] ✅ 完了済み（スキップ）")
        return

    log("[Step 6] 標準バックテスト (standard_backtest_unique.py --full)...")
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    baseline_path = BASELINES_DIR / f'weekend_pipeline_{ts}.json'
    script = ROOT_DIR / 'scripts' / 'backtest' / 'standard_backtest_unique.py'

    rc = run_python(
        [script, '--full', '--save-json', str(baseline_path)],
        timeout=1800,
        dry_run=dry_run,
    )
    if rc != 0:
        raise RuntimeError(f"[Step 6] バックテスト失敗 (rc={rc})")

    log(f"[Step 6] ✅ バックテスト完了 → {baseline_path}")
    mark_step_done(progress, 6, f"baseline={baseline_path.name}")


# =============================================================================
# Step 7: 完了レポート生成
# =============================================================================

def step7_report(progress: dict, dry_run: bool):
    if is_step_done(progress, 7):
        log("[Step 7] ✅ 完了済み（スキップ）")
        return

    log("[Step 7] 完了レポート生成...")
    report_path = ROOT_DIR / 'logs' / f'weekend_pipeline_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'

    lines = [
        "=" * 60,
        "週末放置パイプライン 完了レポート",
        f"生成日時: {datetime.now().isoformat()}",
        "=" * 60,
        "",
        "【実装内容】",
        "  1. escape_rate 連続スコアリング (kimarite_scorer.py)",
        "     - player_escape_stats から逃げ率を線形マッピング [0.30, 0.80] → [0, max]",
        "     - 時系列リーク防止: target_date 以前のスナップショットのみ参照",
        "  2. boaters傾向分析 (analyze_boaters_signal_v2.py)",
        "  3. 全年度 before予測 再生成 (2020-2025)",
        "",
        "【ステップ完了状況】",
    ]
    for i in range(1, 8):
        step_data = progress.get(f"step{i}", {})
        status = "✅" if step_data.get("done") else "❌"
        ts = step_data.get("completed_at", "-")
        note = step_data.get("note", "")
        lines.append(f"  Step {i}: {status}  完了: {ts}  ({note})")

    lines += [
        "",
        "【次のアクション（要人手確認）】",
        "  1. バックテスト結果と前回ベースラインを比較",
        "     前回: v2.61.0 / 4,360件 / ROI 258.0% / +722,740円 / 6/6年黒字",
        "  2. 信頼度分布（A率）が正常範囲内か確認",
        "     advance: A%/予測 = 2〜5%（>10% → 異常）",
        "     before:  A%/予測 = 2〜9%（>10% → 異常）",
        "  3. 時系列リーク検証（2020年が2021年以降の逃げ率を使っていないか確認）",
        "  4. 残タスク一覧.md のベースライン更新",
        "  5. HANDOVER.md 更新",
        "",
        "=" * 60,
    ]

    report_text = '\n'.join(lines)
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding='utf-8')
        log(f"  レポート保存: {report_path}")

    print('\n' + report_text)
    mark_step_done(progress, 7, f"report={report_path.name}")


# =============================================================================
# メイン
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='週末放置パイプライン')
    parser.add_argument('--from-step', type=int, default=None, help='このステップ以降を強制再実行')
    parser.add_argument('--status', action='store_true', help='進捗状況を表示して終了')
    parser.add_argument('--dry-run', action='store_true', help='実際のコマンドを実行しない')
    args = parser.parse_args()

    progress = load_progress()

    if args.status:
        log("=== 週末パイプライン 進捗状況 ===")
        step_names = {
            1: "ボーターズ収集完了待機",
            2: "boaters傾向分析",
            3: "全年度 CSV生成 (~100h)",
            4: "DBインポート（安全時間帯）",
            5: "信頼度分布品質チェック",
            6: "標準バックテスト",
            7: "完了レポート",
        }
        for i in range(1, 8):
            step_data = progress.get(f"step{i}", {})
            status = "✅ 完了" if step_data.get("done") else "⏳ 未完了"
            ts = step_data.get("completed_at", "-")
            note = step_data.get("note", "")
            log(f"  Step {i} [{step_names[i]}]: {status}  {ts}  {note}")
        return

    # --from-step 指定時は指定ステップ以降のマークをリセット
    if args.from_step:
        for i in range(args.from_step, 8):
            if f"step{i}" in progress:
                del progress[f"step{i}"]
        save_progress(progress)
        log(f"Step {args.from_step} 以降をリセットして再実行します")

    if args.dry_run:
        log("=== DRY-RUN モード（実際には実行しない）===")

    log("=" * 60)
    log("週末放置パイプライン 開始")
    log(f"  進捗ファイル: {PROGRESS_FILE}")
    log(f"  ログ: {LOG_FILE}")
    log("=" * 60)

    try:
        step1_wait_boaters(progress, args.dry_run)
        step2_analyze_boaters(progress, args.dry_run)
        step3_generate_csvs(progress, args.dry_run)
        step4_import_db(progress, args.dry_run)
        step5_quality_check(progress, args.dry_run)
        step6_backtest(progress, args.dry_run)
        step7_report(progress, args.dry_run)

        log("=" * 60)
        log("✅ 週末放置パイプライン 全ステップ完了！")
        log("   人手確認が必要な事項はレポートを参照してください")
        log("=" * 60)

    except RuntimeError as e:
        log(f"\n❌ パイプライン中断: {e}")
        log("  進捗は保存済みです。修正後に再実行すると途中から再開します")
        log(f"  再実行: python scripts/automation/weekend_pipeline.py")
        sys.exit(1)


if __name__ == '__main__':
    main()
