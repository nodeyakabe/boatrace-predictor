#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
順次実行版（完了月スキップ機能付き）

2021年9-12月 + 2023年1-12月を順次実行
既に完了している月は自動的にスキップ
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

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

def main():
    start_time = datetime.now()
    print(f"[{start_time.strftime('%H:%M:%S')}] データ収集開始")
    print(f"対象: 2021年9-12月 + 2023年1-12月（16ヶ月）")
    print()

    script = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_欠損データ.py'

    # 全タスク
    tasks = []
    for month in range(9, 13):
        tasks.append((2021, month))
    for month in range(1, 13):
        tasks.append((2023, month))

    # 進捗カウント
    total = len(tasks)
    completed_count = 0
    skipped_count = 0
    failed_count = 0

    # 2021年9-12月
    for month in range(9, 13):
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 2021年{month}月")

        # 完了チェック
        if check_month_completed(2021, month):
            print(f"[SKIP] 2021年{month}月は既に完了済み")
            print(f"{'='*60}")
            skipped_count += 1
            continue

        print(f"[START] 2021年{month}月 開始")
        print(f"{'='*60}")

        result = subprocess.call([
            sys.executable, str(script),
            '--year', '2021',
            '--month', str(month)
        ])

        if result != 0:
            print(f"\n[ERROR] 2021年{month}月でエラー発生（終了コード: {result}）")
            failed_count += 1
            # エラーでも継続
        else:
            print(f"\n[OK] 2021年{month}月 完了")
            completed_count += 1

    # 2023年1-12月
    for month in range(1, 13):
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 2023年{month}月")

        # 完了チェック
        if check_month_completed(2023, month):
            print(f"[SKIP] 2023年{month}月は既に完了済み")
            print(f"{'='*60}")
            skipped_count += 1
            continue

        print(f"[START] 2023年{month}月 開始")
        print(f"{'='*60}")

        result = subprocess.call([
            sys.executable, str(script),
            '--year', '2023',
            '--month', str(month)
        ])

        if result != 0:
            print(f"\n[ERROR] 2023年{month}月でエラー発生（終了コード: {result}）")
            failed_count += 1
            # エラーでも継続
        else:
            print(f"\n[OK] 2023年{month}月 完了")
            completed_count += 1

    # サマリー
    end_time = datetime.now()
    elapsed = end_time - start_time

    print(f"\n{'='*60}")
    print(f"[{end_time.strftime('%H:%M:%S')}] 全処理完了")
    print(f"{'='*60}")
    print(f"総タスク数: {total}ヶ月")
    print(f"新規完了: {completed_count}ヶ月")
    print(f"スキップ: {skipped_count}ヶ月（既に完了済み）")
    print(f"失敗: {failed_count}ヶ月")
    print(f"所要時間: {elapsed}")
    print()

    if failed_count > 0:
        print("[WARNING] 一部の月で処理に失敗しました")
        return 1
    else:
        print("[SUCCESS] 全ての月の処理が完了しました")
        return 0

if __name__ == '__main__':
    sys.exit(main())
