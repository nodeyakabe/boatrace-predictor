"""
daily_scheduler.py のスマートリカバリー

用途:
- ロックファイルの妥当性検証
- 孤児ロックファイルの削除
- スケジューラーの自動再起動（オプション）
"""

import os
import sys
import psutil
from pathlib import Path
from datetime import datetime
import subprocess

project_root = Path(__file__).parent.parent.parent
lock_file = project_root / "data" / "daily_scheduler.lock"

def check_lock_status():
    """ロックファイルの状態を確認"""
    if not lock_file.exists():
        return {"status": "no_lock", "message": "ロックファイルなし"}

    try:
        with open(lock_file, 'r') as f:
            pid = int(f.read().strip())
    except (ValueError, FileNotFoundError) as e:
        return {"status": "corrupted", "message": f"ロックファイル破損: {e}", "pid": None}

    # プロセス存在確認
    if not psutil.pid_exists(pid):
        return {"status": "orphan", "message": f"プロセス終了済み（PID: {pid}）", "pid": pid}

    # プロセス詳細確認
    try:
        proc = psutil.Process(pid)
        cmdline = ' '.join(proc.cmdline())

        if 'daily_scheduler.py' in cmdline:
            create_time = datetime.fromtimestamp(proc.create_time())
            return {
                "status": "running",
                "message": f"daily_scheduler.py 実行中（PID: {pid}）",
                "pid": pid,
                "create_time": create_time
            }
        else:
            return {
                "status": "different_process",
                "message": f"PID {pid} は別プロセス: {cmdline[:100]}",
                "pid": pid
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {"status": "orphan", "message": f"プロセス情報取得不可（PID: {pid}）", "pid": pid}

def remove_lock():
    """ロックファイルを削除"""
    try:
        lock_file.unlink()
        return True
    except Exception as e:
        print(f"[ERROR] ロックファイル削除失敗: {e}")
        return False

def restart_scheduler():
    """スケジューラーを起動"""
    scheduler_path = project_root / "scripts" / "automation" / "daily_scheduler.py"
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"scheduler_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    try:
        # バックグラウンドで起動（detach）
        if sys.platform == 'win32':
            # Windows: CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS
            with open(log_file, 'w') as f:
                subprocess.Popen(
                    [sys.executable, str(scheduler_path)],
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                    stdout=f,
                    stderr=subprocess.STDOUT
                )
        else:
            # Unix: nohup相当
            with open(log_file, 'w') as f:
                subprocess.Popen(
                    [sys.executable, str(scheduler_path)],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )

        print(f"[INFO] ログファイル: {log_file}")
        return True
    except Exception as e:
        print(f"[ERROR] スケジューラー起動失敗: {e}")
        return False

def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description="daily_scheduler.py リカバリースクリプト")
    parser.add_argument('--check', action='store_true', help="ロック状態の確認のみ")
    parser.add_argument('--force-remove', action='store_true', help="ロックファイルを強制削除")
    parser.add_argument('--restart', action='store_true', help="孤児ロック削除後に自動再起動")

    args = parser.parse_args()

    # ロック状態確認
    status = check_lock_status()

    print("=" * 60)
    print("daily_scheduler.py リカバリーツール")
    print("=" * 60)
    print(f"ステータス: {status['status']}")
    print(f"メッセージ: {status['message']}")

    if status.get('create_time'):
        print(f"起動時刻: {status['create_time']}")

    print()

    # --check オプション（確認のみ）
    if args.check:
        return 0

    # running状態の処理
    if status['status'] == 'running':
        print("[INFO] スケジューラーは正常稼働中です")
        return 0

    # 孤児ロックファイルまたは破損の処理
    if status['status'] in ['orphan', 'corrupted', 'different_process'] or args.force_remove:
        print("[ACTION] ロックファイルを削除します...")

        if remove_lock():
            print("[OK] ロックファイル削除完了")

            # --restart オプション
            if args.restart:
                print("\n[ACTION] スケジューラーを再起動します...")
                import time
                time.sleep(1)  # ロック削除後の待機

                if restart_scheduler():
                    print("[OK] スケジューラー起動完了")
                    print("\n動作確認:")
                    print("  python scripts/automation/recover_scheduler.py --check")
                    return 0
                else:
                    print("[ERROR] スケジューラー起動失敗")
                    return 1
        else:
            return 1

    # ロックファイルなし
    if status['status'] == 'no_lock':
        if args.restart:
            print("[ACTION] スケジューラーを起動します...")
            if restart_scheduler():
                print("[OK] スケジューラー起動完了")
                return 0
            else:
                print("[ERROR] スケジューラー起動失敗")
                return 1
        else:
            print("[INFO] ロックファイルなし。起動可能な状態です")
            print("\nスケジューラーを起動する場合:")
            print("  python scripts/automation/daily_scheduler.py")
            print("または:")
            print("  python scripts/automation/recover_scheduler.py --restart")

    return 0

if __name__ == "__main__":
    sys.exit(main())
