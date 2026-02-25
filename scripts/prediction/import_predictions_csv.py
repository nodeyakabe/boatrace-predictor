#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予測CSVをDBに投入するスタンドアロンユーティリティ

generate_advance_fast.py / generate_before_fast.py の --csv-only で生成した
CSVファイルを後からまとめてDBに投入する場合や、
手動でCSVを確認・修正した後に再投入する場合に使用する。

【使用例】
  # 単一ファイルを投入
  python scripts/prediction/import_predictions_csv.py \
      data/predictions_csv/advance/2024/2024-01-01.csv

  # ディレクトリ配下のCSVを一括投入
  python scripts/prediction/import_predictions_csv.py \
      --dir data/predictions_csv/advance/2024

  # 年度全体を投入
  python scripts/prediction/import_predictions_csv.py \
      --dir data/predictions_csv/advance/2024 \
      --dir data/predictions_csv/before/2024

  # ドライランで件数だけ確認
  python scripts/prediction/import_predictions_csv.py \
      --dir data/predictions_csv/advance/2024 --dry-run
"""
import sys
import os
import io
import csv
import argparse
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.database.data_manager import DataManager


def count_csv_rows(csv_path: str) -> int:
    """CSVの行数（ヘッダー除く）をカウント"""
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return -1


def collect_csv_files(paths: list) -> list:
    """
    引数のパスリストからCSVファイルを収集。
    ファイルならそのまま、ディレクトリなら配下の*.csvを再帰的に収集。
    """
    result = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == '.csv':
            result.append(path)
        elif path.is_dir():
            result.extend(sorted(path.rglob('*.csv')))
        else:
            print(f"[!] 対象外パス（スキップ）: {p}")
    return sorted(set(result))


def main():
    parser = argparse.ArgumentParser(
        description='予測CSVをDB（race_predictions）にUPSERT投入する',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('files', nargs='*', metavar='CSV_FILE',
                        help='投入するCSVファイル（複数指定可）')
    parser.add_argument('--dir', action='append', metavar='CSV_DIR', dest='dirs',
                        help='ディレクトリ配下のCSVを一括投入（複数指定可）')
    parser.add_argument('--dry-run', action='store_true',
                        help='実際のDB投入は行わず、件数の確認のみ')
    args = parser.parse_args()

    # 対象ファイルを収集
    all_paths = list(args.files or []) + list(args.dirs or [])
    if not all_paths:
        parser.print_help()
        sys.exit(1)

    csv_files = collect_csv_files(all_paths)

    if not csv_files:
        print("[!] CSVファイルが見つかりませんでした。")
        sys.exit(1)

    print("=" * 70)
    print("予測CSV → DB UPSERT投入")
    print("=" * 70)
    print(f"対象ファイル数: {len(csv_files)}件")
    if args.dry_run:
        print("モード: ドライラン（DB投入なし）")
    print()

    # ドライラン: 件数確認のみ
    if args.dry_run:
        total = 0
        for csv_path in csv_files:
            count = count_csv_rows(str(csv_path))
            status = f"{count:,}行" if count >= 0 else "読み込みエラー"
            print(f"  {csv_path.name}: {status}")
            if count > 0:
                total += count
        print()
        print(f"合計投入予定行数: {total:,}件")
        print("（--dry-run のため実際の投入は行いません）")
        return

    # 実投入
    data_manager = DataManager()
    start_time = datetime.now()
    total_rows = 0
    success_files = 0
    failed_files = []

    for csv_path in csv_files:
        count = data_manager.import_predictions_from_csv(str(csv_path))
        if count >= 0:
            total_rows += count
            success_files += 1
            print(f"  [OK] {csv_path.name}: {count:,}件")
        else:
            failed_files.append(str(csv_path))
            print(f"  [X]  {csv_path.name}: 失敗")

    elapsed = (datetime.now() - start_time).total_seconds()
    print()
    print("=" * 70)
    print("完了")
    print("=" * 70)
    print(f"成功ファイル: {success_files}件")
    print(f"失敗ファイル: {len(failed_files)}件")
    print(f"DB投入件数: {total_rows:,}件")
    print(f"所要時間: {elapsed:.1f}秒")
    if failed_files:
        print("\n失敗ファイル一覧:")
        for f in failed_files:
            print(f"  {f}")
    print("=" * 70)

    sys.exit(0 if not failed_files else 1)


if __name__ == '__main__':
    main()
