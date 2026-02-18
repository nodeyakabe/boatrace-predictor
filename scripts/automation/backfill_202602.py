#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
スケジューラー停止期間（2026/02/02〜02/13）のデータ欠損補完スクリプト

実行ステップ:
  Step 1 : レース基本データ + 結果補完
  Step 2a: 直前情報をCSV収集
  Step 2b: CSVをDBに投入
  Step 3 : 直前予想を日付ループで生成（2/02〜2/13 の12日分）

使用方法:
    python scripts/automation/backfill_202602.py
    python scripts/automation/backfill_202602.py --dry-run   # 実行計画の確認のみ
"""

import sys
import io
import os
import subprocess
import time
from pathlib import Path
from datetime import datetime, timedelta

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.automation.notify import send_discord_notification, send_error_notification

# ============================================================
# 補完対象期間
# ============================================================
BACKFILL_START = "2026-02-02"
BACKFILL_END = "2026-02-13"
CSV_OUTPUT_DIR = str(PROJECT_ROOT / "data" / "csv" / "beforeinfo_補完_2026_02")


# ============================================================
# ユーティリティ
# ============================================================

def get_date_range(start_date: str, end_date: str) -> list:
    """YYYY-MM-DD 形式の日付リストを返す"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def format_elapsed(seconds: float) -> str:
    """秒数を「X分Y秒」形式に変換"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


# ============================================================
# コマンド実行
# ============================================================

def run_command(cmd: list, step_name: str) -> dict:
    """
    subprocess でコマンドをリアルタイム出力しながら実行する。

    Returns:
        dict: {"status": "OK"/"ERROR", "elapsed": float, "returncode": int, "error": str|None}
    """
    print(f"\n{'='*70}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {step_name}")
    print(f"  コマンド: {' '.join(str(c) for c in cmd)}")
    print(f"{'='*70}")

    start_time = time.time()

    try:
        # PYTHONUNBUFFERED=1 でリアルタイム出力を保証
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(PROJECT_ROOT),
            env=env,
        )

        for line in process.stdout:
            print(f"  | {line}", end='')

        process.wait()
        elapsed = time.time() - start_time

        if process.returncode == 0:
            print(f"\n  [OK] {step_name} 完了 ({format_elapsed(elapsed)})")
            return {"status": "OK", "elapsed": elapsed, "returncode": 0, "error": None}
        else:
            error_msg = f"終了コード: {process.returncode}"
            print(f"\n  [WARNING] {step_name} 異常終了 ({error_msg}, {format_elapsed(elapsed)})")
            return {"status": "ERROR", "elapsed": elapsed, "returncode": process.returncode, "error": error_msg}

    except FileNotFoundError as e:
        elapsed = time.time() - start_time
        error_msg = f"コマンドが見つかりません: {e}"
        print(f"\n  [ERROR] {error_msg}")
        return {"status": "ERROR", "elapsed": elapsed, "returncode": -1, "error": error_msg}

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"予期しないエラー: {e}"
        print(f"\n  [ERROR] {error_msg}")
        return {"status": "ERROR", "elapsed": elapsed, "returncode": -1, "error": error_msg}


# ============================================================
# ステップ定義
# ============================================================

def build_steps() -> list:
    """実行ステップ一覧を構築して返す"""
    py = sys.executable
    data_coll = PROJECT_ROOT / "scripts" / "data_collection"
    automation = PROJECT_ROOT / "scripts" / "automation"

    steps = []

    # Step 1: レース基本データ + 結果
    steps.append({
        "name": "Step 1: レース基本データ + 結果補完",
        "cmd": [
            py,
            str(data_coll / "fetch_historical_data_parallel.py"),
            "--start", BACKFILL_START,
            "--end", BACKFILL_END,
            "--skip-existing",
        ],
    })

    # Step 2a: 直前情報CSV収集
    steps.append({
        "name": "Step 2a: 直前情報CSV収集",
        "cmd": [
            py,
            str(data_coll / "collect_beforeinfo_to_csv_parallel.py"),
            "--start", BACKFILL_START,
            "--end", BACKFILL_END,
            "--output", CSV_OUTPUT_DIR,
        ],
    })

    # Step 2b: CSV→DB投入
    steps.append({
        "name": "Step 2b: 直前情報CSV→DB投入",
        "cmd": [
            py,
            str(data_coll / "import_beforeinfo_csv_to_db.py"),
            "--input", CSV_OUTPUT_DIR,
        ],
    })

    # Step 3: 直前予想生成（日付ループ）
    for date_str in get_date_range(BACKFILL_START, BACKFILL_END):
        steps.append({
            "name": f"Step 3: 直前予想生成 ({date_str})",
            "cmd": [
                py,
                str(automation / "generate_yesterday_before_predictions.py"),
                "--date", date_str,
                "--force",
            ],
        })

    return steps


# ============================================================
# 表示・通知
# ============================================================

def print_plan(steps: list):
    """実行計画を表示"""
    print("\n" + "=" * 70)
    print("  データ欠損補完スクリプト")
    print(f"  対象期間: {BACKFILL_START} 〜 {BACKFILL_END}")
    print(f"  総ステップ数: {len(steps)}")
    print("=" * 70)
    for i, step in enumerate(steps, 1):
        print(f"  [{i:2d}/{len(steps)}] {step['name']}")
    print("=" * 70 + "\n")


def print_summary(results: list, total_elapsed: float) -> tuple:
    """実行結果サマリーを表示し (success_count, error_count) を返す"""
    success_count = sum(1 for r in results if r["result"]["status"] == "OK")
    error_count = len(results) - success_count

    print("\n" + "=" * 70)
    print("  実行結果サマリー")
    print("=" * 70)
    print(f"  総ステップ数   : {len(results)}")
    print(f"  成功           : {success_count}")
    print(f"  失敗           : {error_count}")
    print(f"  総所要時間     : {format_elapsed(total_elapsed)}")
    print("-" * 70)

    for entry in results:
        r = entry["result"]
        icon = "[OK]   " if r["status"] == "OK" else "[ERROR]"
        line = f"  {icon} {entry['name']} ({format_elapsed(r['elapsed'])})"
        if r["status"] == "ERROR":
            line += f" → {r['error']}"
        print(line)

    print("=" * 70)
    return success_count, error_count


def build_discord_message(results: list, total_elapsed: float) -> str:
    """Discord通知用メッセージを構築（2000文字制限対応）"""
    success_count = sum(1 for r in results if r["result"]["status"] == "OK")
    error_count = len(results) - success_count

    status_icon = "✅" if error_count == 0 else "⚠️"

    lines = [
        f"{status_icon} **データ欠損補完完了**",
        "",
        f"対象期間: {BACKFILL_START} 〜 {BACKFILL_END}",
        f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "**結果:**",
        f"- 成功: {success_count}/{len(results)} ステップ",
        f"- 失敗: {error_count} ステップ",
        f"- 総所要時間: {format_elapsed(total_elapsed)}",
        "",
        "**ステップ詳細:**",
    ]

    step3_ok = step3_err = 0
    step3_elapsed = 0.0

    for entry in results:
        name = entry["name"]
        r = entry["result"]

        if name.startswith("Step 3:"):
            step3_elapsed += r["elapsed"]
            if r["status"] == "OK":
                step3_ok += 1
            else:
                step3_err += 1
            continue

        icon = "✅" if r["status"] == "OK" else "❌"
        lines.append(f"{icon} {name} ({format_elapsed(r['elapsed'])})")

    if step3_ok + step3_err > 0:
        step3_total = step3_ok + step3_err
        step3_icon = "✅" if step3_err == 0 else "⚠️"
        lines.append(
            f"{step3_icon} Step 3: 直前予想生成 {step3_ok}/{step3_total}日成功 ({format_elapsed(step3_elapsed)})"
        )

    if error_count > 0:
        lines.append(f"\n⚠️ エラー {error_count}件 - ログを確認してください")

    return "\n".join(lines)


# ============================================================
# メイン
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=f"スケジューラー停止期間（{BACKFILL_START}〜{BACKFILL_END}）のデータ欠損補完"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="実行計画を表示するだけで処理は行わない")
    args = parser.parse_args()

    steps = build_steps()
    print_plan(steps)

    if args.dry_run:
        print("[DRY-RUN] 実行計画の確認のみです。実際の処理は行いません。")
        return 0

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 補完処理を開始します...\n")
    overall_start = time.time()
    results = []

    for i, step in enumerate(steps, 1):
        print(f"\n--- ステップ [{i}/{len(steps)}] ---")
        result = run_command(step["cmd"], step["name"])
        results.append({"name": step["name"], "result": result})

        if result["status"] == "ERROR":
            print(f"  [WARNING] 失敗しましたが後続ステップを続行します。")

    overall_elapsed = time.time() - overall_start
    success_count, error_count = print_summary(results, overall_elapsed)

    # Discord通知
    try:
        message = build_discord_message(results, overall_elapsed)
        send_discord_notification(message)
        print("\n[OK] Discord通知送信完了")
    except Exception as e:
        print(f"[WARNING] Discord通知送信失敗: {e}")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
