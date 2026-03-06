"""
2025年 全月 brute-force収集 → DBインポート
Claudeのセッションと独立して動作（start コマンドで起動）
"""
import subprocess, sys, os, time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
LOG  = ROOT / "logs" / f"2025_brute_force_main_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG.parent.mkdir(exist_ok=True)

FETCH  = str(ROOT / "scripts/data_collection/fetch_to_csv_parallel_improved.py")
IMPORT = str(ROOT / "scripts/data_collection/import_races_csv.py")

MONTHS = [
    ("01", "2025-01-01", "2025-01-31"),
    ("02", "2025-02-01", "2025-02-28"),
    ("03", "2025-03-01", "2025-03-31"),
    ("04", "2025-04-01", "2025-04-30"),
    ("05", "2025-05-01", "2025-05-31"),
    ("06", "2025-06-01", "2025-06-30"),
    ("07", "2025-07-01", "2025-07-31"),
    ("08", "2025-08-01", "2025-08-31"),
    ("09", "2025-09-01", "2025-09-30"),
    ("10", "2025-10-01", "2025-10-31"),
    ("11", "2025-11-01", "2025-11-30"),
    ("12", "2025-12-01", "2025-12-31"),
]

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def csv_rows(csv_path):
    try:
        with open(csv_path, encoding="utf-8") as f:
            return sum(1 for _ in f) - 1  # ヘッダー除く
    except:
        return 0

log("=" * 60)
log("2025年 brute-force補完 開始")
log("=" * 60)

completed_dirs = []

for m, start, end in MONTHS:
    outdir = ROOT / f"data/csv/2025_補完_{m}"
    races_csv = outdir / "races.csv"

    # 既に十分なCSVがある場合はスキップ（1月分は現在収集中なので待つ）
    rows = csv_rows(races_csv)
    if rows > 2000:
        log(f"{m}月: スキップ（races.csv={rows}行 既存）")
        completed_dirs.append(str(outdir))
        continue

    # 1月分だけ: 別プロセスが実行中なら待機
    if m == "01":
        log(f"{m}月: 別プロセス実行中の可能性あり → 完了を待機中...")
        waited = 0
        while True:
            rows = csv_rows(races_csv)
            if rows > 2000:
                log(f"{m}月: 別プロセス完了確認（races.csv={rows}行）→ スキップ")
                completed_dirs.append(str(outdir))
                break
            # プロセスが動いているか確認
            result = subprocess.run(
                ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
                capture_output=True, text=True
            )
            if "2025_補完_01" in result.stdout:
                if waited % 300 == 0:  # 5分ごとにログ
                    log(f"{m}月: 収集プロセス動作中... ({waited//60}分経過)")
                time.sleep(30)
                waited += 30
            else:
                log(f"{m}月: プロセス未検出 → 自前で収集開始")
                break
        if rows > 2000:
            continue

    log(f"{m}月: 収集開始 ({start}〜{end})")
    outdir.mkdir(parents=True, exist_ok=True)
    ret = subprocess.run(
        [sys.executable, FETCH,
         "--start", start, "--end", end,
         "--output", str(outdir),
         "--brute-force", "--workers", "12"],
        cwd=str(ROOT),
        capture_output=False
    )
    rows = csv_rows(races_csv)
    if ret.returncode == 0 and rows > 0:
        log(f"{m}月: 収集完了 races.csv={rows}行")
        completed_dirs.append(str(outdir))
    else:
        log(f"{m}月: 警告 終了コード={ret.returncode} races.csv={rows}行")
        if rows > 0:
            completed_dirs.append(str(outdir))

log("=" * 60)
log("全月収集完了 → DBインポート開始")
log("=" * 60)

if not completed_dirs:
    log("ERROR: インポート対象ディレクトリなし")
    sys.exit(1)

import_args = [sys.executable, IMPORT]
for d in completed_dirs:
    import_args += ["--dir", d]

ret = subprocess.run(import_args, cwd=str(ROOT), capture_output=False)
log(f"DBインポート完了（終了コード={ret.returncode}）")

log("=" * 60)
log("最終確認")
import sqlite3
conn = sqlite3.connect(str(ROOT / "data/boatrace.db"))
cur = conn.cursor()
cur.execute("SELECT strftime('%Y-%m', race_date), COUNT(*) FROM races WHERE race_date LIKE '2025%' GROUP BY 1 ORDER BY 1")
total = 0
for ym, cnt in cur.fetchall():
    log(f"  {ym}: {cnt:,}件")
    total += cnt
log(f"  合計: {total:,}件（改善前: 25,041件）")
conn.close()
log("全処理完了")
