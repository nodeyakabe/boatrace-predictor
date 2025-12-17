import shutil
import os
from datetime import datetime
import sys

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def create_backup():
    """データベースのバックアップを作成"""
    current_db = r"C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"
    backup_dir = r"C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\backups"

    if not os.path.exists(current_db):
        print(f"エラー: DBが見つかりません: {current_db}")
        return None

    # バックアップディレクトリを作成
    os.makedirs(backup_dir, exist_ok=True)

    # バックアップファイル名（タイムスタンプ付き）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"boatrace_backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    # ファイルサイズ取得
    file_size = os.path.getsize(current_db)
    file_size_mb = file_size / (1024 * 1024)

    print("=" * 80)
    print("データベースバックアップ作成")
    print("=" * 80)
    print(f"\n元のDB: {current_db}")
    print(f"ファイルサイズ: {file_size_mb:.2f} MB")
    print(f"\nバックアップ先: {backup_path}")
    print("\nコピー中...")

    # バックアップ作成
    shutil.copy2(current_db, backup_path)

    # 確認
    if os.path.exists(backup_path):
        backup_size = os.path.getsize(backup_path)
        backup_size_mb = backup_size / (1024 * 1024)
        print(f"\n✓ バックアップ完了")
        print(f"  バックアップサイズ: {backup_size_mb:.2f} MB")
        print(f"  保存場所: {backup_path}")

        # デスクトップにもコピー
        desktop_backup = os.path.join(r"C:\Users\User\Desktop", backup_filename)
        shutil.copy2(current_db, desktop_backup)
        print(f"\n✓ デスクトップにもコピーしました")
        print(f"  {desktop_backup}")

        return backup_path
    else:
        print("\n✗ バックアップ失敗")
        return None

if __name__ == "__main__":
    create_backup()
