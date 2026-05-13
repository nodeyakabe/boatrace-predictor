#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
補完タスク実行: 2020-2023年の直前情報収集とbefore予測生成

マスタースクリプトでスキップされたタスクを直接実行します。
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

from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 100)
print("補完タスク実行開始")
print("=" * 100)
print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()
print("タスク1: 2020-2023年 直前情報収集")
print("タスク2: 2020-2023年 before予測生成")
print()
print("=" * 100)
print()

# タスク1: 直前情報収集
print("タスク1を開始します...")
print()

try:
    exec(open(PROJECT_ROOT / "scripts" / "collect_beforeinfo_2020_2023.py", encoding='utf-8').read())
    print()
    print("OK: タスク1完了")
except Exception as e:
    print(f"NG: タスク1失敗 - {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 100)
print()

# タスク2: before予測生成
print("タスク2を開始します...")
print()

try:
    exec(open(PROJECT_ROOT / "scripts" / "regenerate_predictions_2020_2023_before.py", encoding='utf-8').read())
    print()
    print("OK: タスク2完了")
except Exception as e:
    print(f"NG: タスク2失敗 - {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 100)
print("補完タスク実行完了")
print("=" * 100)
print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
