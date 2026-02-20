# -*- coding: utf-8 -*-
"""単一月のテスト（2020年2月）"""
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
import json

ROOT_DIR = Path(__file__).parent
CSV_BASE_DIR = ROOT_DIR / "data" / "csv" / "exhibition_data"
LOG_DIR = ROOT_DIR / "logs"

LOG_DIR.mkdir(parents=True, exist_ok=True)

def log(message):
    """ログ出力"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] {message}"
    print(log_message)

def collect_month(year_month):
    """1ヶ月分のデータを収集してインポート"""
    year, month = year_month.split('-')

    start_date = f"{year}-{month}-01"
    end_date = f"{year}-{month}-29"  # 2月は29日まで

    output_dir = CSV_BASE_DIR / f"{year}_{month}"

    log("="*80)
    log(f"収集開始: {year_month}")
    log(f"期間: {start_date} - {end_date}")
    log(f"出力先: {output_dir}")
    log("="*80)

    # Step 1: CSV収集
    log("Step 1/2: CSVファイルに収集中...")
    csv_cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "data_collection" / "fetch_exhibition_data_to_csv.py"),
        "--start", start_date,
        "--end", end_date,
        "--output", str(output_dir),
        "--workers", "8"
    ]

    log(f"実行コマンド: {' '.join(csv_cmd)}")

    try:
        result = subprocess.run(csv_cmd, capture_output=True, text=True, timeout=3600)

        if result.returncode != 0:
            log(f"エラー: CSV収集失敗 (exit code: {result.returncode})")
            log(f"STDOUT: {result.stdout[:1000]}")
            log(f"STDERR: {result.stderr[:1000]}")
            return False

        log("CSV収集完了")
        # 出力の最後の部分を表示
        stdout_lines = result.stdout.strip().split('\n')
        for line in stdout_lines[-10:]:
            log(f"  {line}")

    except subprocess.TimeoutExpired:
        log("タイムアウト: CSV収集（60分以内に完了しなかった）")
        return False
    except Exception as e:
        log(f"例外発生: {type(e).__name__} - {e}")
        return False

    # Step 2: DB投入
    csv_file = output_dir / "exhibition_data.csv"
    if not csv_file.exists():
        log(f"エラー: CSVファイルが見つかりません: {csv_file}")
        return False

    log(f"Step 2/2: DBに投入中...")
    import_cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "maintenance" / "import_exhibition_data_from_csv.py"),
        "--input", str(output_dir)
    ]

    try:
        result = subprocess.run(import_cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            log(f"エラー: DB投入失敗 (exit code: {result.returncode})")
            log(f"STDOUT: {result.stdout[:1000]}")
            log(f"STDERR: {result.stderr[:1000]}")
            return False

        log("DB投入完了")
        # 出力の最後の部分を表示
        stdout_lines = result.stdout.strip().split('\n')
        for line in stdout_lines[-10:]:
            log(f"  {line}")

        log("="*80)
        return True

    except subprocess.TimeoutExpired:
        log("タイムアウト: DB投入（10分以内に完了しなかった）")
        return False
    except Exception as e:
        log(f"例外発生: {type(e).__name__} - {e}")
        return False

log("="*80)
log("2020年2月 単一月テスト開始")
log("="*80)

success = collect_month("2020-02")

log("")
log("="*80)
if success:
    log("[OK] テスト成功！")
    log("")
    log("次のステップ:")
    log("  python scripts/data_collection/collect_exhibition_2020_2024.py")
else:
    log("[NG] テスト失敗")
log("="*80)
