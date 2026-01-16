#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年全レースのrace_conditions収集

fetch_historical_data.pyを使用して2024年のデータを自動収集
"""
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
script_path = PROJECT_ROOT / "scripts" / "fetch_historical_data.py"

# fetch_historical_data.pyを実行
subprocess.run([
    sys.executable, str(script_path),
    "--start", "2024-01-01",
    "--end", "2024-12-31",
    "--no-predict"  # 予測生成はスキップ
], check=True)
