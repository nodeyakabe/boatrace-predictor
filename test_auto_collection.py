# -*- coding: utf-8 -*-
"""自動収集スクリプトのテスト（2020年1-2月のみ）"""
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
import json

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# 一時的に2020年1-2月のみをテスト
test_script = ROOT_DIR / "scripts" / "data_collection" / "collect_exhibition_2020_2024.py"

# スクリプトを読み込んで2ヶ月に制限
with open(test_script, 'r', encoding='utf-8') as f:
    script_content = f.read()

# get_month_range関数を2020年1-2月に制限
script_content = script_content.replace(
    "months = get_month_range(2020, 1, 2024, 12)",
    "months = get_month_range(2020, 1, 2020, 2)  # TEST: 2ヶ月のみ"
)

# 一時スクリプト作成
test_script_path = ROOT_DIR / "test_collection_2months.py"
with open(test_script_path, 'w', encoding='utf-8') as f:
    f.write(script_content)

print("="*80)
print("自動収集スクリプト テスト実行（2020年1-2月）")
print("="*80)
print()
print("実行中...")
print()

# 実行
result = subprocess.run([sys.executable, str(test_script_path)],
                       capture_output=True, text=True, timeout=7200)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

print()
print("="*80)
print(f"終了コード: {result.returncode}")
print("="*80)

# 一時ファイル削除
test_script_path.unlink()

if result.returncode == 0:
    print()
    print("✓ テスト成功！本番実行の準備が整いました。")
    print()
    print("本番実行コマンド（バックグラウンド）:")
    print("  python scripts/data_collection/collect_exhibition_2020_2024.py > logs/collection_output.log 2>&1")
else:
    print()
    print("✗ テスト失敗。エラーを確認してください。")
