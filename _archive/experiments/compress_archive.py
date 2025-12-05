#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
アーカイブフォルダを圧縮して容量削減

使用方法:
  python compress_archive.py --dry-run  # 圧縮後のサイズを推定
  python compress_archive.py --execute  # 実際に圧縮して元ファイル削除
"""
import os
import shutil
import argparse
from pathlib import Path
from datetime import datetime

def get_folder_size(folder_path):
    """フォルダサイズを取得（MB単位）"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return total_size / (1024 * 1024)  # MB

def main():
    parser = argparse.ArgumentParser(description='アーカイブフォルダ圧縮')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='圧縮後のサイズを推定（実際には圧縮しない）')
    group.add_argument('--execute', action='store_true', help='実際に圧縮を実行')

    args = parser.parse_args()

    archive_dir = Path('archive')

    if not archive_dir.exists():
        print("[エラー] archive/ フォルダが存在しません")
        return

    print("=" * 80)
    print("アーカイブフォルダ圧縮")
    print("=" * 80)

    # 現在のサイズ確認
    scripts_size = get_folder_size('archive/scripts_old') if Path('archive/scripts_old').exists() else 0
    docs_size = get_folder_size('archive/docs_old') if Path('archive/docs_old').exists() else 0
    total_size = scripts_size + docs_size

    print(f"\n【圧縮前のサイズ】")
    print(f"  archive/scripts_old/: {scripts_size:.2f} MB")
    print(f"  archive/docs_old/: {docs_size:.2f} MB")
    print(f"  合計: {total_size:.2f} MB")

    if args.dry_run:
        # ZIP圧縮率を20-30%と仮定
        estimated_size = total_size * 0.25  # 25%に圧縮と仮定
        print(f"\n【圧縮後の推定サイズ】")
        print(f"  archive_20251118.zip: {estimated_size:.2f} MB")
        print(f"  削減量: {total_size - estimated_size:.2f} MB ({(1 - estimated_size/total_size)*100:.1f}%削減)")
        print(f"\n[DRY RUN] 実際には圧縮していません")
        print(f"実行する場合は: python compress_archive.py --execute")

    else:
        # 実際に圧縮
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_name = f'archive_{timestamp}'

        print(f"\n圧縮中...")
        shutil.make_archive(zip_name, 'zip', 'archive')

        zip_path = Path(f'{zip_name}.zip')
        zip_size = zip_path.stat().st_size / (1024 * 1024)  # MB

        print(f"\n【圧縮完了】")
        print(f"  作成ファイル: {zip_name}.zip")
        print(f"  圧縮後のサイズ: {zip_size:.2f} MB")
        print(f"  削減量: {total_size - zip_size:.2f} MB ({(1 - zip_size/total_size)*100:.1f}%削減)")

        # 元のフォルダを自動削除（容量削減のため）
        print(f"\n元のarchive/フォルダを削除します（{total_size:.2f} MB削減）")
        shutil.rmtree('archive')
        print(f"\n[完了] archive/フォルダを削除しました")
        print(f"復元する場合は: unzip {zip_name}.zip")

if __name__ == "__main__":
    main()
