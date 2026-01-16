#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
補完スクリプト: 2020-2023年の直前情報収集とbefore予測生成

マスタースクリプトでスキップされたタスクを補完します。
"""
import sys
import os

# 最初に文字コード設定
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['AUTO_START'] = '1'  # 確認プロンプトをスキップ

import subprocess
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ログファイル
LOG_FILE = PROJECT_ROOT / "logs" / f"complement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG_FILE.parent.mkdir(exist_ok=True)


def log(message):
    """ログ出力"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg, flush=True)

    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')


def run_script(script_name, description, timeout_hours=12):
    """スクリプトを実行して完了を待機"""
    log("=" * 100)
    log(f"開始: {description}")
    log(f"スクリプト: {script_name}")
    log("=" * 100)

    script_path = PROJECT_ROOT / "scripts" / script_name

    # 環境変数設定
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['AUTO_START'] = '1'

    start_time = time.time()

    try:
        # スクリプト実行
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            universal_newlines=True,
            bufsize=1
        )

        # リアルタイム出力
        for line in process.stdout:
            log(f"  {line.rstrip()}")

        # 完了待機
        return_code = process.wait(timeout=timeout_hours * 3600)

        elapsed = time.time() - start_time

        if return_code == 0:
            log(f"OK 完了: {description} ({elapsed/60:.1f}分)")
            return True
        else:
            log(f"NG エラー: {description} (終了コード: {return_code})")
            return False

    except subprocess.TimeoutExpired:
        log(f"NG タイムアウト: {description} ({timeout_hours}時間)")
        process.kill()
        return False
    except Exception as e:
        log(f"NG 例外: {description} - {e}")
        return False


def main():
    log("=" * 100)
    log("補完スクリプト起動: 2020-2023年 直前情報とbefore予測")
    log("=" * 100)
    log(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"ログファイル: {LOG_FILE}")
    log("")

    start_time = time.time()

    # タスク定義
    tasks = [
        {
            'name': 'collect_beforeinfo_2020_2023',
            'description': '2020-2023年 直前情報収集（展示・ST・気象等）',
            'script': 'collect_beforeinfo_2020_2023.py',
            'timeout': 10
        },
        {
            'name': 'generate_before_2020_2023',
            'description': '2020-2023年 before予測生成',
            'script': 'regenerate_predictions_2020_2023_before.py',
            'timeout': 3
        }
    ]

    completed = []
    failed = []

    # タスク実行
    for i, task in enumerate(tasks, 1):
        log("")
        log(f"{'='*100}")
        log(f"タスク {i}/{len(tasks)}: {task['description']}")
        log(f"{'='*100}")

        try:
            success = run_script(
                task['script'],
                task['description'],
                timeout_hours=task.get('timeout', 12)
            )

            if success:
                completed.append(task['name'])
            else:
                failed.append(task['name'])
                log(f"NG タスク失敗: {task['description']}")

        except KeyboardInterrupt:
            log("ユーザーによる中断")
            break
        except Exception as e:
            log(f"NG タスク例外: {task['description']} - {e}")
            failed.append(task['name'])

    # 最終サマリー
    elapsed = time.time() - start_time

    log("")
    log("=" * 100)
    log("補完スクリプト 完了")
    log("=" * 100)
    log(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"総所要時間: {elapsed/3600:.2f}時間 ({elapsed/60:.1f}分)")
    log("")
    log(f"完了タスク: {len(completed)}/{len(tasks)}")
    for name in completed:
        log(f"  OK {name}")

    if failed:
        log(f"\n失敗タスク: {len(failed)}")
        for name in failed:
            log(f"  NG {name}")

    log("")
    log(f"ログファイル: {LOG_FILE}")
    log("=" * 100)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"致命的エラー: {e}")
        import traceback
        traceback.print_exc()
        raise
