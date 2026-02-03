#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
簡易版: 月ごとに順次実行（subprocess.callを使用）
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] データ収集開始")
    print(f"対象: 2021年9-12月 + 2023年1-12月（16ヶ月）")
    print()

    script = PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_2021_2023_欠損データ.py'

    # 2021年9-12月
    for month in range(9, 13):
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 2021年{month}月 開始")
        print(f"{'='*60}")

        result = subprocess.call([
            sys.executable, str(script),
            '--year', '2021',
            '--month', str(month)
        ])

        if result != 0:
            print(f"\n[ERROR] 2021年{month}月でエラー発生（終了コード: {result}）")
            return 1

        print(f"\n[OK] 2021年{month}月 完了")

    # 2023年1-12月
    for month in range(1, 13):
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 2023年{month}月 開始")
        print(f"{'='*60}")

        result = subprocess.call([
            sys.executable, str(script),
            '--year', '2023',
            '--month', str(month)
        ])

        if result != 0:
            print(f"\n[ERROR] 2023年{month}月でエラー発生（終了コード: {result}）")
            return 1

        print(f"\n[OK] 2023年{month}月 完了")

    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 全データ収集完了")
    print(f"{'='*60}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
