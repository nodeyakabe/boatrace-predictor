"""
予測生成キュー管理スクリプト（TJ-3b 全年度再生成版 2026-02-27更新）
- 既存プロセスを含めて最大4並列を維持
- 完了次第キューの次タスクを起動
- 30秒ごとにポーリング
- 全予測完了後: 統計指標再生成 → 標準テスト → ログ保存
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
# TJ-3b: ST_SCORE_RANGES修正（2026-02-27）後の全年度予測再生成
# 優先度: 2024・2025 → 2023 → 2022 → 2021 → 2020
TASK_QUEUE = [
    # === 優先: 2024・2025年（TJ-3b効果確認用） ===
    ("generate_advance_fast.py", "2024", []),   # slot1: advance/before 同時起動
    ("generate_before_fast.py",  "2024", []),   # slot2
    ("generate_advance_fast.py", "2025", []),   # slot3
    ("generate_before_fast.py",  "2025", []),   # slot4
    # === 残年度（全年度展開） ===
    ("generate_advance_fast.py", "2023", []),
    ("generate_before_fast.py",  "2023", []),
    ("generate_advance_fast.py", "2022", []),
    ("generate_before_fast.py",  "2022", []),
    ("generate_advance_fast.py", "2021", []),
    ("generate_before_fast.py",  "2021", []),
    ("generate_advance_fast.py", "2020", []),
    ("generate_before_fast.py",  "2020", []),
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


def run_post_processing():
    """全予測再生成完了後の後処理（統計再生成 → 標準テスト）"""
    log("=" * 60)
    log("後処理開始: 統計指標再生成 → 標準テスト")
    log("=" * 60)

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # 1. 統計指標再生成（2024年・データ補完完了後のため必要）
    log("[1/2] 統計指標再生成 (build_indicator_stats.py --year 2024)")
    stats_log = os.path.join(log_dir, "build_indicator_stats_2024.log")
    with open(stats_log, "w", encoding="utf-8") as lf:
        lf.write(f"開始: {datetime.now()}\n")
    try:
        result = subprocess.run(
            [sys.executable, "scripts/data_collection/build_indicator_stats.py", "--year", "2024"],
            stdout=open(stats_log, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            timeout=3600  # 1時間タイムアウト
        )
        log(f"  完了 (rc={result.returncode}) → {stats_log}")
    except subprocess.TimeoutExpired:
        log(f"  タイムアウト（1時間超過）→ スキップ")
    except Exception as e:
        log(f"  エラー: {e} → スキップ")

    # 2. 標準テスト（6年間・TJ-3b効果測定）
    log("[2/2] 標準テスト (standard_backtest_unique.py --full)")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backtest_log = os.path.join(log_dir, f"backtest_tj3b_{ts}.log")
    with open(backtest_log, "w", encoding="utf-8") as lf:
        lf.write(f"TJ-3b ST_SCORE_RANGES 修正後バックテスト\n")
        lf.write(f"変更内容: 0.15-0.18: 0.8→0.9 / 0.18-0.20: 0.6→0.8 / 0.20+: 0.4→0.7\n")
        lf.write(f"ベースライン: 7,528件 / ROI 129.2% / +289,480円 / 5/6年黒字\n")
        lf.write(f"開始: {datetime.now()}\n")
        lf.write("=" * 60 + "\n\n")
    try:
        result = subprocess.run(
            [sys.executable, "scripts/backtest/standard_backtest_unique.py", "--full"],
            stdout=open(backtest_log, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            timeout=3600
        )
        log(f"  完了 (rc={result.returncode}) → {backtest_log}")
    except subprocess.TimeoutExpired:
        log(f"  タイムアウト（1時間超過）")
    except Exception as e:
        log(f"  エラー: {e}")

    log("=" * 60)
    log("後処理完了！帰ってきたら以下を確認してください:")
    log(f"  バックテスト結果: {backtest_log}")
    log(f"  ベースライン比較: ROI 129.2% / +289,480円 / 5/6年黒字")
    log("=" * 60)


def main():
    log("=" * 60)
    log("予測生成キュー管理スクリプト 開始（TJ-3b 全年度再生成）")
    log(f"最大並列数: {MAX_PARALLEL}")
    log(f"キュー: {len(TASK_QUEUE)}タスク")
    for s, y, _ in TASK_QUEUE:
        ptype = "before" if "before" in s else "advance"
        log(f"  - {ptype} {y}")
    log("完了後: 統計指標再生成 → 標準テスト自動実行")
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
    log("全予測タスク完了！後処理を開始します...")
    log("=" * 60)

    # 後処理: 統計再生成 → バックテスト
    run_post_processing()


if __name__ == "__main__":
    main()
