#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""インポートテスト"""

import sys
import traceback

def test_import(module_name, from_name=None):
    try:
        if from_name:
            exec(f"from {module_name} import {from_name}")
            print(f"✅ {module_name}.{from_name}: OK")
        else:
            exec(f"import {module_name}")
            print(f"✅ {module_name}: OK")
        return True
    except Exception as e:
        print(f"❌ {module_name}: ERROR")
        print(f"   {e}")
        traceback.print_exc()
        return False

print("=== インポートテスト開始 ===\n")

# 基本モジュール
test_import("streamlit")
test_import("pandas")
test_import("numpy")

print("\n=== コンポーネントテスト ===\n")

# コンポーネントのインポートテスト
test_import("ui.components.bet_history", "render_bet_history_page")
test_import("ui.components.backtest", "render_backtest_page")

print("\n=== テスト完了 ===")
