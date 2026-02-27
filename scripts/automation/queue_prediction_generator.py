"""
予測生成キュー管理スクリプト
- 既存プロセスを含めて最大4並列を維持
- 完了次第キューの次タスクを起動
- 30秒ごとにポーリング
"""
import subprocess
import time
import sys
import os
import io
from datetime import datetime

# Windowsのコンソールエンコード問題を回避（ファイルリダイレクト時もUTF-8で出力）
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# キュー（実行順）
TASK_QUEUE = [
    # advance 2025: 前半(1-11月)と後半(12月)に分割して並列処理
    ("generate_advance_fast.py", "2025", ["--end-date",   "2025-11-30"]),  # slot1: 即起動
    ("generate_advance_fast.py", "2025", ["--start-date", "2025-12-01"]),  # slot2: 即起動
    # before 2024: 12月分を先行生成（before 2021完了後のスロットで起動）
    ("generate_before_fast.py",  "2024", ["--start-date", "2024-12-01"]),  # slot3: 空き次第
]

MAX_PARALLEL = 4
POLL_INTERVAL = 30  # 秒

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)

def get_running_prediction_processes():
    """現在実行中の予測生成プロセス一覧を返す (PID, year, type)"""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "CommandLine,ProcessId"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        procs = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if "generate_before_fast.py" in line or "generate_advance_fast.py" in line:
                # PIDは行末の数値
                parts = line.rsplit(None, 1)
                pid = int(parts[-1]) if len(parts) > 1 and parts[-1].isdigit() else None
                ptype = "before" if "generate_before_fast" in line else "advance"
                # --year の次の引数を取得
                tokens = line.split()
                year = None
                for i, tok in enumerate(tokens):
                    if tok == "--year" and i + 1 < len(tokens):
                        year = tokens[i + 1]
                        break
                procs.append({"pid": pid, "type": ptype, "year": year})
        return procs
    except Exception as e:
        log(f"プロセス確認エラー: {e}")
        return []

def start_task(script, year, extra_args):
    """タスクをバックグラウンドで起動し、Popenオブジェクトを返す"""
    script_path = os.path.join("scripts", "prediction", script)
    cmd = [sys.executable, script_path, "--year", year] + extra_args

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    ptype = "before" if "before" in script else "advance"
    log_file = os.path.join(log_dir, f"gen_{ptype}_{year}.log")

    log(f"起動: {' '.join(cmd)}  → ログ: {log_file}")
    with open(log_file, "a", encoding="utf-8") as lf:
        lf.write(f"\n{'='*60}\n{datetime.now()} 開始\n{'='*60}\n")

    proc = subprocess.Popen(
        cmd,
        stdout=open(log_file, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    return proc

def main():
    log("=" * 60)
    log("予測生成キュー管理スクリプト 開始")
    log(f"最大並列数: {MAX_PARALLEL}")
    log(f"キュー: {len(TASK_QUEUE)}タスク")
    for s, y, _ in TASK_QUEUE:
        ptype = "before" if "before" in s else "advance"
        log(f"  - {ptype} {y}")
    log("=" * 60)

    queue = list(TASK_QUEUE)
    # このスクリプトが起動したプロセス: pid -> Popen
    my_procs = {}

    # 現在の状況を表示
    existing = get_running_prediction_processes()
    log(f"既存の実行中プロセス: {len(existing)}件")
    for p in existing:
        log(f"  - {p['type']} {p['year']} (PID={p['pid']})")

    while queue or existing or my_procs:
        # 全体の実行中数を確認
        existing = get_running_prediction_processes()
        total_running = len(existing)

        # このスクリプトが起動したプロセスの完了チェック
        finished = [pid for pid, proc in my_procs.items() if proc.poll() is not None]
        for pid in finished:
            proc = my_procs.pop(pid)
            rc = proc.returncode
            status = "[完了]" if rc == 0 else f"[失敗 rc={rc}]"
            log(f"{status}: PID={pid}")

        # スロットが空いていてキューがあれば起動
        slots_available = MAX_PARALLEL - total_running
        started = 0
        while slots_available > 0 and queue:
            script, year, extra = queue.pop(0)
            proc = start_task(script, year, extra)
            my_procs[proc.pid] = proc
            slots_available -= 1
            started += 1

        # ステータス表示
        existing = get_running_prediction_processes()
        if existing:
            summary = ", ".join(f"{p['type']}:{p['year']}" for p in existing)
            log(f"実行中({len(existing)}/{MAX_PARALLEL}): {summary} | キュー残:{len(queue)}")
        elif queue:
            log(f"実行中なし | キュー残:{len(queue)}")

        # 終了判定
        if not queue and not existing:
            break

        time.sleep(POLL_INTERVAL)

    log("=" * 60)
    log("全タスク完了！")
    log("=" * 60)

if __name__ == "__main__":
    main()
