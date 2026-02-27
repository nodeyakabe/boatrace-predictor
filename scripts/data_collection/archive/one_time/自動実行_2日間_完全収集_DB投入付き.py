#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2日間完全自動データ収集+DB投入スクリプト

2021年・2023年の全データを48時間で自動収集し、DBに投入します。

実行内容:
1. 2021年1-12月のデータ収集（CSV）
2. 2021年データのDB投入
3. 2023年1-12月のデータ収集（CSV）
4. 2023年データのDB投入
5. データ整合性チェック（オプション）
6. 標準バックテスト（オプション）

特徴:
- エラー発生時も次の月に進む
- 詳細なログ出力
- 途中経過を常に保存
- 失敗した月をリスト化
- 完了後自動でDB投入
"""
import sys
import io
import subprocess
from pathlib import Path
from datetime import datetime
import time
import argparse

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def log(message: str):
    """タイムスタンプ付きログ出力"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def run_command(description: str, command: list) -> bool:
    """
    コマンドを実行

    Args:
        description: コマンドの説明
        command: 実行するコマンドのリスト

    Returns:
        成功時True、失敗時False
    """
    log(f"実行: {description}")
    start_time = time.time()

    try:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=False,
            text=True
        )

        elapsed = time.time() - start_time
        log(f"完了: {description} （所要時間: {elapsed/60:.1f}分）")
        return True

    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        log(f"[ERROR] 失敗: {description} （所要時間: {elapsed/60:.1f}分）")
        log(f"[ERROR] 終了コード: {e.returncode}")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        log(f"[ERROR] 予期しないエラー: {description} （所要時間: {elapsed/60:.1f}分）")
        log(f"[ERROR] エラー内容: {e}")
        return False

def run_collection(year: int, month: int) -> bool:
    """
    指定年月のデータ収集を実行

    Returns:
        成功時True、失敗時False
    """
    script = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_完全版.py'

    # 完全版スクリプトが存在しない場合は欠損データスクリプトを使用
    if not script.exists():
        log(f"[WARNING] 完全版スクリプトが見つかりません。欠損データスクリプトを使用します")
        script = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_欠損データ.py'

    return run_command(
        f"{year}年{month}月 データ収集",
        [sys.executable, str(script), '--year', str(year), '--month', str(month)]
    )

def run_db_insert(year: int) -> bool:
    """
    指定年のデータをDBに投入

    Returns:
        成功時True、失敗時False
    """
    script = PROJECT_ROOT / 'scripts' / 'maintenance' / '投入_2021_2023_補完データ.py'

    return run_command(
        f"{year}年 DB投入",
        [sys.executable, str(script), '--year', str(year), '--all-months']
    )

def main():
    parser = argparse.ArgumentParser(description='2日間完全自動データ収集+DB投入')
    parser.add_argument('--skip-collection', action='store_true', help='データ収集をスキップ（DB投入のみ）')
    parser.add_argument('--skip-db-insert', action='store_true', help='DB投入をスキップ（収集のみ）')
    parser.add_argument('--run-backtest', action='store_true', help='完了後にバックテストを実行')
    args = parser.parse_args()

    log("=" * 80)
    log("2日間完全自動データ収集+DB投入スクリプト")
    log("=" * 80)
    log("実行内容:")
    if not args.skip_collection:
        log("  1. 2021年1-12月のデータ収集（CSV）")
        log("  2. 2021年データのDB投入")
        log("  3. 2023年1-12月のデータ収集（CSV）")
        log("  4. 2023年データのDB投入")
    else:
        log("  1. データ収集はスキップ")
        log("  2. DB投入のみ実行")

    if args.run_backtest:
        log("  5. 標準バックテスト実行")

    log("  推定所要時間: 48-72時間（収集）+ 1-2時間（DB投入）")
    log("=" * 80)
    log("")

    start_time = datetime.now()
    failed_months = []
    success_count = 0
    total_count = 0

    # フェーズ1: 2021年データ収集
    if not args.skip_collection:
        log("")
        log("=" * 80)
        log("フェーズ1: 2021年のデータ収集（1-12月）")
        log("=" * 80)
        log("")

        for month in range(1, 13):
            total_count += 1
            if run_collection(2021, month):
                success_count += 1
            else:
                failed_months.append(f"2021年{month}月")

            # 進捗表示
            log("")
            log(f"--- 進捗: {total_count}/24 完了 ({success_count}成功, {len(failed_months)}失敗) ---")
            elapsed = datetime.now() - start_time
            log(f"--- 経過時間: {elapsed} ---")
            log("")

    # フェーズ2: 2021年DB投入
    if not args.skip_db_insert:
        log("")
        log("=" * 80)
        log("フェーズ2: 2021年データのDB投入")
        log("=" * 80)
        log("")

        if not run_db_insert(2021):
            log("[WARNING] 2021年のDB投入に失敗しましたが、処理を継続します")

    # フェーズ3: 2023年データ収集
    if not args.skip_collection:
        log("")
        log("=" * 80)
        log("フェーズ3: 2023年のデータ収集（1-12月）")
        log("=" * 80)
        log("")

        for month in range(1, 13):
            total_count += 1
            if run_collection(2023, month):
                success_count += 1
            else:
                failed_months.append(f"2023年{month}月")

            # 進捗表示
            log("")
            log(f"--- 進捗: {total_count}/24 完了 ({success_count}成功, {len(failed_months)}失敗) ---")
            elapsed = datetime.now() - start_time
            log(f"--- 経過時間: {elapsed} ---")
            log("")

    # フェーズ4: 2023年DB投入
    if not args.skip_db_insert:
        log("")
        log("=" * 80)
        log("フェーズ4: 2023年データのDB投入")
        log("=" * 80)
        log("")

        if not run_db_insert(2023):
            log("[WARNING] 2023年のDB投入に失敗しましたが、処理を継続します")

    # フェーズ5: バックテスト（オプション）
    if args.run_backtest:
        log("")
        log("=" * 80)
        log("フェーズ5: 標準バックテスト")
        log("=" * 80)
        log("")

        run_command(
            "標準バックテスト",
            [sys.executable, 'scripts/backtest/standard_backtest.py', '--full']
        )

    # 最終レポート
    end_time = datetime.now()
    total_elapsed = end_time - start_time

    log("")
    log("=" * 80)
    log("全処理完了")
    log("=" * 80)
    log(f"開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"終了時刻: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"所要時間: {total_elapsed}")
    log("")

    if not args.skip_collection:
        log(f"データ収集結果: {success_count}成功 / {len(failed_months)}失敗 / {total_count}総数")
        log("")

        if failed_months:
            log("失敗した月:")
            for failed in failed_months:
                log(f"  - {failed}")
            log("")
            log("失敗した月は後で個別に再実行してください")
        else:
            log("全ての月のデータ収集が成功しました！")

    log("")
    log("=" * 80)
    log("次のステップ:")
    log("=" * 80)

    if failed_months:
        log("1. 失敗した月を個別に再実行")
        log("")

    if args.skip_db_insert:
        log("1. データベース投入:")
        log("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months")
        log("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months")
        log("")

    if not args.run_backtest:
        log("1. 標準バックテスト:")
        log("   python scripts/backtest/standard_backtest.py --full")
        log("")

    log("2. データ充足率チェック:")
    log("   python scripts/maintenance/check_data_quality.py")
    log("")
    log("=" * 80)

    # 失敗があった場合は1を返す
    return 1 if failed_months else 0

if __name__ == '__main__':
    sys.exit(main())
