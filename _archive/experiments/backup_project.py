"""
プロジェクトバックアップスクリプト
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import shutil
import os
from datetime import datetime

def backup_project():
    """プロジェクト全体をバックアップ"""
    source = r"C:\Users\seizo\Desktop\BoatRace"
    timestamp = datetime.now().strftime("%Y%m%d")
    dest = rf"C:\Users\seizo\Desktop\BoatRace_backup_{timestamp}"

    print(f"バックアップ開始...")
    print(f"元: {source}")
    print(f"先: {dest}")

    # 除外するディレクトリとファイル
    exclude_dirs = {'venv', '__pycache__', '.git', 'node_modules', 'rdmdb_tide_data'}
    exclude_files = {'.pyc', '.pyo', '.pyd', '.so', '.dll', 'nul'}

    def ignore_patterns(dir, files):
        """除外パターン"""
        ignore = []
        for file in files:
            # 特殊ファイルの除外
            if file in exclude_files or file == 'nul':
                ignore.append(file)
                continue
            # ディレクトリの除外
            if file in exclude_dirs:
                ignore.append(file)
                continue
            # 拡張子の除外
            if any(file.endswith(ext) for ext in exclude_files):
                ignore.append(file)
        return ignore

    try:
        # バックアップ実行
        shutil.copytree(
            source,
            dest,
            ignore=ignore_patterns,
            dirs_exist_ok=False
        )
        print(f"\nバックアップ完了: {dest}")

        # バックアップサイズ確認
        total_size = 0
        total_files = 0
        for dirpath, dirnames, filenames in os.walk(dest):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                    total_files += 1
                except:
                    pass

        print(f"バックアップサイズ: {total_size / (1024**2):.2f} MB")
        print(f"ファイル数: {total_files:,}")

    except Exception as e:
        print(f"バックアップ失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    backup_project()
