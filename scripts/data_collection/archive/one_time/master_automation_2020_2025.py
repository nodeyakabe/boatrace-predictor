#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完全自動化マスタースクリプト（2020-2025年データ整備）

実行順序：
1. 2020-2023年 advance予測生成完了を待機 ✓ 実行中
2. 2020-2023年 直前情報収集（5-8時間）
3. 2020-2023年 before予測生成（2時間）
4. 2024年 race_conditions収集（2時間）
5. 2024年 advance予測生成（1時間）
6. 2024年 before予測生成（1時間）
7. 2025年 advance予測生成（2時間）
8. 2025年 before予測生成（2時間）

総推定時間: 約15-20時間
"""
import sys
import os
import io
import subprocess
import time
import sqlite3
from pathlib import Path
from datetime import datetime

# Windows環境での文字コード問題を回避
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

db_path = PROJECT_ROOT / "data" / "boatrace.db"

# ログファイル
LOG_FILE = PROJECT_ROOT / "logs" / f"master_automation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG_FILE.parent.mkdir(exist_ok=True)


def log(message):
    """ログ出力"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg, flush=True)

    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')


def run_script(script_name, description, env_vars=None, timeout_hours=12):
    """スクリプトを実行して完了を待機"""
    log("=" * 100)
    log(f"開始: {description}")
    log(f"スクリプト: {script_name}")
    log("=" * 100)

    script_path = PROJECT_ROOT / "scripts" / script_name

    # 環境変数設定
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    if env_vars:
        env.update(env_vars)

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
            log(f"✓ 完了: {description} ({elapsed/60:.1f}分)")
            return True
        else:
            log(f"✗ エラー: {description} (終了コード: {return_code})")
            return False

    except subprocess.TimeoutExpired:
        log(f"✗ タイムアウト: {description} ({timeout_hours}時間)")
        process.kill()
        return False
    except Exception as e:
        log(f"✗ 例外: {description} - {e}")
        return False


def wait_for_advance_2020_2023():
    """2020-2023年のadvance予測生成完了を待機"""
    log("=" * 100)
    log("待機中: 2020-2023年 advance予測生成")
    log("=" * 100)

    TARGET_RACES = 64168

    while True:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(DISTINCT race_id)
            FROM race_predictions
            WHERE prediction_type = 'advance'
              AND race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')
        """)

        current = cursor.fetchone()[0]
        conn.close()

        progress = current / TARGET_RACES * 100

        if progress >= 99.0:
            log(f"✓ 完了: 2020-2023年 advance予測 ({current:,}件)")
            return True

        log(f"  進捗: {current:,}/{TARGET_RACES:,}件 ({progress:.1f}%)")
        time.sleep(60)


def check_completion(description, query):
    """完了状態をチェック"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(query)
    result = cursor.fetchone()[0]
    conn.close()

    log(f"  確認: {description} = {result:,}件")
    return result


