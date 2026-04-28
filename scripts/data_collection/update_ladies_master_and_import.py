"""
女性レーサーマスター更新 → racers.gender 一括更新（UI 用ラッパー）

以下を順次実行する:
  1. fetch_ladies_master.py  — ladies-info.jp から最新女性選手リストを取得
  2. import_racers_csv.py    — ladies_master.csv を参照して racers.gender を更新

UI（data_maintenance.py）からバックグラウンドジョブとして呼び出される。
手動実行も可能:
  python scripts/data_collection/update_ladies_master_and_import.py
"""

import os
import sys
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, 'scripts', 'data_collection')


def run_step(script_name: str, extra_args: list = None):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [sys.executable, script_path] + (extra_args or [])
    print(f'\n{"="*50}')
    print(f'実行: {script_name}')
    print('='*50)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f'\n[エラー] {script_name} が失敗しました (returncode={result.returncode})')
        sys.exit(result.returncode)


def main():
    print('女性レーサーマスター更新 → racers.gender 一括更新')
    print(f'PROJECT_ROOT: {PROJECT_ROOT}')

    run_step('fetch_ladies_master.py')
    run_step('import_racers_csv.py')

    print('\n' + '='*50)
    print('全工程完了')
    print('='*50)


if __name__ == '__main__':
    main()
