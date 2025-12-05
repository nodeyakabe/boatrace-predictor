"""
プロジェクト整理スクリプト

不要なファイルとディレクトリを削除し、プロジェクトをクリーンアップ
"""

import os
import shutil
from pathlib import Path


def get_size_mb(path):
    """ファイルまたはディレクトリのサイズをMBで取得"""
    if os.path.isfile(path):
        return os.path.getsize(path) / (1024 * 1024)
    elif os.path.isdir(path):
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total += os.path.getsize(filepath)
                except:
                    pass
        return total / (1024 * 1024)
    return 0


def cleanup_project():
    """プロジェクトをクリーンアップ"""

    print("=" * 70)
    print("BoatRaceプロジェクト クリーンアップ")
    print("=" * 70)

    total_deleted_size = 0
    deleted_count = 0

    # フェーズ1: 大きなバックアップファイルとテストデータの削除
    print("\n【フェーズ1】バックアップファイルとテストデータの削除")

    files_to_delete = [
        'BoatRace_backup_20251109_205755.zip',
        'BoatRace_backup_20251109_205946.zip',
        'BoatRace_Transfer_Package.zip',
        'v6_output.log',
        'v5_fixed_output.log',
        'v5_output.log',
        'v4_output.log',
        'v3_output.log',
        'fetch_v3_log.txt',
        'test_backtest_report.txt'
    ]

    for filename in files_to_delete:
        if os.path.exists(filename):
            size = get_size_mb(filename)
            os.remove(filename)
            print(f"  [削除] {filename} ({size:.2f} MB)")
            total_deleted_size += size
            deleted_count += 1

    # ディレクトリの削除
    dirs_to_delete = [
        'rdmdb_tide_data_test',
        'rdmdb_downloads',
        'rdmdb_test_debug',
        'rdmdb_test_single',
        'backup',
        'test_prediction_report'
    ]

    for dirname in dirs_to_delete:
        if os.path.exists(dirname):
            size = get_size_mb(dirname)
            shutil.rmtree(dirname)
            print(f"  [削除] {dirname}/ ({size:.2f} MB)")
            total_deleted_size += size
            deleted_count += 1

    # フェーズ2: デバッグファイルとHTMLファイルの削除
    print("\n【フェーズ2】デバッグファイルとHTMLの削除")

    debug_patterns = [
        'debug_*.py',
        'debug_*.txt',
        'debug_*.html',
        'beforeinfo_*.html',
        'raceresult_*.html',
        'test_scraper_*.html'
    ]

    for pattern in debug_patterns:
        for file in Path('.').glob(pattern):
            if file.is_file():
                size = get_size_mb(str(file))
                file.unlink()
                print(f"  [削除] {file} ({size:.3f} MB)")
                total_deleted_size += size
                deleted_count += 1

    # フェーズ3: 旧バージョンテストスクリプトの削除
    print("\n【フェーズ3】旧バージョンテストスクリプトの削除")

    old_test_files = [
        'test_improved_v2.py',
        'test_improved_v3.py',
        'test_v3_multiple.py',
        'test_st_time_補充.py',
        'check_db_status_progress.py',
        'check_db_status_quick.py'
    ]

    for filename in old_test_files:
        if os.path.exists(filename):
            size = get_size_mb(filename)
            os.remove(filename)
            print(f"  [削除] {filename} ({size:.3f} MB)")
            total_deleted_size += size
            deleted_count += 1

    # フェーズ4: __pycache__ ディレクトリの削除
    print("\n【フェーズ4】__pycache__ディレクトリの削除")

    for pycache in Path('.').rglob('__pycache__'):
        if pycache.is_dir():
            size = get_size_mb(str(pycache))
            shutil.rmtree(pycache)
            print(f"  [削除] {pycache} ({size:.3f} MB)")
            total_deleted_size += size
            deleted_count += 1

    # フェーズ5: .pyc ファイルの削除
    print("\n【フェーズ5】.pycファイルの削除")

    for pyc in Path('.').rglob('*.pyc'):
        if pyc.is_file():
            pyc.unlink()
            deleted_count += 1

    # サマリー
    print("\n" + "=" * 70)
    print("クリーンアップ完了")
    print("=" * 70)
    print(f"削除ファイル数: {deleted_count}個")
    print(f"削減サイズ: {total_deleted_size:.2f} MB")
    print("=" * 70)


if __name__ == "__main__":
    # 確認
    print("このスクリプトはプロジェクト内の不要なファイルを削除します。")
    print("続行しますか? (y/n): ", end="")

    # 自動実行の場合はコメントアウト
    # response = input().lower()
    # if response != 'y':
    #     print("キャンセルしました。")
    #     exit(0)

    # 自動実行
    cleanup_project()
