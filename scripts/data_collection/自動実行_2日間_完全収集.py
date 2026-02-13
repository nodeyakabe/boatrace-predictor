#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2日間完全自動データ収集スクリプト

2021年・2023年の全データを48時間で自動収集します。

実行内容:
1. 2021年1-12月のデータ収集（CSV）
2. 2023年1-12月のデータ収集（CSV）
3. データベース投入（オプション）
4. データ整合性チェック（オプション）

特徴:
- エラー発生時も次の月に進む
- 詳細なログ出力
- 途中経過を常に保存
- 失敗した月をリスト化
"""
import sys
import io
import subprocess
from pathlib import Path
from datetime import datetime
import time

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def log(message: str):
    """タイムスタンプ付きログ出力"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def run_collection(year: int, month: int) -> bool:
    """
    指定年月のデータ収集を実行

    Returns:
        成功時True、失敗時False
    """
    log(f"開始: {year}年{month}月のデータ収集")

    script = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_完全版.py'

    # 完全版スクリプトが存在しない場合は欠損データスクリプトを使用
    if not script.exists():
        log(f"[WARNING] 完全版スクリプトが見つかりません。欠損データスクリプトを使用します")
        script = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_欠損データ.py'

    start_time = time.time()

    try:
        result = subprocess.run(
            [sys.executable, str(script), '--year', str(year), '--month', str(month)],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=False,
            text=True
        )

        elapsed = time.time() - start_time
        log(f"完了: {year}年{month}月 （所要時間: {elapsed/60:.1f}分）")
        return True

    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        log(f"[ERROR] 失敗: {year}年{month}月 （所要時間: {elapsed/60:.1f}分）")
        log(f"[ERROR] 終了コード: {e.returncode}")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        log(f"[ERROR] 予期しないエラー: {year}年{month}月 （所要時間: {elapsed/60:.1f}分）")
        log(f"[ERROR] エラー内容: {e}")
        return False

def main():
    log("=" * 80)
    log("2日間完全自動データ収集スクリプト")
    log("=" * 80)
    log("実行内容:")
    log("  1. 2021年1-12月のデータ収集（CSV）")
    log("  2. 2023年1-12月のデータ収集（CSV）")
    log("  推定所要時間: 48-72時間")
    log("=" * 80)
    log("")

    start_time = datetime.now()
    failed_months = []
    success_count = 0
    total_count = 0

    # 2021年1-12月
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

    # 2023年1-12月
    log("")
    log("=" * 80)
    log("フェーズ2: 2023年のデータ収集（1-12月）")
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

    # 最終レポート
    end_time = datetime.now()
    total_elapsed = end_time - start_time

    log("")
    log("=" * 80)
    log("データ収集完了")
    log("=" * 80)
    log(f"開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"終了時刻: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"所要時間: {total_elapsed}")
    log("")
    log(f"結果: {success_count}成功 / {len(failed_months)}失敗 / {total_count}総数")
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
    log("1. データベース投入:")
    log("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months")
    log("   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months")
    log("")
    log("2. データ整合性チェック:")
    log("   python scripts/maintenance/check_data_quality.py")
    log("")
    log("3. 標準バックテスト:")
    log("   python scripts/backtest/standard_backtest.py --full")
    log("")
    log("=" * 80)

    # 失敗があった場合は1を返す
    return 1 if failed_months else 0

if __name__ == '__main__':
    sys.exit(main())
