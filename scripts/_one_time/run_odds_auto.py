"""
odds + exhibition_time 自動補完スクリプト
対象:
  1. 2025年 trifecta_odds (31,074件欠損)
  2. 2020年1-8月 trifecta_odds (26,586件欠損)
  3. 2025年 exhibition_time (44.6%欠損)
  4. 2020年1-8月 exhibition_time (20-74%欠損)

予測生成は行わない。
"""
import sys
import os
import subprocess
import sqlite3
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "data" / "boatrace.db"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / f"odds_exhibition_補完_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def wal_checkpoint():
    """WALをcheckpointしてディスク空きを確保"""
    try:
        conn = sqlite3.connect(str(DB))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        log("WAL checkpoint 完了")
    except Exception as e:
        log(f"WAL checkpoint エラー: {e}")

def check_odds_coverage(year_prefix):
    """指定年度のtrifecta_odds充足率を確認"""
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT r.id), COUNT(DISTINCT t.race_id)
        FROM races r LEFT JOIN trifecta_odds t ON r.id = t.race_id
        WHERE r.race_date LIKE ?
    """, (f"{year_prefix}%",))
    total, has = cur.fetchone()
    conn.close()
    pct = has * 100 / total if total else 0
    return total, has, pct

def check_exhibition_coverage(year_prefix):
    """指定年度のexhibition_time充足率を確認"""
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    # race_detailsのexhibition_time有り行数
    cur.execute("""
        SELECT COUNT(*), COUNT(CASE WHEN rd.exhibition_time IS NOT NULL AND rd.exhibition_time > 0 THEN 1 END)
        FROM race_details rd JOIN races r ON rd.race_id = r.id
        WHERE r.race_date LIKE ?
    """, (f"{year_prefix}%",))
    total, has = cur.fetchone()
    conn.close()
    pct = has * 100 / total if total else 0
    return total, has, pct

def run(cmd, desc):
    """サブプロセスを実行してログ出力"""
    log(f"開始: {desc}")
    log(f"コマンド: {' '.join(str(c) for c in cmd)}")
    ret = subprocess.run(cmd, cwd=str(ROOT), capture_output=False, stdin=subprocess.DEVNULL)
    if ret.returncode == 0:
        log(f"完了: {desc}")
    else:
        log(f"警告: {desc} 終了コード={ret.returncode}")
    return ret.returncode

# ============================================================
# STEP 1: 2025年 trifecta_odds
# ============================================================
def step_odds_2025():
    total, has, pct = check_odds_coverage("2025")
    log(f"[STEP1] 2025年 trifecta_odds: {has}/{total} ({pct:.1f}%)")
    if pct >= 95:
        log("[STEP1] スキップ（95%以上達成済み）")
        return
    missing = total - has
    log(f"[STEP1] 欠損 {missing:,}件 → 収集開始")
    run([
        sys.executable,
        str(ROOT / "scripts/data_collection/fetch_odds_parallel_safe.py"),
        "--start-date", "2025-01-01",
        "--end-date", "2025-12-31",
        "--workers", "10",
    ], "2025年 trifecta_odds収集")
    wal_checkpoint()
    total2, has2, pct2 = check_odds_coverage("2025")
    log(f"[STEP1] 完了後: {has2}/{total2} ({pct2:.1f}%)")

# ============================================================
# STEP 2: 2020年1-8月 trifecta_odds
# ============================================================
def step_odds_2020():
    total, has, pct = check_odds_coverage("2020")
    log(f"[STEP2] 2020年 trifecta_odds: {has}/{total} ({pct:.1f}%)")
    if pct >= 95:
        log("[STEP2] スキップ（95%以上達成済み）")
        return
    missing = total - has
    log(f"[STEP2] 欠損 {missing:,}件 → 収集開始（1-8月）")
    run([
        sys.executable,
        str(ROOT / "scripts/data_collection/fetch_odds_parallel_safe.py"),
        "--start-date", "2020-01-01",
        "--end-date", "2020-08-31",
        "--workers", "10",
    ], "2020年1-8月 trifecta_odds収集")
    wal_checkpoint()
    total2, has2, pct2 = check_odds_coverage("2020")
    log(f"[STEP2] 完了後: {has2}/{total2} ({pct2:.1f}%)")

# ============================================================
# STEP 3: 2025年 exhibition_time
# ============================================================
def step_exhibition_2025():
    total, has, pct = check_exhibition_coverage("2025")
    log(f"[STEP3] 2025年 exhibition_time: {has}/{total} ({pct:.1f}%)")
    if pct >= 90:
        log("[STEP3] スキップ（90%以上達成済み）")
        return
    out_dir = ROOT / "data/csv/beforeinfo/2025"
    log(f"[STEP3] 欠損 → 収集開始")
    run([
        sys.executable,
        str(ROOT / "scripts/data_collection/collect_beforeinfo_to_csv_parallel.py"),
        "--start", "2025-01-01",
        "--end", "2025-12-31",
        "--output", str(out_dir),
        "--workers", "12",
    ], "2025年 exhibition_time CSV収集")
    # CSV→DB投入
    csv_file = out_dir / "beforeinfo.csv"
    if csv_file.exists():
        run([
            sys.executable,
            str(ROOT / "scripts/data_collection/import_beforeinfo_csv_to_db.py"),
            "--input", str(out_dir),
        ], "2025年 exhibition_time DB投入")
        wal_checkpoint()
    else:
        log(f"[STEP3] CSVが存在しない: {csv_file}")
    total2, has2, pct2 = check_exhibition_coverage("2025")
    log(f"[STEP3] 完了後: {has2}/{total2} ({pct2:.1f}%)")

# ============================================================
# STEP 4: 2020年1-8月 exhibition_time
# ============================================================
def step_exhibition_2020():
    total, has, pct = check_exhibition_coverage("2020")
    log(f"[STEP4] 2020年 exhibition_time: {has}/{total} ({pct:.1f}%)")
    if pct >= 90:
        log("[STEP4] スキップ（90%以上達成済み）")
        return
    out_dir = ROOT / "data/csv/beforeinfo/2020_1_8"
    log(f"[STEP4] 欠損 → 収集開始（1-8月）")
    run([
        sys.executable,
        str(ROOT / "scripts/data_collection/collect_beforeinfo_to_csv_parallel.py"),
        "--start", "2020-01-01",
        "--end", "2020-08-31",
        "--output", str(out_dir),
        "--workers", "12",
    ], "2020年1-8月 exhibition_time CSV収集")
    csv_file = out_dir / "beforeinfo.csv"
    if csv_file.exists():
        run([
            sys.executable,
            str(ROOT / "scripts/data_collection/import_beforeinfo_csv_to_db.py"),
            "--input", str(out_dir),
        ], "2020年1-8月 exhibition_time DB投入")
        wal_checkpoint()
    else:
        log(f"[STEP4] CSVが存在しない: {csv_file}")
    total2, has2, pct2 = check_exhibition_coverage("2020")
    log(f"[STEP4] 完了後: {has2}/{total2} ({pct2:.1f}%)")

# ============================================================
# STEP 5: 最終充足率レポート
# ============================================================
def final_report():
    log("=" * 60)
    log("最終充足率レポート")
    log("=" * 60)
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    for y in ["2020", "2021", "2022", "2023", "2024", "2025"]:
        cur.execute("SELECT COUNT(*) FROM races WHERE race_date LIKE ?", (f"{y}%",))
        races = cur.fetchone()[0]
        cur.execute("""SELECT COUNT(DISTINCT t.race_id) FROM trifecta_odds t
                       JOIN races r ON t.race_id=r.id WHERE r.race_date LIKE ?""", (f"{y}%",))
        odds = cur.fetchone()[0]
        cur.execute("""SELECT COUNT(CASE WHEN rd.exhibition_time IS NOT NULL AND rd.exhibition_time > 0 THEN 1 END)
                       FROM race_details rd JOIN races r ON rd.race_id=r.id WHERE r.race_date LIKE ?""", (f"{y}%",))
        exh = cur.fetchone()[0]
        odds_pct = odds * 100 // races if races else 0
        exh_pct = exh * 100 // races if races else 0
        log(f"  {y}: races={races:,} | odds={odds_pct}% | exhibition={exh_pct}%")
    conn.close()

# ============================================================
# メイン
# ============================================================
if __name__ == "__main__":
    log("=" * 60)
    log("odds + exhibition_time 自動補完 開始")
    log("=" * 60)

    step_odds_2025()
    step_odds_2020()
    step_exhibition_2025()
    step_exhibition_2020()
    final_report()

    log("全ステップ完了")
