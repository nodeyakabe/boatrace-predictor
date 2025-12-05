"""
プロジェクトをZIPファイルにパッケージング
別のPCで作業できるようにDBとソースコードをまとめる
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import zipfile
import os
from datetime import datetime
from pathlib import Path

def create_zip_package():
    """プロジェクトとDBをZIPファイルにまとめる"""
    source_dir = Path(r"C:\Users\seizo\Desktop\BoatRace")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = source_dir.parent / f"BoatRace_package_{timestamp}.zip"

    print(f"ZIPパッケージ作成開始...")
    print(f"元: {source_dir}")
    print(f"先: {zip_path}")

    # 除外するディレクトリ
    exclude_dirs = {
        'venv', '__pycache__', '.git', 'node_modules',
        'rdmdb_tide_data', 'backups', '.claude'
    }

    # 除外するファイルパターン
    exclude_extensions = {'.pyc', '.pyo', '.pyd', '.so', '.dll', '.log', '.lzh'}
    exclude_files = {'nul', 'desktop.ini', '.DS_Store'}

    # 重要なファイル/フォルダ（必ず含める）
    important_patterns = {
        'src',           # ソースコード
        'scripts',       # スクリプト
        'config',        # 設定
        'data',          # データ（DBを含む）
        'ui',            # UI
        'docs',          # ドキュメント
        'tests',         # テスト
        'requirements.txt',
        'README.md',
        '*.py',          # ルートのPythonファイル
        '*.md',          # ドキュメント
        '*.bat',         # バッチファイル
        '*.txt',         # テキストファイル
    }

    try:
        file_count = 0
        total_size = 0

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            for root, dirs, files in os.walk(source_dir):
                # 除外ディレクトリをスキップ
                dirs[:] = [d for d in dirs if d not in exclude_dirs]

                rel_root = Path(root).relative_to(source_dir)

                for file in files:
                    # 除外ファイルチェック
                    if file in exclude_files:
                        continue

                    file_path = Path(root) / file

                    # 拡張子チェック
                    if file_path.suffix in exclude_extensions:
                        # ただし.dbファイルは含める
                        if file_path.suffix != '.db':
                            continue

                    # 特殊ファイルスキップ
                    if file == 'nul' or not file_path.exists():
                        continue

                    try:
                        # ファイルサイズ確認（大きすぎるファイルは警告）
                        file_size = file_path.stat().st_size

                        # DBファイルは大きくても含める、それ以外は1GB以上スキップ
                        if file_size > 1024 * 1024 * 1024 and not file.endswith('.db'):
                            print(f"  スキップ（大きすぎる）: {rel_root / file} ({file_size / (1024**3):.2f} GB)")
                            continue

                        # 受け渡しフォルダ内のDBはスキップ（古いバックアップ）
                        if '受け渡し' in str(rel_root) and file.endswith('.db'):
                            print(f"  スキップ（古いバックアップ）: {rel_root / file}")
                            continue

                        # ZIPに追加
                        arc_name = str(rel_root / file)
                        zipf.write(file_path, arc_name)

                        file_count += 1
                        total_size += file_size

                        # DBファイルは特別に表示
                        if file.endswith('.db') and file_size > 1024 * 1024:
                            print(f"  追加: {arc_name} ({file_size / (1024**2):.2f} MB)")

                    except Exception as e:
                        print(f"  警告: {file} をスキップ - {e}")
                        continue

        # 結果表示
        zip_size = zip_path.stat().st_size
        compression_ratio = (1 - zip_size / total_size) * 100 if total_size > 0 else 0

        print(f"\n=== ZIPパッケージ作成完了 ===")
        print(f"ファイル数: {file_count:,}")
        print(f"元サイズ: {total_size / (1024**2):.2f} MB")
        print(f"ZIPサイズ: {zip_size / (1024**2):.2f} MB")
        print(f"圧縮率: {compression_ratio:.1f}%")
        print(f"\n保存先: {zip_path}")
        print(f"\nこのZIPファイルを別のPCに転送し、解凍すれば作業を継続できます。")

        return str(zip_path)

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = create_zip_package()
    if result:
        print(f"\n成功: {result}")
    else:
        print("\n失敗")
