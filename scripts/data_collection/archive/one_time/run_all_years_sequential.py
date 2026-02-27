#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全年度オッズ収集自動実行スクリプト

2023年は完了済みとして、残りの年度を順次実行します。
"""
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent.parent.parent
os.chdir(PROJECT_ROOT)

# 収集対象年度（2023年は完了済みなので除外）
YEARS = [
    {"year": 2024, "races": 25434, "hours": 6.8, "status": "running"},  # 実行中
    {"year": 2022, "races": 20976, "hours": 5.6, "status": "pending"},
    {"year": 2020, "races": 19068, "hours": 5.1, "status": "pending"},
    {"year": 2021, "races": 12323, "hours": 3.3, "status": "pending"},
    {"year": 2025, "races": 3959, "hours": 1.1, "status": "pending"},
    {"year": 2026, "races": 551, "hours": 0.1, "status": "pending"},
]

def run_year_collection(year_info):
    """指定年度のオッズ収集を実行"""
    year = year_info["year"]

    print("=" * 80)
    print(f"{year}年のオッズ収集開始")
    print(f"  対象レース: {year_info['races']:,}件")
    print(f"  推定時間: {year_info['hours']}時間")
    print(f"  開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    cmd = [
        sys.executable,
        "scripts/data_collection/fetch_odds_to_csv_parallel.py",
        "--start-date", f"{year}-01-01",
        "--end-date", f"{year}-12-31",
        "--output", f"data/csv/odds/{year}",
        "--delay", "0.3",
        "--workers", "10",
        "--progress-interval", "200"
    ]

    try:
        result = subprocess.run(cmd, check=True)
        print()
        print("=" * 80)
        print(f"[OK] {year}年の収集完了")
        print(f"  完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()
        return True
    except subprocess.CalledProcessError as e:
        print()
        print("=" * 80)
        print(f"[ERROR] {year}年の収集失敗")
        print(f"  エラーコード: {e.returncode}")
        print("=" * 80)
        print()
        return False
    except KeyboardInterrupt:
        print()
        print("=" * 80)
        print("⚠️ ユーザーによる中断")
        print("=" * 80)
        print()
        raise

def main():
    print("=" * 80)
    print("全年度オッズ自動収集（CSV方式）")
    print("=" * 80)
    print()
    print("実行予定:")
    for info in YEARS:
        status_icon = "[実行中]" if info["status"] == "running" else "[待機中]"
        print(f"  {status_icon} {info['year']}年: {info['races']:,}レース（約{info['hours']}時間）")
    print()

    total_hours = sum(info["hours"] for info in YEARS)
    print(f"合計推定時間: 約{total_hours}時間")
    print()
    print("=" * 80)
    print()

    # 2024年が実行中の可能性があるので、スキップするか確認
    print("注意: 2024年が既に実行中の場合はスキップします")
    print()

    completed = []
    failed = []

    try:
        for year_info in YEARS:
            year = year_info["year"]

            # 2024年は既に実行中なので、完了を待つメッセージを表示してスキップ
            if year == 2024:
                print(f"[SKIP] {year}年: 既に実行中のためスキップ（別プロセスで実行中）")
                print()
                continue

            # 収集実行
            success = run_year_collection(year_info)

            if success:
                completed.append(year)
            else:
                failed.append(year)
                print(f"[WARNING] {year}年で失敗しましたが、次の年度に進みます")
                print()

    except KeyboardInterrupt:
        print("\n中断されました")

    finally:
        # 最終レポート
        print()
        print("=" * 80)
        print("全年度収集完了レポート")
        print("=" * 80)
        print()
        print(f"[OK] 完了: {len(completed)}年度")
        for year in completed:
            print(f"     {year}年")

        if failed:
            print()
            print(f"[ERROR] 失敗: {len(failed)}年度")
            for year in failed:
                print(f"     {year}年")

        print()
        print("=" * 80)
        print()
        print("【次の作業】")
        print("  全年度のCSV収集完了後、以下のコマンドでDBに投入してください:")
        print("  python scripts/data_collection/import_odds_csv_to_db.py --input data/csv/odds")
        print()
        print("=" * 80)

if __name__ == "__main__":
    main()
