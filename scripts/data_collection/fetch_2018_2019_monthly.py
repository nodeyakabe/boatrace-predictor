# -*- coding: utf-8 -*-
"""
2018-2019年データを月単位で安全に収集するバッチスクリプト

【特徴】
- 月単位で実行（再起動時のロストを最大1ヶ月分に限定）
- 完了月はスキップ（progress.json で管理 → 再起動後も再開可能）
- エラー時はスキップして次月へ継続
- 全月完了後にCSV→DB投入を自動実行

【使用方法】
  # 通常実行（2018-01 ～ 2019-12 の24ヶ月を順番に実行）
  python scripts/data_collection/fetch_2018_2019_monthly.py

  # 途中再開（progress.json が残っていれば完了済み月を自動スキップ）
  python scripts/data_collection/fetch_2018_2019_monthly.py

  # 並列数を変更
  python scripts/data_collection/fetch_2018_2019_monthly.py --workers 8

  # CSV収集のみ（DB投入は後で手動）
  python scripts/data_collection/fetch_2018_2019_monthly.py --csv-only

  # 特定月から再開（例: 2018-06 から）
  python scripts/data_collection/fetch_2018_2019_monthly.py --start-month 2018-06

  # 進捗リセット（最初からやり直し）
  python scripts/data_collection/fetch_2018_2019_monthly.py --reset
"""

import sys
import io
import os
import json
import argparse
import subprocess
import calendar
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "csv" / "2018_2019_full"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"
LOG_FILE = OUTPUT_DIR / "fetch_log.txt"

# 対象期間: 2018年1月 ～ 2019年12月
TARGET_MONTHS = []
for year in [2018, 2019]:
    for month in range(1, 13):
        last_day = calendar.monthrange(year, month)[1]
        TARGET_MONTHS.append({
            "label": f"{year}-{month:02d}",
            "start": f"{year}-{month:02d}-01",
            "end":   f"{year}-{month:02d}-{last_day:02d}",
        })


def load_progress() -> dict:
    """進捗ファイルを読み込む"""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed": [], "failed": [], "started_at": datetime.now().isoformat()}


def save_progress(progress: dict):
    """進捗ファイルを保存"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def log(message: str):
    """ログ出力（標準出力 + ファイル）"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {message}"
    print(line)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + "\n")


def run_fetch_month(month_info: dict, workers: int) -> bool:
    """
    1ヶ月分のデータをfetch_to_csv_parallel_improved.pyで取得

    Returns:
        True: 成功, False: 失敗
    """
    label = month_info["label"]
    start = month_info["start"]
    end = month_info["end"]

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "data_collection" / "fetch_to_csv_parallel_improved.py"),
        "--start", start,
        "--end", end,
        "--output", str(OUTPUT_DIR),
        "--workers", str(workers),
    ]

    log(f"[{label}] 開始 ({start} ～ {end})")
    log(f"[{label}] コマンド: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            timeout=7200,  # 2時間タイムアウト（1ヶ月分の最大時間）
            text=True,
            encoding='utf-8',
            errors='replace',
            capture_output=True,  # stdout/stderrをキャプチャしてログに記録
        )

        # 子プロセスの出力をログファイルに記録（デバッグ用）
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                log(f"  [stdout] {line}")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-10:]:  # stderrは末尾10行のみ
                log(f"  [stderr] {line}")

        if result.returncode != 0:
            log(f"[{label}] ❌ 失敗 (returncode={result.returncode})")
            return False

        # サイレント失敗チェック: スケジュールAPI失敗時に0件で正常終了するケースを検出
        if "取得レース数: 0" in (result.stdout or "") or "タスク: 0" in (result.stdout or ""):
            log(f"[{label}] ❌ 取得レース数0件（スケジュール取得失敗の可能性）")
            return False

        log(f"[{label}] ✅ 完了")
        return True

    except subprocess.TimeoutExpired:
        log(f"[{label}] ❌ タイムアウト（2時間超過）")
        return False
    except Exception as e:
        log(f"[{label}] ❌ 例外: {e}")
        return False


