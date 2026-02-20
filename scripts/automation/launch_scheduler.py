"""
スケジューラーをWindowsターミナル独立プロセスとして起動するランチャー。

DETACHED_PROCESS フラグを使い、どのターミナルが閉じても死なないプロセスとして起動する。
ログは logs/scheduler_startup.log に記録される。
"""
import sys
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def main():
    log_path = PROJECT_ROOT / "logs" / "scheduler_startup.log"
    err_path = PROJECT_ROOT / "logs" / "scheduler_startup_err.log"
    scheduler_script = PROJECT_ROOT / "scripts" / "automation" / "daily_scheduler.py"
    lock_path = PROJECT_ROOT / "data" / "daily_scheduler.lock"

    # 既存ロックファイルの確認
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text().strip())
            import psutil
            if psutil.pid_exists(old_pid):
                proc = psutil.Process(old_pid)
                if 'daily_scheduler' in ' '.join(proc.cmdline()):
                    print(f"スケジューラーは既に起動中です (PID: {old_pid})")
                    return 1
        except Exception:
            pass
        lock_path.unlink(missing_ok=True)

    # Windows DETACHED_PROCESS フラグで完全独立起動
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000

    with open(log_path, 'a', encoding='utf-8') as stdout_f, \
         open(err_path, 'a', encoding='utf-8') as stderr_f:

        proc = subprocess.Popen(
            [sys.executable, str(scheduler_script)],
            stdout=stdout_f,
            stderr=stderr_f,
            cwd=str(PROJECT_ROOT),
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
        )

    print(f"スケジューラーを起動しました (PID: {proc.pid})")
    print(f"ログ: {log_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
