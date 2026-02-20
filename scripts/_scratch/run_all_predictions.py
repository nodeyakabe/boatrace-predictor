"""全年度の予想生成スクリプト（バッチ実行版）"""
import sys
import io
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent
SCRIPT = PROJECT_ROOT / "scripts" / "prediction" / "fast_prediction_generator.py"
DB_PATH = PROJECT_ROOT / "data" / "boatrace.db"
LOG_FILE = PROJECT_ROOT / "logs" / f"all_predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


def log(msg):
    print(msg, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def get_incomplete_dates(year: str, pred_type: str) -> list:
    """未生成の日付を取得"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT r.race_date
        FROM races r
        WHERE r.race_date LIKE '{year}%'
        AND r.id NOT IN (
            SELECT DISTINCT rp.race_id
            FROM race_predictions rp
            WHERE rp.prediction_type = '{pred_type}'
        )
        ORDER BY r.race_date
    """)
    dates = [row[0] for row in cur.fetchall()]
    conn.close()
    return dates


def run_date(date: str, pred_type: str) -> bool:
    """1日分の予想を生成"""
    cmd = [sys.executable, str(SCRIPT), "--date", date, "--type", pred_type]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=300
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--years', default='2020,2021,2022,2023,2024,2025')
parser.add_argument('--type', default='before', choices=['advance', 'before', 'both'])
args = parser.parse_args()

years = args.years.split(',')
pred_types = ['advance', 'before'] if args.type == 'both' else [args.type]

log("="*70)
log(f"全年度予想生成バッチ")
log("="*70)
log(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log(f"対象年度: {', '.join(years)}")
log(f"予測タイプ: {', '.join(pred_types)}")
log(f"ログ: {LOG_FILE}")

total_success = 0
total_failed = 0
overall_start = datetime.now()

for year in years:
    for pred_type in pred_types:
        dates = get_incomplete_dates(year, pred_type)
        if not dates:
            log(f"\n{year}年 {pred_type}: 既に完了済み")
            continue

        log(f"\n{'='*50}")
        log(f"{year}年 {pred_type}: {len(dates)}日分を生成")
        log(f"{'='*50}")

        year_success = 0
        year_failed = 0
        start_time = datetime.now()

        for i, date in enumerate(dates, 1):
            success = run_date(date, pred_type)
            if success:
                year_success += 1
                total_success += 1
            else:
                year_failed += 1
                total_failed += 1

            # 50日ごとに進捗表示
            if i % 50 == 0 or i == len(dates):
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = i / elapsed if elapsed > 0 else 0
                remaining = len(dates) - i
                eta_s = remaining / rate if rate > 0 else 0
                eta = datetime.now() + timedelta(seconds=eta_s)
                log(f"  {year}年{pred_type}: {i}/{len(dates)} ({100*i/len(dates):.1f}%) "
                    f"成功={year_success} 失敗={year_failed} "
                    f"完了予定: {eta.strftime('%m/%d %H:%M')}")

        elapsed = (datetime.now() - start_time).total_seconds()
        log(f"  {year}年{pred_type} 完了: 成功={year_success}, 失敗={year_failed}, "
            f"時間={elapsed/60:.1f}分")

total_elapsed = (datetime.now() - overall_start).total_seconds()
log("\n" + "="*70)
log(f"全体完了: 成功={total_success}, 失敗={total_failed}, 時間={total_elapsed/60:.1f}分")
log(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log("="*70)
