# -*- coding: utf-8 -*-
"""クイックテスト"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent
print(f"ROOT_DIR: {ROOT_DIR}")

fetch_script = ROOT_DIR / "scripts" / "data_collection" / "fetch_exhibition_data_to_csv.py"
print(f"fetch_script exists: {fetch_script.exists()}")
print(f"fetch_script path: {fetch_script}")

import_script = ROOT_DIR / "scripts" / "maintenance" / "import_exhibition_data_from_csv.py"
print(f"import_script exists: {import_script.exists()}")
print(f"import_script path: {import_script}")

print(f"\nPython executable: {sys.executable}")
print(f"Python version: {sys.version}")