def run_import_csv() -> bool:
    """
    CSV→DB投入（import_races_csv.py）を実行

    Returns:
        True: 成功, False: 失敗
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "data_collection" / "import_races_csv.py"),
        "--dir", str(OUTPUT_DIR),
    ]

    log("=== CSV→DB投入開始 ===")
    log(f"コマンド: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            timeout=3600,  # 1時間タイムアウト
            text=True,
            encoding='utf-8',
            errors='replace',
        )

        if result.returncode == 0:
            log("✅ CSV→DB投入完了")
            return True
        else:
            log(f"❌ CSV→DB投入失敗 (returncode={result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        log("❌ CSV→DB投入タイムアウト")
        return False
    except Exception as e:
        log(f"❌ CSV→DB投入例外: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='2018-2019年データを月単位で安全に収集',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--workers', type=int, default=12,
                        help='並列ワーカー数（デフォルト: 12）')
    parser.add_argument('--csv-only', action='store_true',
                        help='CSV収集のみ（DB投入を行わない）')
    parser.add_argument('--start-month', type=str, default=None,
                        help='開始月（例: 2018-06）。これより前の月はスキップ')
    parser.add_argument('--reset', action='store_true',
                        help='進捗をリセットして最初からやり直し')
    parser.add_argument('--auto-import', action='store_true',
                        help='全月完了後のDB投入を自動実行（バックグラウンド実行時に使用）')
    args = parser.parse_args()

    # 出力ディレクトリ作成
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("2018-2019年データ 月別収集バッチ")
    print("=" * 70)
    print(f"出力先:   {OUTPUT_DIR}")
    print(f"進捗管理: {PROGRESS_FILE}")
    print(f"ログ:     {LOG_FILE}")
    print(f"並列数:   {args.workers}スレッド")
    print(f"対象:     {TARGET_MONTHS[0]['label']} ～ {TARGET_MONTHS[-1]['label']}（全{len(TARGET_MONTHS)}ヶ月）")
    print()

    # 進捗リセット
    if args.reset:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            print("⚠️  進捗ファイルをリセットしました。最初からやり直します。")
        else:
            print("進捗ファイルは存在しません。")

    # 進捗読み込み
    progress = load_progress()
    completed_set = set(progress.get("completed", []))
    failed_set = set(progress.get("failed", []))

    if completed_set:
        print(f"✅ 完了済み: {sorted(completed_set)}")
    if failed_set:
        print(f"⚠️  前回失敗: {sorted(failed_set)}（今回は再試行します）")
        # 失敗月は再試行のためcompleted扱いにしない
        progress["failed"] = []
    print()

    # 開始月フィルター
    start_month_filter = args.start_month  # 例: "2018-06"

    # 実行する月のリスト（完了済みをスキップ、開始月フィルター適用）
    months_to_run = []
    months_to_skip = []
    for m in TARGET_MONTHS:
        label = m["label"]

        # 開始月フィルター: 指定月より前はスキップ
        if start_month_filter and label < start_month_filter:
            months_to_skip.append(label)
            continue

        if label in completed_set:
            months_to_skip.append(label)
        else:
            months_to_run.append(m)

    print(f"スキップ: {len(months_to_skip)}ヶ月（完了済み or 開始月フィルター）")
    print(f"実行予定: {len(months_to_run)}ヶ月")
    if months_to_run:
        print(f"  → {months_to_run[0]['label']} ～ {months_to_run[-1]['label']}")
    print()

    if not months_to_run:
        print("✅ 全月収集済みです。")
        if not args.csv_only:
            if args.auto_import:
                print("\n--auto-import モード: CSV→DB投入を自動実行します。")
                run_import_csv()
            else:
                print("\nCSV→DB投入を実行しますか? [y/N]: ", end='', flush=True)
                try:
                    ans = input().strip().lower()
                except (EOFError, OSError):
                    print("\n（バックグラウンド実行: スキップ。--auto-import フラグで自動化可能）")
                    ans = 'n'
                if ans == 'y':
                    run_import_csv()
        return

    # 月別収集ループ
    log("=" * 70)
    log(f"2018-2019年データ月別収集 開始（{len(months_to_run)}ヶ月）")
    log("=" * 70)

    newly_completed = []
    newly_failed = []

    for i, month_info in enumerate(months_to_run, 1):
        label = month_info["label"]
        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(months_to_run)}] {label}")
        print(f"{'=' * 60}")

        success = run_fetch_month(month_info, args.workers)

        if success:
            newly_completed.append(label)
            progress["completed"] = sorted(set(progress.get("completed", [])) | {label})
            save_progress(progress)
            print(f"✅ {label} 完了・進捗保存済み")
        else:
            newly_failed.append(label)
            progress["failed"] = sorted(set(progress.get("failed", [])) | {label})
            save_progress(progress)
            print(f"⚠️  {label} 失敗（記録して次月へ継続）")

        # 進捗表示
        total_done = len(progress.get("completed", []))
        print(f"進捗: {total_done}/{len(TARGET_MONTHS)}ヶ月完了")

    # 最終サマリー
    print()
    print("=" * 70)
    print("月別収集 完了サマリー")
    print("=" * 70)
    print(f"✅ 成功: {len(newly_completed)}ヶ月 {newly_completed}")
    if newly_failed:
        print(f"❌ 失敗: {len(newly_failed)}ヶ月 {newly_failed}")
        print("  → 失敗月は再実行してください:")
        for label in newly_failed:
            print(f"     python scripts/data_collection/fetch_2018_2019_monthly.py --start-month {label}")

    total_completed = len(progress.get("completed", []))
    all_done = total_completed == len(TARGET_MONTHS)

    print(f"\n全体進捗: {total_completed}/{len(TARGET_MONTHS)}ヶ月")

    if all_done:
        log("🎉 全24ヶ月の収集完了！")
        if not args.csv_only:
            print("\n" + "=" * 70)
            print("全月収集完了。CSV→DB投入を実行します。")
            print("=" * 70)
            import_success = run_import_csv()
            if import_success:
                log("✅ CSV→DB投入完了。次のステップ:")
                log("  1. 決まり手補完: python scripts/data_collection/補完_決まり手データ_改善版.py --start-date 2018-01-01 --end-date 2019-12-31")
                log("  2. レース詳細補完: python scripts/data_collection/補完_レース詳細データ_改善版v4.py --start-date 2018-01-01 --end-date 2019-12-31")
                log("  3. オッズ収集: python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2018-01-01 --end-date 2019-12-31")
                log("  4. beforeinfo収集: fetch_2018_2019_beforeinfo.py")

                print()
                print("次のステップ:")
                print("  1. 決まり手補完:")
                print("     python scripts/data_collection/補完_決まり手データ_改善版.py --start-date 2018-01-01 --end-date 2019-12-31")
                print("  2. レース詳細補完:")
                print("     python scripts/data_collection/補完_レース詳細データ_改善版v4.py --start-date 2018-01-01 --end-date 2019-12-31")
                print("  3. オッズ収集:")
                print("     python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2018-01-01 --end-date 2019-12-31")
                print("  4. beforeinfo収集:")
                print("     python scripts/data_collection/fetch_2018_2019_beforeinfo.py")
        else:
            print("\n--csv-only モード。DB投入は手動で実行してください:")
            print(f"  python scripts/data_collection/import_races_csv.py --dir {OUTPUT_DIR}")
    else:
        remaining = len(TARGET_MONTHS) - total_completed
        print(f"\n残り{remaining}ヶ月。再実行すると続きから開始します:")
        print("  python scripts/data_collection/fetch_2018_2019_monthly.py")


if __name__ == '__main__':
    main()
