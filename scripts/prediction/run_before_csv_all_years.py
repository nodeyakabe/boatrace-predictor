"""
2020-2025年 before予測 CSV生成 全年度連続実行スクリプト
再起動耐性あり（完了年度はマーカーファイルでスキップ）

使い方:
    python scripts/prediction/run_before_csv_all_years.py

完了済み年度の再実行が必要な場合:
    python scripts/prediction/run_before_csv_all_years.py --reset 2022
    python scripts/prediction/run_before_csv_all_years.py --reset-all

完了後のDB反映:
    for year in 2020 2021 2022 2023 2024 2025:
        python scripts/prediction/generate_before_fast.py --import-only data/predictions_csv/before/{year}
"""

import subprocess
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
CSV_BASE  = BASE_DIR / "data" / "predictions_csv" / "before"
LOG_DIR   = BASE_DIR / "logs"
LOG_FILE  = LOG_DIR / "before_csv_all_years.log"

# 2024はCSV生成済み（data/predictions_csv/before/2024/ に366日分・Opus品質チェック済み）のため除外
YEARS = [2020, 2021, 2022, 2023, 2025]


def marker_path(year: int) -> Path:
    # マーカーファイルが存在する = その年度のCSV生成が完了している
    # reset時はマーカーのみ削除でよい（--forceがCSVを再生成時にクリアするため）
    return CSV_BASE / str(year) / ".completed"


def is_done(year: int) -> bool:
    return marker_path(year).exists()


def mark_done(year: int):
    marker_path(year).parent.mkdir(parents=True, exist_ok=True)
    marker_path(year).write_text(datetime.now().isoformat())


def reset_marker(year: int):
    p = marker_path(year)
    if p.exists():
        p.unlink()
        print(f"[reset] {year} のマーカーを削除しました")
    else:
        print(f"[reset] {year} のマーカーは存在しません（未完了）")


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_year(year: int) -> bool:
    log(f"=== {year}年 CSV生成 開始 ===")
    cmd = [
        sys.executable,
        str(BASE_DIR / "scripts" / "prediction" / "generate_before_fast.py"),
        "--year", str(year),
        "--force",
        "--csv-only",
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with open(LOG_FILE, "a", encoding="utf-8") as logf:
        logf.write(f"\n--- subprocess開始: {datetime.now().isoformat()} ---\n")
        logf.flush()
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            env=env,
            stdout=logf,
            stderr=logf,
        )
        logf.flush()
        os.fsync(logf.fileno())

    if result.returncode == 0:
        mark_done(year)
        log(f"=== {year}年 CSV生成 完了 ===")
        return True
    else:
        log(f"=== {year}年 CSV生成 失敗（exit code: {result.returncode}）===")
        return False


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="全年度 before予測 CSV生成（再起動耐性あり）")
    parser.add_argument("--reset", type=int, metavar="YEAR",
                        help="指定年度の完了マーカーを削除して再実行対象にする")
    parser.add_argument("--reset-all", action="store_true",
                        help="全年度の完了マーカーを削除する")
    parser.add_argument("--status", action="store_true",
                        help="各年度の完了状態を表示して終了")
    args = parser.parse_args()

    if args.reset_all:
        for y in YEARS:
            reset_marker(y)
        return

    if args.reset:
        reset_marker(args.reset)
        return

    if args.status:
        for y in YEARS:
            status = "done" if is_done(y) else "pending"
            print(f"  {y}: {status}")
        return

    log("=" * 60)
    log(f"全年度 before予測 CSV生成 開始: {YEARS}")
    log("=" * 60)

    try:
        for year in YEARS:
            if is_done(year):
                log(f"--- {year}年 スキップ（完了済み）---")
                continue
            success = run_year(year)
            if not success:
                log(f"エラーにより {year}年 で停止。再実行で {year}年 から再開できます。")
                sys.exit(1)
    except KeyboardInterrupt:
        log("中断されました（Ctrl+C）。再実行すると中断した年度から再開できます。")
        sys.exit(130)

    log("=" * 60)
    log("全年度 CSV生成 完了！")
    log("次のステップ（DB反映）:")
    log("  for year in 2020 2021 2022 2023 2024 2025:")
    log("    python scripts/prediction/generate_before_fast.py --import-only data/predictions_csv/before/{year}")
    log("  python scripts/backtest/standard_backtest_unique.py --full")
    log("=" * 60)


if __name__ == "__main__":
    main()
