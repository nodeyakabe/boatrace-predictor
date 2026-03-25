"""
Phase 1 完了待ち → バックアップ → Phase 2 DB UPSERT 自動実行スクリプト
2026-03-24 作成
"""
import glob, os, sqlite3, subprocess, sys, time

BASE = "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032"
os.chdir(BASE)

YEARS = {2020: 366, 2021: 365, 2022: 365, 2023: 365, 2024: 366, 2025: 365}
BACKUP_PATH = "data/boatrace_before_exhibition_rule_clean.db"

def csv_count(year):
    return len(glob.glob(f"data/predictions_csv/before/{year}/*.csv"))

def all_phase1_done():
    for year, total in YEARS.items():
        if csv_count(year) < total:
            return False, year
    return True, None

# --- Phase 1 完了待ちループ ---
print("=== Phase 1 完了待ち開始 ===", flush=True)
while True:
    done, pending = all_phase1_done()
    if done:
        print("全年度 Phase 1 完了！", flush=True)
        break
    count = csv_count(pending)
    total = YEARS[pending]
    print(f"  {pending}年: {count}/{total} 待機中...", flush=True)
    time.sleep(300)  # 5分ごとに確認

# --- スケジューラー停止（念のため） ---
print("\n=== スケジューラー停止 ===", flush=True)
subprocess.call(
    ['wmic', 'process', 'where', "name='python.exe' and commandline like '%daily_scheduler%'", 'delete'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
print("停止完了（非稼働なら無視）", flush=True)
time.sleep(5)

# --- SQLiteオンラインバックアップ ---
print(f"\n=== バックアップ作成: {BACKUP_PATH} ===", flush=True)
if os.path.exists(BACKUP_PATH):
    os.remove(BACKUP_PATH)
t = time.time()
src = sqlite3.connect("data/boatrace.db")
dst = sqlite3.connect(BACKUP_PATH)
src.backup(dst, pages=1000)
dst.close()
src.close()
print(f"バックアップ完了: {time.time()-t:.0f}秒", flush=True)

# integrity check
conn = sqlite3.connect(BACKUP_PATH)
cur = conn.cursor()
cur.execute("PRAGMA quick_check")
result = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM race_predictions WHERE prediction_type='before'")
cnt = cur.fetchone()[0]
conn.close()
print(f"quick_check: {result} / before予測: {cnt}件", flush=True)

if result != "ok":
    print("❌ バックアップ破損。Phase 2 を中断します。", flush=True)
    sys.exit(1)
print("✅ バックアップ正常", flush=True)

# --- Phase 2: CSV → DB UPSERT ---
print("\n=== Phase 2: CSV → DB UPSERT 開始 ===", flush=True)
for year in sorted(YEARS.keys()):
    print(f"\n--- {year}年 投入中 ---", flush=True)
    result = subprocess.run(
        [sys.executable, "scripts/prediction/import_predictions_csv.py",
         "--dir", f"data/predictions_csv/before/{year}"],
        cwd=BASE
    )
    if result.returncode != 0:
        print(f"❌ {year}年 投入失敗", flush=True)
        sys.exit(1)
    print(f"✅ {year}年 完了", flush=True)

print("\n=== 全作業完了 ===", flush=True)
print("次のステップ: python scripts/backtest/standard_backtest_unique.py --full", flush=True)
