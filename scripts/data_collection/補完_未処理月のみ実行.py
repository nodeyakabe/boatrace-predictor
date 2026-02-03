#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
未処理月のみのデータ補完スクリプト

2021年7月～12月 + 2023年全体を収集
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def log(message):
    """ログ出力（時刻付き）"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()

def check_month_completed(year: int, month: int) -> bool:
    """
    指定月のCSVが既に存在するかチェック

    Args:
        year: 対象年
        month: 対象月

    Returns:
        bool: CSVファイルが存在し、一定のサイズがある場合True
    """
    csv_dir = PROJECT_ROOT / 'data' / 'csv' / '補完' / str(year) / f'{month:02d}'

    if not csv_dir.exists():
        return False

    # 必須CSVファイルをチェック
    required_files = ['races.csv', 'entries.csv', 'results.csv']
    for filename in required_files:
        csv_file = csv_dir / filename
        if not csv_file.exists():
            return False
        # ヘッダーのみ（<200バイト）の場合は未完了とみなす
        if csv_file.stat().st_size < 200:
            return False

    return True

def run_month(year: int, month: int, skip_completed: bool = True):
    """
    指定年月のデータ収集を実行

    Args:
        year: 対象年
        month: 対象月
        skip_completed: 既に完了している月をスキップするか

    Returns:
        bool: 成功したかどうか
    """
    # 既に完了しているかチェック
    if skip_completed and check_month_completed(year, month):
        log(f"{'=' * 80}")
        log(f"{year}年{month}月: 既に完了済み（スキップ）")
        log(f"{'=' * 80}")
        return True

    log(f"{'=' * 80}")
    log(f"{year}年{month}月のデータ収集開始")
    log(f"{'=' * 80}")

    script_path = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_欠損データ.py'

    cmd = [sys.executable, str(script_path), '--year', str(year), '--month', str(month)]
    log(f"実行コマンド: python {script_path.name} --year {year} --month {month}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=False,
            text=True,
            check=True
        )
        log(f"✅ {year}年{month}月のデータ収集完了")
        return True
    except subprocess.CalledProcessError as e:
        log(f"❌ {year}年{month}月のデータ収集失敗: {e}")
        return False
    except Exception as e:
        log(f"❌ 予期しないエラー: {e}")
        return False

def main():
    """メイン処理"""
    start_time = datetime.now()
    log("未処理月のみのデータ補完開始")
    log("対象: 2021年7月～12月 + 2023年全体")
    log("")

    # 収集対象
    tasks = []
    # 2021年7月～12月
    for month in range(7, 13):
        tasks.append((2021, month))
    # 2023年全体
    for month in range(1, 13):
        tasks.append((2023, month))

    # 既に完了している月をカウント
    already_completed = sum(1 for year, month in tasks if check_month_completed(year, month))
    remaining = len(tasks) - already_completed

    log(f"総タスク数: {len(tasks)}ヶ月")
    log(f"既に完了: {already_completed}ヶ月")
    log(f"残りタスク: {remaining}ヶ月")
    log(f"予想所要時間: 約{remaining * 2.5:.0f}-{remaining * 3.5:.0f}時間")
    log("")

    # 実行
    success_count = 0
    skipped_count = 0
    failed_months = []

    for year, month in tasks:
        was_completed = check_month_completed(year, month)
        if run_month(year, month):
            if was_completed:
                skipped_count += 1
            else:
                success_count += 1
        else:
            failed_months.append(f"{year}年{month}月")
        log("")

    # 結果サマリー
    end_time = datetime.now()
    elapsed = end_time - start_time

    log(f"{'=' * 80}")
    log("データ補完完了")
    log(f"{'=' * 80}")
    log(f"新規収集: {success_count}ヶ月")
    log(f"スキップ: {skipped_count}ヶ月（既に完了済み）")
    log(f"失敗: {len(failed_months)}ヶ月")
    log(f"合計: {success_count + skipped_count + len(failed_months)}/{len(tasks)}ヶ月")
    log(f"所要時間: {elapsed}")

    if failed_months:
        log("")
        log(f"⚠️ 失敗した月: {', '.join(failed_months)}")

    log("")

    if success_count + skipped_count == len(tasks):
        log("✅ 全ての月のデータ収集が完了しました")
        log("")
        log("次のステップ:")
        log("1. CSV検証:")
        log("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months --dry-run")
        log("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months --dry-run")
        log("")
        log("2. DB投入:")
        log("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months")
        log("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months")
        return 0
    else:
        log("❌ 一部の月でエラーが発生しました")
        log("失敗した月を個別に再実行してください")
        return 1

if __name__ == '__main__':
    sys.exit(main())
