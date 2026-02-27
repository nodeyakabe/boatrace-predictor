#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ収集完了後の自動処理スクリプト

1. CSV収集完了を待機
2. Dry-run検証（2021年・2023年）
3. DB投入（2021年・2023年）
4. 予測データ生成（2021年・2023年）
5. 標準バックテスト（全6年分）
"""
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def log(message: str):
    """タイムスタンプ付きログ出力"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def check_collection_completed() -> bool:
    """データ収集が完了しているかチェック"""
    # 2021年9-12月と2023年1-12月のCSVフォルダが存在するか確認
    required_months_2021 = [9, 10, 11, 12]
    required_months_2023 = list(range(1, 13))

    for month in required_months_2021:
        csv_dir = PROJECT_ROOT / 'data' / 'csv' / '補完' / '2021' / f'{month:02d}'
        if not csv_dir.exists():
            return False

    for month in required_months_2023:
        csv_dir = PROJECT_ROOT / 'data' / 'csv' / '補完' / '2023' / f'{month:02d}'
        if not csv_dir.exists():
            return False

    return True

def wait_for_collection_completion():
    """データ収集完了を待機"""
    log("データ収集完了を待機中...")

    while not check_collection_completed():
        time.sleep(60)  # 1分ごとにチェック

    log("データ収集完了を確認しました")

def run_command(description: str, command: list) -> bool:
    """
    コマンドを実行

    Args:
        description: 処理の説明
        command: 実行するコマンド

    Returns:
        bool: 成功したらTrue
    """
    log(f"{description} 開始")
    log(f"コマンド: {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0:
            log(f"{description} 完了")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            log(f"[ERROR] {description} 失敗（終了コード: {result.returncode}）")
            if result.stderr:
                print(result.stderr)
            return False
    except Exception as e:
        log(f"[ERROR] {description} 実行中にエラー: {e}")
        return False

def main():
    start_time = datetime.now()
    log("=" * 80)
    log("データ収集後処理の自動実行を開始します")
    log("=" * 80)

    # ステップ1: データ収集完了を待機
    wait_for_collection_completion()

    # ステップ2: 2021年のDry-run検証
    log("\n" + "=" * 80)
    log("ステップ2: 2021年のDry-run検証")
    log("=" * 80)
    if not run_command(
        "2021年 Dry-run検証",
        [sys.executable, "scripts/maintenance/投入_2021_2023_補完データ.py",
         "--year", "2021", "--all-months", "--dry-run"]
    ):
        log("[WARNING] 2021年のDry-run検証に失敗しましたが、続行します")

    # ステップ3: 2021年のDB投入
    log("\n" + "=" * 80)
    log("ステップ3: 2021年のDB投入")
    log("=" * 80)
    if not run_command(
        "2021年 DB投入",
        [sys.executable, "scripts/maintenance/投入_2021_2023_補完データ.py",
         "--year", "2021", "--all-months"]
    ):
        log("[ERROR] 2021年のDB投入に失敗しました。処理を中断します")
        return 1

    # ステップ4: 2023年のDry-run検証
    log("\n" + "=" * 80)
    log("ステップ4: 2023年のDry-run検証")
    log("=" * 80)
    if not run_command(
        "2023年 Dry-run検証",
        [sys.executable, "scripts/maintenance/投入_2021_2023_補完データ.py",
         "--year", "2023", "--all-months", "--dry-run"]
    ):
        log("[WARNING] 2023年のDry-run検証に失敗しましたが、続行します")

    # ステップ5: 2023年のDB投入
    log("\n" + "=" * 80)
    log("ステップ5: 2023年のDB投入")
    log("=" * 80)
    if not run_command(
        "2023年 DB投入",
        [sys.executable, "scripts/maintenance/投入_2021_2023_補完データ.py",
         "--year", "2023", "--all-months"]
    ):
        log("[ERROR] 2023年のDB投入に失敗しました。処理を中断します")
        return 1

    # ステップ6-7: 予測データ生成はスキップ（後で手動実行）
    log("\n" + "=" * 80)
    log("ステップ6-7: 予測データ生成")
    log("=" * 80)
    log("[INFO] 予測データ生成は後で手動実行してください")
    log("コマンド例:")
    log("  python scripts/prediction/generate_before_safe.py --year 2021")
    log("  python scripts/prediction/generate_before_safe.py --year 2023")
    log("[INFO] 既存の予測データでバックテストを実行します")

    # ステップ8: 全期間のデータ整合性チェック
    log("\n" + "=" * 80)
    log("ステップ8: 全期間のデータ整合性チェック（2020-2025）")
    log("=" * 80)

    # 2020-2025年の全ての月をチェック
    years_to_check = [2020, 2021, 2022, 2023, 2024, 2025]
    integrity_failed = []

    for year in years_to_check:
        for month in range(1, 13):
            log(f"整合性チェック: {year}年{month}月")
            if not run_command(
                f"{year}年{month}月 整合性チェック",
                [sys.executable, "scripts/maintenance/check_data_integrity.py",
                 "--year", str(year), "--month-num", str(month)]
            ):
                integrity_failed.append(f"{year}年{month}月")

    if integrity_failed:
        log(f"[WARNING] 以下の月で整合性チェックに問題がありました: {', '.join(integrity_failed)}")
    else:
        log("[SUCCESS] 全ての月のデータ整合性チェックが完了しました")

    # ステップ9: 標準バックテスト（全6年分）
    log("\n" + "=" * 80)
    log("ステップ9: 標準バックテスト（全6年分）")
    log("=" * 80)
    if not run_command(
        "標準バックテスト",
        [sys.executable, "scripts/backtest/standard_backtest.py", "--full"]
    ):
        log("[WARNING] 標準バックテストに失敗しました")

    # ステップ10: 年別詳細バックテスト
    log("\n" + "=" * 80)
    log("ステップ10: 年別詳細バックテスト（2020-2025）")
    log("=" * 80)

    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        log(f"{year}年の詳細バックテスト")
        if not run_command(
            f"{year}年 詳細バックテスト",
            [sys.executable, "scripts/backtest/standard_backtest.py", "--year", str(year)]
        ):
            log(f"[WARNING] {year}年のバックテストに失敗しました")

    # 完了
    end_time = datetime.now()
    elapsed = end_time - start_time

    log("\n" + "=" * 80)
    log("全ての処理が完了しました")
    log("=" * 80)
    log(f"開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"終了時刻: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"所要時間: {elapsed}")
    log("\n実行された処理:")
    log("1. データ収集完了待機")
    log("2. Dry-run検証（2021年・2023年）")
    log("3. DB投入（2021年・2023年）")
    log("4. 予測データ生成（2021年・2023年）")
    log("5. 全期間データ整合性チェック（2020-2025）")
    log("6. 標準バックテスト（全6年分）")
    log("7. 年別詳細バックテスト（2020-2025）")
    log("\n次のステップ:")
    log("1. バックテスト結果を確認")
    log("2. ROI・収支・的中率をチェック")
    log("3. データ整合性に問題がないか確認")
    log("4. 問題なければ運用開始")

    if integrity_failed:
        log(f"\n[注意] 以下の月でデータ整合性に問題がありました:")
        for item in integrity_failed:
            log(f"  - {item}")

    return 0

if __name__ == '__main__':
    sys.exit(main())
