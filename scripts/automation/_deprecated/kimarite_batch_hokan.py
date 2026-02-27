#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kimarite一括補完スクリプト（PC再起動後のリカバリ用）
=====================================================
2020年9-12月 → 2021年2-12月 → 2022年1-12月 → 2023年全期間 を順次補完。

usage:
  python scripts/automation/kimarite_batch_补完.py
"""

import sys
import os
import io
import subprocess
import time
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT_DIR / 'scripts' / 'data_collection' / '補完_決まり手データ_改善版.py'
LOG_DIR = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 補完対象期間（不足が大きい期間のみ）
TARGETS = [
    # 2020年: 9月-12月が主な不足（5,418件）
    {'label': '2020年9-12月', 'start': '2020-09-01', 'end': '2020-12-31'},
    # 2020年前半: 少数の不足（6件）→まとめて
    {'label': '2020年1-8月', 'start': '2020-01-01', 'end': '2020-08-31'},
    # 2021年: 11月-12月が主な不足（6,722件）+ 散在（74件）
    {'label': '2021年全期間', 'start': '2021-01-01', 'end': '2021-12-31'},
    # 2022年: 8月-12月が主な不足（16,244件）+ 散在（2件）
    {'label': '2022年全期間', 'start': '2022-01-01', 'end': '2022-12-31'},
    # 2023年: 1,662件の不足
    {'label': '2023年全期間', 'start': '2023-01-01', 'end': '2023-12-31'},
]


def main():
    py = sys.executable
    total = len(TARGETS)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    print(f"=== kimarite一括補完開始 ({total}段階) ===")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    for i, target in enumerate(TARGETS, 1):
        label = target['label']
        start = target['start']
        end = target['end']
        log_file = LOG_DIR / f"kimarite_batch_{label.replace('年', '_').replace('月', '')}_{ts}.log"

        print(f"--- [{i}/{total}] {label} ---")
        print(f"  期間: {start} ~ {end}")
        print(f"  ログ: {log_file.name}")

        t0 = time.time()
        cmd = [py, str(SCRIPT), '--start-date', start, '--end-date', end]

        try:
            with open(log_file, 'w', encoding='utf-8', errors='replace') as fh:
                proc = subprocess.run(
                    cmd,
                    cwd=str(ROOT_DIR),
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    timeout=6 * 3600,  # 6時間タイムアウト
                )
            elapsed = (time.time() - t0) / 60
            if proc.returncode == 0:
                print(f"  [OK] 完了 ({elapsed:.0f}分)")
            else:
                print(f"  [WARN] 終了コード {proc.returncode} ({elapsed:.0f}分)")
        except subprocess.TimeoutExpired:
            elapsed = (time.time() - t0) / 60
            print(f"  [ERR] タイムアウト ({elapsed:.0f}分)")
        except Exception as e:
            elapsed = (time.time() - t0) / 60
            print(f"  [ERR] 例外: {e} ({elapsed:.0f}分)")

        print()

    print(f"=== kimarite一括補完完了 ===")
    print(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nCtrl+Cで中断")
        sys.exit(130)
