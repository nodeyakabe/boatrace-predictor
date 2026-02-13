#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2日間完全自動データ収集スクリプト（再開可能版）

PC再起動やエラーからの復帰に対応したバージョン

特徴:
- 進捗状態を自動保存（.progress.json）
- 再実行時に完了済みの月をスキップ
- 完了した月のリストを保持
- エラー発生時も次の月に進む
"""
import sys
import io
import subprocess
import json
from pathlib import Path
from datetime import datetime
import time
import argparse

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROGRESS_FILE = PROJECT_ROOT / 'data' / '.collection_progress.json'

def log(message: str):
    """タイムスタンプ付きログ出力"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def load_progress():
    """進捗状態を読み込む"""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log(f"[WARNING] 進捗ファイル読み込みエラー: {e}")

    return {
        'completed_months': [],
        'failed_months': [],
        'start_time': None,
        'last_update': None
    }

def save_progress(progress):
    """進捗状態を保存"""
    progress['last_update'] = datetime.now().isoformat()
    try:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"[WARNING] 進捗ファイル保存エラー: {e}")

def run_collection(year: int, month: int) -> bool:
    """
    指定年月のデータ収集を実行

    Returns:
        成功時True、失敗時False
    """
    log(f"開始: {year}年{month}月のデータ収集")

    script = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_完全版.py'

    # 完全版スクリプトが存在しない場合は欠損データスクリプトを使用
    if not script.exists():
        log(f"[WARNING] 完全版スクリプトが見つかりません。欠損データスクリプトを使用します")
        script = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_欠損データ.py'

    start_time = time.time()

    try:
        result = subprocess.run(
            [sys.executable, str(script), '--year', str(year), '--month', str(month)],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=False,
            text=True
        )

        elapsed = time.time() - start_time
        log(f"完了: {year}年{month}月 （所要時間: {elapsed/60:.1f}分）")
        return True

    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        log(f"[ERROR] 失敗: {year}年{month}月 （所要時間: {elapsed/60:.1f}分）")
        log(f"[ERROR] 終了コード: {e.returncode}")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        log(f"[ERROR] 予期しないエラー: {year}年{month}月 （所要時間: {elapsed/60:.1f}分）")
        log(f"[ERROR] エラー内容: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='2日間完全自動データ収集（再開可能版）')
    parser.add_argument('--reset', action='store_true', help='進捗をリセットして最初から実行')
    parser.add_argument('--skip-db-insert', action='store_true', help='DB投入をスキップ')
    args = parser.parse_args()

    log("=" * 80)
    log("2日間完全自動データ収集スクリプト（再開可能版）")
    log("=" * 80)

    # 進捗読み込み
    if args.reset and PROGRESS_FILE.exists():
        log("進捗をリセットします")
        PROGRESS_FILE.unlink()

    progress = load_progress()

    if progress['start_time']:
        log(f"前回の実行開始時刻: {progress['start_time']}")
        log(f"完了済み: {len(progress['completed_months'])}ヶ月")
        log(f"失敗: {len(progress['failed_months'])}ヶ月")
        log("中断した位置から再開します")
    else:
        progress['start_time'] = datetime.now().isoformat()
        save_progress(progress)

    log("=" * 80)
    log("")

    start_time = datetime.now()

    # 収集する月のリスト
    months_to_collect = []
    for year in [2021, 2023]:
        for month in range(1, 13):
            month_id = f"{year}-{month:02d}"
            months_to_collect.append((year, month, month_id))

    total_months = len(months_to_collect)
    completed_count = len(progress['completed_months'])
    remaining = total_months - completed_count

    log(f"全体: {total_months}ヶ月")
    log(f"完了済み: {completed_count}ヶ月")
    log(f"残り: {remaining}ヶ月")
    log("")

    # データ収集
    for year, month, month_id in months_to_collect:
        # 既に完了している月はスキップ
        if month_id in progress['completed_months']:
            log(f"スキップ: {year}年{month}月（既に完了）")
            continue

        # 失敗した月も再試行
        if month_id in progress['failed_months']:
            log(f"再試行: {year}年{month}月（前回失敗）")

        # データ収集実行
        if run_collection(year, month):
            progress['completed_months'].append(month_id)
            # failed_monthsから削除（再試行成功）
            if month_id in progress['failed_months']:
                progress['failed_months'].remove(month_id)
        else:
            if month_id not in progress['failed_months']:
                progress['failed_months'].append(month_id)

        # 進捗保存
        save_progress(progress)

        # 進捗表示
        completed_count = len(progress['completed_months'])
        failed_count = len(progress['failed_months'])
        log("")
        log(f"--- 進捗: {completed_count}/{total_months} 完了 ({failed_count}失敗) ---")
        elapsed = datetime.now() - start_time
        log(f"--- 経過時間: {elapsed} ---")
        log("")

    # DB投入（オプション）
    if not args.skip_db_insert:
        log("")
        log("=" * 80)
        log("DB投入フェーズ")
        log("=" * 80)
        log("")

        for year in [2021, 2023]:
            log(f"{year}年のDB投入")
            script = PROJECT_ROOT / 'scripts' / 'maintenance' / '投入_2021_2023_補完データ.py'
            try:
                subprocess.run(
                    [sys.executable, str(script), '--year', str(year), '--all-months'],
                    cwd=str(PROJECT_ROOT),
                    check=True
                )
                log(f"完了: {year}年のDB投入")
            except Exception as e:
                log(f"[ERROR] 失敗: {year}年のDB投入 - {e}")

    # 最終レポート
    end_time = datetime.now()
    total_elapsed = end_time - start_time

    log("")
    log("=" * 80)
    log("データ収集完了")
    log("=" * 80)
    log(f"開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"終了時刻: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"所要時間: {total_elapsed}")
    log("")

    completed_count = len(progress['completed_months'])
    failed_count = len(progress['failed_months'])

    log(f"結果: {completed_count}成功 / {failed_count}失敗 / {total_months}総数")
    log("")

    if progress['failed_months']:
        log("失敗した月:")
        for failed in sorted(progress['failed_months']):
            log(f"  - {failed}")
        log("")
        log("失敗した月は以下のコマンドで再実行してください:")
        log(f"  python {__file__}")
    else:
        log("全ての月のデータ収集が成功しました！")
        log("")
        log("進捗ファイルを削除します")
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()

    log("")
    log("=" * 80)

    return 1 if progress['failed_months'] else 0

if __name__ == '__main__':
    sys.exit(main())
