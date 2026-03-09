"""
before予測 残り全年度 自動チェーンスクリプト
--------------------------------------------
2023年 May-Dec の生成完了を待ってから、
2022 → 2021 → 2020 → 2024 → 2025 を順番に実行する。

使い方:
  python run_before_regen_chain.py

実行時間の目安:
  各年度 12~16時間 × 5年度 = 60~80時間（約3日）
"""

import os
import subprocess
import time
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "boatrace.db")

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def wal_checkpoint():
    """大量書き込み後のWALをTRUNCATEしてディスク節約"""
    try:
        conn = sqlite3.connect(DB_PATH)
        result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        conn.close()
        log(f"WAL checkpoint完了: {result}")
    except Exception as e:
        log(f"WAL checkpoint失敗（続行）: {e}")

def wait_for_2023_completion():
    """2023年 May-Dec の完了を待機"""
    last_csv = os.path.join(BASE_DIR, "data", "predictions_csv", "before", "2023", "2023-12-31.csv")
    log("2023年 May-Dec の完了待機中...")

    while True:
        if os.path.exists(last_csv):
            age_sec = time.time() - os.path.getmtime(last_csv)
            if age_sec > 1800:  # 30分以上前に生成済み = Phase 2 (DB投入) も完了
                log(f"2023年完了確認（{age_sec/60:.0f}分前にCSV生成済み）")
                return
            else:
                log(f"2023年 Phase 1完了、Phase 2待機中... あと {(1800-age_sec)/60:.0f}分")
        else:
            log("2023年まだ生成中...")
        time.sleep(120)  # 2分ごとにチェック

def run_year(year):
    """指定年度の before 予測を生成"""
    log(f"{'='*60}")
    log(f"{year}年 before予測 生成開始")
    log(f"{'='*60}")

    cmd = [
        "python",
        os.path.join(BASE_DIR, "scripts", "prediction", "generate_before_fast.py"),
        "--year", str(year),
        "--force"
    ]
    result = subprocess.run(cmd, cwd=BASE_DIR)

    if result.returncode != 0:
        log(f"[WARN] {year}年 生成失敗 (returncode={result.returncode}) -> 次年度に進む")
    else:
        log(f"[OK] {year}年 完了")

    # WALが膨らんでいればここでTRUNCATEしてディスク節約
    wal_checkpoint()
    time.sleep(30)

def main():
    log("before予測 残り全年度 チェーンスクリプト 開始（再起動版2: 2023/2022/2021完了済み）")

    # Step 1: 2023/2022/2021 は完了済みのためスキップ
    log("2023/2022/2021 は完了済み -> スキップ")

    # Step 2: 残り年度を順番に実行（ディスクI/O考慮で直列）
    years_to_run = [2020, 2024, 2025]
    for year in years_to_run:
        run_year(year)

    log("=" * 60)
    log("全年度 before予測 再生成完了！")
    log("次に standard_backtest_unique.py --full を実行してください")
    log("=" * 60)

if __name__ == "__main__":
    main()
