"""
BoatRaceプロジェクトのバックアップ作成
別端末で作業できるよう必要なファイルをZIP化
"""

import os
import zipfile
import shutil
from datetime import datetime

def create_backup():
    # バックアップ名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f'BoatRace_backup_{timestamp}.zip'
    
    print("="*80)
    print("BoatRace Project Backup")
    print("="*80)
    print(f"\nBackup file: {zip_name}")
    print(f"Timestamp: {timestamp}\n")
    
    # 含めるファイル・フォルダ
    include_items = {
        # ソースコード
        'src/': 'Source code',
        'config/': 'Configuration files',
        
        # スクリプト
        'fetch_improved_v3.py': 'V3 collection script',
        'test_improved_v3.py': 'V3 test script',
        'verify_v3_data.py': 'V3 verification script',
        'count_missing.py': 'Missing data counter',
        'check_pit3_pattern.py': 'Pit3 pattern checker',
        'SUMMARY_V3_FIX.md': 'V3 fix summary',
        
        # 設定・ドキュメント
        'requirements.txt': 'Python dependencies',
        'README.md': 'Project README',
    }
    
    # データベース（別途コピー）
    db_files = [
        'data/boatrace.db',
        'data/boatrace.db-shm',
        'data/boatrace.db-wal',
    ]
    
    # 除外パターン
    exclude_patterns = ['__pycache__', '.pyc', '.git', 'venv', '.venv', '.log']
    
    def should_exclude(path):
        return any(pattern in path for pattern in exclude_patterns)
    
    # ZIPファイル作成
    total_files = 0
    total_size = 0
    
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 通常ファイルを追加
        for item, desc in include_items.items():
            if os.path.isfile(item):
                size = os.path.getsize(item)
                zipf.write(item)
                print(f"[FILE] {item:<40} {size:>15,} bytes - {desc}")
                total_files += 1
                total_size += size
            elif os.path.isdir(item):
                for root, dirs, files in os.walk(item):
                    dirs[:] = [d for d in dirs if not should_exclude(d)]
                    
                    for file in files:
                        file_path = os.path.join(root, file)
                        if not should_exclude(file_path):
                            size = os.path.getsize(file_path)
                            zipf.write(file_path)
                            total_files += 1
                            total_size += size
                
                print(f"[DIR]  {item:<40} - {desc}")
            else:
                print(f"[SKIP] {item:<40} - Not found")
        
        # データベースファイルを追加（存在する場合）
        print("\n" + "-"*80)
        print("Database files:")
        print("-"*80)
        
        for db_file in db_files:
            if os.path.isfile(db_file):
                try:
                    size = os.path.getsize(db_file)
                    zipf.write(db_file)
                    print(f"[DB]   {db_file:<40} {size:>15,} bytes")
                    total_files += 1
                    total_size += size
                except Exception as e:
                    print(f"[ERROR] {db_file}: {e}")
            else:
                print(f"[SKIP] {db_file:<40} - Not found")
    
    # サマリー
    zip_size = os.path.getsize(zip_name)
    compression = (1 - zip_size/total_size)*100 if total_size > 0 else 0
    
    print("\n" + "="*80)
    print("Backup Summary")
    print("="*80)
    print(f"Total files:       {total_files}")
    print(f"Total size:        {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
    print(f"ZIP size:          {zip_size:,} bytes ({zip_size/1024/1024:.2f} MB)")
    print(f"Compression ratio: {compression:.1f}%")
    print(f"\n[SUCCESS] Backup created: {zip_name}")
    print("="*80)
    
    # 別端末での使用方法を表示
    print("\n" + "="*80)
    print("How to use on another PC:")
    print("="*80)
    print(f"1. Copy {zip_name} to the new PC")
    print("2. Extract the ZIP file:")
    print("   unzip BoatRace_backup_*.zip -d BoatRace")
    print("3. Install dependencies:")
    print("   cd BoatRace")
    print("   pip install -r requirements.txt")
    print("4. Continue V3 collection:")
    print("   python fetch_improved_v3.py --fill-missing --workers 5")
    print("="*80)

if __name__ == '__main__':
    create_backup()
