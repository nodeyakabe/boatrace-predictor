#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2021年・2023年データ一括補完スクリプト

2年分のデータを連続で自動収集する統合スクリプト
"""
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def log(message):
    """ログ出力（時刻付き）"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()

def run_collection(year: int, test_mode: bool = False):
    """
    指定年のデータ収集を実行

    Args:
        year: 対象年（2021 or 2023）
        test_mode: テストモード（1ヶ月のみ）
    """
    log(f"{'=' * 80}")
    log(f"{year}年データ収集開始（{'テストモード' if test_mode else '全月'}）")
    log(f"{'=' * 80}")

    script_path = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_欠損データ.py'

    if test_mode:
        # テストモード: 1月のみ
        cmd = [sys.executable, str(script_path), '--year', str(year), '--month', '1']
        log(f"実行コマンド: python {script_path.name} --year {year} --month 1")
    else:
        # 本番モード: 全月
        cmd = [sys.executable, str(script_path), '--year', str(year), '--all-months']
        log(f"実行コマンド: python {script_path.name} --year {year} --all-months")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=False,  # リアルタイム出力
            text=True,
            check=True
        )
        log(f"✅ {year}年データ収集完了")
        return True
    except subprocess.CalledProcessError as e:
        log(f"❌ {year}年データ収集失敗: {e}")
        return False
    except Exception as e:
        log(f"❌ 予期しないエラー: {e}")
        return False

def check_csv_output(year: int):
    """CSV出力を確認"""
    csv_dir = PROJECT_ROOT / 'data' / 'csv' / '補完' / str(year)

    if not csv_dir.exists():
        log(f"⚠️ CSVディレクトリが見つかりません: {csv_dir}")
        return False

    csv_files = list(csv_dir.glob('*.csv'))
    if not csv_files:
        log(f"⚠️ CSVファイルが見つかりません: {csv_dir}")
        return False

    log(f"✅ {year}年のCSVファイル: {len(csv_files)}個")

    # ファイルサイズを確認
    total_size = sum(f.stat().st_size for f in csv_files)
    log(f"   合計サイズ: {total_size / 1024 / 1024:.2f} MB")

    return True

def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='2021年・2023年データを一括補完',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  # テスト実行（各年1月のみ）
  python scripts/data_collection/補完_2021_2023_一括実行.py --test

  # 本番実行（全月）
  python scripts/data_collection/補完_2021_2023_一括実行.py

  # 2021年のみ
  python scripts/data_collection/補完_2021_2023_一括実行.py --year 2021

所要時間:
  テストモード: 約3-4時間（各年1月のみ）
  本番モード: 約60-80時間（2年×全月）
        '''
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='テストモード（各年1月のみ収集）'
    )
    parser.add_argument(
        '--year',
        type=int,
        choices=[2021, 2023],
        help='特定年のみ実行（指定なしで両年）'
    )

    args = parser.parse_args()

    start_time = datetime.now()
    log(f"データ補完スクリプト開始")
    log(f"モード: {'テスト' if args.test else '本番'}")
    log(f"対象年: {args.year if args.year else '2021, 2023'}")
    log("")

    # 対象年を決定
    if args.year:
        years = [args.year]
    else:
        years = [2021, 2023]

    # 収集実行
    success_count = 0
    for year in years:
        if run_collection(year, test_mode=args.test):
            success_count += 1
            log("")

            # CSV出力確認
            if check_csv_output(year):
                log(f"✅ {year}年のデータ収集・検証完了")
            else:
                log(f"⚠️ {year}年のCSV出力に問題がある可能性があります")
            log("")

    # 結果サマリー
    end_time = datetime.now()
    elapsed = end_time - start_time

    log(f"{'=' * 80}")
    log(f"データ補完完了")
    log(f"{'=' * 80}")
    log(f"成功: {success_count}/{len(years)}年")
    log(f"所要時間: {elapsed}")
    log("")

    if success_count == len(years):
        log("✅ 全ての年のデータ収集が完了しました")
        log("")
        log("次のステップ:")
        log("1. CSV検証:")
        log(f"   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months --dry-run")
        log(f"   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months --dry-run")
        log("")
        log("2. DB投入:")
        log(f"   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2021 --all-months")
        log(f"   python scripts/maintenance/投入_2021_2023_補完データ.py --year 2023 --all-months")
        return 0
    else:
        log("❌ 一部の年でエラーが発生しました")
        log("ログを確認してください")
        return 1

if __name__ == '__main__':
    sys.exit(main())
