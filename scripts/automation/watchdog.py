"""
BoatRaceScheduler ウォッチドッグ

スタートアップフォルダのVBSから起動され、5分ごとにスケジューラの生存確認を行う。
スケジューラが死んでいたら自動再起動する。

実行方法: python scripts/automation/watchdog.py
"""

import sys
import os
import time
import subprocess
import psutil
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
LOG_PATH = project_root / "logs" / f"watchdog_{datetime.now().strftime('%Y%m')}.log"
SCHEDULER_SCRIPT = project_root / "scripts" / "automation" / "daily_scheduler.py"
PYTHON_EXE = sys.executable
CHECK_INTERVAL = 300  # 5分


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def is_scheduler_running() -> bool:
    """daily_scheduler.py が動いているか確認"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' not in (proc.info['name'] or '').lower():
                continue
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'daily_scheduler.py' in cmdline:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def start_scheduler():
    """スケジューラを起動"""
    today = datetime.now().strftime('%Y%m%d')
    log_file = project_root / "logs" / f"scheduler_{today}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, 'a', encoding='utf-8') as lf:
        subprocess.Popen(
            [PYTHON_EXE, str(SCHEDULER_SCRIPT)],
            cwd=str(project_root),
            stdout=lf,
            stderr=lf,
            creationflags=0x00000008,  # DETACHED_PROCESS
        )
    log(f"スケジューラを起動しました → {log_file.name}")


def main():
    log("ウォッチドッグ起動")
    # 初回は少し待ってから確認（VBSと同時起動時の競合回避）
    time.sleep(30)

    while True:
        if is_scheduler_running():
            log("スケジューラ稼働中 (OK)")
        else:
            log("スケジューラ停止を検出 → 再起動します")
            start_scheduler()

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
