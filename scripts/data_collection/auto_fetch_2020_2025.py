# -*- coding: utf-8 -*-
"""
2020-2025年データ自動取得マスタースクリプト

3日間放置で全データを自動収集:
1. 2022年8-12月（現在実行中のタスクをスキップ可能）
2. 2020年全年
3. 2021年全年
4. 2023年全年
5. 2024年全年
6. 2025年1-12月

推定所要時間: 15-25時間（並列12スレッド）

使用方法:
    python scripts/data_collection/auto_fetch_2020_2025.py

    # 2022年をスキップ（既に実行中の場合）
    python scripts/data_collection/auto_fetch_2020_2025.py --skip-2022

    # 特定年から開始
    python scripts/data_collection/auto_fetch_2020_2025.py --start-year 2023

    # 特定日付から再開（例: 2020年8月から）
    python scripts/data_collection/auto_fetch_2020_2025.py --start-date 2020-08-01
"""

import sys
import os
import io
import subprocess
import time
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

DB_PATH = ROOT_DIR / 'data' / 'boatrace.db'
LOG_DIR = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# ログファイル
LOG_FILE = LOG_DIR / f"auto_fetch_2020_2025_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# 停止時刻（None = 無制限）
STOP_TIME = None  # 無制限（必要に応じて設定）


def should_stop():
    """停止すべきかチェック"""
    if STOP_TIME is None:
        return False
    return datetime.now() >= STOP_TIME


def log(message):
    """ログ出力（コンソール＋ファイル）"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg, flush=True)

    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')


def check_data_status(year: int) -> dict:
    """指定年のデータ状況を確認"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    # レース数
    cursor.execute('''
        SELECT COUNT(*) FROM races
        WHERE race_date >= ? AND race_date <= ?
    ''', (start_date, end_date))
    race_count = cursor.fetchone()[0]

    # 結果数
    cursor.execute('''
        SELECT COUNT(DISTINCT r.id) FROM races r
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
    ''', (start_date, end_date))
    result_count = cursor.fetchone()[0]

    conn.close()

    # 期待値（約52,000レース/年）
    expected = 52000

    return {
        'year': year,
        'race_count': race_count,
        'result_count': result_count,
        'expected': expected,
        'completeness': race_count / expected * 100 if expected > 0 else 0
    }


def run_fetch_script(start_date: str, end_date: str, workers: int = 12, max_retries: int = 3) -> bool:
    """並列化版データ取得スクリプトを実行（リトライ機能付き）"""
    script_path = ROOT_DIR / 'scripts' / 'data_collection' / 'fetch_historical_data_parallel.py'

    log(f"実行: {start_date} - {end_date}")
    log(f"並列数: {workers}スレッド")

    cmd = [
        sys.executable,
        str(script_path),
        '--start', start_date,
        '--end', end_date,
        '--workers', str(workers)
    ]

    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'

    for attempt in range(max_retries):
        if attempt > 0:
            wait_time = 60 * (2 ** (attempt - 1))  # 60秒, 120秒
            log(f"リトライ {attempt + 1}/{max_retries}: {wait_time}秒後に再試行...")
            time.sleep(wait_time)

        start_time = time.time()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                encoding='utf-8',
                errors='replace',
                bufsize=1
            )

            # リアルタイム出力
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    # 進捗行のみログに記録
                    if '進捗:' in line or '完了' in line or 'レース' in line:
                        log(f"  {line}")

            return_code = process.wait()
            elapsed = time.time() - start_time

            if return_code == 0:
                log(f"完了: {start_date} - {end_date} (所要時間: {elapsed/60:.1f}分)")
                return True
            else:
                log(f"エラー: 終了コード {return_code}")
                if attempt == max_retries - 1:
                    return False

        except Exception as e:
            log(f"例外: {e}")
            if attempt == max_retries - 1:
                return False

    return False


