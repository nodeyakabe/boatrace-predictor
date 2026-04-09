#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
advance予測 全年度再生成スクリプト（2020-2025順次実行）

2020年がすでに実行中の場合は完了を待ってから残年度を順次実行する。
PC再起動後も同コマンドで再実行可能（--force付きのためスキップなし）。

使い方:
    python scripts/run_advance_regen_all.py
    python scripts/run_advance_regen_all.py --start-year 2021  # 途中から再開
    python scripts/run_advance_regen_all.py --workers 3
"""
import subprocess
import sys
import os
import time
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCRIPT = os.path.join(PROJECT_ROOT, 'scripts', 'prediction', 'generate_advance_fast_parallel.py')
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


def is_year_running(year, exclude_self=True):
    """指定年度のgenerate_advance_fast_parallelが実行中か確認

    exclude_self=True: 自分自身のプロセス（run_advance_regen_all）を除外
    """
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where',
             f'commandline like "%generate_advance_fast_parallel%--year {year}%"',
             'get', 'processid,commandline'],
            capture_output=True, text=True
        )
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            return False

        if exclude_self:
            # 自分自身（run_advance_regen_all）やWMIC自身を除外
            real_lines = []
            for line in lines[1:]:  # ヘッダー行をスキップ
                if 'run_advance_regen_all' in line:
                    continue
                if 'wmic' in line.lower():
                    continue
                if line.strip():
                    real_lines.append(line)
            return len(real_lines) > 0

        return len(lines) >= 2
    except Exception:
        return False


def wait_for_year(year, check_interval=30):
    """指定年度の処理が完了するまで待機"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {year}年の完了を待機中...", flush=True)
    while is_year_running(year):
        time.sleep(check_interval)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {year}年 完了確認", flush=True)


def run_year(year, workers):
    """指定年度のadvance予測を再生成"""
    print(f"\n{'='*60}", flush=True)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {year}年 開始 (workers={workers})", flush=True)
    print(f"{'='*60}", flush=True)

    cmd = [sys.executable, SCRIPT, '--year', str(year), '--force', '--workers', str(workers)]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {year}年 完了 OK", flush=True)
        return True
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {year}年 エラー（returncode={result.returncode}）NG", flush=True)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-year', type=int, default=2020, help='開始年度（デフォルト: 2020）')
    parser.add_argument('--workers', type=int, default=3, help='並列ワーカー数（デフォルト: 3）')
    args = parser.parse_args()

    target_years = [y for y in YEARS if y >= args.start_year]

    print(f"advance予測 全年度再生成スクリプト")
    print(f"対象年度: {target_years}")
    print(f"workers: {args.workers}")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # start-yearより前の年度が実行中なら、まず完了を待つ（DB競合回避）
    prior_years = [y for y in YEARS if y < args.start_year]
    for prior in prior_years:
        if is_year_running(prior):
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 先行年度 {prior}年が実行中 → 完了を待機してから開始", flush=True)
            wait_for_year(prior)
            print(f"  → {prior}年 完了確認", flush=True)

    failed = []

    for year in target_years:
        # すでに同じ年度が外部で実行中なら完了を待つ
        if is_year_running(year):
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {year}年は外部プロセスで実行中 → 完了待機", flush=True)
            wait_for_year(year)
            print(f"  → 外部プロセス完了。次の年度へ進む（今年度はスキップ）", flush=True)
            continue

        ok = run_year(year, args.workers)
        if not ok:
            failed.append(year)
            print(f"\n⚠️  {year}年が失敗。次の年度へ続行します。", flush=True)

    print(f"\n{'='*60}")
    print(f"全年度処理完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if failed:
        print(f"❌ 失敗年度: {failed}")
        print(f"   再実行: python scripts/run_advance_regen_all.py --start-year {min(failed)}")
    else:
        print(f"✅ 全年度成功")
        print(f"\n次のステップ:")
        print(f"  python scripts/backtest/standard_backtest_unique.py --full")


if __name__ == '__main__':
    main()
