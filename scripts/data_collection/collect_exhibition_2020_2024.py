# -*- coding: utf-8 -*-
"""2020-2024年の展示データを月別に自動収集

使用例:
    python scripts/data_collection/collect_exhibition_2020_2024.py

特徴:
- 2020-2024年の60ヶ月を順次収集
- 各月をCSVに保存後、DBに自動インポート
- エラー時も次の月に進む（後でリトライ可能）
- 進捗をログファイルに記録
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import json

# プロジェクトルート
ROOT_DIR = Path(__file__).parent.parent.parent
CSV_BASE_DIR = ROOT_DIR / "data" / "csv" / "exhibition_data"
LOG_DIR = ROOT_DIR / "logs"

# ログディレクトリ作成
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ログファイル
log_file = LOG_DIR / f"exhibition_collection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
progress_file = LOG_DIR / "exhibition_collection_progress.json"

def log(message):
    """ログ出力"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] {message}"
    print(log_message, flush=True)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(log_message + '\n')
        f.flush()

def save_progress(progress_data):
    """進捗保存"""
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, indent=2, ensure_ascii=False)

def load_progress():
    """進捗ロード"""
    if progress_file.exists():
        with open(progress_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'completed_months': [], 'failed_months': [], 'last_update': None}

def get_month_range(start_year, start_month, end_year, end_month):
    """月のリストを生成"""
    months = []
    current = datetime(start_year, start_month, 1)
    end = datetime(end_year, end_month, 1)

    while current <= end:
        months.append(current.strftime('%Y-%m'))
        # 次の月へ
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)

    return months

def collect_month(year_month):
    """1ヶ月分のデータを収集してインポート"""
    year, month = year_month.split('-')

    # 月の最終日を計算
    if month == '12':
        next_month = datetime(int(year) + 1, 1, 1)
    else:
        next_month = datetime(int(year), int(month) + 1, 1)
    last_day = (next_month - timedelta(days=1)).day

    start_date = f"{year}-{month}-01"
    end_date = f"{year}-{month}-{last_day:02d}"

    output_dir = CSV_BASE_DIR / f"{year}_{month}"

    log(f"{'='*80}")
    log(f"収集開始: {year_month}")
    log(f"期間: {start_date} ～ {end_date}")
    log(f"出力先: {output_dir}")
    log(f"{'='*80}")

    # Step 1: CSV収集
    log(f"Step 1/2: CSVファイルに収集中...")
    csv_cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "data_collection" / "fetch_exhibition_data_to_csv.py"),
        "--start", start_date,
        "--end", end_date,
        "--output", str(output_dir),
        "--workers", "8"
    ]

    try:
        result = subprocess.run(csv_cmd, capture_output=True, text=True, timeout=5400)

        if result.returncode != 0:
            log(f"エラー: CSV収集失敗 (exit code: {result.returncode})")
            log(f"STDOUT: {result.stdout[:500]}")
            log(f"STDERR: {result.stderr[:500]}")
            # CSVファイルが作成されていれば成功とみなす
            csv_file = output_dir / "exhibition_data.csv"
            if csv_file.exists() and csv_file.stat().st_size > 1000:
                log(f"CSVファイルは作成済み: {csv_file.stat().st_size} bytes")
                log(f"収集は成功したとみなします")
            else:
                return False

        log(f"CSV収集完了")

    except subprocess.TimeoutExpired:
        log(f"タイムアウト: CSV収集（60分以内に完了しなかった）")
        return False
    except Exception as e:
        log(f"例外発生: {type(e).__name__} - {e}")
        return False

    # Step 2: DB投入
    csv_file = output_dir / "exhibition_data.csv"
    if not csv_file.exists():
        log(f"エラー: CSVファイルが見つかりません: {csv_file}")
        return False

    log(f"Step 2/2: DBに投入中...")
    import_cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "maintenance" / "import_exhibition_data_from_csv.py"),
        "--input", str(output_dir)
    ]

    try:
        result = subprocess.run(import_cmd, capture_output=True, text=True, timeout=1200)

        if result.returncode != 0:
            log(f"エラー: DB投入失敗")
            log(f"STDOUT: {result.stdout[:500]}")
            log(f"STDERR: {result.stderr[:500]}")
            return False

        log(f"DB投入完了")
        log(f"{'='*80}")
        return True

    except subprocess.TimeoutExpired:
        log(f"タイムアウト: DB投入（10分以内に完了しなかった）")
        return False
    except Exception as e:
        log(f"例外発生: {type(e).__name__} - {e}")
        return False

def main():
    log("="*80)
    log("2020-2024年 展示データ 自動収集開始")
    log("="*80)

    # 進捗ロード
    progress = load_progress()
    completed = set(progress.get('completed_months', []))
    failed = set(progress.get('failed_months', []))

    # 月リスト生成
    months = get_month_range(2020, 1, 2024, 12)

    log(f"対象期間: 2020-01 ～ 2024-12 ({len(months)}ヶ月)")
    log(f"既に完了: {len(completed)}ヶ月")
    log(f"前回失敗: {len(failed)}ヶ月")
    log(f"残り: {len(months) - len(completed)}ヶ月")
    log("")

    # 統計
    total_success = len(completed)
    total_failed = 0
    start_time = datetime.now()

    for i, month in enumerate(months, 1):
        if month in completed:
            log(f"[{i}/{len(months)}] スキップ: {month}（既に完了）")
            continue

        log(f"[{i}/{len(months)}] 処理中: {month}")

        success = collect_month(month)

        if success:
            total_success += 1
            completed.add(month)
            if month in failed:
                failed.remove(month)
            log(f"[OK] 成功: {month}")
        else:
            total_failed += 1
            failed.add(month)
            log(f"[NG] 失敗: {month}")

        # 進捗保存
        progress['completed_months'] = list(completed)
        progress['failed_months'] = list(failed)
        progress['last_update'] = datetime.now().isoformat()
        save_progress(progress)

        # 統計表示
        elapsed = (datetime.now() - start_time).total_seconds() / 60
        remaining = len(months) - i
        avg_time = elapsed / i if i > 0 else 0
        eta = remaining * avg_time

        log(f"進捗: {i}/{len(months)} ({i/len(months)*100:.1f}%)")
        log(f"成功: {total_success} / 失敗: {total_failed}")
        log(f"経過時間: {elapsed:.1f}分 / 残り推定: {eta:.1f}分")
        log("")

    # 最終サマリー
    total_time = (datetime.now() - start_time).total_seconds() / 60

    log("="*80)
    log("最終結果")
    log("="*80)
    log(f"対象月: {len(months)}ヶ月")
    log(f"成功: {total_success}ヶ月")
    log(f"失敗: {total_failed}ヶ月")
    log(f"所要時間: {total_time:.1f}分 ({total_time/60:.1f}時間)")

    if total_failed > 0:
        log("")
        log("失敗した月:")
        for month in sorted(failed):
            log(f"  - {month}")
        log("")
        log("再実行コマンド:")
        log(f"  python {__file__}")

    log("="*80)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("")
        log("中断されました（Ctrl+C）")
        log("進捗は保存されています。再実行で続きから開始できます。")
    except Exception as e:
        log(f"予期しないエラー: {type(e).__name__} - {e}")
        import traceback
        log(traceback.format_exc())
