import sqlite3
import shutil
import os
from datetime import datetime
import sys

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_and_fix_database():
    """データベースの整合性チェックと修復"""
    db_path = r"C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\boatrace.db"

    print("=" * 80)
    print("データベース整合性チェック")
    print("=" * 80)

    # まず接続テスト
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 整合性チェック
        print("\n整合性チェック実行中...")
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()

        if result[0] == 'ok':
            print("✅ データベースは正常です")

            # 簡単なクエリテスト
            cursor.execute("SELECT COUNT(*) FROM races WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'")
            count = cursor.fetchone()[0]
            print(f"✅ 2024年レース数: {count:,}")

            conn.close()
            return True
        else:
            print(f"⚠️ 整合性チェック結果: {result[0]}")
            conn.close()

    except sqlite3.DatabaseError as e:
        print(f"🔴 データベースエラー: {e}")

        # バックアップから復元を試みる
        print("\n" + "=" * 80)
        print("バックアップから復元を試みます")
        print("=" * 80)

        # 最新のバックアップを探す
        backup_dir = r"C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data\backups"
        if os.path.exists(backup_dir):
            backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
            if backups:
                backups.sort(reverse=True)  # 最新順
                latest_backup = backups[0]
                backup_path = os.path.join(backup_dir, latest_backup)

                print(f"\n最新のバックアップ: {latest_backup}")
                print(f"サイズ: {os.path.getsize(backup_path) / (1024*1024):.2f} MB")

                # 現在のDBを一時退避
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                damaged_path = db_path.replace(".db", f"_damaged_{timestamp}.db")
                shutil.move(db_path, damaged_path)
                print(f"\n破損DBを退避: {damaged_path}")

                # バックアップから復元
                shutil.copy2(backup_path, db_path)
                print(f"✅ バックアップから復元完了: {backup_path}")

                # 復元後のチェック
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check")
                    result = cursor.fetchone()

                    if result[0] == 'ok':
                        print("✅ 復元されたDBは正常です")

                        cursor.execute("SELECT COUNT(*) FROM races WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'")
                        count = cursor.fetchone()[0]
                        print(f"✅ 2024年レース数: {count:,}")

                        conn.close()
                        return True
                    else:
                        print(f"⚠️ 復元後も問題あり: {result[0]}")
                        conn.close()
                        return False

                except Exception as e2:
                    print(f"🔴 復元後もエラー: {e2}")
                    return False
            else:
                print("🔴 バックアップファイルが見つかりません")
                return False
        else:
            print("🔴 バックアップディレクトリが存在しません")
            return False

    except Exception as e:
        print(f"🔴 予期しないエラー: {e}")
        return False

if __name__ == "__main__":
    success = check_and_fix_database()

    if success:
        print("\n" + "=" * 80)
        print("✅ データベースは使用可能です")
        print("=" * 80)
        print("\n次のステップ:")
        print("python check_2024_data_readiness.py")
    else:
        print("\n" + "=" * 80)
        print("🔴 データベースの修復に失敗しました")
        print("=" * 80)
        print("\nデスクトップの最新バックアップを確認してください:")
        print("C:\\Users\\User\\Desktop\\boatrace_backup_20251216_104054.db")
