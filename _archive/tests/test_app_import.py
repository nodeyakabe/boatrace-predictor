#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""app.py import test"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("app.py import test start")
print("=" * 60)

try:
    print("\n1. Basic modules...")
    import streamlit as st
    print("   [OK] streamlit")

    import pandas as pd
    print("   [OK] pandas")

    import shap
    print("   [OK] shap")

    print("\n2. Components...")
    from ui.components.bet_history import render_bet_history_page
    print("   [OK] bet_history")

    from ui.components.backtest import render_backtest_page
    print("   [OK] backtest")

    print("\n3. app.py syntax...")
    with open('ui/app.py', 'r', encoding='utf-8') as f:
        code = f.read()
    compile(code, 'ui/app.py', 'exec')
    print("   [OK] app.py syntax")

    print("\n" + "=" * 60)
    print("[SUCCESS] All import tests passed!")
    print("=" * 60)

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