def main():
    parser = argparse.ArgumentParser(description='2020-2025年データ自動取得')
    parser.add_argument('--skip-2022', action='store_true', help='2022年8-12月をスキップ')
    parser.add_argument('--start-year', type=int, default=2020, help='開始年（デフォルト: 2020）')
    parser.add_argument('--start-date', type=str, default=None, help='開始日付（例: 2020-08-01）指定すると--start-yearより優先')
    parser.add_argument('--workers', type=int, default=12, help='並列数（デフォルト: 12）')
    parser.add_argument('--check-only', action='store_true', help='状況確認のみ')
    args = parser.parse_args()

    # --start-dateが指定された場合、--start-yearを上書き
    start_date_override = None
    if args.start_date:
        try:
            start_date_override = datetime.strptime(args.start_date, '%Y-%m-%d')
            args.start_year = start_date_override.year
        except ValueError:
            print(f"エラー: --start-date の形式が不正です: {args.start_date} (正しい形式: YYYY-MM-DD)")
            sys.exit(1)

    log("=" * 80)
    log("2020-2025年データ自動取得マスタースクリプト")
    log("=" * 80)
    log(f"ログファイル: {LOG_FILE}")
    log(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("")

    # 現在のデータ状況を表示
    log("=== 現在のデータ状況 ===")
    for year in range(2020, 2026):
        status = check_data_status(year)
        log(f"  {year}年: {status['race_count']:,}レース ({status['completeness']:.1f}%)")
    log("")

    if args.check_only:
        return

    # 取得タスクを定義
    tasks = []

    # 2022年8-12月（スキップオプションがない場合）
    if not args.skip_2022 and args.start_year <= 2022:
        tasks.append(('2022-08-01', '2022-12-31', '2022年8-12月'))

    # 年単位のタスク
    for year in range(args.start_year, 2026):
        if year == 2022:
            # 2022年前半は完了しているのでスキップ
            continue

        if year == 2025:
            # 2025年は現在日付まで
            end_date = min(f"{year}-12-31", datetime.now().strftime('%Y-%m-%d'))
        else:
            end_date = f"{year}-12-31"

        # --start-dateが指定されている場合、その年の開始日を調整
        if start_date_override and year == start_date_override.year:
            start = args.start_date
            name = f"{year}年（{start_date_override.month}月～）"
        else:
            start = f"{year}-01-01"
            name = f"{year}年"

        tasks.append((start, end_date, name))

    log(f"=== 取得タスク: {len(tasks)}件 ===")
    for start, end, name in tasks:
        log(f"  - {name}: {start} - {end}")
    log("")

    # 推定時間
    total_days = sum(
        (datetime.strptime(end, '%Y-%m-%d') - datetime.strptime(start, '%Y-%m-%d')).days + 1
        for start, end, _ in tasks
    )
    estimated_hours = total_days * 0.5 / 60  # 1日あたり約30秒-1分
    log(f"推定所要時間: 約{estimated_hours:.1f}-{estimated_hours*2:.1f}時間")
    log("")

    # 実行開始
    master_start = time.time()
    completed = []
    failed = []

    for i, (start_date, end_date, name) in enumerate(tasks, 1):
        # 停止時刻チェック
        if should_stop():
            log("")
            log("=" * 80)
            log(f"停止時刻({STOP_TIME})に達したため処理を中断します")
            log("=" * 80)
            break

        log("")
        log("=" * 80)
        log(f"タスク {i}/{len(tasks)}: {name}")
        log("=" * 80)

        # 実行前の状況確認
        if '年' in name and '-' not in name:
            year = int(name.replace('年', ''))
            before_status = check_data_status(year)
            log(f"実行前: {before_status['race_count']:,}レース")

        success = run_fetch_script(start_date, end_date, args.workers)

        if success:
            completed.append(name)

            # 実行後の状況確認
            if '年' in name and '-' not in name:
                after_status = check_data_status(year)
                added = after_status['race_count'] - before_status['race_count']
                log(f"実行後: {after_status['race_count']:,}レース (+{added:,})")
        else:
            failed.append(name)
            log(f"警告: {name} でエラーが発生しましたが、次のタスクを続行します")

        # タスク間の休憩（サーバー負荷軽減）
        if i < len(tasks):
            log("次のタスクまで30秒待機...")
            time.sleep(30)

    # 最終サマリー
    master_elapsed = time.time() - master_start

    log("")
    log("=" * 80)
    log("全タスク完了")
    log("=" * 80)
    log(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"総所要時間: {master_elapsed/3600:.2f}時間 ({master_elapsed/60:.1f}分)")
    log("")

    log(f"成功: {len(completed)}/{len(tasks)}")
    for name in completed:
        log(f"  [OK] {name}")

    if failed:
        log(f"\n失敗: {len(failed)}")
        for name in failed:
            log(f"  [NG] {name}")

    log("")
    log("=== 最終データ状況 ===")
    for year in range(2020, 2026):
        status = check_data_status(year)
        log(f"  {year}年: {status['race_count']:,}レース ({status['completeness']:.1f}%)")

    log("")
    log(f"ログファイル: {LOG_FILE}")
    log("=" * 80)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("\nユーザーによる中断")
    except Exception as e:
        log(f"致命的エラー: {e}")
        raise