def main():
    log("=" * 100)
    log("完全自動化マスタースクリプト起動")
    log("=" * 100)
    log(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"ログファイル: {LOG_FILE}")
    log("")

    master_start = time.time()

    # タスク定義
    tasks = [
        # タスク1: 2020-2023年 advance予測完了待機（既に実行中）
        {
            'name': 'wait_advance_2020_2023',
            'description': '2020-2023年 advance予測生成完了待機',
            'action': wait_for_advance_2020_2023
        },

        # タスク2: 2020-2023年 直前情報収集
        {
            'name': 'collect_beforeinfo_2020_2023',
            'description': '2020-2023年 直前情報収集（展示・ST・気象等）',
            'script': 'collect_beforeinfo_2020_2023.py',
            'env': {'AUTO_START': '1'},
            'timeout': 10,
            'verify': ("2020-2023年 展示データ",
                      "SELECT COUNT(DISTINCT race_id) FROM exhibition_data WHERE race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')")
        },

        # タスク3: 2020-2023年 before予測生成
        {
            'name': 'generate_before_2020_2023',
            'description': '2020-2023年 before予測生成',
            'script': 'regenerate_predictions_2020_2023_before.py',
            'timeout': 3,
            'verify': ("2020-2023年 before予測",
                      "SELECT COUNT(DISTINCT race_id) FROM race_predictions WHERE prediction_type = 'before' AND race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')")
        },

        # タスク4: 2024年 race_conditions収集
        {
            'name': 'collect_conditions_2024',
            'description': '2024年 race_conditions収集',
            'script': 'fetch_historical_data_2024.py',
            'timeout': 3,
            'verify': ("2024年 race_conditions",
                      "SELECT COUNT(*) FROM race_conditions WHERE race_id IN (SELECT id FROM races WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01')")
        },

        # タスク5: 2024年 advance予測生成
        {
            'name': 'generate_advance_2024',
            'description': '2024年 advance予測生成',
            'script': 'generate_advance_predictions_2024.py',
            'timeout': 2,
            'verify': ("2024年 advance予測",
                      "SELECT COUNT(DISTINCT race_id) FROM race_predictions WHERE prediction_type = 'advance' AND race_id IN (SELECT id FROM races WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01')")
        },

        # タスク6: 2024年 before予測生成
        {
            'name': 'generate_before_2024',
            'description': '2024年 before予測生成',
            'script': 'generate_before_predictions_2024.py',
            'timeout': 2,
            'verify': ("2024年 before予測",
                      "SELECT COUNT(DISTINCT race_id) FROM race_predictions WHERE prediction_type = 'before' AND race_id IN (SELECT id FROM races WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01')")
        },

        # タスク7: 2025年 advance予測再生成
        {
            'name': 'regenerate_advance_2025',
            'description': '2025年 advance予測再生成',
            'script': 'regenerate_predictions_2025_advance.py',
            'timeout': 3,
            'verify': ("2025年 advance予測",
                      "SELECT COUNT(DISTINCT race_id) FROM race_predictions WHERE prediction_type = 'advance' AND race_id IN (SELECT id FROM races WHERE race_date >= '2025-01-01')")
        },

        # タスク8: 2025年 before予測再生成
        {
            'name': 'regenerate_before_2025',
            'description': '2025年 before予測再生成',
            'script': 'regenerate_predictions_2025_before.py',
            'timeout': 3,
            'verify': ("2025年 before予測",
                      "SELECT COUNT(DISTINCT race_id) FROM race_predictions WHERE prediction_type = 'before' AND race_id IN (SELECT id FROM races WHERE race_date >= '2025-01-01')")
        }
    ]

    # タスク実行
    completed = []
    failed = []

    for i, task in enumerate(tasks, 1):
        log("")
        log(f"{'='*100}")
        log(f"タスク {i}/{len(tasks)}: {task['description']}")
        log(f"{'='*100}")

        try:
            if 'action' in task:
                # カスタムアクション（待機等）
                success = task['action']()
            else:
                # スクリプト実行
                success = run_script(
                    task['script'],
                    task['description'],
                    env_vars=task.get('env'),
                    timeout_hours=task.get('timeout', 12)
                )

            if success:
                completed.append(task['name'])

                # 完了確認
                if 'verify' in task:
                    check_completion(task['verify'][0], task['verify'][1])
            else:
                failed.append(task['name'])
                log(f"✗ タスク失敗: {task['description']}")

                # 失敗時の対応
                response = input("\n続行しますか？ (y/N): ")
                if response.lower() != 'y':
                    log("ユーザーによる中断")
                    break

        except KeyboardInterrupt:
            log("ユーザーによる中断")
            break
        except Exception as e:
            log(f"✗ タスク例外: {task['description']} - {e}")
            failed.append(task['name'])

    # 最終サマリー
    master_elapsed = time.time() - master_start

    log("")
    log("=" * 100)
    log("完全自動化マスタースクリプト 完了")
    log("=" * 100)
    log(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"総所要時間: {master_elapsed/3600:.2f}時間 ({master_elapsed/60:.1f}分)")
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
        raise
